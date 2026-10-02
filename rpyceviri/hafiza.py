"""Oyunlar arası ortak çeviri hafızası.

Bir oyunda çevrilen kısa ve bağlamdan bağımsız metinler ("Yes", "Thanks!",
"Load Game"...) burada saklanır; başka bir oyunda aynı metin geçerse API
harcanmadan kullanılır. Uzun diyaloglar bağlama bağlı olduğundan hafızaya
alınmaz (aynı cümle başka oyunda farklı hitap/tonla çevrilmeli olabilir).
"""

import json
import os
import re
import threading

from .ayarlar import KOK

HAFIZA_DOSYASI = os.path.join(KOK, "hafiza", "ortak_ceviri_hafizasi.json")

_KELIME_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def uygun_mu(kaynak, tur):
    """Bu metin oyunlar arası paylaşılmaya uygun mu?"""
    if not isinstance(kaynak, str) or not kaynak.strip() or len(kaynak) > 80:
        return False
    if "[" in kaynak or "{" in kaynak or "\n" in kaynak:
        return False
    if tur in ("arayuz", "isim"):
        return True
    # Diyalog/seçenek: sadece en fazla 3 kelimelik kısa ünlem/cevaplar.
    return len(_KELIME_RE.findall(kaynak)) <= 3


class Hafiza(object):

    def __init__(self, yol=HAFIZA_DOSYASI):
        self.yol = yol
        self._kilit = threading.RLock()
        self.kayitlar = {}
        try:
            with open(yol, "r", encoding="utf-8-sig") as f:
                veri = json.load(f)
            if isinstance(veri, dict):
                self.kayitlar = {k: v for k, v in veri.items() if isinstance(v, dict) and isinstance(v.get("c"), str)}
        except FileNotFoundError:
            pass
        except Exception:
            # Bozuk hafıza dosyası programı durdurmasın.
            self.kayitlar = {}
        self._degisti = False

    def al(self, kaynak, tur):
        if not uygun_mu(kaynak, tur):
            return None
        with self._kilit:
            k = self.kayitlar.get(kaynak)
            return k["c"] if k else None

    def ekle(self, kaynak, ceviri, tur, elle=False):
        if not uygun_mu(kaynak, tur) or not isinstance(ceviri, str) or not ceviri.strip():
            return
        if ceviri == kaynak:
            return
        with self._kilit:
            eski = self.kayitlar.get(kaynak)
            # Elle düzeltilmiş kayıt, otomatik çevirinin üzerine yazılmaz.
            if eski and eski.get("e") and not elle:
                return
            if eski and eski.get("c") == ceviri and bool(eski.get("e")) == bool(elle):
                return
            kayit = {"c": ceviri}
            if elle:
                kayit["e"] = 1
            self.kayitlar[kaynak] = kayit
            self._degisti = True

    def kaydet(self):
        with self._kilit:
            if not self._degisti:
                return
            os.makedirs(os.path.dirname(self.yol), exist_ok=True)
            gecici = self.yol + ".tmp"
            with open(gecici, "w", encoding="utf-8") as f:
                json.dump(self.kayitlar, f, ensure_ascii=False, indent=0, sort_keys=True)
            os.replace(gecici, self.yol)
            self._degisti = False

    def __len__(self):
        return len(self.kayitlar)
