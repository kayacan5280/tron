"""Türkçe yamanın oyuna kurulması ve kaldırılması.

Oyunun hiçbir dosyası değiştirilmez; sadece şu dosyalar EKLENİR:
  game/zzzz_trceviri_yama.rpy     -> çeviriyi uygulayan küçük Ren'Py betiği
  game/trceviri/ceviri.json       -> çeviriler
  game/trceviri/fontlar/...       -> (isteğe bağlı) yedek font
Kaldırmak için bu dosyaları silmek yeterlidir.
"""

import json
import os
import shutil

from . import fontlar
from . import koruma
from .ayarlar import RENPY_DOSYALARI, VERI_KLASORU

YAMA_KAYNAK = os.path.join(RENPY_DOSYALARI, "trceviri_yama.rpy")
YAMA_AD = "zzzz_trceviri_yama.rpy"
VERI_KLASOR_AD = "trceviri"


def arayuz_tablosu():
    """Yerleşik Türkçe arayüz tablosu: (her oyuna eklenenler, sadece hazır çeviri olarak kullanılanlar)."""
    with open(os.path.join(VERI_KLASORU, "renpy_arayuz_tr.json"), "r", encoding="utf-8") as f:
        veri = json.load(f)
    return dict(veri.get("ortak") or {}), dict(veri.get("ek") or {})


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
    for o in cikti.get("ogeler") or []:
        m = o.get("m")
        if not isinstance(m, str):
            continue
        c = proje.ceviri_al(m)
        if c and c != m:
            # Son bir güvenlik kontrolü: oyunu bozabilecek çeviri asla yazılmaz.
            c2, ciddi, _s = koruma.dogrula(m, c)
            if not ciddi:
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
                metinler[m] = c2

    # Oyunun "translate None strings" ile değiştirdiği arayüz metinleri.
    for eski, yeni in (cikti.get("none_ozel") or {}).items():
        c = proje.ceviri_al(yeni)
        if c:
            c2, ciddi, _s = koruma.dogrula(yeni, c)
            if not ciddi:
                metinler[eski] = c2
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
    }
    _atomik_json(os.path.join(veri_klasoru, "ceviri.json"), paket)

    # Yama betiği (eski derlenmiş hali silinir ki yeniden derlensin).
    hedef = os.path.join(oyun.game, YAMA_AD)
    for eski in (hedef + "c",):
        try:
            if os.path.exists(eski):
                os.remove(eski)
        except Exception:
            pass
    shutil.copyfile(YAMA_KAYNAK, hedef)

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
