"""Türkçe "çeviri kokusu" dedektörü (yapay zeka kullanmaz).

İngilizceden çevrilmiş metinlerde sık görülen ve Türkçeyi yapay gösteren
kalıpları kural tabanlı olarak işaretler. İşaretlenen satırlar, kalite modu
"dengeli" ise ikinci bir "Türk editör" geçişinden geçirilir.

Kurallar bilerek temkinlidir: amaç her satırı yargılamak değil, büyük olasılıkla
düzeltilmesi gereken satırları bulmaktır.
"""

import re

from . import koruma

_KELIME_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

# Türkçede fiil eki kişiyi zaten gösterdiği için çoğu zaman gereksiz olan zamirler.
_ATILABILIR_ZAMIRLER = {"ben", "sen", "biz", "siz", "onlar", "benim", "senin", "bizim", "sizin"}

_KITABI_MEKTE = re.compile(
    r"\w+(?:makta|mekte)(?:yım|yim|sın|sin|dır|dir|yız|yiz|sınız|siniz|lar|ler)\b", re.UNICODE)

_DIR_SON = re.compile(r"(\w{4,}(?:dır|dir|dur|dür|tır|tir|tur|tür))\s*[.!?…]*\s*$", re.UNICODE)
# -dır ile biten ama ek fiil olmayan sık kelimeler (emir kipi, isim vb.)
_DIR_ISTISNA = {
    "kaldır", "yaptır", "aldır", "bıktır", "sıktır", "getir", "götür", "bitir", "yetir", "kudur",
    "ezdir", "öldür", "güldür", "yüzdür", "durdur", "kandır", "kızdır", "korkut", "çaldır", "yedir",
    "içir", "giydir", "sevindir", "üzdür", "bildir", "indir", "gönder", "kader", "kadir", "ekmeğimdir",
}

# İngilizceden birebir aktarılmış, Türkçede doğal durmayan ifadeler -> daha doğal öneri
CEVIRI_KALIPLARI = [
    ("ne cehennem", "Ne halt / Ne oluyor be"),
    ("kutsal bok", "Vay anasını / Hassiktir"),
    ("iyi iş", "Aferin / Eline sağlık"),
    ("harika iş", "Harikasın / Eline sağlık"),
    ("bir anlam ifade et", "mantıklı / bir şey ifade etmek"),
    ("sahip olduğum", "'var' ile kur (Benim ... var)"),
    ("sahip olduğun", "'var' ile kur"),
    ("sahip misin", "'var mı' ile kur"),
    ("sahibim", "'var' ile kur"),
    ("adamım", "dostum / kanka / abi"),
    ("oh tanrım", "Aman Tanrım / Allah'ım"),
    ("senin için mutluyum", "Senin adına sevindim"),
    ("seni görmek güzel", "Seni gördüğüme sevindim"),
    ("harika bir gün geçir", "İyi günler / Kendine iyi bak"),
    ("iyi bir gün geçir", "İyi günler"),
]

_INGILIZCE_KALINTI = {"the", "and", "you", "what", "this", "that", "are", "your", "yes", "okay",
                      "please", "sorry", "hello", "just", "really", "with", "about"}

_KONUSMA_TURLERI = ("diyalog", "secenek", "menu_basligi")

# Bu uzunluğu ve kaynağın bu katını aşan satır, metin kutusundan taşabilir.
TASMA_KARAKTER = 180
TASMA_ORAN = 1.45


def koku(kaynak, ceviri, tur="diyalog", konusan=""):
    """Çevirideki doğallık sorunlarını puanlar.

    Döndürür: (puan, nedenler). puan >= 2 ise satırın editörden geçmesi önerilir.
    """
    if not isinstance(ceviri, str) or tur not in _KONUSMA_TURLERI:
        return 0, []

    duz = koruma.duz_metin(ceviri)
    kucuk = koruma.turkce_kucuk(duz)
    kelimeler = _KELIME_RE.findall(kucuk)
    if not kelimeler:
        return 0, []

    puan = 0
    nedenler = []
    konusma = bool(konusan) or tur == "secenek"

    zamir = sum(1 for k in kelimeler if k in _ATILABILIR_ZAMIRLER)
    if zamir >= 3 or (zamir >= 2 and len(kelimeler) <= 14):
        puan += 2
        nedenler.append("gereksiz zamir kullanımı (%d)" % zamir)

    kaynak_duz = koruma.duz_metin(kaynak).strip().lower()
    if konusma and re.match(r"^(i|you|we)\b", kaynak_duz) and re.match(r"^(ben|sen|biz|siz)\b", kucuk.strip()):
        puan += 1
        nedenler.append("cümle başında İngilizceden kalma zamir")

    if _KITABI_MEKTE.search(kucuk):
        puan += 2 if konusma else 1
        nedenler.append("kitabi '-mekte' kalıbı")

    if konusma:
        for cumle in re.split(r"(?<=[.!?…])\s+", kucuk):
            m = _DIR_SON.search(cumle)
            if m and m.group(1) not in _DIR_ISTISNA and len(m.group(1)) >= 7:
                puan += 1
                nedenler.append("konuşmada resmî '-dır' eki (%s)" % m.group(1))
                break

    for kalip, oneri in CEVIRI_KALIPLARI:
        if kalip in kucuk:
            puan += 2
            nedenler.append("birebir çeviri kalıbı: '%s'%s" % (kalip, (" (öneri: %s)" % oneri) if oneri else ""))
            break

    if sum(1 for k in kelimeler if k == "bu") >= 3:
        puan += 1
        nedenler.append("'bu' kelimesi çok tekrarlanmış")

    kalinti = [k for k in kelimeler if k in _INGILIZCE_KALINTI]
    if kalinti:
        puan += 2
        nedenler.append("İngilizce kelime kalmış: " + ", ".join(sorted(set(kalinti))))

    kl = len(koruma.duz_metin(kaynak).strip())
    cl = len(duz.strip())
    if kl and cl > TASMA_KARAKTER and cl > kl * TASMA_ORAN:
        puan += 2
        nedenler.append("oyunun metin kutusuna sığmayabilir: anlamı koruyarak kısalt")
    elif kl and cl > 60 and cl > kl * 1.7:
        puan += 1
        nedenler.append("çeviri kaynağa göre çok uzun")

    return puan, nedenler


def isaretli_mi(kaynak, ceviri, tur="diyalog", konusan="", esik=2):
    puan, _ = koku(kaynak, ceviri, tur, konusan)
    return puan >= esik


def tasma_riski(kaynak, ceviri):
    """Çeviri, kaynağa göre metin kutusundan taşacak kadar uzamış mı?"""
    kl = len(koruma.duz_metin(kaynak).strip())
    cl = len(koruma.duz_metin(ceviri).strip())
    return bool(kl) and cl > TASMA_KARAKTER and cl > kl * TASMA_ORAN
