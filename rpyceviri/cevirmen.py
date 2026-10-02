"""Çeviri motoru: metinleri paketler, Gemini'ye gönderir, sonuçları doğrular ve kaydeder.

Akış:
  1. Sözlük (karakter adları, unvanlar, terimler) hazırlanır.
  2. Diyaloglar oyundaki sırayla, bağlamıyla birlikte paketler halinde çevrilir.
  3. Arayüz/kod metinleri paketler halinde çevrilir.
Her satır koruma.dogrula ile kontrol edilir; oyunu bozabilecek çeviriler asla
kaydedilmez. Hatalı satırlar uyarı notuyla tekrar denenir, gerekirse korunan
parçalar maskelenerek (<t0>) çevrilir. Hiçbir şekilde çevrilemeyen satır
orijinal haliyle kalır ve raporlanır.
"""

import collections
import json
import queue
import threading
import time

from . import gemini
from . import istem
from . import koruma
from . import proje as proje_mod
from .anahtarlar import IptalEdildi, TumKotalarBitti
from .sozluk import terim_adaylari


class Oge(object):
    """Çevrilecek tek bir benzersiz metin."""

    __slots__ = ("id", "m", "tur", "k", "sira", "ciddi", "suphe_denendi", "yedek", "uyari",
                 "maske", "harita", "eksik")

    def __init__(self, kimlik, metin, tur, konusan="", sira=0):
        self.id = str(kimlik)
        self.m = metin
        self.tur = tur
        self.k = konusan or ""
        self.sira = sira
        self.ciddi = 0
        self.suphe_denendi = False
        self.yedek = None
        self.uyari = None
        self.maske = False
        self.harita = None
        self.eksik = 0


def konusan_etiketi(k):
    if not k:
        return ""
    if k == "extend":
        return "(önceki konuşmacı devam ediyor)"
    if k == "narrator":
        return ""
    if k.startswith("[") and k.endswith("]"):
        return k + " (oyuncunun belirlediği ad)"
    return k


_GECICI_HATALAR = (
    gemini.AG, gemini.ZAMAN_ASIMI, gemini.SUNUCU, gemini.KOTA, gemini.KOTA_DAKIKA, gemini.KOTA_GUNLUK,
    gemini.GECERSIZ_ANAHTAR, gemini.MODEL_YOK, gemini.BOLGE,
)


class BaglantiKesildi(Exception):
    """Art arda çok sayıda ağ/sunucu hatası: internet yok ya da Google erişilemiyor."""


class Cevirmen(object):

    def __init__(self, proje, yonetici, ayar, sozluk, oyun_adi="", oyun_notu="", ilerleme=None, bildir=None):
        self.proje = proje
        self.yonetici = yonetici
        self.ayar = ayar
        self.sozluk = sozluk
        self.oyun_adi = oyun_adi or ""
        self.oyun_notu = oyun_notu or ""
        self.ilerleme = ilerleme          # fonk(yapilan, toplam, ek_metin)
        self.bildir = bildir or (lambda tur, mesaj: None)   # tur: bilgi/uyari/hata
        self.iptal = threading.Event()
        self.durdurma_nedeni = None
        self.kritik_hata = None
        self.istatistik = collections.Counter()
        self._kilit = threading.RLock()
        self._yapilan = 0
        self._toplam = 0
        self._sira_listesi = []           # bağlam için tüm diyaloglar (sıralı)
        self._sira_konum = {}             # oge.id -> sira listesindeki konum
        self._karakter_satirlari = []
        self.son_model = ""
        self._ardisik_ag = 0
        self._ardisik_sunucu = 0
        self._model_reddi = collections.Counter()
        self.son_hata = ""

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------

    def _gunluk(self, mesaj):
        self.proje.gunluge_yaz(mesaj)

    def _ilerle(self, adet=1):
        with self._kilit:
            self._yapilan += adet
            if self.ilerleme:
                try:
                    self.ilerleme(self._yapilan, self._toplam, self.son_model)
                except Exception:
                    pass

    def _kaydet(self, oge, ceviri, model, not_=None):
        self.proje.ceviri_kaydet(oge.m, ceviri, proje_mod.TAMAM, model=model, not_=not_)
        self.istatistik["cevrildi"] += 1
        self._ilerle()

    def _basarisiz(self, oge, neden):
        self.proje.basarisiz_kaydet(oge.m, neden)
        self.istatistik["basarisiz"] += 1
        self._gunluk("BAŞARISIZ [%s] %r -> %s" % (oge.tur, oge.m[:120], neden))
        self._ilerle()

    def karakter_satirlarini_hazirla(self, konusan_sayaci):
        satirlar = []
        for ad, _n in konusan_sayaci.most_common(40):
            if not ad or ad == "extend":
                continue
            karsilik = self.sozluk.karsilik(ad)
            cins = self.sozluk.cinsiyet(ad)
            s = ad
            if karsilik and karsilik != ad:
                s += " → " + karsilik
            if cins:
                s += " (" + cins + ")"
            satirlar.append(s)
        self._karakter_satirlari = satirlar

    def _sistem_istemi(self, ogeler, baglam):
        metinler = [o.m for o in ogeler] + [b.get("m", "") for b in baglam]
        sozluk_satirlari = self.sozluk.ilgili_satirlar(metinler)
        return istem.ANA_TALIMAT + istem.oyun_bilgisi_metni(
            self.oyun_adi, self.oyun_notu, sozluk_satirlari, self._karakter_satirlari
        )

    def _kullanici_istemi(self, ogeler, baglam):
        satirlar = []
        for o in ogeler:
            metin = o.m
            if o.maske:
                metin, o.harita = koruma.maskele(o.m)
            s = {"id": o.id, "t": o.tur, "m": metin}
            k = konusan_etiketi(o.k)
            if k:
                s["k"] = k
            if o.uyari:
                s["not"] = o.uyari
            satirlar.append(s)
        veri = {"satirlar": satirlar}
        if baglam:
            veri = {"baglam": baglam, "satirlar": satirlar}
        return json.dumps(veri, ensure_ascii=False)

    def _baglam(self, ogeler):
        """Paketin ilk satırından önceki diyalogları (varsa çevirileriyle) döndürür."""
        n = self.ayar.get("baglam_satir", 10)
        if not n or not ogeler:
            return []
        konum = self._sira_konum.get(ogeler[0].id)
        if konum is None:
            return []
        baslangic = max(0, konum - n)
        baglam = []
        for o in self._sira_listesi[baslangic:konum]:
            b = {"m": o.m}
            k = konusan_etiketi(o.k)
            if k:
                b["k"] = k
            c = self.proje.ceviri_al(o.m)
            if c:
                b["c"] = c
            baglam.append(b)
        return baglam

    # ------------------------------------------------------------------
    # API çağrısı (özellik uyarlamalı)
    # ------------------------------------------------------------------

    def _istek_yap(self, sistem, kullanici, sema, haric=None):
        while True:
            if self.iptal.is_set():
                raise IptalEdildi()
            i, anahtar, model = self.yonetici.al(iptal=self.iptal, haric=haric)
            self.son_model = model
            ozl = self.yonetici.ozellik(model)
            govde = istem.istek_govdesi(sistem, kullanici, self.ayar, ozl, model, sema)
            try:
                metin, kullanim = gemini.icerik_uret(anahtar, model, govde, self.ayar.get("zaman_asimi_sn", 240))
            except gemini.ApiHatasi as h:
                h.model = model
                if h.tur == gemini.GECERSIZ_ISTEK:
                    ozellik = istem.kapatilacak_ozellik(h.mesaj)
                    if ozellik and self.yonetici.ozellik_kapat(model, ozellik):
                        self._gunluk("Model %s '%s' özelliğini desteklemiyor, kapatıldı: %s" % (model, ozellik, h.mesaj[:200]))
                        continue
                if h.tur == gemini.GECERSIZ_ISTEK:
                    # Hiç başarılı isteği olmayan bir model isteklerimizi sürekli reddediyorsa
                    # (ör. yeni/deneysel model) o modeli bırakıp diğerlerine geç; satırlar
                    # "çevrilemedi" sayılmasın.
                    with self._kilit:
                        self._model_reddi[model] += 1
                        reddedildi = self._model_reddi[model]
                    if reddedildi >= 3 and self.yonetici.model_basarisi(model) == 0:
                        self._gunluk("Model %s isteklerimizi sürekli reddediyor, devre dışı bırakıldı: %s" % (model, h.mesaj[:300]))
                        h = gemini.ApiHatasi(gemini.MODEL_YOK, "Model istekleri reddediyor: " + h.mesaj[:150], h.http)
                        h.model = model
                self.son_hata = "[%s] %s" % (model, h)
                self.yonetici.hata(i, model, h)
                self._gunluk("API hatası [%s, anahtar #%d]: %s | %s" % (model, i + 1, h, (h.ham or "")[:200]))
                self.istatistik["api_hata_" + h.tur] += 1
                with self._kilit:
                    if h.tur in (gemini.AG, gemini.ZAMAN_ASIMI):
                        self._ardisik_ag += 1
                    elif h.tur == gemini.SUNUCU:
                        self._ardisik_sunucu += 1
                    if self._ardisik_ag >= 12 or self._ardisik_sunucu >= 25:
                        self.kritik_hata = BaglantiKesildi(
                            "İnternet bağlantısı yok ya da Google sunucularına ulaşılamıyor" if self._ardisik_ag >= 12
                            else "Google sunucuları uzun süredir yanıt vermiyor (aşırı yoğunluk)")
                        self.iptal.set()
                raise
            with self._kilit:
                self._ardisik_ag = 0
                self._ardisik_sunucu = 0
            self.yonetici.basarili(i, model)
            self.istatistik["istek"] += 1
            try:
                self.istatistik["token_girdi"] += int(kullanim.get("promptTokenCount", 0) or 0)
                self.istatistik["token_cikti"] += int(kullanim.get("candidatesTokenCount", 0) or 0)
            except Exception:
                pass
            return metin, model

    # ------------------------------------------------------------------
    # Paket işleme
    # ------------------------------------------------------------------

    def _paketi_isle(self, ogeler, baglamli=True, derinlik=0):
        bekleyen = list(ogeler)
        deneme_siniri = self.ayar.get("deneme_sayisi", 6)
        hata_sayisi = 0
        tur = 0
        haric = set()
        sunucu_hatasi = collections.Counter()
        zaman_asimi = 0
        bos_yanit = 0
        model = ""

        while bekleyen:
            if self.iptal.is_set():
                return

            baglam = self._baglam(bekleyen) if baglamli else []
            sistem = self._sistem_istemi(bekleyen, baglam)
            kullanici = self._kullanici_istemi(bekleyen, baglam)

            try:
                metin, model = self._istek_yap(sistem, kullanici, istem.CIKTI_SEMASI, haric)
            except (TumKotalarBitti, IptalEdildi):
                raise
            except gemini.ApiHatasi as h:
                if h.tur == gemini.SSL:
                    self.kritik_hata = h
                    self.iptal.set()
                    raise IptalEdildi()

                if h.tur == gemini.ZAMAN_ASIMI:
                    zaman_asimi += 1
                if h.tur == gemini.BOS_YANIT:
                    bos_yanit += 1

                bolunmeli = h.tur in (gemini.ENGELLENDI, gemini.KESILDI, gemini.GECERSIZ_ISTEK) or \
                    (h.tur == gemini.ZAMAN_ASIMI and zaman_asimi >= 2) or \
                    (h.tur == gemini.BOS_YANIT and bos_yanit >= 2)
                if bolunmeli and len(bekleyen) > 1:
                    yari = (len(bekleyen) + 1) // 2
                    self._paketi_isle(bekleyen[:yari], baglamli, derinlik + 1)
                    self._paketi_isle(bekleyen[yari:], baglamli, derinlik + 1)
                    return
                if h.tur == gemini.ENGELLENDI and len(bekleyen) == 1:
                    # Tek satır engellendi: bir kez de başka bir modelle dene.
                    model_adi = getattr(h, "model", None)
                    if model_adi and model_adi not in haric and len(self.yonetici.modeller) > 1:
                        haric.add(model_adi)
                        bekleyen[0].uyari = None
                        continue
                    self._basarisiz(bekleyen[0], "yapay zekanın güvenlik filtresine takıldı")
                    return
                if h.tur == gemini.ZAMAN_ASIMI and len(bekleyen) == 1 and zaman_asimi >= 3:
                    self._basarisiz(bekleyen[0], "yanıt sürekli zaman aşımına uğradı")
                    return

                if h.tur == gemini.SUNUCU and getattr(h, "model", None):
                    sunucu_hatasi[h.model] += 1
                    if sunucu_hatasi[h.model] >= 2:
                        haric.add(h.model)

                # Geçici sorunlar (ağ, yoğunluk, kota, anahtar/model değişimi) satırları
                # "çevrilemedi" saydırmaz: anahtar yöneticisi bekletir/değiştirir, uzun
                # süren kesinti ise genel olarak algılanıp çeviri durdurulur.
                if h.tur in _GECICI_HATALAR:
                    continue

                hata_sayisi += 1
                if h.tur == gemini.GECERSIZ_ISTEK and hata_sayisi >= 2:
                    hata_sayisi = deneme_siniri
                if hata_sayisi >= deneme_siniri:
                    for o in bekleyen:
                        if o.yedek:
                            self._kaydet(o, o.yedek, model or "?", "şüpheli")
                        else:
                            self._basarisiz(o, str(h))
                    return
                continue

            veri = istem.json_cozumle(metin)
            harita = istem.ceviri_haritasi(veri) if veri is not None else {}
            if not harita:
                hata_sayisi += 1
                self._gunluk("Yanıt çözümlenemedi (%s): %r" % (model, metin[:300]))
                if hata_sayisi >= 2 and len(bekleyen) > 1:
                    yari = (len(bekleyen) + 1) // 2
                    self._paketi_isle(bekleyen[:yari], baglamli, derinlik + 1)
                    self._paketi_isle(bekleyen[yari:], baglamli, derinlik + 1)
                    return
                if hata_sayisi >= deneme_siniri:
                    for o in bekleyen:
                        self._basarisiz(o, "yanıt çözümlenemedi")
                    return
                continue

            yeni = []
            for o in bekleyen:
                ham = harita.get(o.id)
                if ham is None:
                    o.eksik += 1
                    o.uyari = "Önceki yanıtta bu satır eksikti; mutlaka çevir ve aynı id ile döndür."
                    yeni.append(o)
                    continue

                if o.maske:
                    acik = koruma.maske_kaldir(ham, o.harita or [])
                    if acik is None:
                        o.ciddi += 1
                        o.uyari = "Önceki çeviride <tN> belirteçleri eksik/fazlaydı. Her belirteci tam bir kez kullan."
                        if o.ciddi >= 4:
                            self._basarisiz(o, "korunan parçalar korunamadı")
                        else:
                            yeni.append(o)
                        continue
                    ham = acik

                c, ciddi, suphe = koruma.dogrula(o.m, ham)
                if ciddi:
                    o.ciddi += 1
                    o.uyari = ("Önceki çeviri hatalıydı: " + "; ".join(ciddi) +
                               ". [değişken] ve {etiket} parçalarını kaynaktaki gibi AYNEN kullan.")
                    self._gunluk("Hatalı çeviri (deneme %d) %r -> %r : %s" % (o.ciddi, o.m[:100], ham[:100], "; ".join(ciddi)))
                    if o.ciddi >= 2:
                        o.maske = True
                    if o.ciddi >= 4:
                        self._basarisiz(o, "; ".join(ciddi))
                    else:
                        yeni.append(o)
                    continue

                if suphe and not o.suphe_denendi:
                    o.suphe_denendi = True
                    o.yedek = c
                    o.uyari = "Önceki çevirinin sorunu: " + "; ".join(suphe) + ". Doğal Türkçeye çevir."
                    yeni.append(o)
                    continue

                if suphe:
                    self.istatistik["supheli_kabul"] += 1
                    self._kaydet(o, c, model, "şüpheli: " + "; ".join(suphe))
                else:
                    self._kaydet(o, c, model)

            bekleyen = yeni
            tur += 1

            if bekleyen and tur >= deneme_siniri:
                for o in bekleyen:
                    if o.yedek:
                        self._kaydet(o, o.yedek, model, "şüpheli")
                    else:
                        self._basarisiz(o, o.uyari or "çevrilemedi")
                return

            # İki turdan sonra hâlâ birkaç inatçı satır kaldıysa onları tek tek gönder
            # (yapay zeka tek satıra daha iyi odaklanır).
            if bekleyen and 1 < len(bekleyen) <= 5 and tur >= 2:
                for o in bekleyen:
                    self._paketi_isle([o], baglamli, derinlik + 1)
                return

    # ------------------------------------------------------------------
    # Sözlük
    # ------------------------------------------------------------------

    def sozluk_olustur(self, isimler, diyaloglar, ornek_bul):
        """Karakter adları ve terimler için tek seferlik sözlük isteği yapar."""
        adaylar = []
        gorulen = set()
        for ad in isimler:
            if ad in gorulen or not koruma.cevrilecek_mi(ad) or len(ad) > 60:
                continue
            gorulen.add(ad)
            adaylar.append({"m": ad, "ornek": ornek_bul(ad) or ""})
        for terim, ornek in terim_adaylari(diyaloglar):
            if terim in gorulen:
                continue
            gorulen.add(terim)
            adaylar.append({"m": terim, "ornek": ornek})
        adaylar = adaylar[:150]
        if not adaylar:
            return 0

        eklenen = 0
        for bas in range(0, len(adaylar), 60):
            parca = adaylar[bas:bas + 60]
            kullanici = json.dumps({"oyun": self.oyun_adi, "not": self.oyun_notu, "terimler": parca}, ensure_ascii=False)
            for deneme in range(3):
                try:
                    metin, _model = self._istek_yap(istem.SOZLUK_TALIMATI, kullanici, istem.SOZLUK_SEMASI)
                except (TumKotalarBitti, IptalEdildi):
                    raise
                except gemini.ApiHatasi as h:
                    self._gunluk("Sözlük isteği hatası: %s" % h)
                    if h.tur in (gemini.ENGELLENDI, gemini.GECERSIZ_ISTEK, gemini.KESILDI):
                        break
                    continue
                veri = istem.json_cozumle(metin)
                if not isinstance(veri, list):
                    continue
                for e in veri:
                    if not isinstance(e, dict):
                        continue
                    m = e.get("m")
                    c = e.get("c")
                    if not isinstance(m, str) or not isinstance(c, str) or m not in gorulen:
                        continue
                    c2, ciddi, _s = koruma.dogrula(m, c)
                    if ciddi:
                        continue
                    cins = e.get("cinsiyet")
                    self.sozluk.ekle(m, c2, cins if cins in ("kadın", "erkek") else None)
                    eklenen += 1
                break
        return eklenen

    # ------------------------------------------------------------------
    # Ana çalıştırma
    # ------------------------------------------------------------------

    def paketle(self, ogeler):
        boyut = self.ayar.get("paket_satir", 40)
        karakter = self.ayar.get("paket_karakter", 7000)
        paketler = []
        mevcut = []
        uzunluk = 0
        for o in ogeler:
            l = len(o.m) + len(o.k) + 30
            if mevcut and (len(mevcut) >= boyut or uzunluk + l > karakter):
                paketler.append(mevcut)
                mevcut = []
                uzunluk = 0
            mevcut.append(o)
            uzunluk += l
        if mevcut:
            paketler.append(mevcut)
        return paketler

    def calistir(self, diyaloglar, arayuz_ogeleri, tum_diyalog_sirasi):
        """diyaloglar/arayuz_ogeleri: çevrilecek Oge listeleri (önbellekte olmayanlar).
        tum_diyalog_sirasi: bağlam için bütün diyalog Oge'leri (çevrilmiş olanlar dahil).
        """
        self._sira_listesi = list(tum_diyalog_sirasi)
        self._sira_konum = {o.id: i for i, o in enumerate(self._sira_listesi)}
        self._toplam = len(diyaloglar) + len(arayuz_ogeleri)
        self._yapilan = 0
        if self.ilerleme:
            self.ilerleme(0, self._toplam, "")

        isler = queue.Queue()
        for p in self.paketle(diyaloglar):
            isler.put((p, True))
        for p in self.paketle(arayuz_ogeleri):
            isler.put((p, False))

        isci_sayisi = max(1, min(self.ayar.get("paralel", 3), self.yonetici.kullanilabilir_anahtar_sayisi() * 2, isler.qsize() or 1))

        def isci():
            while not self.iptal.is_set():
                try:
                    paket, baglamli = isler.get_nowait()
                except queue.Empty:
                    return
                try:
                    self._paketi_isle(paket, baglamli)
                except TumKotalarBitti as e:
                    with self._kilit:
                        if self.durdurma_nedeni is None:
                            self.durdurma_nedeni = e
                    self.iptal.set()
                except IptalEdildi:
                    return
                except Exception as e:  # beklenmeyen hata: kaydet ve devam et
                    import traceback
                    self._gunluk("Beklenmeyen hata: " + traceback.format_exc())
                    with self._kilit:
                        if self.kritik_hata is None:
                            self.kritik_hata = e
                finally:
                    try:
                        self.proje.kaydet()
                    except Exception as e:
                        self._gunluk("Kayıt hatası: %s" % e)

        iscilar = [threading.Thread(target=isci, daemon=True) for _ in range(isci_sayisi)]
        for t in iscilar:
            t.start()
        try:
            while any(t.is_alive() for t in iscilar):
                for t in iscilar:
                    t.join(timeout=0.5)
        except KeyboardInterrupt:
            self.iptal.set()
            self.bildir("uyari", "Durduruluyor... (çeviriler kaydediliyor)")
            bitis = time.time() + 5
            for t in iscilar:
                t.join(timeout=max(0.1, bitis - time.time()))
            self.proje.kaydet()
            raise
        self.proje.kaydet()
