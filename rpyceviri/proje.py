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
ELLE = "elle"          # kullanıcı elle düzeltti: hiçbir otomatik işlem üzerine yazmaz
HAFIZA = "hafiza"      # ortak çeviri hafızasından (başka bir oyunda çevrilmiş aynı metin)

GECERLI_DURUMLAR = (TAMAM, HAZIR, SOZLUK, ELLE, HAFIZA)


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
        self.karakter_yolu = os.path.join(self.klasor, "karakterler.txt")
        self.duzenleme_yolu = os.path.join(self.klasor, "ceviri_duzenle.txt")
        self.ek_istisna_yolu = os.path.join(self.klasor, "ek_istisnalari.txt")
        self.kor_test_yolu = os.path.join(self.klasor, "kalite_testi.html")
        self.maliyet_yolu = os.path.join(self.klasor, "maliyet.json")

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
            if isinstance(k, dict) and isinstance(k.get("c"), str) and k.get("d") in GECERLI_DURUMLAR:
                return k["c"]
            return None

    def kayit_al(self, kaynak):
        with self._kilit:
            k = self.ceviriler.get(kaynak)
            return dict(k) if isinstance(k, dict) else None

    def durum_al(self, kaynak):
        with self._kilit:
            k = self.ceviriler.get(kaynak)
            return k.get("d") if isinstance(k, dict) else None

    def ceviri_kaydet(self, kaynak, ceviri, durum=TAMAM, model=None, not_=None, incelendi=False, zorla=False):
        """Çeviriyi kaydeder. Elle düzeltilmiş bir çevirinin üzerine sadece zorla=True ile yazılır."""
        with self._kilit:
            eski = self.ceviriler.get(kaynak)
            if not zorla and durum != ELLE and isinstance(eski, dict) and eski.get("d") == ELLE:
                return False
            kayit = {"c": ceviri, "d": durum}
            if model:
                kayit["m"] = model
            if not_:
                kayit["n"] = not_
            if incelendi:
                kayit["i"] = 1
            if durum == ELLE:
                kayit["z"] = int(time.time())
            self.ceviriler[kaynak] = kayit
            self._kirli += 1
            return True

    def incelendi_isaretle(self, kaynak):
        with self._kilit:
            k = self.ceviriler.get(kaynak)
            if isinstance(k, dict) and not k.get("i"):
                k["i"] = 1
                self._kirli += 1

    def incelendi_mi(self, kaynak):
        with self._kilit:
            k = self.ceviriler.get(kaynak)
            return bool(isinstance(k, dict) and k.get("i"))

    def elle_duzeltilenler(self, en_fazla=None):
        """Kullanıcının elle düzelttiği (kaynak, çeviri) çiftleri, en yeniden eskiye."""
        with self._kilit:
            liste = [(v.get("z", 0), k, v["c"]) for k, v in self.ceviriler.items()
                     if isinstance(v, dict) and v.get("d") == ELLE and isinstance(v.get("c"), str)]
        liste.sort(reverse=True)
        sonuc = [(k, c) for _z, k, c in liste]
        return sonuc[:en_fazla] if en_fazla else sonuc

    def basarisiz_kaydet(self, kaynak, neden):
        with self._kilit:
            eski = self.ceviriler.get(kaynak)
            if isinstance(eski, dict) and eski.get("d") in GECERLI_DURUMLAR:
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

    # ------------------------------------------------------------------
    # Ücretli servis harcaması (oyun başına, tüm oturumlar toplamı)

    def maliyet_al(self):
        veri = json_oku(self.maliyet_yolu, {}) or {}
        try:
            return float(veri.get("toplam_usd", 0.0)) if isinstance(veri, dict) else 0.0
        except (TypeError, ValueError):
            return 0.0

    def maliyet_ekle(self, tutar):
        if not tutar:
            return
        toplam = self.maliyet_al() + float(tutar)
        try:
            json_yaz(self.maliyet_yolu, {"toplam_usd": round(toplam, 6)})
        except OSError:
            pass
