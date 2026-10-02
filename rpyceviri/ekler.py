# -*- coding: utf-8 -*-
# Turkce ek uyumu (unlu/unsuz uyumu) motoru.
#
# Oyunlarda oyuncunun adi gibi degiskenler ([name]) ceviri sirasinda bilinmez;
# bu yuzden yapay zeka ekleri isaretli yazar:  [name]{ek=in}  ->  oyunda "Ali'nin",
# "Elif'in", "Sylvie'nin" olur.
#
# BU DOSYA IKI YERDE KULLANILIR:
#   1) Ceviri programinda (Python 3)                -> dogrulama ve testler
#   2) Oyunun icindeki Turkce yamada (Python 2 / 3) -> yamaya aynen gomulur
# Bu yuzden: Python 2.7 ile uyumlu sozdizimi, ek paket yok; Turkce harfler
# sadece u"..." dizgelerinde bulunur (Ren'Py .rpy dosyalarini UTF-8 okur).

import re as _ek_re

_EK_UNLULER = u"aeıioöuü"          # a e i(noktasiz) i o o u u
_EK_INCE = u"eiöü"                       # e i o u (ince)
_EK_YUVARLAK = u"ouöü"                   # o u o u (yuvarlak)
_EK_SERT = u"fstkçşhp"                   # f s t k c s h p (sert unsuzler)
_EK_TR_OZEL = u"çğıöşüÇĞİÖŞÜ"

# Ek turu -> kabul edilen yazilislar (ilki yedek/varsayilan bicim).
EK_TURLERI = {
    u"in": (u"in", u"ın", u"un", u"ün", u"nin", u"nın", u"nun", u"nün"),    # ilgi: Ali'nin
    u"i": (u"i", u"ı", u"u", u"ü", u"yi", u"yı", u"yu", u"yü"),            # belirtme: Ali'yi
    u"e": (u"e", u"a", u"ye", u"ya"),                                                              # yonelme: Ali'ye
    u"de": (u"de", u"da", u"te", u"ta"),                                                           # bulunma: Ali'de
    u"den": (u"den", u"dan", u"ten", u"tan"),                                                      # ayrilma: Ali'den
    u"le": (u"le", u"la", u"yle", u"yla"),                                                         # ile: Ali'yle
    u"ler": (u"ler", u"lar"),                                                                      # cogul: Ali'ler
    u"dir": (u"dir", u"dır", u"dur", u"dür", u"tir", u"tır", u"tur", u"tür"),  # Ali'dir
    u"mi": (u"mi", u"mı", u"mu", u"mü"),                                                 # soru: Ali mi?
}

_EK_VARYANT = {}
for _ek_tur, _ek_liste in EK_TURLERI.items():
    for _ek_v in _ek_liste:
        _EK_VARYANT[_ek_v] = _ek_tur

# [degisken] + (istege bagli kesme isareti / bosluk) + {ek=...}
ISARET_RE = _ek_re.compile(u"(\\[[^\\[\\]]+\\])('?)( ?)\\{ek=([a-zçğıöşü]+)\\}", _ek_re.UNICODE)
# Herhangi bir {ek=...} (dogrulama icin)
HAM_ISARET_RE = _ek_re.compile(u"\\{ek=([^{}]*)\\}", _ek_re.UNICODE)

# Kullanicinin istisna dosyasindan gelen okunuslar: {"mike": "mayk"}
OZEL_OKUNUS = {}


def _ek_tr(s):
    """Tablodaki ASCII yer tutuculari Turkce harfe cevirir: I=i(noktasiz) S=s C=c O=o U=u G=g."""
    return (s.replace(u"I", u"ı").replace(u"S", u"ş").replace(u"C", u"ç")
            .replace(u"O", u"ö").replace(u"U", u"ü").replace(u"G", u"ğ"))


# Yazilisi ile okunusu farkli olup Turkce eki degistiren yaygin yabanci isimler.
# (sadece eki etkileyen kisim onemlidir; buyuk harf = Turkce harf, bkz. _ek_tr)
_EK_ISIM_TABLOSU = u"""
kate=keyt jane=ceyn grace=greys claire=kler clare=kler rose=roz june=cun jade=ceyd anne=en
brooke=bruk paige=peyc hope=houp skye=skay jasmine=cezmin caroline=kerolayn catherine=ketrin
katherine=ketrin kathryn=ketrin madeline=medlin candace=kendIs joyce=coys alice=alis beatrice=biatris
michelle=miSel nicole=nikol danielle=danyel isabelle=izabel belle=bel eve=iv mae=mey faye=fey
kaye=key elaine=ileyn lorraine=loreyn blaire=bler adele=edel estelle=estel janelle=canel
mike=mayk jake=ceyk luke=luk dave=deyv steve=stiv pete=pit nate=neyt gabe=geyb blake=bleyk
chase=Ceys lance=lens bruce=brus duke=duk cole=kol dale=deyl kyle=kayl lyle=layl vince=vins
joe=co george=corc charles=Carlz jacques=jak sean=Son shawn=Son shane=Seyn wayne=veyn
dwayne=dveyn michael=maykIl rachel=reyCIl karen=kerIn taylor=teylIr louis=lui hugh=hyu
ray=rey jay=cey kay=key guy=gay mason=meysIn jason=ceysIn grayson=greysIn
peter=pitIr oliver=olivIr alexander=aleksandIr christopher=kristofIr walter=voltIr roger=rocIr
hunter=hantIr tyler=taylIr parker=parkIr spencer=spensIr carter=kartIr jasper=cespIr
jennifer=cenifIr heather=hedIr amber=embIr esther=estIr harper=harpIr piper=paypIr
summer=samIr tucker=takIr cooper=kupIr archer=arCIr homer=houmIr chester=CestIr
"""

_EK_YABANCI = {}
for _ek_parca in _EK_ISIM_TABLOSU.split():
    if u"=" in _ek_parca:
        _ek_a, _ek_b = _ek_parca.split(u"=", 1)
        _EK_YABANCI[_ek_a] = _ek_tr(_ek_b)

_EK_RAKAM = {
    0: u"sıfır", 1: u"bir", 2: u"iki", 3: u"üç", 4: u"dört",
    5: u"beş", 6: u"altı", 7: u"yedi", 8: u"sekiz", 9: u"dokuz",
}
_EK_ONLAR = {
    1: u"on", 2: u"yirmi", 3: u"otuz", 4: u"kırk", 5: u"elli",
    6: u"altmış", 7: u"yetmiş", 8: u"seksen", 9: u"doksan",
}
_EK_HARF_ADI = {
    u"a": u"a", u"b": u"be", u"c": u"ce", u"d": u"de", u"e": u"e", u"f": u"fe", u"g": u"ge",
    u"h": u"he", u"i": u"i", u"j": u"je", u"k": u"ke", u"l": u"le", u"m": u"me", u"n": u"ne",
    u"o": u"o", u"p": u"pe", u"q": u"kü", u"r": u"re", u"s": u"se", u"t": u"te", u"u": u"u",
    u"v": u"ve", u"w": u"ve", u"x": u"iks", u"y": u"ye", u"z": u"ze",
}


def _ek_sayi_okunusu(rakamlar):
    try:
        n = int(rakamlar)
    except Exception:
        return None
    if n == 0:
        return _EK_RAKAM[0]
    if n % 10:
        return _EK_RAKAM[n % 10]
    if n % 100:
        return _EK_ONLAR[(n // 10) % 10]
    if n % 1000:
        return u"yüz"
    if n % 1000000:
        return u"bin"
    if n % 1000000000:
        return u"milyon"
    return u"milyar"


def _ek_kucuk(kelime):
    # Turkce harf iceren kelimede I->i(noktasiz), I(noktali)->i; digerlerinde normal kucultme.
    for h in kelime:
        if h in _EK_TR_OZEL:
            return kelime.replace(u"I", u"ı").replace(u"İ", u"i").lower()
    return kelime.lower()


def _ek_ingilizce_okunus(k):
    """Turkce harf icermeyen kelimeler icin kaba okunus tahmini (sadece son hece onemli)."""
    if k in _EK_YABANCI:
        return _EK_YABANCI[k]
    # Kelime sonlari: Sylvie, Mickey, Lucy, Lee, Sue, Andrew, Drew
    if k.endswith(u"ie") or k.endswith(u"ee") or k.endswith(u"ey"):
        k = k[:-2] + u"i"
    elif len(k) > 1 and k.endswith(u"y") and k[-2] not in u"aeiou":
        k = k[:-1] + u"i"
    elif k.endswith(u"ue") or k.endswith(u"ew") or k.endswith(u"oo"):
        k = k[:-2] + u"u"
    for eski, yeni in ((u"th", u"t"), (u"ck", u"k"), (u"sh", u"ş"), (u"ch", u"ç"), (u"ph", u"f"), (u"x", u"ks")):
        k = k.replace(eski, yeni)
    return k


def _ek_okunus(deger):
    """Degiskenin degerinden, ekin bagli oldugu son kelimenin Turkce okunusu."""
    if deger is None:
        return None
    try:
        metin = _ek_re.sub(u"\\{[^{}]*\\}", u"", u"%s" % (deger,))
    except Exception:
        return None
    parcalar = _ek_re.findall(u"[^\\W_]+", metin, _ek_re.UNICODE)
    if not parcalar:
        return None

    # Sayi: "1.000", "3,5" -> son rakam grubu; "10" -> on
    son = parcalar[-1]
    rakamlar = u"".join(h for h in son if h.isdigit())
    if rakamlar and len(rakamlar) == len(son):
        tum = _ek_re.findall(u"[0-9][0-9.,]*$", metin.strip())
        if tum:
            rakamlar = tum[-1].replace(u".", u"").replace(u",", u"")
        return _ek_sayi_okunusu(rakamlar)

    kelime = son
    kk = _ek_kucuk(kelime)
    if kk in OZEL_OKUNUS:
        return OZEL_OKUNUS[kk]

    # Kisaltma (MC, NPC, BBC): son harfin Turkce adi
    if kelime.isupper() and len(kelime) <= 5 and (len(kelime) <= 3 or not any(h in u"AEIOU" for h in kelime)):
        son_harf = kk[-1]
        return _EK_HARF_ADI.get(son_harf, kk)

    if any(h in _EK_TR_OZEL for h in kelime):
        return kk
    return _ek_ingilizce_okunus(kk)


def ek_bul(deger, tur):
    """Degerin okunusuna gore ekin dogru bicimini dondurur (kesme isareti olmadan).

    Belirlenemezse None doner.
    """
    okunus = _ek_okunus(deger)
    if not okunus:
        return None
    unluler = [h for h in okunus if h in _EK_UNLULER]
    if not unluler:
        return None
    son_unlu = unluler[-1]
    son_ses = okunus[-1]
    unluyle_biter = son_ses in _EK_UNLULER
    sert = son_ses in _EK_SERT
    ince = son_unlu in _EK_INCE
    yuvarlak = son_unlu in _EK_YUVARLAK

    if ince:
        I = u"ü" if yuvarlak else u"i"
        A = u"e"
    else:
        I = u"u" if yuvarlak else u"ı"
        A = u"a"
    D = u"t" if sert else u"d"
    y = u"y" if unluyle_biter else u""

    if tur == u"in":
        return (u"n" if unluyle_biter else u"") + I + u"n"
    if tur == u"i":
        return y + I
    if tur == u"e":
        return y + A
    if tur == u"de":
        return D + A
    if tur == u"den":
        return D + A + u"n"
    if tur == u"le":
        return y + u"l" + A
    if tur == u"ler":
        return u"l" + A + u"r"
    if tur == u"dir":
        return D + I + u"r"
    if tur == u"mi":
        return u"m" + I
    return None


def gecerli_varyant(varyant):
    return varyant in _EK_VARYANT


def isaretleri_coz(metin, deger_bul):
    """Metindeki [degisken]{ek=..} isaretlerini degiskenin gercek degerine gore cozer.

    deger_bul(token) -> degiskenin ekrandaki degeri (or. "Elif") ya da None.
    Deger bulunamazsa yapay zekanin yazdigi bicim kullanilir. Degisken parcasi
    ([name]) yerinde kalir; Ren'Py onu daha sonra kendisi doldurur.
    """
    if u"{ek=" not in metin:
        return metin

    def degistir(m):
        token, varyant = m.group(1), m.group(4)
        tur = _EK_VARYANT.get(varyant)
        ek = None
        if tur is not None:
            try:
                ek = ek_bul(deger_bul(token), tur)
            except Exception:
                ek = None
        if ek is None:
            ek = varyant
        if tur == u"mi":
            return token + u" " + ek
        return token + u"'" + ek

    return ISARET_RE.sub(degistir, metin)


def isaretleri_sabitle(metin):
    """Degiskenin degeri bilinmeden isaretleri yapay zekanin yazdigi bicimle sabitler."""
    if u"{ek=" not in metin:
        return metin

    def degistir(m):
        token, varyant = m.group(1), m.group(4)
        if _EK_VARYANT.get(varyant) == u"mi":
            return token + u" " + varyant
        return token + u"'" + varyant

    return ISARET_RE.sub(degistir, metin)
