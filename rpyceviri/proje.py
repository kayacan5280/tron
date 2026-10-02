"""Her oyun için bir proje klasörü: çıkarılan metinler, çeviriler, sözlük, rapor.

Çeviriler her paket bittiğinde güvenli biçimde (önce geçici dosyaya, sonra
yerine taşıyarak) kaydedilir. Program kapansa, elektrik gitse bile en fazla
son paket kaybolur ve bir sonraki çalıştırmada kaldığı yerden devam edilir.
"""

import datetime
import hashlib
import json
import os
import re
import shutil
import threading
import time

from .ayarlar import PROJE_KLASORU

# Çeviri durumları
TAMAM = "tamam"        # yapay zeka çevirdi, doğrulandı
HAZIR = "hazir"        # yerleşik Türkçe arayüz tablosundan
SOZLUK = "sozluk"      # sözlükten (karakter adı vb.)
BASARISIZ = "basarisiz"  # çevrilemedi, orijinal metin kalacak (sonraki çalıştırmada tekrar denenir)


def guvenli_ad(metin):
    metin = re.sub(r"[^\w\-. ]+", "_", metin, flags=re.UNICODE).strip(" ._")
    return metin[:60] or "oyun"


def json_yaz(yol, veri):
    """Güvenli yazım: önce geçici dosya, sonra yerine taşıma.

    Windows'ta antivirüs/yedekleme programları dosyayı kısa süre kilitleyebilir;
    bu yüzden birkaç kez yeniden denenir.
    """
    gecici = yol + ".tmp"
    son_hata = None
    for deneme in range(6):
        try:
            with open(gecici, "w", encoding="utf-8") as f:
                json.dump(veri, f, ensure_ascii=False, indent=0)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
            os.replace(gecici, yol)
            return
        except (PermissionError, OSError) as e:
            son_hata = e
            time.sleep(0.3 * (deneme + 1))
    raise son_hata


def json_oku(yol, varsayilan=None):
    if not os.path.exists(yol):
        return varsayilan
    try:
        with open(yol, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        # Bozuk dosyayı yedekle; yedek (.tmp) varsa onu dene.
        try:
            shutil.copy(yol, yol + ".bozuk")
        except Exception:
            pass
        if os.path.exists(yol + ".tmp"):
            try:
                with open(yol + ".tmp", "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return varsayilan


class Proje(object):

    def __init__(self, oyun_kok, oyun_adi=None):
        mutlak = os.path.normcase(os.path.abspath(oyun_kok))
        ozet = hashlib.sha1(mutlak.encode("utf-8")).hexdigest()[:8]
        ad = guvenli_ad(oyun_adi or os.path.basename(os.path.abspath(oyun_kok)))
        self.klasor = os.path.join(PROJE_KLASORU, "%s_%s" % (ad, ozet))
        os.makedirs(self.klasor, exist_ok=True)

        self.cikti_yolu = os.path.join(self.klasor, "cikarilan_metinler.json")
        self.ceviri_yolu = os.path.join(self.klasor, "ceviriler.json")
        self.sozluk_yolu = os.path.join(self.klasor, "sozluk.txt")
        self.not_yolu = os.path.join(self.klasor, "oyun_notu.txt")
        self.rapor_yolu = os.path.join(self.klasor, "rapor.txt")
        self.gunluk_yolu = os.path.join(self.klasor, "gunluk.txt")

        self._kilit = threading.RLock()
        self.ceviriler = json_oku(self.ceviri_yolu, {}) or {}
        if not isinstance(self.ceviriler, dict):
            self.ceviriler = {}
        self._kirli = 0

    # ------------------------------------------------------------------

    def gunluge_yaz(self, mesaj):
        try:
            with self._kilit:
                with open(self.gunluk_yolu, "a", encoding="utf-8") as f:
                    f.write(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "  " + mesaj + "\n")
        except Exception:
            pass

    def ceviri_al(self, kaynak):
        with self._kilit:
            k = self.ceviriler.get(kaynak)
            if isinstance(k, dict) and isinstance(k.get("c"), str) and k.get("d") in (TAMAM, HAZIR, SOZLUK):
                return k["c"]
            return None

    def durum_al(self, kaynak):
        with self._kilit:
            k = self.ceviriler.get(kaynak)
            return k.get("d") if isinstance(k, dict) else None

    def ceviri_kaydet(self, kaynak, ceviri, durum=TAMAM, model=None, not_=None):
        with self._kilit:
            kayit = {"c": ceviri, "d": durum}
            if model:
                kayit["m"] = model
            if not_:
                kayit["n"] = not_
            self.ceviriler[kaynak] = kayit
            self._kirli += 1

    def basarisiz_kaydet(self, kaynak, neden):
        with self._kilit:
            eski = self.ceviriler.get(kaynak)
            if isinstance(eski, dict) and eski.get("d") in (TAMAM, HAZIR, SOZLUK):
                return
            self.ceviriler[kaynak] = {"c": None, "d": BASARISIZ, "n": str(neden)[:300]}
            self._kirli += 1

    def kaydet(self, zorla=False):
        with self._kilit:
            if not self._kirli and not zorla:
                return
            json_yaz(self.ceviri_yolu, self.ceviriler)
            self._kirli = 0

    def basarisizlari_sifirla(self):
        with self._kilit:
            for k in [k for k, v in self.ceviriler.items() if isinstance(v, dict) and v.get("d") == BASARISIZ]:
                del self.ceviriler[k]
            self._kirli += 1

    def tum_cevirileri_sil(self):
        with self._kilit:
            self.ceviriler = {}
            self._kirli += 1
            self.kaydet()

    # ------------------------------------------------------------------

    def oyun_notu(self):
        try:
            with open(self.not_yolu, "r", encoding="utf-8-sig") as f:
                return f.read().strip()
        except Exception:
            return ""

    def oyun_notu_yaz(self, metin):
        with open(self.not_yolu, "w", encoding="utf-8") as f:
            f.write((metin or "").strip() + "\n")
