"""Karakter kartları ve hitap (sen/siz) tablosu.

Oyunun başında yapay zeka, her önemli karakterin örnek repliklerine bakarak bir
"karakter kartı" (cinsiyet, yaş, kişilik ve konuşma tarzı) ve karakterler arası
hitap tablosu (kim kime "sen", kim kime "siz" der) çıkarır. Bunlar
"karakterler.txt" dosyasında durur, kullanıcı düzenleyebilir ve her çeviri
paketine sadece o pakette geçen karakterler için eklenir. Böylece tüm oyun
boyunca ses tonu ve hitap tutarlı kalır.

Dosya biçimi:
    [Sylvie]
    cinsiyet = kadın
    yaş = genç yetişkin
    üslup = Neşeli, samimi, hafif utangaç; kısa cümleler kurar.

    # HİTAP
    Sylvie -> Me = sen
"""

import collections
import re

_BOLUM_RE = re.compile(r"^\[(.+)\]\s*$")
_ALAN_RE = re.compile(r"^\s*([^=]+?)\s*=\s*(.*?)\s*$")
_HITAP_RE = re.compile(r"^\s*(.+?)\s*->\s*(.+?)\s*=\s*(sen|siz)\b\s*(.*)$", re.IGNORECASE)

_ALAN_ADLARI = {
    "cinsiyet": "cinsiyet", "yaş": "yas", "yas": "yas", "üslup": "uslup", "uslup": "uslup",
    "not": "not",
}


class Karakterler(object):

    def __init__(self):
        self.kartlar = collections.OrderedDict()   # ad -> {"cinsiyet", "yas", "uslup", "not"}
        self.hitap = collections.OrderedDict()     # (konuşan, dinleyen) -> "sen"/"siz"

    def __len__(self):
        return len(self.kartlar)

    def kart_ekle(self, ad, cinsiyet="", yas="", uslup="", not_=""):
        ad = (ad or "").strip()
        if not ad or "\n" in ad or "]" in ad:
            return
        kart = {}
        for anahtar, deger in (("cinsiyet", cinsiyet), ("yas", yas), ("uslup", uslup), ("not", not_)):
            deger = (deger or "").strip().replace("\n", " ")
            if deger:
                kart[anahtar] = deger[:300]
        self.kartlar[ad] = kart

    def hitap_ekle(self, konusan, dinleyen, hitap):
        konusan = (konusan or "").strip()
        dinleyen = (dinleyen or "").strip()
        hitap = (hitap or "").strip().lower()
        if not konusan or not dinleyen or konusan == dinleyen or hitap not in ("sen", "siz"):
            return
        if "->" in konusan or "->" in dinleyen:
            return
        self.hitap[(konusan, dinleyen)] = hitap

    # ------------------------------------------------------------------

    def yaz(self, yol):
        with open(yol, "w", encoding="utf-8") as f:
            f.write("# KARAKTER KARTLARI VE HİTAP TABLOSU\n")
            f.write("# Çeviride karakterlerin ses tonu ve sen/siz kullanımı buna göre belirlenir.\n")
            f.write("# Değiştirebilir, ekleyebilir ya da silebilirsiniz. Satır biçimleri:\n")
            f.write("#   [Karakter Adı]         -> yeni kart başlar\n")
            f.write("#   cinsiyet = kadın        (kadın / erkek / belirsiz)\n")
            f.write("#   yaş = genç yetişkin\n")
            f.write("#   üslup = konuşma tarzı, kişilik\n")
            f.write("#   Konuşan -> Dinleyen = sen   (veya siz)\n\n")
            for ad, kart in self.kartlar.items():
                f.write("[%s]\n" % ad)
                if kart.get("cinsiyet"):
                    f.write("cinsiyet = %s\n" % kart["cinsiyet"])
                if kart.get("yas"):
                    f.write("yaş = %s\n" % kart["yas"])
                if kart.get("uslup"):
                    f.write("üslup = %s\n" % kart["uslup"])
                if kart.get("not"):
                    f.write("not = %s\n" % kart["not"])
                f.write("\n")
            f.write("# HİTAP (kim kime nasıl hitap eder)\n")
            for (a, b), h in self.hitap.items():
                f.write("%s -> %s = %s\n" % (a, b, h))

    @classmethod
    def oku(cls, yol):
        k = cls()
        try:
            with open(yol, "r", encoding="utf-8-sig") as f:
                satirlar = f.read().splitlines()
        except FileNotFoundError:
            return k
        mevcut = None
        for satir in satirlar:
            s = satir.strip()
            if not s or s.startswith("#"):
                continue
            m = _BOLUM_RE.match(s)
            if m:
                mevcut = m.group(1).strip()
                k.kartlar.setdefault(mevcut, {})
                continue
            m = _HITAP_RE.match(s)
            if m:
                k.hitap_ekle(m.group(1), m.group(2), m.group(3))
                mevcut = None
                continue
            m = _ALAN_RE.match(s)
            if m and mevcut is not None:
                alan = _ALAN_ADLARI.get(m.group(1).strip().lower())
                if alan and m.group(2):
                    k.kartlar[mevcut][alan] = m.group(2)[:300]
        return k

    # ------------------------------------------------------------------

    def cinsiyet(self, ad):
        c = (self.kartlar.get(ad) or {}).get("cinsiyet", "").lower()
        if c.startswith("kad"):
            return "kadın"
        if c.startswith("erk"):
            return "erkek"
        return None

    def istem_satirlari(self, adlar, en_fazla_kart=10, en_fazla_hitap=20):
        """Verilen karakterler için istemde gösterilecek kart ve hitap satırları."""
        adlar = [a for a in adlar if a]
        kume = set(adlar)
        kart_satirlari = []
        for ad in adlar:
            if len(kart_satirlari) >= en_fazla_kart:
                break
            kart = self.kartlar.get(ad)
            if not kart:
                continue
            parca = [kart[a] for a in ("cinsiyet", "yas") if kart.get(a)]
            s = ad + (" (" + ", ".join(parca) + ")" if parca else "")
            if kart.get("uslup"):
                s += ": " + kart["uslup"]
            if kart.get("not"):
                s += " Not: " + kart["not"]
            kart_satirlari.append(s)
        hitap_satirlari = []
        for (a, b), h in self.hitap.items():
            if len(hitap_satirlari) >= en_fazla_hitap:
                break
            if a in kume:
                hitap_satirlari.append("%s → %s: %s" % (a, b, h))
        return kart_satirlari, hitap_satirlari


def analiz_verisi(ogeler, en_fazla_karakter=25, ornek_sayisi=8, en_fazla_cift=40):
    """Karakter analizi isteği için örnek replikler ve konuşma çiftleri hazırlar.

    ogeler: oyundaki sırayla [{"m": metin, "k": konuşan}, ...]
    """
    sayac = collections.Counter(o.get("k") for o in ogeler if o.get("k") and o.get("k") != "extend")
    secilen = [ad for ad, _n in sayac.most_common(en_fazla_karakter)]
    secilen_kume = set(secilen)

    replikler = collections.defaultdict(list)
    for o in ogeler:
        k = o.get("k")
        if k in secilen_kume:
            replikler[k].append(o.get("m", ""))

    karakterler = []
    for ad in secilen:
        liste = [r for r in replikler[ad] if len(r) > 12] or replikler[ad]
        if len(liste) > ornek_sayisi:
            adim = len(liste) / float(ornek_sayisi)
            liste = [liste[int(i * adim)] for i in range(ornek_sayisi)]
        karakterler.append({"ad": ad, "replik_sayisi": sayac[ad], "ornekler": [r[:200] for r in liste]})

    ciftler = collections.Counter()
    ornek_ciftler = {}
    onceki = None
    for o in ogeler:
        k = o.get("k")
        if k == "extend":
            continue
        if onceki and k and k != onceki.get("k") and onceki.get("k") in secilen_kume and k in secilen_kume:
            anahtar = (onceki["k"], k)
            ciftler[anahtar] += 1
            ornek_ciftler.setdefault(anahtar, [])
            if len(ornek_ciftler[anahtar]) < 2:
                ornek_ciftler[anahtar].append([onceki.get("m", "")[:160], o.get("m", "")[:160]])
        onceki = o if k else None

    cift_listesi = []
    for (a, b), _n in ciftler.most_common(en_fazla_cift):
        cift_listesi.append({"konusan": a, "dinleyen": b, "ornek_konusmalar": ornek_ciftler[(a, b)]})
    return {"karakterler": karakterler, "ciftler": cift_listesi}
