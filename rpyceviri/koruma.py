"""Ren'Py metinlerindeki özel parçaların korunması ve çevirinin doğrulanması.

Ren'Py metinlerinde şunlar bulunur ve çeviride AYNEN kalmalıdır:
  [isim], [mc!t]       -> değişken (interpolasyon). Yanlışı oyunu çökertir.
  [[  {{               -> köşeli/süslü parantezin kendisi (kaçış).
  {i} {/i} {w=0.5} ... -> metin etiketleri. Bilinmeyen etiket oyunu çökertir.
  %s %(ad)s %%         -> eski tip Python biçimlendirme.

Bu modül, yapay zekadan gelen çeviriyi kaynakla karşılaştırır; oyunu bozabilecek
her durumu tespit eder ve güvenle düzeltilebilecek olanları düzeltir.
"""

import collections
import re

from . import ekler

_TOKEN_RE = re.compile(
    r"\{\{"                      # {{  (kaçış)
    r"|\{[^{}]*\}"               # {etiket}
    r"|\[\["                     # [[  (kaçış)
    r"|\[[^\[\]]*\]"             # [degisken]
    r"|%%"                       # %%
    r"|%\([A-Za-z_][A-Za-z0-9_]*\)[-#0+]*\d*(?:\.\d+)?[sdifrxXeEgGc]"  # %(ad)s
    r"|%[sdifr](?![A-Za-z])"     # %s %d
)

_HARF_RE = re.compile(r"[^\W\d_]", re.UNICODE)
_LATIN_KELIME_RE = re.compile(r"[A-Za-z]{3,}")

# Kapanışı olmayan (tek başına kullanılan) Ren'Py metin etiketleri.
_TEKIL_ETIKETLER = {
    "w", "p", "nw", "fast", "done", "clear", "vspace", "space", "image", "#",
    "alt", "noalt", "shader", "art", "lb", "ek",
}

_TIRNAK_CIFTLERI = [('"', '"'), ("“", "”"), ("„", "“"), ("«", "»"), ("'", "'"), ("‘", "’"), ("「", "」"), ("『", "』")]

_INGILIZCE = set("the and you is are to of it that what this with have for not be was were your i'm don't can't it's will would there they".split())
_TR_HARF_RE = re.compile("[çğıöşüÇĞİÖŞÜ]")

_ONEKLER = re.compile(r"^\s*(?:çeviri|türkçe|turkish|translation|tr)\s*[:：]\s*", re.IGNORECASE)


def parcalar(metin):
    """Metindeki korunan parçaları sırasıyla döndürür."""
    return _TOKEN_RE.findall(metin or "")


# Kaçış çiftleri ekranda sadece '[' / '{' / '%' gösterir; eksik/fazla olmaları oyunu
# bozmaz. Bu yüzden karşılaştırmaya katılmazlar.
_KACISLAR = ("[[", "{{", "%%")


def _sayac(metin):
    return collections.Counter(p for p in parcalar(metin) if p not in _KACISLAR)


def duz_metin(metin):
    """Korunan parçalar çıkarılmış düz metin."""
    return _TOKEN_RE.sub(" ", metin or "")


def cevrilecek_mi(metin):
    """Metinde çevrilecek doğal dil var mı? (sadece etiket/sayı/sembol ise hayır)"""
    if not metin or not metin.strip():
        return False
    duz = duz_metin(metin)
    harfler = _HARF_RE.findall(duz)
    if not harfler:
        return False
    # Tek harf (ör. "A", "Q" kısayolları) çevrilmez.
    if len(harfler) == 1 and len(duz.strip()) <= 2:
        return False
    return True


def _etiket_adi(token):
    """'{color=#fff}' -> ('color', False) ; '{/color}' -> ('color', True)"""
    ic = token[1:-1].strip()
    kapanis = ic.startswith("/")
    if kapanis:
        ic = ic[1:]
    if ic.startswith("#"):
        return "#", kapanis
    ad = re.split(r"[=\s:]", ic, 1)[0].lower()
    return ad, kapanis


def _etiket_dizilimi_dogru_mu(metin):
    """Açılış/kapanış etiketleri düzgün iç içe mi?"""
    yigin = []
    for t in parcalar(metin):
        if not t.startswith("{") or t == "{{":
            continue
        ad, kapanis = _etiket_adi(t)
        if not ad:
            continue
        if kapanis:
            if not yigin or yigin[-1] != ad:
                return False
            yigin.pop()
        elif ad not in _TEKIL_ETIKETLER:
            yigin.append(ad)
    # Kapatılmamış etiketler Ren'Py'da sorun çıkarmaz (satır sonunda kapanır) ama
    # kaynakla karşılaştırma ayrıca yapılır.
    return True


def _serbest_ozel_karakterleri_kacir(metin):
    """Korunan parçaların dışında kalan tek '[' ve '{' karakterlerini kaçışlar.

    Tek bir '[' veya '{' Ren'Py'da oyunu çökertir; '[[' / '{{' ise ekranda
    '[' / '{' olarak görünür.
    """
    sonuc = []
    konum = 0
    for m in _TOKEN_RE.finditer(metin):
        ara = metin[konum:m.start()]
        sonuc.append(ara.replace("[", "[[").replace("{", "{{"))
        sonuc.append(m.group(0))
        konum = m.end()
    ara = metin[konum:]
    sonuc.append(ara.replace("[", "[[").replace("{", "{{"))
    return "".join(sonuc)


def _disarida_uygula(metin, fonk):
    """fonk'u sadece korunan parçaların DIŞINDAKİ metne uygular."""
    sonuc = []
    konum = 0
    for m in _TOKEN_RE.finditer(metin):
        sonuc.append(fonk(metin[konum:m.start()]))
        sonuc.append(m.group(0))
        konum = m.end()
    sonuc.append(fonk(metin[konum:]))
    return "".join(sonuc)


def turkce_buyuk(s):
    """Türkçe kurallarıyla büyük harf: i -> İ, ı -> I (Python'un upper() i'yi I yapar)."""
    return s.replace("i", "İ").replace("ı", "I").upper()


def turkce_kucuk(s):
    return s.replace("I", "ı").replace("İ", "i").lower()


def tamami_buyuk_mu(metin):
    harfler = _HARF_RE.findall(duz_metin(metin))
    return len(harfler) >= 3 and all(not h.islower() for h in harfler)


_OZEL_KARAKTERLER = (
    ("…", "..."), ("“", '"'), ("”", '"'), ("„", '"'), ("«", '"'), ("»", '"'),
    ("‘", "'"), ("’", "'"), ("\u00a0", " "),
)


def _karakterleri_normallestir(kaynak, ceviri):
    """Kaynakta olmayan … “ ” ‘ ’ gibi karakterleri düz karşılıklarına çevirir.

    Oyunun fontunda bu karakterler olmayabilir ve kutu (□) olarak görünür.
    """
    for ozel, duz in _OZEL_KARAKTERLER:
        if ozel in ceviri and ozel not in kaynak:
            ceviri = ceviri.replace(ozel, duz)
    return ceviri


def _ek_normallestir(metin):
    """Geçerli ek işaretlerini standart biçime getirir: [ad]'{ek=in} -> [ad]{ek=in}, soru eki: [ad] {ek=mi}."""
    def degistir(m):
        token, _kesme, _bosluk, varyant = m.groups()
        if not ekler.gecerli_varyant(varyant):
            return m.group(0)
        if ekler.EK_TURLERI.get("mi") and varyant in ekler.EK_TURLERI["mi"]:
            return token + " {ek=" + varyant + "}"
        return token + "{ek=" + varyant + "}"
    return ekler.ISARET_RE.sub(degistir, metin)


def _ek_isaretsiz(metin):
    """Karşılaştırma için geçerli ek işaretlerini çıkarır (değişken parçası kalır)."""
    def degistir(m):
        if ekler.gecerli_varyant(m.group(4)):
            return m.group(1)
        return m.group(0)
    return ekler.ISARET_RE.sub(degistir, metin)


def _bosluklari_esle(kaynak, ceviri):
    bas = re.match(r"^\s*", kaynak).group(0)
    son = re.search(r"\s*$", kaynak).group(0)
    govde = ceviri.strip()
    if not kaynak.strip():
        return kaynak
    return bas + govde + son


def _tirnaklari_temizle(kaynak, ceviri):
    k = kaynak.strip()
    c = ceviri.strip()
    for ac, kapa in _TIRNAK_CIFTLERI:
        if len(c) >= 2 and c.startswith(ac) and c.endswith(kapa) and not (k.startswith(ac) and k.endswith(kapa)):
            # İçeride aynı tırnaktan yoksa (tek parça alıntıysa) soy.
            ic = c[len(ac):-len(kapa)]
            if ac not in ic and kapa not in ic:
                return ic
    return ceviri


def dogrula(kaynak, ceviri):
    """Çeviriyi kontrol eder ve güvenli düzeltmeleri uygular.

    Döndürür: (duzeltilmis_ceviri, ciddi_sorunlar, supheler)
      ciddi_sorunlar: boş değilse çeviri KULLANILAMAZ (oyunu bozabilir/boş).
      supheler: kullanılabilir ama bir kez daha denemeye değer.
    """
    ciddi = []
    suphe = []

    if not isinstance(ceviri, str):
        return ceviri, ["çeviri metin değil"], suphe

    c = ceviri.replace("\r\n", "\n").replace("\r", "\n")

    # Yapay zekanın eklediği "Çeviri:" gibi önekleri temizle.
    if not _ONEKLER.match(kaynak):
        c = _ONEKLER.sub("", c, count=1)

    c = _tirnaklari_temizle(kaynak, c)
    c = _bosluklari_esle(kaynak, c)

    if kaynak.strip() and not c.strip():
        return c, ["boş çeviri"], suphe

    # Kaynakta olmayan tek '[' / '{' karakterlerini kaçışla.
    c = _serbest_ozel_karakterleri_kacir(c)
    c = _karakterleri_normallestir(kaynak, c)

    # Bağıran (tamamı büyük harf) satırlar Türkçe kurallarla büyük harf olsun.
    if tamami_buyuk_mu(kaynak) and not tamami_buyuk_mu(c):
        c = _disarida_uygula(c, turkce_buyuk)

    # Ek işaretleri ([ad]{ek=in}) sadece değişkenden hemen sonra ve geçerli ekle olabilir.
    c = _ek_normallestir(c)
    for v in ekler.HAM_ISARET_RE.findall(c):
        if not ekler.gecerli_varyant(v):
            ciddi.append("geçersiz ek işareti {ek=%s}" % v)
    if "{ek=" in _ek_isaretsiz(c) and not any("geçersiz ek" in x for x in ciddi):
        ciddi.append("ek işareti sadece [değişken] parçasından hemen sonra kullanılabilir")

    ks = _sayac(kaynak)
    cs = _sayac(_ek_isaretsiz(c))

    if ks != cs:
        eksik = ks - cs
        fazla = cs - ks
        parca = []
        if eksik:
            parca.append("eksik: " + ", ".join(sorted(eksik.elements())))
        if fazla:
            parca.append("fazladan: " + ", ".join(sorted(fazla.elements())))
        ciddi.append("korunan parçalar uyuşmuyor (" + "; ".join(parca) + ")")

    if _etiket_dizilimi_dogru_mu(kaynak) and not _etiket_dizilimi_dogru_mu(c):
        ciddi.append("metin etiketlerinin açılış/kapanış sırası bozuk")

    kl = len(duz_metin(kaynak).strip())
    cl = len(duz_metin(c).strip())
    if kl >= 1 and cl > kl * 3.5 + 40:
        suphe.append("çeviri kaynaktan çok uzun (açıklama eklenmiş olabilir)")
    if kl >= 40 and cl < kl * 0.25:
        suphe.append("çeviri kaynaktan çok kısa (eksik çevrilmiş olabilir)")

    if c.strip() == kaynak.strip() and len(_LATIN_KELIME_RE.findall(duz_metin(kaynak))) >= 3:
        suphe.append("çevrilmeden aynen bırakılmış")
    else:
        kelimeler = re.findall(r"[A-Za-z']+", duz_metin(c).lower())
        if len(kelimeler) >= 5 and not _TR_HARF_RE.search(c):
            ingilizce = sum(1 for k in kelimeler if k in _INGILIZCE)
            if ingilizce >= 3 and ingilizce >= len(kelimeler) * 0.2:
                suphe.append("çeviri hâlâ İngilizce görünüyor")

    return c, ciddi, suphe


# ---------------------------------------------------------------------------
# Maskeleme: ikinci deneme stratejisi. Korunan parçalar <t0>, <t1>... ile
# değiştirilir; yapay zeka bunları sadece yerinde tutar.
# ---------------------------------------------------------------------------

_MASKE_RE = re.compile(r"<t(\d+)>")


def maskele(metin):
    harita = []

    def degistir(m):
        harita.append(m.group(0))
        return "<t%d>" % (len(harita) - 1)

    maskeli = _TOKEN_RE.sub(degistir, metin)
    return maskeli, harita


def maske_kaldir(maskeli, harita):
    """<tN> belirteçlerini geri koyar. Belirteçler eksik/fazla ise None döner."""
    gorulen = collections.Counter(int(x) for x in _MASKE_RE.findall(maskeli))
    beklenen = collections.Counter(range(len(harita)))
    if gorulen != beklenen:
        return None
    # Maske dışında kalan özel karakterleri önce kaçışla, sonra belirteçleri koy.
    # Belirteçten hemen sonra gelen geçerli ek işareti ({ek=in}) korunur.
    parcalar_ = _MASKE_RE.split(maskeli)
    sonuc = []
    for i, p in enumerate(parcalar_):
        if i % 2 == 0:
            on = ""
            if i > 0:
                m = _MASKE_EK_RE.match(p)
                if m and ekler.gecerli_varyant(m.group(3)):
                    on, p = m.group(0), p[m.end():]
            sonuc.append(on + p.replace("[", "[[").replace("{", "{{"))
        else:
            sonuc.append(harita[int(p)])
    return "".join(sonuc)


_MASKE_EK_RE = re.compile(r"^('?)( ?)\{ek=([a-zçğıöşü]+)\}")
