"""Google Gemini REST API istemcisi (sadece standart kütüphane).

Hataları türlerine göre sınıflandırır, böylece üst katman doğru kararı
verebilir: anahtarı değiştir, modeli değiştir, bekle, paketi böl vb.
"""

import json
import os
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request

API_TABANI = os.environ.get("TRCEVIRI_API_URL", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")

# Hata türleri
GECERSIZ_ANAHTAR = "gecersiz_anahtar"   # anahtar yanlış/silinmiş/sızdırılmış -> bu anahtarı bırak
KOTA_GUNLUK = "kota_gunluk"             # günlük kota bitti -> bu anahtar+model yarına kadar kapalı
KOTA_DAKIKA = "kota_dakika"             # dakikalık sınır -> kısa bekle
KOTA = "kota"                           # türü belirsiz kota hatası
MODEL_YOK = "model_yok"                 # model bulunamadı/desteklenmiyor -> sonraki model
GECERSIZ_ISTEK = "gecersiz_istek"       # istek biçimi reddedildi -> özellik kapat / paketi küçült
SUNUCU = "sunucu"                       # 5xx, aşırı yük -> tekrar dene
AG = "ag"                               # bağlantı sorunu -> tekrar dene
ZAMAN_ASIMI = "zaman_asimi"             # yanıt gelmedi -> tekrar dene / paketi küçült
SSL = "ssl"                             # sertifika sorunu -> kullanıcıya bildir
ENGELLENDI = "engellendi"               # güvenlik filtresi -> paketi böl / satırı ayır
BOS_YANIT = "bos_yanit"                 # boş yanıt -> tekrar dene
KESILDI = "kesildi"                     # çıktı token sınırı -> paketi böl
BOLGE = "bolge"                         # bölge desteklenmiyor
KREDI = "kredi"                         # ücretli hesabın kredisi/bakiyesi bitti -> bu anahtarı bu oturumda bırak
SDK_YOK = "sdk_yok"                     # sağlayıcının gerekli Python paketi kurulu değil


class ApiHatasi(Exception):

    def __init__(self, tur, mesaj, http=None, bekle=None, ham=None, kismi=None):
        Exception.__init__(self, mesaj)
        self.tur = tur
        self.mesaj = mesaj
        self.http = http
        self.bekle = bekle
        self.ham = ham
        self.kismi = kismi

    def __str__(self):
        ek = (" (HTTP %s)" % self.http) if self.http else ""
        return "%s: %s%s" % (self.tur, self.mesaj, ek)


def _sure_coz(metin):
    """'41s', '1.5s', '2m' gibi süreleri saniyeye çevirir."""
    if not metin:
        return None
    m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(ms|s|m|h)?\s*$", str(metin))
    if not m:
        return None
    deger = float(m.group(1))
    birim = m.group(2) or "s"
    return deger * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[birim]


def hata_coz(kod, govde, basliklar=None):
    """HTTP hata yanıtını ApiHatasi'na çevirir."""
    try:
        metin = govde.decode("utf-8", "replace") if isinstance(govde, bytes) else (govde or "")
    except Exception:
        metin = ""

    mesaj = metin[:500]
    durum = ""
    nedenler = []
    kota_kimlikleri = []
    bekle = None

    try:
        veri = json.loads(metin)
        hata = veri.get("error", {}) if isinstance(veri, dict) else {}
        if isinstance(hata, dict):
            mesaj = str(hata.get("message") or mesaj)[:500]
            durum = str(hata.get("status") or "")
            for ayrinti in hata.get("details") or []:
                if not isinstance(ayrinti, dict):
                    continue
                tip = str(ayrinti.get("@type", ""))
                if "ErrorInfo" in tip and ayrinti.get("reason"):
                    nedenler.append(str(ayrinti["reason"]))
                if "QuotaFailure" in tip:
                    for ihlal in ayrinti.get("violations") or []:
                        if isinstance(ihlal, dict):
                            kota_kimlikleri.append(str(ihlal.get("quotaId", "")) + " " + str(ihlal.get("quotaMetric", "")))
                if "RetryInfo" in tip:
                    bekle = _sure_coz(ayrinti.get("retryDelay"))
    except Exception:
        pass

    if bekle is None and basliklar is not None:
        try:
            bekle = _sure_coz(basliklar.get("Retry-After"))
        except Exception:
            bekle = None

    kucuk = mesaj.lower()
    nedenler_metin = " ".join(nedenler).upper()

    if "API_KEY_INVALID" in nedenler_metin or "api key not valid" in kucuk or "api key expired" in kucuk \
            or "API_KEY_EXPIRED" in nedenler_metin or "invalid api key" in kucuk:
        return ApiHatasi(GECERSIZ_ANAHTAR, "API anahtarı geçersiz veya süresi dolmuş", kod, ham=mesaj)

    if kod == 400 and ("location is not supported" in kucuk or "not available in your country" in kucuk):
        return ApiHatasi(BOLGE, "Gemini API bu bölgede desteklenmiyor (VPN/konum sorunu olabilir)", kod, ham=mesaj)

    if kod in (401, 403):
        if "leaked" in kucuk:
            return ApiHatasi(GECERSIZ_ANAHTAR, "Anahtar sızdırılmış olarak işaretlenmiş ve engellenmiş; yeni anahtar alın", kod, ham=mesaj)
        if "SERVICE_DISABLED" in nedenler_metin or "has not been used" in kucuk or "is disabled" in kucuk:
            return ApiHatasi(GECERSIZ_ANAHTAR, "Bu anahtarın projesinde Gemini API kapalı", kod, ham=mesaj)
        return ApiHatasi(GECERSIZ_ANAHTAR, "Anahtarın yetkisi yok: " + mesaj[:200], kod, ham=mesaj)

    if kod == 404 or durum == "NOT_FOUND":
        return ApiHatasi(MODEL_YOK, "Model bulunamadı veya bu anahtarla kullanılamıyor", kod, ham=mesaj)

    if kod == 429 or durum == "RESOURCE_EXHAUSTED":
        kimlik = " ".join(kota_kimlikleri).lower()
        if "perday" in kimlik or "per_day" in kimlik or "daily" in kimlik or "per day" in kucuk or "daily" in kucuk:
            return ApiHatasi(KOTA_GUNLUK, "Günlük kota doldu", kod, bekle=bekle, ham=mesaj)
        if "perminute" in kimlik or "per_minute" in kimlik or "per minute" in kucuk:
            return ApiHatasi(KOTA_DAKIKA, "Dakikalık istek sınırı aşıldı", kod, bekle=bekle, ham=mesaj)
        if "limit: 0" in kucuk or "limit:0" in kucuk:
            # Bu modelin bu anahtar için ücretsiz kotası hiç yok.
            return ApiHatasi(KOTA_GUNLUK, "Bu model bu anahtar için ücretsiz kotaya sahip değil", kod, bekle=bekle, ham=mesaj)
        return ApiHatasi(KOTA, "Kota sınırına takıldı", kod, bekle=bekle, ham=mesaj)

    if kod == 413:
        return ApiHatasi(GECERSIZ_ISTEK, "İstek çok büyük", kod, ham=mesaj)

    if kod == 400 or durum in ("INVALID_ARGUMENT", "FAILED_PRECONDITION"):
        if "model" in kucuk and ("not found" in kucuk or "not supported" in kucuk or "is not available" in kucuk):
            return ApiHatasi(MODEL_YOK, "Model desteklenmiyor: " + mesaj[:200], kod, ham=mesaj)
        return ApiHatasi(GECERSIZ_ISTEK, mesaj[:300], kod, ham=mesaj)

    if kod is not None and kod >= 500:
        return ApiHatasi(SUNUCU, "Sunucu hatası / aşırı yoğunluk", kod, bekle=bekle, ham=mesaj)

    return ApiHatasi(SUNUCU, "Beklenmeyen yanıt: " + mesaj[:200], kod, bekle=bekle, ham=mesaj)


_ENGEL_NEDENLERI = ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION", "IMAGE_SAFETY", "LANGUAGE")


def yanit_coz(veri):
    """generateContent yanıtından metni çıkarır. Döndürür: (metin, kullanim)."""
    if not isinstance(veri, dict):
        raise ApiHatasi(BOS_YANIT, "Yanıt JSON nesnesi değil")

    geri = veri.get("promptFeedback") or {}
    if isinstance(geri, dict) and geri.get("blockReason"):
        raise ApiHatasi(ENGELLENDI, "İstek güvenlik filtresine takıldı: %s" % geri.get("blockReason"))

    adaylar = veri.get("candidates") or []
    if not adaylar:
        raise ApiHatasi(BOS_YANIT, "Yanıtta aday yok")

    aday = adaylar[0] if isinstance(adaylar[0], dict) else {}
    neden = str(aday.get("finishReason") or "")
    parcalar = ((aday.get("content") or {}).get("parts")) or []
    metin = "".join(
        p.get("text", "") for p in parcalar
        if isinstance(p, dict) and isinstance(p.get("text"), str) and not p.get("thought")
    )

    if neden in _ENGEL_NEDENLERI:
        raise ApiHatasi(ENGELLENDI, "Yanıt güvenlik filtresine takıldı: %s" % neden, kismi=metin)
    if neden == "MAX_TOKENS":
        raise ApiHatasi(KESILDI, "Yanıt token sınırında kesildi", kismi=metin)
    if not metin.strip():
        raise ApiHatasi(BOS_YANIT, "Boş yanıt (neden: %s)" % (neden or "?"))

    return metin, veri.get("usageMetadata") or {}


def http_istek(url, basliklar, veri=None, zaman_asimi=120, hata_cozucu=None):
    """Bir HTTP isteği yapar; hataları ApiHatasi'na çevirir. Döndürür: yanıt gövdesi (bytes)."""
    basliklar = dict(basliklar)
    if veri is not None:
        basliklar["Content-Type"] = "application/json; charset=utf-8"
    istek = urllib.request.Request(url, data=veri, headers=basliklar, method="POST" if veri is not None else "GET")
    try:
        with urllib.request.urlopen(istek, timeout=zaman_asimi) as yanit:
            return yanit.read()
    except urllib.error.HTTPError as e:
        try:
            govde = e.read()
        except Exception:
            govde = b""
        raise (hata_cozucu or hata_coz)(e.code, govde, e.headers)
    except (socket.timeout, TimeoutError):
        raise ApiHatasi(ZAMAN_ASIMI, "Sunucu zamanında yanıt vermedi")
    except urllib.error.URLError as e:
        neden = getattr(e, "reason", e)
        if isinstance(neden, ssl.SSLError) or "CERTIFICATE_VERIFY_FAILED" in str(e):
            raise ApiHatasi(SSL, "Güvenli bağlantı (SSL sertifika) hatası: %s" % neden)
        if isinstance(neden, (socket.timeout, TimeoutError)):
            raise ApiHatasi(ZAMAN_ASIMI, "Sunucu zamanında yanıt vermedi")
        raise ApiHatasi(AG, "Bağlantı kurulamadı: %s" % neden)
    except ssl.SSLError as e:
        raise ApiHatasi(SSL, "Güvenli bağlantı (SSL) hatası: %s" % e)
    except Exception as e:  # ConnectionResetError, IncompleteRead, RemoteDisconnected...
        raise ApiHatasi(AG, "Bağlantı koptu: %s" % e.__class__.__name__)


def _istek(url, anahtar, veri=None, zaman_asimi=120):
    return http_istek(url, {"x-goog-api-key": anahtar}, veri, zaman_asimi)


def icerik_uret(anahtar, model, govde, zaman_asimi=120):
    """Bir generateContent isteği yapar. Döndürür: (metin, kullanim)."""
    url = "%s/models/%s:generateContent" % (API_TABANI, urllib.parse.quote(model, safe="-._~"))
    veri = json.dumps(govde, ensure_ascii=False).encode("utf-8")
    ham = _istek(url, anahtar, veri, zaman_asimi)
    try:
        cozulmus = json.loads(ham.decode("utf-8", "replace"))
    except Exception:
        raise ApiHatasi(BOS_YANIT, "Yanıt JSON olarak çözülemedi")
    return yanit_coz(cozulmus)


def modelleri_listele(anahtar, zaman_asimi=30):
    """Anahtarın erişebildiği, metin üretebilen modellerin adlarını döndürür.

    Bu çağrı üretim kotası harcamaz; anahtarın geçerliliğini sınamak için de kullanılır.
    """
    adlar = []
    sayfa = None
    for _ in range(20):
        url = API_TABANI + "/models?pageSize=1000"
        if sayfa:
            url += "&pageToken=" + urllib.parse.quote(sayfa)
        ham = _istek(url, anahtar, None, zaman_asimi)
        try:
            veri = json.loads(ham.decode("utf-8", "replace"))
        except Exception:
            raise ApiHatasi(BOS_YANIT, "Model listesi çözülemedi")
        for m in veri.get("models") or []:
            if not isinstance(m, dict):
                continue
            yontemler = m.get("supportedGenerationMethods") or []
            if "generateContent" in yontemler:
                adlar.append(str(m.get("name", "")).replace("models/", ""))
        sayfa = veri.get("nextPageToken")
        if not sayfa:
            break
    return adlar
