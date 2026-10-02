"""Oyuna özel sözlük: karakter adları, unvanlar ve sık geçen terimler.

Sözlük, proje klasöründe "sozluk.txt" olarak saklanır ve elle düzenlenebilir:
    Kaynak = Türkçe karşılık (kadın)
"""

import collections
import re

_SATIR_RE = re.compile(r"^(.+?)\s*=\s*(.*?)\s*(?:\((kadın|erkek|belirsiz)\))?\s*$")

# Cümle içinde büyük harfle başlasa da terim sayılmayacak yaygın kelimeler.
_YAYGIN = set("""
I I'm I've I'll I'd Im Ive OK Okay Oh Ah Eh Uh Um Hmm Huh Yes No Yeah Yep Nope Hey Hi Hello Bye Well
So But And Or If Then When What Why How Who Where Which That This These Those The A An It Its It's
He She We They You Your My Mine Our His Her Their Me Us Them Mr Mrs Ms Dr Miss Sir Madam
Monday Tuesday Wednesday Thursday Friday Saturday Sunday
January February March April May June July August September October November December
God Gosh Wow Damn Shit Fuck Please Thanks Thank Sorry Wait Look Come Go Let Let's Just Maybe
Not Now Here There Today Tomorrow Yesterday Good Great Nice Fine Sure Really Right Wrong
""".split())

_KELIME_RE = re.compile(r"\b[A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){0,2}\b")
_ETIKET_RE = re.compile(r"\{[^{}]*\}|\[[^\[\]]*\]")


class Sozluk(object):

    def __init__(self):
        self.girdiler = collections.OrderedDict()   # kaynak -> (türkçe, cinsiyet)

    def ekle(self, kaynak, turkce, cinsiyet=None):
        kaynak = (kaynak or "").strip()
        turkce = (turkce or "").strip()
        if not kaynak or not turkce or "\n" in kaynak or "\n" in turkce:
            return
        if cinsiyet not in ("kadın", "erkek"):
            cinsiyet = None
        self.girdiler[kaynak] = (turkce, cinsiyet)

    def karsilik(self, kaynak):
        g = self.girdiler.get(kaynak)
        return g[0] if g else None

    def cinsiyet(self, kaynak):
        g = self.girdiler.get(kaynak)
        return g[1] if g else None

    def __len__(self):
        return len(self.girdiler)

    def yaz(self, yol):
        with open(yol, "w", encoding="utf-8") as f:
            f.write("# OYUN SÖZLÜĞÜ\n")
            f.write("# Biçim:  Kaynak = Türkçe karşılık   (isteğe bağlı sonuna: (kadın) / (erkek))\n")
            f.write("# Çevirilerde buradaki karşılıklar tutarlı biçimde kullanılır.\n")
            f.write("# Değiştirebilir, yeni satır ekleyebilir veya satır silebilirsiniz.\n")
            f.write("# Kişi adları genelde aynen kalır; unvanlar (Mom, Teacher...) Türkçeleşir.\n\n")
            for kaynak, (turkce, cinsiyet) in self.girdiler.items():
                satir = "%s = %s" % (kaynak, turkce)
                if cinsiyet:
                    satir += " (%s)" % cinsiyet
                f.write(satir + "\n")

    @classmethod
    def oku(cls, yol):
        s = cls()
        try:
            with open(yol, "r", encoding="utf-8-sig") as f:
                for satir in f:
                    satir = satir.rstrip("\n")
                    if not satir.strip() or satir.lstrip().startswith("#"):
                        continue
                    m = _SATIR_RE.match(satir.strip())
                    if m:
                        s.ekle(m.group(1), m.group(2), m.group(3))
        except FileNotFoundError:
            pass
        return s

    def tum_satirlar(self, en_fazla=150):
        """Bütün girdiler 'Kaynak → Türkçe (cinsiyet)' satırları olarak (en fazla en_fazla)."""
        satirlar = []
        for kaynak, (turkce, cinsiyet) in self.girdiler.items():
            if len(satirlar) >= en_fazla:
                break
            satirlar.append("%s → %s%s" % (kaynak, turkce, (" (%s)" % cinsiyet) if cinsiyet else ""))
        return satirlar

    def ilgili_satirlar(self, metinler, en_fazla=80):
        """Verilen metinlerde geçen sözlük girdilerini 'Kaynak → Türkçe' satırları olarak döndürür."""
        birlesik = "\n".join(metinler)
        kucuk = birlesik.lower()
        satirlar = []
        for kaynak, (turkce, _c) in self.girdiler.items():
            if len(satirlar) >= en_fazla:
                break
            k = kaynak.lower()
            if k not in kucuk:
                continue
            # Tam kelime eşleşmesi (kısa terimlerde yanlış eşleşmeyi önle)
            if re.search(r"(?<![\w])" + re.escape(k) + r"(?![\w])", kucuk):
                satirlar.append("%s → %s" % (kaynak, turkce))
        return satirlar


def terim_adaylari(diyaloglar, en_fazla=60, en_az_tekrar=3):
    """Diyaloglarda sık geçen, cümle ortasında büyük harfle başlayan terimleri bulur."""
    sayac = collections.Counter()
    ornek = {}
    for metin in diyaloglar:
        temiz = _ETIKET_RE.sub(" ", metin)
        for m in _KELIME_RE.finditer(temiz):
            kelimeler = m.group(0).split()
            onceki = temiz[:m.start()].rstrip()
            # Cümle başındaki kelime büyük harfle başlar; terim sayılmaz
            # ("Then Lucy left" -> "Lucy").
            if not onceki or onceki[-1] in ".!?\"“”…:-—(":
                kelimeler = kelimeler[1:]
            while kelimeler and kelimeler[0].strip("'-") in _YAYGIN:
                kelimeler = kelimeler[1:]
            if not kelimeler:
                continue
            terim = re.sub(r"'s$", "", " ".join(kelimeler).strip("'-"))
            if terim in _YAYGIN or len(terim) < 2:
                continue
            sayac[terim] += 1
            if terim not in ornek:
                ornek[terim] = metin[:160]
    adaylar = [(t, n) for t, n in sayac.most_common() if n >= en_az_tekrar]
    return [(t, ornek[t]) for t, _ in adaylar[:en_fazla]]
