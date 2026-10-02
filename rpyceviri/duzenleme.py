"""Çevirilerin elle düzenlenmesi.

Bütün çeviriler oyundaki sırayla, Not Defteri'nde kolayca düzenlenebilecek bir
metin dosyasına yazılır:

    [12] Sylvie
    EN: Hi there! How was class?
    TR: Selam! Ders nasıldı?

Kullanıcı sadece "TR:" satırlarını değiştirir. Dosya geri okunduğunda değişen
satırlar doğrulanır ve "elle düzeltildi" olarak kaydedilir: hiçbir otomatik
işlem bunların üzerine yazmaz, ayrıca sonraki çevirilerde üslup örneği olarak
yapay zekaya gösterilir.
"""

import json
import os
import re

from . import koruma
from . import proje as proje_mod

BASLIK = """# ÇEVİRİ DÜZENLEME DOSYASI - {oyun}
#
# NASIL KULLANILIR:
#  - Sadece "TR:" ile başlayan satırları değiştirin.
#  - "EN:" satırlarına ve [numara] satırlarına DOKUNMAYIN (eşleştirme bunlarla yapılır).
#  - [isim] gibi köşeli parantezli ve {{i}} gibi süslü parantezli parçaları AYNEN bırakın.
#  - Satır içi alt satıra geçiş "\\n" olarak yazılmıştır; öyle bırakın.
#  - Boş "TR:" satırı = henüz çevrilmemiş. Doldurursanız o çeviri kullanılır.
#  - Aramak için Ctrl+F kullanın. Bitince kaydedip (Ctrl+S) programa dönün.
#
# Durum işaretleri: (elle) = sizin düzelttiğiniz, (çevrilmedi) = henüz çevrilemeyen.

"""

_BLOK_RE = re.compile(r"^\[(\d+)\]")


def _kacisla(metin):
    return metin.replace("\\", "\\\\").replace("\n", "\\n")


def _kacisi_coz(metin):
    sonuc = []
    i = 0
    while i < len(metin):
        h = metin[i]
        if h == "\\" and i + 1 < len(metin):
            s = metin[i + 1]
            if s == "n":
                sonuc.append("\n")
                i += 2
                continue
            if s == "\\":
                sonuc.append("\\")
                i += 2
                continue
        sonuc.append(h)
        i += 1
    return "".join(sonuc)


def _ozgun_yolu(proje):
    return proje.duzenleme_yolu + ".ozgun.json"


def _ozgun_oku(proje):
    """Dosya yazılırken TR satırlarında olan metinler: {kaynak: çeviri}."""
    try:
        with open(_ozgun_yolu(proje), "r", encoding="utf-8") as f:
            veri = json.load(f)
        return veri if isinstance(veri, dict) else None
    except (OSError, ValueError):
        return None


def _ozgun_yaz(proje, ozgun):
    yol = _ozgun_yolu(proje)
    with open(yol + ".tmp", "w", encoding="utf-8") as f:
        json.dump(ozgun, f, ensure_ascii=False)
    os.replace(yol + ".tmp", yol)


def degismis_mi(proje):
    """Düzenleme dosyası, en son yazıldığından/okunduğundan beri kaydedilmiş mi?"""
    try:
        return os.path.getmtime(proje.duzenleme_yolu) > os.path.getmtime(_ozgun_yolu(proje)) + 1
    except OSError:
        return False


def disari_aktar(proje, ogeler, oyun_adi):
    """ogeler: (kaynak, konuşan, tür) listesi, oyundaki sırayla. Döndürür: yazılan blok sayısı."""
    satirlar = [BASLIK.format(oyun=oyun_adi)]
    gorulen = set()
    ozgun = {}
    n = 0
    for kaynak, konusan, tur in ogeler:
        if kaynak in gorulen or not koruma.cevrilecek_mi(kaynak):
            continue
        gorulen.add(kaynak)
        n += 1
        kayit = proje.kayit_al(kaynak) or {}
        ceviri = proje.ceviri_al(kaynak) or ""
        etiket = konusan or ("(seçenek)" if tur == "secenek" else ("(arayüz)" if tur in ("arayuz", "isim", "python") else "(anlatıcı)"))
        durum = ""
        if kayit.get("d") == proje_mod.ELLE:
            durum = "  (elle)"
        elif not ceviri:
            durum = "  (çevrilmedi)"
        satirlar.append("[%d] %s%s\n" % (n, etiket, durum))
        satirlar.append("EN: %s\n" % _kacisla(kaynak))
        satirlar.append("TR: %s\n\n" % _kacisla(ceviri))
        ozgun[kaynak] = ceviri
    with open(proje.duzenleme_yolu, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write("".join(satirlar))
    _ozgun_yaz(proje, ozgun)
    return n


def iceri_al(proje, gecerli_kaynaklar=None):
    """Düzenleme dosyasını okur, değişen çevirileri kaydeder.

    Bir satır, dosya yazıldığındaki halinden farklıysa "kullanıcı değiştirdi" sayılır;
    böylece dosya yazıldıktan sonra programın yaptığı iyileştirmeler, dosyadaki eski
    metinle ezilmez.

    Döndürür: (değişen_sayısı, hatalar[list of str], degisen_ciftler[list of (kaynak, çeviri)])
    """
    try:
        with open(proje.duzenleme_yolu, "r", encoding="utf-8-sig") as f:
            satirlar = f.read().splitlines()
    except FileNotFoundError:
        return 0, ["Düzenleme dosyası bulunamadı."], []

    ozgun = _ozgun_oku(proje)
    degisen = 0
    hatalar = []
    ciftler = []
    numara = None
    kaynak = None
    for satir_no, satir in enumerate(satirlar, 1):
        if satir.startswith("#"):
            continue
        m = _BLOK_RE.match(satir)
        if m:
            numara = m.group(1)
            kaynak = None
            continue
        if satir.startswith("EN:"):
            kaynak = _kacisi_coz(satir[4:] if satir[3:4] == " " else satir[3:])
            continue
        if satir.startswith("TR:") and kaynak is not None:
            yeni = _kacisi_coz(satir[4:] if satir[3:4] == " " else satir[3:])
            k = kaynak
            kaynak = None
            if gecerli_kaynaklar is not None and k not in gecerli_kaynaklar:
                hatalar.append("[%s] (satır %d): EN satırı değiştirilmiş ya da oyunda yok; atlandı." % (numara, satir_no))
                continue
            eski = proje.ceviri_al(k) or ""
            if yeni == eski or not yeni.strip():
                continue
            if ozgun is not None and k in ozgun and yeni == ozgun[k]:
                continue
            c, ciddi, _s = koruma.dogrula(k, yeni)
            if ciddi:
                hatalar.append("[%s] (satır %d): %s -> bu düzeltme kaydedilmedi." % (numara, satir_no, "; ".join(ciddi)))
                continue
            proje.ceviri_kaydet(k, c, proje_mod.ELLE, model="elle", zorla=True)
            ciftler.append((k, c))
            degisen += 1
            if ozgun is not None:
                ozgun[k] = yeni
    proje.kaydet()
    if ozgun is not None:
        try:
            _ozgun_yaz(proje, ozgun)
        except OSError:
            pass
    return degisen, hatalar, ciftler
