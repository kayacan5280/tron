"""Oyun klasörünü tanıma, oyunu başlatma ve metinleri oyunun içinden çıkarma.

Metinler, oyuna geçici olarak eklenen küçük bir Ren'Py dosyası sayesinde oyunun
kendi motoru tarafından okunur. Bu sayede .rpa arşivli, kaynak kodu (.rpy)
olmayan, sadece derlenmiş (.rpyc) dosyaları bulunan oyunlar da çevrilebilir.
"""

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse

from .ayarlar import RENPY_DOSYALARI

CIKARICI_KAYNAK = os.path.join(RENPY_DOSYALARI, "trceviri_cikarici.rpy")
CIKARICI_AD = "zzzz_trceviri_cikarici.rpy"
BAYRAK_AD = "trceviri_cikar.txt"
YEDEK_CIKTI_AD = "trceviri_cikti.json"


class OyunHatasi(Exception):
    pass


class Oyun(object):

    def __init__(self, kok):
        self.kok = kok
        self.game = os.path.join(kok, "game")
        self.ad = os.path.basename(os.path.normpath(kok))
        self.renpy_surumu = renpy_surumu_bul(kok)


def yol_temizle(girdi):
    """Konsola sürükle-bırak ile gelen yolu temizler (tırnak, PowerShell '& ', file://)."""
    s = (girdi or "").strip()
    if s.startswith("& "):
        s = s[2:].strip()
    for _ in range(2):
        if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
            s = s[1:-1].strip()
    if s.lower().startswith("file://"):
        s = urllib.parse.unquote(s[7:])
        if os.name == "nt" and re.match(r"^/[A-Za-z]:", s):
            s = s[1:]
    s = os.path.expanduser(s)
    if not s:
        return s
    return os.path.normpath(s)


def _renpy_oyun_klasoru_mu(game):
    if not os.path.isdir(game):
        return False
    sayac = 0
    for kok, klasorler, dosyalar in os.walk(game):
        for d in dosyalar:
            if d.endswith((".rpy", ".rpyc", ".rpa", ".rpym", ".rpymc")):
                return True
        sayac += 1
        if sayac > 400:
            break
    return False


def oyun_bul(yol):
    """Verilen yoldan Ren'Py oyununun kök klasörünü bulur."""
    if not yol:
        raise OyunHatasi("Klasör yolu boş.")
    if not os.path.exists(yol):
        raise OyunHatasi("Böyle bir klasör yok: %s" % yol)

    if os.path.isfile(yol):
        yol = os.path.dirname(yol)

    adaylar = []
    if yol.lower().endswith(".app"):
        adaylar.append(os.path.join(yol, "Contents", "Resources", "autorun"))
    adaylar.append(yol)
    if os.path.basename(os.path.normpath(yol)).lower() == "game":
        adaylar.append(os.path.dirname(os.path.normpath(yol)))
    # Bir üst/alt klasör seçilmiş olabilir.
    try:
        for alt in sorted(os.listdir(yol)):
            tam = os.path.join(yol, alt)
            if os.path.isdir(tam):
                adaylar.append(tam)
                if alt.lower().endswith(".app"):
                    adaylar.append(os.path.join(tam, "Contents", "Resources", "autorun"))
    except Exception:
        pass

    bulunan = []
    for a in adaylar:
        game = os.path.join(a, "game")
        if _renpy_oyun_klasoru_mu(game) and os.path.abspath(a) not in [os.path.abspath(b) for b in bulunan]:
            bulunan.append(a)
        if bulunan and a == yol:
            break

    if not bulunan:
        raise OyunHatasi(
            "Bu klasörde Ren'Py oyunu bulunamadı.\n"
            "  Oyunun ana klasörünü seçin: içinde 'game' klasörü ve oyunun .exe dosyası bulunan klasör."
        )
    if len(bulunan) > 1:
        raise OyunHatasi(
            "Bu klasörde birden fazla oyun var. Lütfen doğrudan oyunun klasörünü verin:\n  "
            + "\n  ".join(bulunan[:10])
        )
    return Oyun(os.path.abspath(bulunan[0]))


def renpy_surumu_bul(kok):
    yol = os.path.join(kok, "renpy", "vc_version.py")
    try:
        with open(yol, "r", encoding="utf-8", errors="replace") as f:
            metin = f.read()
        m = re.search(r"^version\s*=\s*u?['\"]([0-9.]+)['\"]", metin, re.M)
        if m:
            return m.group(1)
    except Exception:
        pass
    yol = os.path.join(kok, "renpy", "__init__.py")
    try:
        with open(yol, "r", encoding="utf-8", errors="replace") as f:
            metin = f.read()
        m = re.search(r"version_tuple\s*=\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", metin)
        if m:
            return "%s.%s.%s" % m.groups()
    except Exception:
        pass
    lib = os.path.join(kok, "lib")
    if os.path.isdir(lib):
        adlar = os.listdir(lib)
        if any(a.startswith("py3-") for a in adlar):
            return "8.x"
        if any(a.startswith("py2-") for a in adlar):
            return "7.x"
        if adlar:
            return "6.x/7.x"
    return ""


def baslatma_komutu(kok):
    """Oyunu başlatmak için komut listesi; bulunamazsa None."""
    py_adlari = [os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(kok, "*.py"))]

    if os.name == "nt":
        exeler = [p for p in glob.glob(os.path.join(kok, "*.exe"))]
        uygun = []
        for e in exeler:
            ad = os.path.splitext(os.path.basename(e))[0]
            kucuk = ad.lower()
            if kucuk.endswith("-32") or kucuk.startswith(("python", "pythonw", "zsync", "unitycrash", "notification", "dxweb", "vc_redist", "unins")):
                continue
            uygun.append((0 if ad in py_adlari else 1, ad, e))
        if uygun:
            uygun.sort()
            return [uygun[0][2]]
        return None

    if sys.platform == "darwin":
        uygulamalar = glob.glob(os.path.join(kok, "*.app"))
        for u in uygulamalar:
            ikili = glob.glob(os.path.join(u, "Contents", "MacOS", "*"))
            if ikili:
                return [ikili[0]]
        if "/Contents/Resources/autorun" in kok.replace("\\", "/"):
            uygulama = kok.replace("\\", "/").split("/Contents/Resources/autorun")[0]
            ikili = glob.glob(os.path.join(uygulama, "Contents", "MacOS", "*"))
            if ikili:
                return [ikili[0]]

    shler = glob.glob(os.path.join(kok, "*.sh"))
    shler.sort(key=lambda p: (0 if os.path.splitext(os.path.basename(p))[0] in py_adlari else 1, p))
    if shler:
        return ["sh", shler[0]]
    return None


def yazilabilir_mi(klasor):
    deneme = os.path.join(klasor, ".trceviri_yazma_testi")
    try:
        with open(deneme, "w") as f:
            f.write("x")
        os.remove(deneme)
        return True
    except Exception:
        return False


def cikariciyi_temizle(oyun):
    for ad in (CIKARICI_AD, CIKARICI_AD + "c", BAYRAK_AD, YEDEK_CIKTI_AD, YEDEK_CIKTI_AD + ".yaziliyor"):
        yol = os.path.join(oyun.game, ad)
        try:
            if os.path.exists(yol):
                os.remove(yol)
        except Exception:
            pass


def _hata_dosyalarini_oku(oyun):
    parcalar = []
    for ad in ("traceback.txt", "errors.txt"):
        yol = os.path.join(oyun.kok, ad)
        try:
            if os.path.exists(yol) and time.time() - os.path.getmtime(yol) < 900:
                with open(yol, "r", encoding="utf-8", errors="replace") as f:
                    icerik = f.read().strip()
                parcalar.append("--- %s ---\n%s" % (ad, "\n".join(icerik.splitlines()[-25:])))
        except Exception:
            pass
    return "\n".join(parcalar)


def metinleri_cikar(oyun, hedef_json, bekleme_sn=600, durum=None, manuel_bekle=None):
    """Oyunu kısa süreliğine çalıştırıp tüm metinleri hedef_json dosyasına çıkarır.

    durum: fonk(mesaj) - ilerleme mesajları için.
    manuel_bekle: fonk() - oyun otomatik başlatılamazsa kullanıcıya oyunu açtırmak için.
    Döndürür: çıkarılan veri (dict).
    """
    durum = durum or (lambda m: None)

    if not yazilabilir_mi(oyun.game):
        raise OyunHatasi(
            "Oyun klasörüne yazılamıyor (izin yok): %s\n"
            "  Çözüm: Oyunu 'Program Files' dışındaki bir klasöre kopyalayın veya bu programı yönetici olarak çalıştırın."
            % oyun.game
        )

    cikariciyi_temizle(oyun)
    if os.path.exists(hedef_json):
        os.remove(hedef_json)

    shutil.copyfile(CIKARICI_KAYNAK, os.path.join(oyun.game, CIKARICI_AD))
    with open(os.path.join(oyun.game, BAYRAK_AD), "wb") as f:
        f.write(os.path.abspath(hedef_json).encode("utf-8"))

    yedek_cikti = os.path.join(oyun.game, YEDEK_CIKTI_AD)

    def sonuc_var():
        for yol in (hedef_json, yedek_cikti):
            if os.path.exists(yol):
                return yol
        return None

    surec = None
    try:
        komut = baslatma_komutu(oyun.kok)
        if komut:
            ortam = dict(os.environ)
            ortam["TRCEVIRI_CIKTI"] = os.path.abspath(hedef_json)
            durum("Oyun başlatılıyor: %s" % os.path.basename(komut[-1]))
            try:
                surec = subprocess.Popen(
                    komut, cwd=oyun.kok, env=ortam,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                )
            except Exception as e:
                durum("Oyun otomatik başlatılamadı (%s)." % e)
                surec = None

        if surec is None:
            if manuel_bekle is None:
                raise OyunHatasi("Oyun başlatılamadı.")
            manuel_bekle()

        baslangic = time.time()
        bitis_ani = None
        son_bildirim = 0
        while True:
            yol = sonuc_var()
            if yol:
                # Dosyanın yazımı bitsin.
                time.sleep(0.5)
                break
            gecen = time.time() - baslangic
            if gecen - son_bildirim >= 5:
                son_bildirim = gecen
                durum("Metinler çıkarılıyor... (%d sn)" % gecen)
            # Oyun hata verdiyse Ren'Py traceback.txt / errors.txt yazar.
            for ad in ("traceback.txt", "errors.txt"):
                hata_yolu = os.path.join(oyun.kok, ad)
                try:
                    if os.path.exists(hata_yolu) and os.path.getmtime(hata_yolu) >= baslangic - 2:
                        time.sleep(1.0)
                        if sonuc_var():
                            break
                        if surec is not None:
                            try:
                                surec.kill()
                            except Exception:
                                pass
                        raise OyunHatasi(
                            "Oyun açılırken hata verdi (oyun penceresi açık kaldıysa kapatın).\n"
                            + _hata_dosyalarini_oku(oyun)
                        )
                except OyunHatasi:
                    raise
                except Exception:
                    pass
            if surec is not None and bitis_ani is None and surec.poll() is not None:
                bitis_ani = time.time()
            # Başlatıcı kapandıysa (bazı oyunlar ayrı bir süreç açar, Steam yeniden
            # başlatabilir) metin dosyası için bir süre daha bekle.
            if bitis_ani is not None and time.time() - bitis_ani > 120:
                ek = _hata_dosyalarini_oku(oyun)
                raise OyunHatasi(
                    "Oyun kapandı ama metinler çıkarılamadı.\n"
                    "  Oyun bir hata vermiş olabilir. Oyunu normal açıp çalıştığından emin olun."
                    + ("\n" + ek if ek else "")
                )
            if gecen > bekleme_sn:
                raise OyunHatasi(
                    "Oyun %d saniye içinde metinleri çıkaramadı.\n"
                    "  Oyun penceresi açık kaldıysa kapatıp tekrar deneyin." % bekleme_sn
                )
            time.sleep(0.5)

        try:
            with open(yol, "r", encoding="utf-8") as f:
                veri = json.load(f)
        except Exception as e:
            raise OyunHatasi("Çıkarılan metin dosyası okunamadı: %s" % e)

        if yol != hedef_json:
            shutil.copyfile(yol, hedef_json)

        if surec is not None:
            try:
                surec.wait(timeout=15)
            except Exception:
                try:
                    surec.kill()
                except Exception:
                    pass

        if not isinstance(veri, dict):
            raise OyunHatasi("Çıkarılan veri beklenmeyen biçimde.")
        if veri.get("hata"):
            raise OyunHatasi("Metin çıkarılırken oyun içinde hata oluştu:\n" + str(veri["hata"])[-1500:])
        return veri
    finally:
        # Hata/iptal durumunda açık kalan oyun sürecini kapat.
        if surec is not None:
            try:
                if surec.poll() is None:
                    surec.kill()
            except Exception:
                pass
        cikariciyi_temizle(oyun)
