"""Konsol arayüzü: renkli yazı, soru sorma, ilerleme çubuğu.

Windows'un siyah komut ekranında (cmd / PowerShell / Windows Terminal) ve
Linux/Mac terminallerinde çalışır. Renk desteklenmiyorsa düz yazıya döner.
"""

import os
import sys
import threading
import time

_kilit = threading.RLock()
_renk_acik = False
_ilerleme_satiri = ""


def _konsolu_hazirla():
    """Windows konsolunda UTF-8 ve ANSI renk desteğini açar."""
    global _renk_acik

    for akis in (sys.stdout, sys.stderr):
        try:
            akis.reconfigure(errors="replace")
        except Exception:
            pass

    if os.environ.get("NO_COLOR"):
        _renk_acik = False
        return

    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            tutamac = kernel32.GetStdHandle(-11)
            kip = ctypes.c_uint32()
            if kernel32.GetConsoleMode(tutamac, ctypes.byref(kip)):
                # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
                if kernel32.SetConsoleMode(tutamac, kip.value | 0x0004):
                    _renk_acik = True
        except Exception:
            _renk_acik = False
    else:
        _renk_acik = sys.stdout.isatty()


_konsolu_hazirla()

_RENKLER = {
    "kirmizi": "\033[91m",
    "yesil": "\033[92m",
    "sari": "\033[93m",
    "mavi": "\033[94m",
    "mor": "\033[95m",
    "camgobegi": "\033[96m",
    "gri": "\033[90m",
    "kalin": "\033[1m",
}
_SIFIRLA = "\033[0m"


def renk(metin, ad):
    if not _renk_acik or ad not in _RENKLER:
        return metin
    return _RENKLER[ad] + metin + _SIFIRLA


def _yaz(metin, akis=None):
    akis = akis or sys.stdout
    with _kilit:
        _ilerlemeyi_sil()
        try:
            akis.write(metin + "\n")
        except UnicodeEncodeError:
            akis.write(metin.encode("ascii", "replace").decode("ascii") + "\n")
        akis.flush()
        _ilerlemeyi_yeniden_ciz()


def yaz(metin=""):
    _yaz(metin)


def bilgi(metin):
    _yaz(renk("• ", "camgobegi") + metin)


def basari(metin):
    _yaz(renk("✔ ", "yesil") + metin)


def uyari(metin):
    _yaz(renk("! ", "sari") + renk(metin, "sari"))


def hata(metin):
    _yaz(renk("✘ ", "kirmizi") + renk(metin, "kirmizi"))


def baslik(metin):
    cizgi = "═" * max(10, min(70, len(metin) + 4))
    _yaz("")
    _yaz(renk(cizgi, "mavi"))
    _yaz(renk("  " + metin, "kalin"))
    _yaz(renk(cizgi, "mavi"))


def ara_baslik(metin):
    _yaz("")
    _yaz(renk("── " + metin + " ──", "camgobegi"))


def sor(soru, varsayilan=None):
    """Kullanıcıdan bir satır metin alır."""
    ek = ""
    if varsayilan:
        ek = renk(" [" + varsayilan + "]", "gri")
    with _kilit:
        _ilerlemeyi_sil()
    try:
        cevap = input(renk("? ", "mor") + soru + ek + ": ")
    except EOFError:
        cevap = ""
    cevap = cevap.strip()
    if not cevap and varsayilan is not None:
        return varsayilan
    return cevap


def evet_mi(soru, varsayilan=True):
    """Evet/hayır sorusu. Enter varsayılanı seçer."""
    secenek = "E/h" if varsayilan else "e/H"
    while True:
        cevap = sor(soru + " (" + secenek + ")").lower()
        if not cevap:
            return varsayilan
        if cevap in ("e", "evet", "y", "yes", "1"):
            return True
        if cevap in ("h", "hayir", "hayır", "n", "no", "0"):
            return False
        uyari("Lütfen 'e' (evet) veya 'h' (hayır) yazın.")


def secim(soru, secenekler, varsayilan=None):
    """Numaralı menüden seçim yaptırır. secenekler: [(anahtar, açıklama), ...]"""
    for anahtar, aciklama in secenekler:
        _yaz("  " + renk("[" + anahtar + "]", "kalin") + " " + aciklama)
    gecerli = [a for a, _ in secenekler]
    while True:
        cevap = sor(soru, varsayilan)
        for a in gecerli:
            if cevap.lower() == a.lower():
                return a
        uyari("Geçersiz seçim. Şunlardan birini yazın: " + ", ".join(gecerli))


def bekle(mesaj="Devam etmek için Enter'a basın"):
    sor(mesaj)


# ---------------------------------------------------------------------------
# İlerleme çubuğu
# ---------------------------------------------------------------------------


def _ilerlemeyi_sil():
    if _ilerleme_satiri and sys.stdout.isatty():
        sys.stdout.write("\r" + " " * min(len(_ilerleme_satiri) + 2, 200) + "\r")
        sys.stdout.flush()


def _ilerlemeyi_yeniden_ciz():
    if _ilerleme_satiri and sys.stdout.isatty():
        try:
            sys.stdout.write(_ilerleme_satiri)
        except UnicodeEncodeError:
            sys.stdout.write(_ilerleme_satiri.encode("ascii", "replace").decode("ascii"))
        sys.stdout.flush()


def sure_metni(saniye):
    saniye = int(max(0, saniye))
    if saniye < 60:
        return "%d sn" % saniye
    if saniye < 3600:
        return "%d dk %d sn" % (saniye // 60, saniye % 60)
    return "%d sa %d dk" % (saniye // 3600, (saniye % 3600) // 60)


class Ilerleme(object):
    """Tek satırda güncellenen ilerleme çubuğu."""

    def __init__(self, toplam, etiket="Çeviri"):
        self.toplam = max(0, toplam)
        self.etiket = etiket
        self.yapilan = 0
        self.baslangic = time.time()
        self.ek = ""
        self._son_cizim = 0
        self._ilk_yapilan = None

    def guncelle(self, yapilan=None, ek=None, zorla=False):
        global _ilerleme_satiri
        if yapilan is not None:
            self.yapilan = yapilan
        if ek is not None:
            self.ek = ek
        if self._ilk_yapilan is None:
            self._ilk_yapilan = self.yapilan

        simdi = time.time()
        if not zorla and simdi - self._son_cizim < 0.3:
            return
        self._son_cizim = simdi

        oran = (float(self.yapilan) / self.toplam) if self.toplam else 1.0
        oran = max(0.0, min(1.0, oran))
        genislik = 24
        dolu = int(oran * genislik)
        cubuk = "█" * dolu + "░" * (genislik - dolu)

        gecen = simdi - self.baslangic
        bu_oturum = self.yapilan - (self._ilk_yapilan or 0)
        kalan_metin = ""
        if bu_oturum > 0 and gecen > 5:
            hiz = bu_oturum / gecen
            kalan = (self.toplam - self.yapilan) / hiz if hiz > 0 else 0
            kalan_metin = " | kalan ~" + sure_metni(kalan)

        satir = "\r%s %s %5.1f%% %d/%d%s %s" % (
            self.etiket, cubuk, oran * 100, self.yapilan, self.toplam, kalan_metin, self.ek
        )
        with _kilit:
            if sys.stdout.isatty():
                _ilerlemeyi_sil()
                _ilerleme_satiri = satir[:220]
                _ilerlemeyi_yeniden_ciz()
            else:
                _ilerleme_satiri = ""

    def bitir(self):
        global _ilerleme_satiri
        self.guncelle(zorla=True)
        with _kilit:
            if sys.stdout.isatty():
                sys.stdout.write("\n")
                sys.stdout.flush()
            _ilerleme_satiri = ""
