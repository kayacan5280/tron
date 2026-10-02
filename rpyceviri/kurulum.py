"""Türkçe yamanın oyuna kurulması ve kaldırılması.

Oyunun hiçbir dosyası değiştirilmez; sadece şu dosyalar EKLENİR:
  game/zzzz_trceviri_yama.rpy     -> çeviriyi uygulayan küçük Ren'Py betiği
  game/trceviri/ceviri.json       -> çeviriler
  game/trceviri/fontlar/...       -> (isteğe bağlı) yedek font
Kaldırmak için bu dosyaları silmek yeterlidir.
"""

import json
import os
import re
import shutil

from . import ekler
from . import fontlar
from . import koruma
from .ayarlar import PAKET_KLASORU, RENPY_DOSYALARI, VERI_KLASORU

YAMA_KAYNAK = os.path.join(RENPY_DOSYALARI, "trceviri_yama.rpy")
EKLER_KAYNAK = os.path.join(PAKET_KLASORU, "ekler.py")
YAMA_AD = "zzzz_trceviri_yama.rpy"
VERI_KLASOR_AD = "trceviri"
EKLER_ISARETI = "# @@EKLER@@"

EK_ISTISNA_SABLONU = """# EK İSTİSNALARI (isteğe bağlı)
#
# Oyuncunun adı gibi değişkenlere gelen ekler (Ali'nin, Elif'in, Mike'ın) oyun
# sırasında ismin OKUNUŞUNA göre otomatik seçilir. Bir isimde yanlış ek çıkarsa
# o ismin okunuşunu aşağıya yazın, sonra yamayı yeniden uygulayın
# (ana menü -> "Kayıtlı çeviriyi oyuna yeniden uygula").
#
# Biçim:   İsim = okunuşu
# Örnekler (başındaki # işaretini silerek kullanabilirsiniz):
#   Mike = mayk        -> Mike'ın, Mike'a
#   Chloe = klovi      -> Chloe'nin, Chloe'ye
#   Siobhan = şivon    -> Siobhan'ın
"""

# Kendinden sonra metin gelmeyen duraklama/geçiş etiketleri {size} etiketinin dışında kalır.
_SON_ETIKETLER_RE = re.compile(r"((?:\{(?:nw|w|p|fast|done)(?:=[^{}]*)?\})+)\s*$")


def arayuz_tablosu():
    """Yerleşik Türkçe arayüz tablosu: (her oyuna eklenenler, sadece hazır çeviri olarak kullanılanlar)."""
    with open(os.path.join(VERI_KLASORU, "renpy_arayuz_tr.json"), "r", encoding="utf-8") as f:
        veri = json.load(f)
    return dict(veri.get("ortak") or {}), dict(veri.get("ek") or {})


def yama_metni():
    """Yama betiğini, ek uyumu kodu (ekler.py) içine gömülmüş olarak döndürür."""
    with open(YAMA_KAYNAK, "r", encoding="utf-8") as f:
        yama = f.read()
    with open(EKLER_KAYNAK, "r", encoding="utf-8") as f:
        ek_kodu = f.read()
    girintili = "\n".join(("    " + s) if s.strip() else "" for s in ek_kodu.splitlines())
    satirlar = yama.splitlines()
    for i, s in enumerate(satirlar):
        if s.strip() == EKLER_ISARETI:
            satirlar[i] = girintili
            break
    else:
        raise RuntimeError("Yama dosyasında ek uyumu işareti bulunamadı")
    return "\n".join(satirlar) + "\n"


def ek_istisnalari_oku(yol):
    """ek_istisnalari.txt -> {"mike": "mayk"} (anahtar: ismin son kelimesi, küçük harf)."""
    sonuc = {}
    try:
        with open(yol, "r", encoding="utf-8-sig") as f:
            satirlar = f.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return sonuc
    for satir in satirlar:
        satir = satir.strip()
        if not satir or satir.startswith("#") or "=" not in satir:
            continue
        ad, okunus = [x.strip() for x in satir.split("=", 1)]
        okunus = okunus.split("#", 1)[0].strip()
        kelimeler = re.findall(r"[^\W_]+", ad)
        if not kelimeler or not okunus:
            continue
        sonuc[ekler._ek_kucuk(kelimeler[-1])] = koruma.turkce_kucuk(okunus).replace(" ", "")
    return sonuc


def ek_istisna_sablonu_yaz(yol):
    if not os.path.exists(yol):
        with open(yol, "w", encoding="utf-8") as f:
            f.write(EK_ISTISNA_SABLONU)


def uzun_satiri_kucult(kaynak, ceviri):
    """Türkçesi çok uzayan diyalog satırının yazısını biraz küçültür (kutudan taşmasın).

    Döndürür: (yeni çeviri, küçültme miktarı: 0 / 2 / 4)
    """
    if "{size" in ceviri or "{/size" in ceviri:
        return ceviri, 0
    kl = len(koruma.duz_metin(kaynak).strip())
    cl = len(koruma.duz_metin(ceviri).strip())
    if not kl:
        return ceviri, 0
    oran = cl / float(kl)
    if cl > 220 and oran > 1.6:
        n = 4
    elif cl > 180 and oran > 1.35:
        n = 2
    else:
        return ceviri, 0
    m = _SON_ETIKETLER_RE.search(ceviri)
    govde, son = (ceviri[:m.start()], ceviri[m.start():]) if m else (ceviri, "")
    if not govde.strip():
        return ceviri, 0
    return "{size=-%d}%s{/size}%s" % (n, govde, son), n


def yama_kurulu_mu(oyun):
    return os.path.exists(os.path.join(oyun.game, YAMA_AD))


def _atomik_json(yol, veri):
    gecici = yol + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(gecici, yol)


def yamayi_yaz(oyun, cikti, proje, ayar, uyar=None):
    """Mevcut çevirilerle yamayı oyuna yazar. Döndürür: istatistik sözlüğü."""
    uyar = uyar or (lambda m: None)
    ortak, _ek = arayuz_tablosu()

    diyalog = {}
    kucult = bool(ayar.get("uzun_satir_kucult", True))
    kucultulen = 0
    for o in cikti.get("ogeler") or []:
        m = o.get("m")
        if not isinstance(m, str) or m in diyalog:
            continue
        c = proje.ceviri_al(m)
        if c and c != m:
            # Son bir güvenlik kontrolü: oyunu bozabilecek çeviri asla yazılmaz.
            c2, ciddi, _s = koruma.dogrula(m, c)
            if not ciddi:
                # Ek işaretleri ([ad]{ek=in}) oyun sırasında ismin okunuşuna göre çözülür.
                if kucult and (o.get("tur") or "diyalog") == "diyalog":
                    c2, n = uzun_satiri_kucult(m, c2)
                    if n:
                        kucultulen += 1
                diyalog[m] = c2

    metinler = dict(ortak)
    python_ac = ayar.get("python_metinleri", True)
    for s in cikti.get("metinler") or []:
        m = s.get("m")
        if not isinstance(m, str):
            continue
        if s.get("tur") == "python" and not python_ac:
            continue
        c = proje.ceviri_al(m)
        if c and c != m:
            c2, ciddi, _s = koruma.dogrula(m, c)
            if not ciddi:
                # Arayüz metinleri Ren'Py'ın kendi tablosundan geçtiği için ek işaretleri
                # burada yapay zekanın yazdığı biçimle sabitlenir.
                metinler[m] = ekler.isaretleri_sabitle(c2)

    # Oyunun "translate None strings" ile değiştirdiği arayüz metinleri.
    for eski, yeni in (cikti.get("none_ozel") or {}).items():
        c = proje.ceviri_al(yeni)
        if c:
            c2, ciddi, _s = koruma.dogrula(yeni, c)
            if not ciddi:
                metinler[eski] = ekler.isaretleri_sabitle(c2)
        # Çevirisi yoksa: yerleşik tablodaki genel Türkçe karşılık (varsa) kalır;
        # anlamca yakın Türkçe metin, İngilizce özel metinden daha iyidir.

    eksik_fontlar = []
    bilinmeyen_fontlar = []
    for f in cikti.get("fontlar") or []:
        if f.get("eksik"):
            eksik_fontlar.append(f.get("dosya"))
        elif f.get("eksik") is None:
            bilinmeyen_fontlar.append(f.get("dosya"))

    veri_klasoru = os.path.join(oyun.game, VERI_KLASOR_AD)
    os.makedirs(veri_klasoru, exist_ok=True)

    yedek_font = "DejaVuSans.ttf"
    yedek_font_kalin = "DejaVuSans-Bold.ttf"
    if ayar.get("yedek_font"):
        kaynak = ayar["yedek_font"]
        if os.path.isfile(kaynak):
            eksik = fontlar.dosya_eksik_harfler(kaynak)
            if eksik:
                uyar("Seçilen yedek font da Türkçe harfleri içermiyor (%s); Ren'Py'ın varsayılan fontu kullanılacak." % eksik)
            else:
                hedef_klasor = os.path.join(veri_klasoru, "fontlar")
                os.makedirs(hedef_klasor, exist_ok=True)
                shutil.copyfile(kaynak, os.path.join(hedef_klasor, os.path.basename(kaynak)))
                yedek_font = VERI_KLASOR_AD + "/fontlar/" + os.path.basename(kaynak)
                yedek_font_kalin = ""
                kalin = ayar.get("yedek_font_kalin")
                if kalin and os.path.isfile(kalin) and not fontlar.dosya_eksik_harfler(kalin):
                    shutil.copyfile(kalin, os.path.join(hedef_klasor, os.path.basename(kalin)))
                    yedek_font_kalin = VERI_KLASOR_AD + "/fontlar/" + os.path.basename(kalin)
        else:
            uyar("Ayarlardaki yedek font bulunamadı: %s (varsayılan font kullanılacak)" % kaynak)

    paket = {
        "surum": 1,
        "diyalog": diyalog,
        "metinler": metinler,
        "eksik_fontlar": [f for f in eksik_fontlar if f],
        "yedek_font": yedek_font,
        "yedek_font_kalin": yedek_font_kalin,
        "yedek_katman": bool(ayar.get("yedek_katman", True)),
        "kisayol": ayar.get("kisayol") or "",
        "ek_istisnalari": ek_istisnalari_oku(proje.ek_istisna_yolu),
    }
    _atomik_json(os.path.join(veri_klasoru, "ceviri.json"), paket)
    try:
        ek_istisna_sablonu_yaz(proje.ek_istisna_yolu)
    except OSError:
        pass

    # Yama betiği (eski derlenmiş hali silinir ki yeniden derlensin).
    hedef = os.path.join(oyun.game, YAMA_AD)
    for eski in (hedef + "c",):
        try:
            if os.path.exists(eski):
                os.remove(eski)
        except Exception:
            pass
    metin = yama_metni()
    gecici = hedef + ".tmp"
    with open(gecici, "w", encoding="utf-8", newline="\n") as f:
        f.write(metin)
    os.replace(gecici, hedef)

    # Doğrulama: yazılan dosya okunabiliyor mu?
    with open(os.path.join(veri_klasoru, "ceviri.json"), "r", encoding="utf-8") as f:
        json.load(f)

    # İstatistik: sadece çevrilmesi gereken satırlar sayılır ("..." gibi satırlar hariç).
    cevrilmeli = {o.get("m") for o in (cikti.get("ogeler") or [])
                  if isinstance(o.get("m"), str) and koruma.cevrilecek_mi(o["m"])}
    cevrilen = {m for m in cevrilmeli if proje.ceviri_al(m) is not None}

    return {
        "diyalog": len(cevrilen),
        "toplam_diyalog": len(cevrilmeli),
        "metin": len(metinler),
        "eksik_fontlar": eksik_fontlar,
        "bilinmeyen_fontlar": bilinmeyen_fontlar,
        "kucultulen": kucultulen,
    }


def yamayi_kaldir(oyun):
    """Yamayı oyundan tamamen kaldırır. Döndürür: silinen öğe sayısı."""
    silinen = 0
    for ad in (YAMA_AD, YAMA_AD + "c", "zzzz_trceviri_cikarici.rpy", "zzzz_trceviri_cikarici.rpyc",
               "trceviri_cikar.txt", "trceviri_cikti.json"):
        yol = os.path.join(oyun.game, ad)
        if os.path.exists(yol):
            os.remove(yol)
            silinen += 1
    klasor = os.path.join(oyun.game, VERI_KLASOR_AD)
    if os.path.isdir(klasor):
        shutil.rmtree(klasor)
        silinen += 1
    hata = os.path.join(oyun.kok, "trceviri_hata.txt")
    if os.path.exists(hata):
        os.remove(hata)
        silinen += 1
    return silinen
