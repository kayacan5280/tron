"""Çeviri motoru: metinleri paketler, yapay zekaya gönderir, sonuçları doğrular ve kaydeder.

Akış:
  1. Sözlük (karakter adları, unvanlar, terimler) ve karakter kartları
     (ses tonu, sen/siz hitap tablosu) hazırlanır.
  2. Diyaloglar oyundaki sırayla, önceki ve sonraki satırlarla birlikte
     paketler halinde çevrilir.
  3. Arayüz/kod metinleri paketler halinde çevrilir.
  4. (Kalite geçişi) Çeviri kokan satırlar bir "Türk editör" isteğinden geçer.
Her satır koruma.dogrula ile kontrol edilir; oyunu bozabilecek çeviriler asla
kaydedilmez. Hatalı satırlar uyarı notuyla tekrar denenir, gerekirse korunan
parçalar maskelenerek (<t0>) çevrilir. Hiçbir şekilde çevrilemeyen satır
orijinal haliyle kalır ve raporlanır.

İnternet kesilirse çeviri durmaz: bağlantı gelene kadar (ayarlardaki süre
kadar) beklenir, sonra kaldığı yerden devam edilir.
"""

import collections
import json
import queue
import random
import threading
import time

from . import dogallik
from . import gemini
from . import istem
from . import karakterler as karakter_mod
from . import koruma
from . import proje as proje_mod
from . import saglayicilar
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


def _gercek_konusan(k):
    return bool(k) and k not in ("extend", "narrator")


# Bu hatalar satırları "çevrilemedi" saydırmaz: anahtar yöneticisi bekletir,
# anahtarı/modeli değiştirir; uzun süren kesinti ayrıca algılanır.
_GECICI_HATALAR = (
    gemini.AG, gemini.ZAMAN_ASIMI, gemini.SUNUCU, gemini.KOTA, gemini.KOTA_DAKIKA, gemini.KOTA_GUNLUK,
    gemini.GECERSIZ_ANAHTAR, gemini.MODEL_YOK, gemini.BOLGE, gemini.KREDI, gemini.SDK_YOK,
)

_KONUSMA_TURLERI = ("diyalog", "secenek", "menu_basligi")


def inceleme_adaylari(proje, ogeler, mod):
    """Editörden (kalite geçişi) geçecek satırlar: [(Oge, sorunlar)].

    dengeli: sadece çeviri kokusu dedektörünün ya da doğrulamanın işaretlediği satırlar
    en_iyi : yapay zekanın çevirdiği bütün konuşma satırları
    Elle düzeltilmiş, hazır tablodan/hafızadan gelen ve daha önce incelenmiş satırlar atlanır.
    """
    sonuc = []
    if mod not in ("dengeli", "en_iyi"):
        return sonuc
    for o in ogeler:
        if o.tur not in _KONUSMA_TURLERI:
            continue
        kayit = proje.kayit_al(o.m)
        if not kayit or kayit.get("d") != proje_mod.TAMAM or kayit.get("i"):
            continue
        c = kayit.get("c")
        if not isinstance(c, str) or not c.strip():
            continue
        puan, nedenler = dogallik.koku(o.m, c, o.tur, o.k)
        not_ = str(kayit.get("n") or "")
        if not_.startswith("şüpheli"):
            puan += 2
            nedenler.append(not_.replace("şüpheli: ", "")[:200] or "doğrulama şüpheli buldu")
        if mod == "en_iyi" or puan >= 2:
            sonuc.append((o, nedenler))
    return sonuc


class BaglantiKesildi(Exception):
    """İnternet uzun süre gelmedi ya da sunuculara ulaşılamıyor."""


class Cevirmen(object):

    def __init__(self, proje, yonetici, ayar, sozluk, oyun_adi="", oyun_notu="", ilerleme=None, bildir=None,
                 karakterler=None):
        self.proje = proje
        self.yonetici = yonetici
        self.ayar = ayar
        self.sozluk = sozluk
        self.karakterler = karakterler if karakterler is not None else karakter_mod.Karakterler()
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
        self._sabit = {}                  # önbelleğe alınabilir sistem talimatları
        self._sorunlar = {}               # editör geçişi: oge.id -> sorun listesi
        self.son_model = ""
        self.son_hata = ""
        self._ardisik_ag = 0
        self._ardisik_saf_ag = 0
        self._ardisik_sunucu = 0
        self._kesinti_baslangic = None
        self.kesinti_sayisi = 0
        self._model_reddi = collections.Counter()
        # Maliyet (ücretli servisler)
        self.maliyet = 0.0
        self.onceki_maliyet = 0.0
        self.butce = 0.0
        self._butce_doldu = False
        self.fiyati_bilinmeyen = set()
        # Kullanıcının elle düzelttiği çeviriler üslup örneği olarak gösterilir.
        try:
            self.kullanici_ornekleri = [(k, c) for k, c in proje.elle_duzeltilenler(30)
                                        if len(k) >= 8 and "\n" not in k][:12]
        except Exception:
            self.kullanici_ornekleri = []

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
                    self.ilerleme(self._yapilan, self._toplam, saglayicilar.model_adi(self.son_model or ""))
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
        """Karakter kartı olmayan oyunlar için sözlükten basit karakter satırları."""
        satirlar = []
        for ad, _n in konusan_sayaci.most_common(40):
            if not _gercek_konusan(ad):
                continue
            karsilik = self.sozluk.karsilik(ad)
            cins = self.sozluk.cinsiyet(ad)
            s = ad
            if karsilik and karsilik != ad:
                s += " → " + karsilik
            if cins:
                s += " (" + cins + ")"
            satirlar.append(s)
        with self._kilit:
            self._karakter_satirlari = satirlar
            self._sabit = {}

    def bilgileri_guncelle(self, sozluk=None, karakterler=None):
        with self._kilit:
            if sozluk is not None:
                self.sozluk = sozluk
            if karakterler is not None:
                self.karakterler = karakterler
            self._sabit = {}

    def _sabit_sistem(self, tur="cevirmen"):
        """Oyun boyunca değişmeyen sistem talimatı (sağlayıcı önbelleğine alınır)."""
        with self._kilit:
            s = self._sabit.get(tur)
            if s is not None:
                return s
            taban = istem.EDITOR_TALIMATI if tur == "editor" else istem.ANA_TALIMAT
            adlar = list(self.karakterler.kartlar)
            adlar += [a for (a, _b) in self.karakterler.hitap if a not in self.karakterler.kartlar]
            kartlar, hitap = self.karakterler.istem_satirlari(adlar, en_fazla_kart=30, en_fazla_hitap=60)
            if not kartlar:
                kartlar = self._karakter_satirlari
            sozluk_satirlari = self.sozluk.tum_satirlar(150) if len(self.sozluk) <= 150 else None
            s = taban + istem.oyun_bilgisi_metni(self.oyun_adi, self.oyun_notu, sozluk_satirlari, kartlar,
                                                 self.kullanici_ornekleri, hitap)
            self._sabit[tur] = s
            return s

    def _degisken_bilgi(self, ogeler, baglam):
        """Pakete özel kısa hatırlatmalar: konuşanlar, onların hitapları, (büyük sözlükte) ilgili terimler."""
        adlar = []
        for k in [o.k for o in ogeler] + [b.get("_k", "") for b in baglam]:
            if _gercek_konusan(k) and k not in adlar:
                adlar.append(k)
        _kart, hitap = self.karakterler.istem_satirlari(adlar, en_fazla_kart=0, en_fazla_hitap=12)
        sozluk_satirlari = None
        if len(self.sozluk) > 150:
            sozluk_satirlari = self.sozluk.ilgili_satirlar([o.m for o in ogeler] + [b.get("m", "") for b in baglam])
        return istem.paket_bilgisi_metni(sozluk_satirlari, [a for a in adlar if a in self.karakterler.kartlar], hitap)

    def _kullanici_istemi(self, ogeler, baglam, sonraki, editor=False):
        satirlar = []
        for o in ogeler:
            metin = o.m
            if o.maske and not editor:
                metin, o.harita = koruma.maskele(o.m)
            s = collections.OrderedDict([("id", o.id), ("t", o.tur), ("m", metin)])
            k = konusan_etiketi(o.k)
            if k:
                s["k"] = k
            if editor:
                s["taslak"] = self.proje.ceviri_al(o.m) or ""
                s["sorunlar"] = self._sorunlar.get(o.id) or []
            elif o.uyari:
                s["not"] = o.uyari
            satirlar.append(s)
        veri = collections.OrderedDict()
        if baglam:
            veri["baglam"] = [{a: v for a, v in b.items() if not a.startswith("_")} for b in baglam]
        veri["satirlar"] = satirlar
        if sonraki:
            veri["sonraki"] = sonraki
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
            b = {"m": o.m, "_k": o.k}
            k = konusan_etiketi(o.k)
            if k:
                b["k"] = k
            c = self.proje.ceviri_al(o.m)
            if c:
                b["c"] = c
            baglam.append(b)
        return baglam

    def _sonraki(self, ogeler):
        """Paketin son satırından sonra gelen birkaç satır (yarım kalan cümleler için)."""
        n = self.ayar.get("sonraki_baglam_satir", 3)
        if not n or not ogeler:
            return []
        konum = self._sira_konum.get(ogeler[-1].id)
        if konum is None:
            return []
        sonuc = []
        for o in self._sira_listesi[konum + 1:konum + 1 + n]:
            b = {"m": o.m}
            k = konusan_etiketi(o.k)
            if k:
                b["k"] = k
            sonuc.append(b)
        return sonuc

    def _ceviri_istegi(self, ogeler, baglamli=True, editor=False):
        baglam = self._baglam(ogeler) if baglamli else []
        sonraki = self._sonraki(ogeler) if baglamli else []
        kullanici = self._kullanici_istemi(ogeler, baglam, sonraki, editor)
        return saglayicilar.Istek(self._sabit_sistem("editor" if editor else "cevirmen"), kullanici, "ceviri",
                                  self._degisken_bilgi(ogeler, baglam))

    # ------------------------------------------------------------------
    # İnternet kesintisi
    # ------------------------------------------------------------------

    def _kesinti_var(self):
        with self._kilit:
            return self._kesinti_baslangic is not None

    def _ag_hatasi(self, h):
        dk = self.ayar.get("internet_bekleme_dk", 20)
        with self._kilit:
            self._ardisik_ag += 1
            if h.tur == gemini.AG:
                self._ardisik_saf_ag += 1
            # Birkaç istek üst üste bağlantı hatası verdiyse internet gitmiş demektir.
            # Sadece zaman aşımıysa (model yavaş da olabilir) daha fazla hata beklenir.
            kesinti = (self._ardisik_ag >= 3 and self._ardisik_saf_ag >= 1) or self._ardisik_ag >= 6
            if kesinti and self._kesinti_baslangic is None:
                self._kesinti_baslangic = time.monotonic()
                self.kesinti_sayisi += 1
                self._gunluk("İnternet kesintisi algılandı: %s" % h)
                self.bildir("uyari", "İnternet bağlantısı kesildi gibi görünüyor. Bağlantı bekleniyor "
                                     "(en fazla %g dk); çeviriler kayıtlı, hiçbir satır kaybolmaz." % dk)

    def _internet_bekle(self):
        """Kesinti sırasında yeni istek göndermeden önce bekler; süre dolarsa çeviriyi durdurur."""
        with self._kilit:
            bas = self._kesinti_baslangic
            n = self._ardisik_ag
        if bas is None:
            return
        dk = self.ayar.get("internet_bekleme_dk", 20)
        kalan = dk * 60.0 - (time.monotonic() - bas)
        if kalan <= 0:
            with self._kilit:
                if self.kritik_hata is None:
                    self.kritik_hata = BaglantiKesildi("İnternet bağlantısı %g dakikadır yok" % dk)
            self.iptal.set()
            raise IptalEdildi()
        bekle = min(30.0, 5.0 * (2 ** max(0, min(n - 3, 3)))) + random.uniform(0, 2)
        self.iptal.wait(min(bekle, kalan + 0.05))
        if self.iptal.is_set():
            raise IptalEdildi()

    def _istek_basarili(self):
        with self._kilit:
            if self._kesinti_baslangic is not None:
                sure = time.monotonic() - self._kesinti_baslangic
                self._gunluk("Bağlantı geri geldi (%.0f sn sonra)." % sure)
                self.bildir("bilgi", "Bağlantı geri geldi, çeviri kaldığı yerden devam ediyor.")
            self._kesinti_baslangic = None
            self._ardisik_ag = 0
            self._ardisik_saf_ag = 0
            self._ardisik_sunucu = 0

    # ------------------------------------------------------------------
    # API çağrısı (sağlayıcıdan bağımsız, özellik uyarlamalı)
    # ------------------------------------------------------------------

    def _maliyet_ekle(self, hedef, kullanim):
        tutar = saglayicilar.maliyet(hedef, kullanim, self.ayar.get("fiyatlar"))
        with self._kilit:
            if tutar is None:
                self.fiyati_bilinmeyen.add(hedef)
                return
            self.maliyet += tutar
            if not self.butce or self._butce_doldu or self.onceki_maliyet + self.maliyet < self.butce:
                return
            self._butce_doldu = True
        for h in list(self.yonetici.modeller):
            if saglayicilar.ucretli_mi(h):
                self.yonetici.hedef_kapat(h, "belirlenen bütçe (%.2f $) doldu" % self.butce)
        self._gunluk("Bütçe doldu: %.4f $" % (self.onceki_maliyet + self.maliyet))
        self.bildir("uyari", "Belirlediğiniz %.2f $ bütçeye ulaşıldı; ücretli servisler durduruldu." % self.butce)

    def _istek_yap(self, istek, haric=None):
        while True:
            if self.iptal.is_set():
                raise IptalEdildi()
            self._internet_bekle()
            i, anahtar, hedef = self.yonetici.al(iptal=self.iptal, haric=haric)
            self.son_model = hedef
            ozl = self.yonetici.ozellik(hedef)
            try:
                metin, kullanim = saglayicilar.uret(hedef, anahtar, istek, self.ayar, ozl)
            except gemini.ApiHatasi as h:
                h.model = hedef
                if h.tur == gemini.GECERSIZ_ISTEK:
                    ozellik = saglayicilar.kapatilacak_ozellik(hedef, h.mesaj)
                    if ozellik and self.yonetici.ozellik_kapat(hedef, ozellik):
                        self._gunluk("Model %s '%s' özelliğini desteklemiyor, kapatıldı: %s" % (hedef, ozellik, h.mesaj[:200]))
                        continue
                if h.tur == gemini.GECERSIZ_ISTEK:
                    # Hiç başarılı isteği olmayan bir model isteklerimizi sürekli reddediyorsa
                    # (ör. yeni/deneysel model) o modeli bırakıp diğerlerine geç; satırlar
                    # "çevrilemedi" sayılmasın.
                    with self._kilit:
                        self._model_reddi[hedef] += 1
                        reddedildi = self._model_reddi[hedef]
                    if reddedildi >= 3 and self.yonetici.model_basarisi(hedef) == 0:
                        self._gunluk("Model %s isteklerimizi sürekli reddediyor, devre dışı bırakıldı: %s" % (hedef, h.mesaj[:300]))
                        h = gemini.ApiHatasi(gemini.MODEL_YOK, "Model istekleri reddediyor: " + h.mesaj[:150], h.http)
                        h.model = hedef
                self.son_hata = "[%s] %s" % (saglayicilar.model_adi(hedef), h)
                self.yonetici.hata(i, hedef, h)
                self._gunluk("API hatası [%s, anahtar #%d]: %s | %s" % (hedef, i + 1, h, (h.ham or "")[:200]))
                self.istatistik["api_hata_" + h.tur] += 1
                if h.tur in (gemini.AG, gemini.ZAMAN_ASIMI):
                    self._ag_hatasi(h)
                elif h.tur == gemini.SUNUCU:
                    with self._kilit:
                        self._ardisik_sunucu += 1
                        if self._ardisik_sunucu >= 25 and self.kritik_hata is None:
                            self.kritik_hata = BaglantiKesildi("Yapay zeka sunucuları uzun süredir yanıt vermiyor (aşırı yoğunluk)")
                            self.iptal.set()
                raise
            self._istek_basarili()
            self.yonetici.basarili(i, hedef)
            with self._kilit:
                self.istatistik["istek"] += 1
                self.istatistik["hedef:" + hedef] += 1
                self.istatistik["token_girdi"] += kullanim["girdi"] + kullanim["onbellek_okuma"] + kullanim["onbellek_yazma"]
                self.istatistik["token_onbellek"] += kullanim["onbellek_okuma"]
                self.istatistik["token_cikti"] += kullanim["cikti"]
            if saglayicilar.ucretli_mi(hedef):
                self._maliyet_ekle(hedef, kullanim)
            return metin, hedef

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
        kesinti_no = self.kesinti_sayisi
        model = ""

        while bekleyen:
            if self.iptal.is_set():
                return

            istek = self._ceviri_istegi(bekleyen, baglamli)

            try:
                metin, model = self._istek_yap(istek, haric)
            except (TumKotalarBitti, IptalEdildi):
                raise
            except gemini.ApiHatasi as h:
                if h.tur == gemini.SSL:
                    self.kritik_hata = h
                    self.iptal.set()
                    raise IptalEdildi()

                if self.kesinti_sayisi != kesinti_no:
                    # Arada internet kesildiyse önceki zaman aşımları paketin suçu değildir.
                    kesinti_no = self.kesinti_sayisi
                    zaman_asimi = 0
                if h.tur == gemini.ZAMAN_ASIMI and not self._kesinti_var():
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
                    if model_adi and model_adi not in haric and len(self.yonetici.modeller) > len(haric) + 1:
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
    # Sözlük ve karakter kartları
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
            istek = saglayicilar.Istek(istem.SOZLUK_TALIMATI, kullanici, "sozluk")
            for _deneme in range(3):
                try:
                    metin, _model = self._istek_yap(istek)
                except (TumKotalarBitti, IptalEdildi):
                    raise
                except gemini.ApiHatasi as h:
                    self._gunluk("Sözlük isteği hatası: %s" % h)
                    if h.tur in (gemini.ENGELLENDI, gemini.GECERSIZ_ISTEK, gemini.KESILDI):
                        break
                    continue
                veri = istem.json_cozumle(metin)
                terimler = istem.liste_al(veri, "terimler")
                if not terimler:
                    continue
                for e in terimler:
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
        with self._kilit:
            self._sabit = {}
        return eklenen

    def karakter_analizi(self, ogeler):
        """Karakter kartlarını ve sen/siz hitap tablosunu yapay zekaya çıkarttırır.

        ogeler: oyundaki sırayla [{"m": metin, "k": konuşan}, ...]
        Döndürür: Karakterler (başarısız olursa boş).
        """
        temiz = [o for o in ogeler if isinstance(o.get("m"), str) and o.get("k") != "narrator"]
        veri = karakter_mod.analiz_verisi(temiz)
        sonuc = karakter_mod.Karakterler()
        if not veri["karakterler"]:
            return sonuc
        adlar = set(c["ad"] for c in veri["karakterler"])
        girdi = collections.OrderedDict([("oyun", self.oyun_adi), ("not", self.oyun_notu)])
        sozluk_satirlari = [s for s in self.sozluk.tum_satirlar(150) if s.split(" → ")[0] in adlar]
        if sozluk_satirlari:
            girdi["sozluk"] = sozluk_satirlari
        girdi["karakterler"] = veri["karakterler"]
        girdi["ciftler"] = veri["ciftler"]
        istek = saglayicilar.Istek(istem.KARAKTER_TALIMATI, json.dumps(girdi, ensure_ascii=False), "karakter")
        for _deneme in range(3):
            try:
                metin, _model = self._istek_yap(istek)
            except (TumKotalarBitti, IptalEdildi):
                raise
            except gemini.ApiHatasi as h:
                self._gunluk("Karakter analizi hatası: %s" % h)
                if h.tur in (gemini.ENGELLENDI, gemini.GECERSIZ_ISTEK, gemini.KESILDI):
                    break
                continue
            cevap = istem.json_cozumle(metin)
            if not isinstance(cevap, dict):
                continue
            for e in cevap.get("karakterler") if isinstance(cevap.get("karakterler"), list) else []:
                if isinstance(e, dict) and e.get("ad") in adlar:
                    sonuc.kart_ekle(e["ad"], e.get("cinsiyet"), e.get("yas"), e.get("uslup"))
            for e in cevap.get("hitap") if isinstance(cevap.get("hitap"), list) else []:
                if isinstance(e, dict) and e.get("konusan") in adlar and e.get("dinleyen") in adlar:
                    sonuc.hitap_ekle(e["konusan"], e["dinleyen"], e.get("hitap"))
            if len(sonuc):
                break
        return sonuc

    # ------------------------------------------------------------------
    # Kalite (editör) geçişi
    # ------------------------------------------------------------------

    def inceleme_adaylari(self, ogeler, mod):
        return inceleme_adaylari(self.proje, ogeler, mod)

    def _inceleme_paketi(self, ogeler, derinlik=0):
        bekleyen = list(ogeler)
        deneme = 0
        gecici = 0
        haric = set()
        while bekleyen and deneme < 3:
            if self.iptal.is_set():
                return
            deneme += 1
            istek = self._ceviri_istegi(bekleyen, True, editor=True)
            try:
                metin, hedef = self._istek_yap(istek, haric)
            except (TumKotalarBitti, IptalEdildi):
                raise
            except gemini.ApiHatasi as h:
                if h.tur == gemini.SSL:
                    self.kritik_hata = h
                    self.iptal.set()
                    raise IptalEdildi()
                if h.tur in (gemini.ENGELLENDI, gemini.KESILDI, gemini.GECERSIZ_ISTEK) and len(bekleyen) > 1:
                    yari = (len(bekleyen) + 1) // 2
                    self._inceleme_paketi(bekleyen[:yari], derinlik + 1)
                    self._inceleme_paketi(bekleyen[yari:], derinlik + 1)
                    return
                if h.tur in _GECICI_HATALAR and gecici < 50:
                    gecici += 1
                    deneme -= 1
                continue
            harita = istem.ceviri_haritasi(istem.json_cozumle(metin))
            if not harita:
                self._gunluk("Editör yanıtı çözümlenemedi (%s): %r" % (hedef, metin[:300]))
                continue
            yeni = []
            for o in bekleyen:
                ham = harita.get(o.id)
                if ham is None:
                    yeni.append(o)
                    continue
                taslak = self.proje.ceviri_al(o.m)
                c, ciddi, suphe = koruma.dogrula(o.m, ham)
                if ciddi or suphe or not c.strip():
                    self._gunluk("Editör önerisi reddedildi %r -> %r : %s" % (o.m[:80], ham[:80], "; ".join(ciddi + suphe)))
                    self.proje.incelendi_isaretle(o.m)
                    self.istatistik["editor_ret"] += 1
                elif c != taslak:
                    if self.proje.ceviri_kaydet(o.m, c, proje_mod.TAMAM, model=hedef + " +editör", incelendi=True):
                        self.istatistik["editor_duzeltti"] += 1
                else:
                    self.proje.incelendi_isaretle(o.m)
                    self.istatistik["editor_onay"] += 1
                self._ilerle()
            bekleyen = yeni
        if bekleyen:
            self._ilerle(len(bekleyen))

    def incele(self, adaylar, tum_diyalog_sirasi=None):
        """Seçilen satırları editör geçişinden geçirir. adaylar: inceleme_adaylari() çıktısı."""
        if tum_diyalog_sirasi is not None:
            self._sira_listesi = list(tum_diyalog_sirasi)
            self._sira_konum = {o.id: i for i, o in enumerate(self._sira_listesi)}
        self._sorunlar = {o.id: n for o, n in adaylar}
        ogeler = [o for o, _n in adaylar]
        self._toplam = len(ogeler)
        self._yapilan = 0
        if self.ilerleme:
            self.ilerleme(0, self._toplam, "")
        boyut = self.ayar.get("editor_paket_satir", 25)
        self._havuzda_calistir([(p,) for p in self.paketle(ogeler, boyut)], self._inceleme_paketi)

    # ------------------------------------------------------------------
    # Ana çalıştırma
    # ------------------------------------------------------------------

    def paketle(self, ogeler, boyut=None):
        boyut = boyut or self.ayar.get("paket_satir", 40)
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

    def _havuzda_calistir(self, isler_listesi, isle):
        """İşleri paralel işçilerle çalıştırır. isler_listesi: isle(*argümanlar) için argüman demetleri."""
        isler = queue.Queue()
        for a in isler_listesi:
            isler.put(a)

        isci_sayisi = max(1, min(self.ayar.get("paralel", 3), self.yonetici.kullanilabilir_anahtar_sayisi() * 2,
                                 isler.qsize() or 1))

        def isci():
            while not self.iptal.is_set():
                try:
                    argumanlar = isler.get_nowait()
                except queue.Empty:
                    return
                try:
                    isle(*argumanlar)
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
        isler = [(p, True) for p in self.paketle(diyaloglar)] + [(p, False) for p in self.paketle(arayuz_ogeleri)]
        self._havuzda_calistir(isler, self._paketi_isle)
