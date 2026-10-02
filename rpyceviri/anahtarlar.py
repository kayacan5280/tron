"""Birden fazla Gemini API anahtarının yönetimi.

- Anahtarlar sırayla/dengeli kullanılır (her biri ayrı Google hesabı/projesi ise
  kotaları ayrıdır).
- Dakikalık sınıra takılan anahtar kısa süre dinlendirilir.
- Günlük kotası biten anahtar+model ikilisi, kotanın sıfırlanacağı ana kadar
  (ABD Pasifik saatiyle gece yarısı) kullanılmaz; bu bilgi diske yazılır, program
  yeniden açılsa da hatırlanır.
- Geçersiz anahtar devre dışı bırakılır.
- En kaliteli modelin bütün anahtarlarda kotası bitince sıradaki modele geçilir.
"""

import hashlib
import json
import os
import random
import threading
import time

from . import gemini
from . import zaman


class TumKotalarBitti(Exception):

    def __init__(self, en_erken=None, nedenler=None):
        Exception.__init__(self, "Kullanılabilir API anahtarı kalmadı")
        self.en_erken = en_erken
        self.nedenler = nedenler or []


class IptalEdildi(Exception):
    pass


def anahtar_kimligi(anahtar):
    return hashlib.sha256(anahtar.encode("utf-8")).hexdigest()[:16]


def anahtar_etiketi(anahtar):
    a = anahtar.strip()
    if len(a) <= 8:
        return "****"
    return a[:4] + "…" + a[-4:]


def anahtarlari_oku(dosya):
    """api_anahtarlari.txt dosyasından anahtarları okur (yorum satırları ve tekrarlar atlanır)."""
    anahtarlar = []
    if not os.path.exists(dosya):
        return anahtarlar
    with open(dosya, "r", encoding="utf-8-sig") as f:
        for satir in f:
            s = satir.strip()
            if not s or s.startswith("#"):
                continue
            # "anahtar  # açıklama" biçimine izin ver
            s = s.split("#", 1)[0].strip().strip('"').strip("'").strip()
            if s and s not in anahtarlar:
                anahtarlar.append(s)
    return anahtarlar


def anahtarlari_yaz(dosya, anahtarlar):
    gecici = dosya + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        f.write("# Gemini API anahtarları - her satıra bir anahtar.\n")
        f.write("# Anahtar almak için: https://aistudio.google.com/apikey\n")
        f.write("# Her anahtarı FARKLI bir Google hesabından alın; aynı hesabın anahtarları kotayı paylaşır.\n")
        f.write("# Bu dosyayı kimseyle paylaşmayın.\n")
        for a in anahtarlar:
            f.write(a + "\n")
    os.replace(gecici, dosya)


def anahtar_bicimi_uygun_mu(anahtar):
    a = anahtar.strip()
    if len(a) < 20 or len(a) > 200:
        return False
    if any(c.isspace() for c in a):
        return False
    return True


class _Ikili(object):
    """Bir anahtar + model ikilisinin anlık durumu."""

    __slots__ = ("son_istek", "bekle_kadar", "gunluk_bitis", "gunluk_kalici", "ardisik_kota", "basarili")

    def __init__(self):
        self.son_istek = 0.0
        self.bekle_kadar = 0.0
        self.gunluk_bitis = None
        self.gunluk_kalici = False
        self.ardisik_kota = 0
        self.basarili = 0


class AnahtarYoneticisi(object):

    def __init__(self, anahtarlar, modeller, aralik_fonk, durum_dosyasi=None, saat=None, utc_saat=None):
        self.anahtarlar = list(anahtarlar)
        self.kimlikler = [anahtar_kimligi(a) for a in self.anahtarlar]
        self.modeller = list(modeller)
        self.aralik_fonk = aralik_fonk          # model -> iki istek arası en az saniye
        self.durum_dosyasi = durum_dosyasi
        self._saat = saat or time.monotonic
        self._utc = utc_saat or zaman.simdi_utc
        self.kosul = threading.Condition(threading.RLock())
        self.gecersiz = {}                       # anahtar indeksi -> neden
        self.model_kapali = {}                   # model -> neden
        self.ozellikler = {}                     # model -> {ozellik: bool}
        self.ikililer = {}                       # (indeks, model) -> _Ikili
        self.son_model = None
        self.toplam_istek = 0
        self._durumu_yukle()

    # ------------------------------------------------------------------
    # Kalıcı durum
    # ------------------------------------------------------------------

    def _ikili(self, i, model):
        anahtar = (i, model)
        d = self.ikililer.get(anahtar)
        if d is None:
            d = _Ikili()
            self.ikililer[anahtar] = d
        return d

    def _durumu_yukle(self):
        if not self.durum_dosyasi or not os.path.exists(self.durum_dosyasi):
            return
        try:
            with open(self.durum_dosyasi, "r", encoding="utf-8") as f:
                veri = json.load(f)
        except Exception:
            return
        simdi = self._utc()
        kayitlar = veri.get("anahtarlar", {}) if isinstance(veri, dict) else {}
        for i, kimlik in enumerate(self.kimlikler):
            k = kayitlar.get(kimlik)
            if not isinstance(k, dict):
                continue
            if k.get("gecersiz"):
                self.gecersiz[i] = str(k["gecersiz"])
            for model, md in (k.get("modeller") or {}).items():
                if not isinstance(md, dict):
                    continue
                bitis = zaman.iso_coz(md.get("gunluk_bitis", ""))
                if bitis and bitis > simdi:
                    d = self._ikili(i, model)
                    d.gunluk_bitis = bitis
                    d.gunluk_kalici = True

    def _durumu_kaydet(self):
        if not self.durum_dosyasi:
            return
        simdi = self._utc()
        kayitlar = {}
        # Bu oturumda olmayan anahtarların kayıtlarını koru.
        try:
            with open(self.durum_dosyasi, "r", encoding="utf-8") as f:
                eski = json.load(f).get("anahtarlar", {})
                if isinstance(eski, dict):
                    kayitlar.update(eski)
        except Exception:
            pass
        for i, kimlik in enumerate(self.kimlikler):
            k = {"gecersiz": self.gecersiz.get(i), "modeller": {}}
            for (j, model), d in self.ikililer.items():
                if j == i and d.gunluk_kalici and d.gunluk_bitis and d.gunluk_bitis > simdi:
                    k["modeller"][model] = {"gunluk_bitis": zaman.iso(d.gunluk_bitis)}
            kayitlar[kimlik] = k
        try:
            gecici = self.durum_dosyasi + ".tmp"
            with open(gecici, "w", encoding="utf-8") as f:
                json.dump({"anahtarlar": kayitlar}, f, ensure_ascii=False, indent=1)
            os.replace(gecici, self.durum_dosyasi)
        except Exception:
            pass

    def durumu_sifirla(self):
        """Kayıtlı 'günlük kota bitti' ve 'geçersiz' işaretlerini temizler."""
        with self.kosul:
            self.gecersiz.clear()
            self.ikililer.clear()
            self.model_kapali.clear()
            self._durumu_kaydet()
            self.kosul.notify_all()

    # ------------------------------------------------------------------
    # Özellik (yetenek) takibi
    # ------------------------------------------------------------------

    def ozellik(self, model):
        with self.kosul:
            return dict(self.ozellikler.setdefault(model, {}))

    def ozellik_kapat(self, model, ad):
        with self.kosul:
            ozl = self.ozellikler.setdefault(model, {})
            if ozl.get(ad, True):
                ozl[ad] = False
                return True
            return False

    # ------------------------------------------------------------------
    # Anahtar alma / bildirim
    # ------------------------------------------------------------------

    def kullanilabilir_anahtar_sayisi(self):
        with self.kosul:
            return len([i for i in range(len(self.anahtarlar)) if i not in self.gecersiz])

    def _uygun_mu(self, i, model, simdi_utc):
        if i in self.gecersiz:
            return False
        d = self.ikililer.get((i, model))
        if d is not None and d.gunluk_bitis is not None and d.gunluk_bitis > simdi_utc:
            return False
        return True

    def al(self, iptal=None, en_fazla_bekleme=None, haric=None):
        """Kullanılacak (anahtar_indeksi, anahtar, model) üçlüsünü döndürür.

        Uygun anahtar o an hazır değilse (dakikalık sınır) bekler. Hiçbir anahtar
        hiçbir modelde kullanılamıyorsa TumKotalarBitti fırlatır.

        haric: mümkünse kaçınılacak modeller (ör. sürekli "aşırı yoğun" hatası
        veren model). Başka model kalmamışsa yine de kullanılır.
        """
        baslangic = self._saat()
        haric = set(haric or ())
        with self.kosul:
            while True:
                if iptal is not None and iptal.is_set():
                    raise IptalEdildi()

                simdi = self._saat()
                simdi_utc = self._utc()
                bekleme = None

                modeller = [m for m in self.modeller if m not in self.model_kapali]
                if haric:
                    tercih = [m for m in modeller if m not in haric and
                              any(self._uygun_mu(i, m, simdi_utc) for i in range(len(self.anahtarlar)))]
                    if tercih:
                        modeller = tercih

                for model in modeller:
                    adaylar = [i for i in range(len(self.anahtarlar)) if self._uygun_mu(i, model, simdi_utc)]
                    if not adaylar:
                        continue
                    aralik = self.aralik_fonk(model)
                    hazir = []
                    en_erken = None
                    for i in adaylar:
                        d = self._ikili(i, model)
                        uygun_an = max(d.bekle_kadar, d.son_istek + aralik)
                        if uygun_an <= simdi:
                            hazir.append((d.son_istek, i))
                        elif en_erken is None or uygun_an < en_erken:
                            en_erken = uygun_an
                    if hazir:
                        hazir.sort()
                        i = hazir[0][1]
                        self._ikili(i, model).son_istek = simdi
                        self.son_model = model
                        self.toplam_istek += 1
                        return i, self.anahtarlar[i], model
                    # Bu modelin anahtarları sadece geçici olarak meşgul: alt modele
                    # geçmek yerine bekle (kalite önceliği).
                    bekleme = max(0.05, en_erken - simdi)
                    break

                if bekleme is None:
                    raise TumKotalarBitti(self.en_erken_sifirlama(), self.durum_nedenleri())

                if en_fazla_bekleme is not None and self._saat() - baslangic > en_fazla_bekleme:
                    raise TumKotalarBitti(self.en_erken_sifirlama(), self.durum_nedenleri())

                self.kosul.wait(timeout=min(bekleme, 1.0))

    def basarili(self, i, model):
        with self.kosul:
            d = self._ikili(i, model)
            d.ardisik_kota = 0
            d.basarili += 1

    def hata(self, i, model, h):
        """Bir isteğin hatasını bildirir; anahtar/model durumunu günceller."""
        with self.kosul:
            d = self._ikili(i, model)
            simdi = self._saat()
            tur = getattr(h, "tur", None)

            if tur == gemini.GECERSIZ_ANAHTAR or tur == gemini.BOLGE:
                self.gecersiz[i] = h.mesaj
                self._durumu_kaydet()

            elif tur == gemini.KOTA_GUNLUK:
                d.gunluk_bitis = zaman.sonraki_kota_sifirlama(self._utc())
                d.gunluk_kalici = True
                self._durumu_kaydet()

            elif tur == gemini.KOTA_DAKIKA:
                bekle = h.bekle if h.bekle else 60.0
                d.bekle_kadar = max(d.bekle_kadar, simdi + min(bekle, 300.0) + random.uniform(0.5, 3.0))

            elif tur == gemini.KOTA:
                d.ardisik_kota += 1
                if d.ardisik_kota >= 5:
                    # Sürekli kota hatası: bu oturum için günlük bitti say (diske yazma).
                    d.gunluk_bitis = zaman.sonraki_kota_sifirlama(self._utc())
                    d.gunluk_kalici = False
                else:
                    bekle = h.bekle if h.bekle else 20.0 * (2 ** (d.ardisik_kota - 1))
                    d.bekle_kadar = max(d.bekle_kadar, simdi + min(bekle, 900.0) + random.uniform(0.5, 3.0))

            elif tur == gemini.MODEL_YOK:
                self.model_kapali[model] = h.mesaj

            elif tur in (gemini.SUNUCU, gemini.AG, gemini.ZAMAN_ASIMI, gemini.BOS_YANIT):
                bekle = h.bekle if (h.bekle and h.bekle < 120) else random.uniform(3.0, 8.0)
                d.bekle_kadar = max(d.bekle_kadar, simdi + bekle)

            self.kosul.notify_all()

    # ------------------------------------------------------------------
    # Bilgi
    # ------------------------------------------------------------------

    def en_erken_sifirlama(self):
        simdi_utc = self._utc()
        en = None
        for (i, model), d in self.ikililer.items():
            if i in self.gecersiz or model in self.model_kapali:
                continue
            if d.gunluk_bitis and d.gunluk_bitis > simdi_utc:
                if en is None or d.gunluk_bitis < en:
                    en = d.gunluk_bitis
        return en

    def durum_nedenleri(self):
        nedenler = []
        for i, n in sorted(self.gecersiz.items()):
            nedenler.append("Anahtar %s: %s" % (anahtar_etiketi(self.anahtarlar[i]), n))
        for m, n in self.model_kapali.items():
            nedenler.append("Model %s: %s" % (m, n))
        return nedenler

    def ozet(self):
        """Ekranda gösterilecek anahtar durum satırları."""
        satirlar = []
        simdi_utc = self._utc()
        with self.kosul:
            for i, a in enumerate(self.anahtarlar):
                if i in self.gecersiz:
                    satirlar.append("%s  GEÇERSİZ (%s)" % (anahtar_etiketi(a), self.gecersiz[i][:80]))
                    continue
                biten = []
                for model in self.modeller:
                    d = self.ikililer.get((i, model))
                    if d and d.gunluk_bitis and d.gunluk_bitis > simdi_utc:
                        biten.append(model)
                if biten:
                    satirlar.append("%s  kotası biten modeller: %s" % (anahtar_etiketi(a), ", ".join(biten)))
                else:
                    satirlar.append("%s  hazır" % anahtar_etiketi(a))
        return satirlar
