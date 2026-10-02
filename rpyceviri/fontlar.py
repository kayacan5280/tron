"""Font dosyalarında Türkçe harf (ç ğ ı İ ö ş ü) desteği kontrolü.

TrueType/OpenType 'cmap' tablosu doğrudan okunur; ek kütüphane gerekmez.
"""

import struct

TURKCE_HARFLER = "çÇğĞıİöÖşŞüÜ"


def _cmap_kontrol_fonksiyonu(veri):
    def u16(o):
        return struct.unpack(">H", veri[o:o + 2])[0]

    def u32(o):
        return struct.unpack(">I", veri[o:o + 4])[0]

    bas = 0
    if veri[0:4] == b"ttcf":
        bas = u32(12)

    tablo_sayisi = u16(bas + 4)
    cmap = None
    for i in range(tablo_sayisi):
        kayit = bas + 12 + 16 * i
        if veri[kayit:kayit + 4] == b"cmap":
            cmap = u32(kayit + 8)
            break
    if cmap is None:
        return None

    alt_sayisi = u16(cmap + 2)
    aday12 = None
    aday4 = None
    for i in range(alt_sayisi):
        pid = u16(cmap + 4 + 8 * i)
        eid = u16(cmap + 6 + 8 * i)
        ofs = cmap + u32(cmap + 8 + 8 * i)
        bicim = u16(ofs)
        if not ((pid == 0) or (pid == 3 and eid in (1, 10))):
            continue
        if bicim == 12 and aday12 is None:
            aday12 = ofs
        elif bicim == 4 and aday4 is None:
            aday4 = ofs

    def var12(cp):
        grup = u32(aday12 + 12)
        for g in range(grup):
            o = aday12 + 16 + 12 * g
            if u32(o) <= cp <= u32(o + 4):
                return True
        return False

    def var4(cp):
        ofs = aday4
        segx2 = u16(ofs + 6)
        son_kod = ofs + 14
        bas_kod = son_kod + segx2 + 2
        delta = bas_kod + segx2
        aralik = delta + segx2
        for s in range(segx2 // 2):
            son = u16(son_kod + 2 * s)
            if cp > son:
                continue
            basla = u16(bas_kod + 2 * s)
            if cp < basla:
                return False
            d = u16(delta + 2 * s)
            ro_adr = aralik + 2 * s
            ro = u16(ro_adr)
            if ro == 0:
                glif = (cp + d) & 0xFFFF
            else:
                glif = u16(ro_adr + ro + 2 * (cp - basla))
                if glif:
                    glif = (glif + d) & 0xFFFF
            return glif != 0
        return False

    if aday12 is not None:
        return var12
    if aday4 is not None:
        return var4
    return None


def eksik_harfler(veri):
    """Font verisinde bulunmayan Türkçe harfleri döndürür. Anlaşılamazsa None."""
    try:
        kontrol = _cmap_kontrol_fonksiyonu(veri)
    except Exception:
        return None
    if kontrol is None:
        return None
    try:
        return "".join(h for h in TURKCE_HARFLER if not kontrol(ord(h)))
    except Exception:
        return None


def dosya_eksik_harfler(yol):
    try:
        with open(yol, "rb") as f:
            return eksik_harfler(f.read())
    except Exception:
        return None
