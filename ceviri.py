#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ren'Py Türkçe Çeviri Motoru - başlatıcı.

Kullanım:
    python ceviri.py                 -> menülü kullanım
    python ceviri.py "OYUN_KLASORU"  -> doğrudan o oyunu çevir
"""

import os
import sys

KOK = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KOK)

if sys.version_info < (3, 8):
    sys.stdout.write("Bu program Python 3.8 veya daha yeni bir surum gerektirir.\n")
    sys.stdout.write("Indirme: https://www.python.org/downloads/\n")
    sys.exit(1)


def _calistir():
    from rpyceviri.ana import main
    return main()


if __name__ == "__main__":
    try:
        kod = _calistir()
    except SystemExit:
        raise
    except BaseException:
        import traceback
        ayrinti = traceback.format_exc()
        yol = os.path.join(KOK, "hata_raporu.txt")
        try:
            with open(yol, "w", encoding="utf-8") as f:
                f.write(ayrinti)
        except Exception:
            yol = None
        sys.stdout.write("\nBeklenmeyen bir hata oluştu ve program durdu.\n")
        sys.stdout.write(ayrinti + "\n")
        if yol:
            sys.stdout.write("Hata ayrıntısı şu dosyaya kaydedildi: %s\n" % yol)
        kod = 1
    sys.exit(kod or 0)
