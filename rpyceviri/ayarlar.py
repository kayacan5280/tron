"""Ayarlar: ayarlar.json dosyasını okur/yazar, eksik değerleri varsayılanla doldurur."""

import copy
import json
import os

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AYAR_DOSYASI = os.path.join(KOK, "ayarlar.json")
ANAHTAR_DOSYASI = os.path.join(KOK, "api_anahtarlari.txt")
ANAHTAR_DURUM_DOSYASI = os.path.join(KOK, "anahtar_durumu.json")
PROJE_KLASORU = os.path.join(KOK, "projeler")
PAKET_KLASORU = os.path.dirname(os.path.abspath(__file__))
RENPY_DOSYALARI = os.path.join(PAKET_KLASORU, "renpy_dosyalari")
VERI_KLASORU = os.path.join(PAKET_KLASORU, "veri")

VARSAYILAN = {
    "modeller": [
        "gemini-2.5-flash",
        "gemini-flash-latest",
        "gemini-2.5-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-2.0-flash",
    ],
    "dakikalik_istek": {"flash-lite": 12, "flash": 8, "pro": 4, "varsayilan": 6},
    "paket_satir": 40,
    "paket_karakter": 7000,
    "baglam_satir": 10,
    "paralel": 3,
    "sicaklik": 0.35,
    "dusunme_butcesi": 0,
    "en_fazla_cikti_token": 16384,
    "zaman_asimi_sn": 240,
    "deneme_sayisi": 6,
    "python_metinleri": True,
    "yedek_katman": True,
    "kisayol": "alt_K_t",
    "yedek_font": "",
    "yedek_font_kalin": "",
    "oyun_baslatma_bekleme_sn": 600,
    "son_oyunlar": [],
}

ACIKLAMA = {
    "modeller": "Sırayla denenecek Gemini modelleri. İlki en kaliteli kabul edilir; onun kotası bitince sonrakine geçilir.",
    "dakikalik_istek": "Her API anahtarı için model başına dakikada en fazla kaç istek gönderileceği (ücretsiz katman sınırları).",
    "paket_satir": "Tek istekte çevrilecek en fazla satır sayısı. Büyük değer = daha az istek (kota tasarrufu).",
    "paket_karakter": "Tek istekteki toplam karakter sınırı.",
    "baglam_satir": "Her pakete bağlam olarak eklenen önceki satır sayısı (tutarlılık için).",
    "paralel": "Aynı anda çalışacak istek sayısı (anahtar sayısından fazla olamaz).",
    "sicaklik": "Yaratıcılık (0-1). Çeviri için 0.2-0.5 arası önerilir.",
    "dusunme_butcesi": "Gemini 2.5 'düşünme' token bütçesi. 0 = kapalı (hızlı, kota dostu). -1 = model karar versin.",
    "en_fazla_cikti_token": "Bir yanıtta en fazla üretilecek token.",
    "zaman_asimi_sn": "Bir isteğin en fazla bekleneceği süre (saniye).",
    "deneme_sayisi": "Bir paket için en fazla deneme sayısı.",
    "python_metinleri": "Oyunun Python kodundaki doğal dil metinlerini de çevir (görev, eşya açıklamaları vb.).",
    "yedek_katman": "Ekrana gelen metinleri son kez kontrol edip çeviren ek güvenlik katmanı.",
    "kisayol": "Oyun içinde Türkçe/orijinal arasında geçiş tuşu (Ren'Py tuş adı). Boş = kapalı.",
    "yedek_font": "Türkçe harf desteği olmayan fontların yerine kullanılacak .ttf/.otf dosyasının tam yolu. Boş = Ren'Py'ın DejaVuSans fontu.",
    "yedek_font_kalin": "Kalın yazılar için yedek font (isteğe bağlı).",
    "oyun_baslatma_bekleme_sn": "Metin çıkarma için oyunun en fazla bekleneceği süre.",
    "son_oyunlar": "Son çevrilen oyunların klasörleri (otomatik doldurulur).",
}


class Ayarlar(dict):

    def kaydet(self):
        veri = {"_aciklamalar": ACIKLAMA}
        for k in VARSAYILAN:
            veri[k] = self.get(k, VARSAYILAN[k])
        gecici = AYAR_DOSYASI + ".tmp"
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False, indent=2)
        os.replace(gecici, AYAR_DOSYASI)


def _tur_uyumlu(varsayilan, deger):
    if isinstance(varsayilan, bool):
        return isinstance(deger, bool)
    if isinstance(varsayilan, (int, float)):
        return isinstance(deger, (int, float)) and not isinstance(deger, bool)
    return isinstance(deger, type(varsayilan))


def yukle():
    """Ayarları yükler. Dosya yoksa veya bozuksa varsayılanlarla oluşturur."""
    ayar = Ayarlar(copy.deepcopy(VARSAYILAN))
    sorunlar = []

    if os.path.exists(AYAR_DOSYASI):
        try:
            with open(AYAR_DOSYASI, "r", encoding="utf-8-sig") as f:
                kullanici = json.load(f)
            if not isinstance(kullanici, dict):
                raise ValueError("ayar dosyası bir sözlük değil")
            for k, v in kullanici.items():
                if k not in VARSAYILAN:
                    continue
                if _tur_uyumlu(VARSAYILAN[k], v):
                    ayar[k] = v
                else:
                    sorunlar.append("'%s' ayarı hatalı, varsayılan kullanıldı." % k)
        except Exception as e:
            sorunlar.append("ayarlar.json okunamadı (%s); varsayılan ayarlar kullanılıyor." % e)
            try:
                os.replace(AYAR_DOSYASI, AYAR_DOSYASI + ".bozuk")
            except Exception:
                pass

    # Mantıksız değerleri düzelt.
    if not ayar["modeller"] or not all(isinstance(m, str) and m.strip() for m in ayar["modeller"]):
        ayar["modeller"] = list(VARSAYILAN["modeller"])
        sorunlar.append("Model listesi boş/hatalı, varsayılan kullanıldı.")
    ayar["modeller"] = [m.strip().replace("models/", "") for m in ayar["modeller"]]
    ayar["paket_satir"] = int(min(150, max(1, ayar["paket_satir"])))
    ayar["paket_karakter"] = int(min(40000, max(500, ayar["paket_karakter"])))
    ayar["baglam_satir"] = int(min(40, max(0, ayar["baglam_satir"])))
    ayar["paralel"] = int(min(16, max(1, ayar["paralel"])))
    ayar["sicaklik"] = float(min(1.5, max(0.0, ayar["sicaklik"])))
    ayar["deneme_sayisi"] = int(min(20, max(2, ayar["deneme_sayisi"])))
    ayar["zaman_asimi_sn"] = int(min(900, max(30, ayar["zaman_asimi_sn"])))
    ayar["en_fazla_cikti_token"] = int(min(65536, max(2048, ayar["en_fazla_cikti_token"])))
    ayar["oyun_baslatma_bekleme_sn"] = int(min(3600, max(60, ayar["oyun_baslatma_bekleme_sn"])))
    if not isinstance(ayar["dakikalik_istek"], dict):
        ayar["dakikalik_istek"] = dict(VARSAYILAN["dakikalik_istek"])

    try:
        ayar.kaydet()
    except Exception as e:
        sorunlar.append("ayarlar.json yazılamadı: %s" % e)

    return ayar, sorunlar


def dakikalik_sinir(ayar, model):
    tablo = ayar.get("dakikalik_istek") or {}
    m = model.lower()
    # En uzun eşleşen anahtar kazanır ("flash-lite", "flash"dan önce gelir).
    adaylar = sorted((k for k in tablo if k != "varsayilan" and k in m), key=len, reverse=True)
    if adaylar:
        deger = tablo[adaylar[0]]
    else:
        deger = tablo.get("varsayilan", 6)
    try:
        deger = float(deger)
    except Exception:
        deger = 6.0
    return max(0.5, deger)
