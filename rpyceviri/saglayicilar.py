"""Yapay zeka sağlayıcıları: Google Gemini (ücretsiz), Anthropic Claude ve
OpenAI uyumlu servisler (DeepSeek, OpenAI, OpenRouter).

Program içinde bir "hedef", "sağlayıcı/model" biçiminde yazılır:
    gemini/gemini-2.5-flash, claude/claude-opus-5-5, deepseek/deepseek-chat
Bütün sağlayıcıların hataları gemini.ApiHatasi türlerine çevrilir; böylece
anahtar değiştirme, bekleme, paket bölme gibi kararlar tek yerde verilir.
"""

import collections
import json
import os
import re
import threading

from . import gemini
from . import istem
from .gemini import ApiHatasi

SAGLAYICILAR = collections.OrderedDict([
    ("gemini", {"ad": "Google Gemini", "ucretli": False,
                "site": "https://aistudio.google.com/apikey"}),
    ("claude", {"ad": "Anthropic Claude", "ucretli": True,
                "site": "https://console.anthropic.com/settings/keys"}),
    ("deepseek", {"ad": "DeepSeek", "ucretli": True, "taban": "https://api.deepseek.com",
                  "site": "https://platform.deepseek.com/api_keys"}),
    ("openai", {"ad": "OpenAI (ChatGPT)", "ucretli": True, "taban": "https://api.openai.com/v1",
                "site": "https://platform.openai.com/api-keys"}),
    ("openrouter", {"ad": "OpenRouter", "ucretli": True, "taban": "https://openrouter.ai/api/v1",
                    "site": "https://openrouter.ai/keys"}),
])

# Claude: bir istek güvenlik sınıflandırıcısına takılırsa Anthropic'in önerdiği
# modelle sunucu tarafında otomatik yeniden denenir.
CLAUDE_YEDEK_BETA = "server-side-fallback-2026-07-01"

# 1 milyon token başına ABD doları: [girdi, çıktı, önbellekten okuma, önbelleğe yazma]
VARSAYILAN_FIYATLAR = {
    "claude-opus-5-5": [4.0, 20.0, 0.20, 5.0],
    "claude-sonnet-5-5": [2.0, 10.0, 0.20, 2.5],
    "claude-haiku-4-5": [1.0, 5.0, 0.10, 1.25],
    "deepseek-chat": [0.28, 0.42, 0.028, 0.28],
    "deepseek-reasoner": [0.28, 0.42, 0.028, 0.28],
}


# ---------------------------------------------------------------------------
# Hedef ve anahtar yardımcıları
# ---------------------------------------------------------------------------


def hedef_coz(hedef):
    """'claude/claude-opus-5-5' -> ('claude', 'claude-opus-5-5'). Önek yoksa Gemini sayılır."""
    sag, ayrac, model = (hedef or "").partition("/")
    if ayrac and sag in SAGLAYICILAR:
        return sag, model
    return "gemini", hedef


def hedef_adi(saglayici, model):
    return "%s/%s" % (saglayici, model)


def hedef_normallestir(hedef):
    sag, model = hedef_coz(hedef)
    return hedef_adi(sag, model)


def model_adi(hedef):
    return hedef_coz(hedef)[1]


def ucretli_mi(hedef_ya_da_saglayici):
    sag = hedef_ya_da_saglayici if hedef_ya_da_saglayici in SAGLAYICILAR else hedef_coz(hedef_ya_da_saglayici)[0]
    return bool(SAGLAYICILAR[sag]["ucretli"])


def saglayici_adi(sag):
    return SAGLAYICILAR.get(sag, {}).get("ad", sag)


_ONEK_RE = re.compile(r"^([A-Za-z]+)\s*[:=]\s*(\S+)$")
_DEEPSEEK_RE = re.compile(r"^sk-[0-9a-f]{32}$")


def anahtar_turu_tahmin(anahtar):
    """Anahtarın biçiminden sağlayıcıyı tahmin eder; emin olunamazsa None."""
    a = anahtar.strip()
    if a.startswith("sk-ant-"):
        return "claude"
    if a.startswith("sk-or-"):
        return "openrouter"
    if a.startswith("AIza"):
        return "gemini"
    if a.startswith("sk-proj-") or a.startswith("sk-svcacct-") or a.startswith("sk-admin-"):
        return "openai"
    if _DEEPSEEK_RE.match(a):
        return "deepseek"
    if a.startswith("sk-"):
        return None
    return "gemini"


def anahtar_coz(satir):
    """Dosyadaki bir satırı (sağlayıcı, anahtar) ikilisine çevirir.

    "claude: sk-ant-..." gibi önekli ya da öneksiz yazılabilir; öneksiz olanların
    türü biçiminden tahmin edilir (eski sürümlerin dosyaları öneksiz Gemini anahtarıdır).
    """
    s = satir.strip()
    m = _ONEK_RE.match(s)
    if m and m.group(1).lower() in SAGLAYICILAR:
        return m.group(1).lower(), m.group(2)
    return anahtar_turu_tahmin(s) or "openai", s


def anahtar_satiri(saglayici, anahtar):
    return anahtar if saglayici == "gemini" else "%s: %s" % (saglayici, anahtar)


# ---------------------------------------------------------------------------
# İstek
# ---------------------------------------------------------------------------


class Istek(object):
    """Sağlayıcıdan bağımsız bir istek.

    sistem: oyun boyunca değişmeyen talimat (önbelleğe alınır)
    degisken: pakete göre değişen ek talimat (boş olabilir)
    kullanici: kullanıcı mesajı (JSON)
    sema: istem.SEMALAR anahtarı ("ceviri", "sozluk", "karakter") ya da None
    """

    __slots__ = ("sistem", "degisken", "kullanici", "sema")

    def __init__(self, sistem, kullanici, sema=None, degisken=""):
        self.sistem = sistem
        self.degisken = degisken or ""
        self.kullanici = kullanici
        self.sema = sema


def _kullanim(girdi=0, cikti=0, okuma=0, yazma=0, model=None):
    return {"girdi": int(girdi or 0), "cikti": int(cikti or 0), "onbellek_okuma": int(okuma or 0),
            "onbellek_yazma": int(yazma or 0), "model": model}


def uret(hedef, anahtar, istek, ayar, ozellikler):
    """İsteği hedefe gönderir. Döndürür: (metin, kullanım sözlüğü)."""
    sag, model = hedef_coz(hedef)
    if sag == "gemini":
        return _gemini_uret(model, anahtar, istek, ayar, ozellikler)
    if sag == "claude":
        return _claude_uret(model, anahtar, istek, ayar, ozellikler)
    return _openai_uret(sag, model, anahtar, istek, ayar, ozellikler)


def kapatilacak_ozellik(hedef, mesaj):
    """400 hatasında hangi özelliğin kapatılacağını tahmin eder (sağlayıcıya göre)."""
    sag, _model = hedef_coz(hedef)
    m = (mesaj or "").lower()
    if sag == "claude":
        if "fallback" in m or "anthropic-beta" in m or "beta" in m:
            return "yedek"
        if "effort" in m:
            return "efor"
        if "output_config" in m or "json_schema" in m or "schema" in m or "format" in m:
            return "sema"
        if "cache_control" in m:
            return "onbellek"
        return None
    if sag != "gemini":
        if "max_tokens" in m or "max_completion_tokens" in m:
            return "en_fazla"
        if "temperature" in m:
            return "sicaklik"
        if "response_format" in m or "json" in m:
            return "json"
        return None
    return istem.kapatilacak_ozellik(mesaj)


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------


def _gemini_uret(model, anahtar, istek, ayar, ozl):
    sistem = istek.sistem + ("\n\n" + istek.degisken if istek.degisken else "")
    sema = istem.gemini_semasi(istem.SEMALAR[istek.sema]) if istek.sema else None
    govde = istem.istek_govdesi(sistem, istek.kullanici, ayar, ozl, model, sema)
    metin, k = gemini.icerik_uret(anahtar, model, govde, ayar.get("zaman_asimi_sn", 240))
    try:
        toplam = int(k.get("promptTokenCount", 0) or 0)
        okuma = int(k.get("cachedContentTokenCount", 0) or 0)
        cikti = int(k.get("candidatesTokenCount", 0) or 0) + int(k.get("thoughtsTokenCount", 0) or 0)
    except Exception:
        toplam = okuma = cikti = 0
    return metin, _kullanim(max(0, toplam - okuma), cikti, okuma, 0, model)


# ---------------------------------------------------------------------------
# Claude (resmî "anthropic" Python paketi ile)
# ---------------------------------------------------------------------------

_claude_kilit = threading.Lock()
_claude_istemciler = {}


def claude_sdk_var_mi():
    try:
        import anthropic
        return anthropic is not None
    except Exception:
        return False


def _claude_modulu():
    try:
        import anthropic
        return anthropic
    except Exception:
        raise ApiHatasi(gemini.SDK_YOK, "Claude için gereken 'anthropic' Python paketi kurulu değil")


def _claude_istemci(anahtar, zaman_asimi):
    anthropic = _claude_modulu()
    k = (anahtar, float(zaman_asimi))
    with _claude_kilit:
        istemci = _claude_istemciler.get(k)
        if istemci is None:
            kw = {"api_key": anahtar, "max_retries": 0, "timeout": float(zaman_asimi)}
            taban = os.environ.get("TRCEVIRI_CLAUDE_URL")
            if taban:
                kw["base_url"] = taban
            istemci = anthropic.Anthropic(**kw)
            _claude_istemciler[k] = istemci
    return anthropic, istemci


def _claude_hata_govdesi(e):
    govde = getattr(e, "body", None)
    tur = ""
    mesaj = str(getattr(e, "message", "") or e)
    if isinstance(govde, dict):
        hata = govde.get("error") if isinstance(govde.get("error"), dict) else govde
        tur = str(hata.get("type") or "")
        mesaj = str(hata.get("message") or mesaj)
    return tur, mesaj[:500]


def _claude_hata_cevir(anthropic, e):
    """Anthropic SDK hatasını ApiHatasi'na çevirir."""
    if isinstance(e, anthropic.APITimeoutError):
        return ApiHatasi(gemini.ZAMAN_ASIMI, "Claude zamanında yanıt vermedi")
    if isinstance(e, anthropic.APIConnectionError):
        neden = repr(getattr(e, "__cause__", None) or e)
        if "CERTIFICATE_VERIFY_FAILED" in neden or "SSLError" in neden or "SSLCertVerificationError" in neden:
            return ApiHatasi(gemini.SSL, "Güvenli bağlantı (SSL) hatası: %s" % neden[:200])
        return ApiHatasi(gemini.AG, "Claude'a bağlanılamadı")
    if not isinstance(e, anthropic.APIStatusError):
        return ApiHatasi(gemini.SUNUCU, "Beklenmeyen Claude hatası: %s" % e)

    kod = getattr(e, "status_code", None)
    tur, mesaj = _claude_hata_govdesi(e)
    kucuk = mesaj.lower()
    bekle = None
    try:
        bekle = gemini._sure_coz(e.response.headers.get("retry-after"))
    except Exception:
        bekle = None

    if "credit balance" in kucuk or "billing" in kucuk or kod == 402:
        return ApiHatasi(gemini.KREDI, "Claude hesabında kredi kalmadı (console.anthropic.com → Billing)", kod, ham=mesaj)
    if kod == 401 or tur == "authentication_error":
        return ApiHatasi(gemini.GECERSIZ_ANAHTAR, "Claude API anahtarı geçersiz", kod, ham=mesaj)
    if kod == 403 or tur == "permission_error":
        return ApiHatasi(gemini.GECERSIZ_ANAHTAR, "Claude anahtarının bu işlem için yetkisi yok: " + mesaj[:150], kod, ham=mesaj)
    if kod == 404 or tur == "not_found_error":
        return ApiHatasi(gemini.MODEL_YOK, "Claude modeli bulunamadı: " + mesaj[:150], kod, ham=mesaj)
    if kod == 429 or tur == "rate_limit_error":
        return ApiHatasi(gemini.KOTA_DAKIKA, "Claude hız sınırı aşıldı", kod, bekle=bekle, ham=mesaj)
    if kod == 413 or tur == "request_too_large":
        return ApiHatasi(gemini.GECERSIZ_ISTEK, "İstek çok büyük", kod, ham=mesaj)
    if tur in ("overloaded_error", "api_error") or (kod is not None and kod >= 500):
        return ApiHatasi(gemini.SUNUCU, "Claude sunucuları yoğun", kod, bekle=bekle, ham=mesaj)
    if kod == 400 or tur == "invalid_request_error":
        return ApiHatasi(gemini.GECERSIZ_ISTEK, mesaj[:300], kod, ham=mesaj)
    return ApiHatasi(gemini.SUNUCU, "Beklenmeyen Claude yanıtı: " + mesaj[:200], kod, bekle=bekle, ham=mesaj)


def _claude_parametreleri(model, istek, ayar, ozl):
    sistem = [{"type": "text", "text": istek.sistem}]
    if ozl.get("onbellek", True):
        # Oyun boyunca değişmeyen talimat önbelleğe alınır: sonraki isteklerde
        # bu kısım çok daha ucuza okunur.
        sistem[0]["cache_control"] = {"type": "ephemeral"}
    if istek.degisken:
        sistem.append({"type": "text", "text": istek.degisken})

    cikti_ayari = {}
    efor = ayar.get("claude_efor")
    if ozl.get("efor", True) and efor:
        cikti_ayari["effort"] = efor
    if ozl.get("sema", True) and istek.sema:
        cikti_ayari["format"] = {"type": "json_schema", "schema": istem.SEMALAR[istek.sema]}

    kw = {
        "model": model,
        "max_tokens": int(ayar.get("claude_en_fazla_token", 32000)),
        "system": sistem,
        "messages": [{"role": "user", "content": istek.kullanici}],
    }
    ek = {}
    if cikti_ayari:
        ek["output_config"] = cikti_ayari
    if ozl.get("yedek", True):
        ek["fallbacks"] = "default"
    return kw, ek


def _claude_uret(model, anahtar, istek, ayar, ozl):
    anthropic, istemci = _claude_istemci(anahtar, ayar.get("zaman_asimi_sn", 240))
    kw, ek = _claude_parametreleri(model, istek, ayar, ozl)
    try:
        try:
            if "fallbacks" in ek:
                kw2 = dict(kw, betas=[CLAUDE_YEDEK_BETA], **ek)
            else:
                kw2 = dict(kw, **ek)
            with istemci.beta.messages.stream(**kw2) as akis:
                mesaj = akis.get_final_message()
        except (TypeError, AttributeError) as e:
            # Eski "anthropic" paketi bu parametreleri tanımıyor: aynı istek ham
            # gövde alanlarıyla gönderilir.
            if "unexpected keyword" not in str(e) and "has no attribute" not in str(e):
                raise
            basliklar = {"anthropic-beta": CLAUDE_YEDEK_BETA} if "fallbacks" in ek else None
            with istemci.messages.stream(extra_body=ek or None, extra_headers=basliklar, **kw) as akis:
                mesaj = akis.get_final_message()
    except ApiHatasi:
        raise
    except anthropic.APIError as e:
        raise _claude_hata_cevir(anthropic, e)
    except Exception as e:
        ad = type(e).__module__ or ""
        if ad.startswith("httpx") or ad.startswith("httpcore") or isinstance(e, (ConnectionError, OSError)):
            raise ApiHatasi(gemini.AG, "Claude bağlantısı koptu: %s" % type(e).__name__)
        raise

    neden = getattr(mesaj, "stop_reason", None)
    if neden == "refusal":
        raise ApiHatasi(gemini.ENGELLENDI, "Claude bu içeriği işlemeyi reddetti")
    metin = "".join(getattr(b, "text", "") or "" for b in (mesaj.content or []) if getattr(b, "type", "") == "text")
    if neden == "max_tokens":
        raise ApiHatasi(gemini.KESILDI, "Yanıt token sınırında kesildi", kismi=metin)
    if not metin.strip():
        raise ApiHatasi(gemini.BOS_YANIT, "Claude boş yanıt döndürdü (neden: %s)" % neden)
    u = getattr(mesaj, "usage", None)
    return metin, _kullanim(
        getattr(u, "input_tokens", 0), getattr(u, "output_tokens", 0),
        getattr(u, "cache_read_input_tokens", 0), getattr(u, "cache_creation_input_tokens", 0),
        getattr(mesaj, "model", model))


def _claude_modeller(anahtar):
    anthropic, istemci = _claude_istemci(anahtar, 30)
    try:
        return [m.id for m in istemci.models.list(limit=100)]
    except anthropic.APIError as e:
        raise _claude_hata_cevir(anthropic, e)
    except AttributeError:
        return []


# ---------------------------------------------------------------------------
# OpenAI uyumlu servisler (DeepSeek, OpenAI, OpenRouter)
# ---------------------------------------------------------------------------


def _taban(sag):
    ortam = os.environ.get("TRCEVIRI_%s_URL" % sag.upper())
    return (ortam or SAGLAYICILAR[sag]["taban"]).rstrip("/")


def _openai_hata_coz(kod, govde, basliklar=None):
    try:
        metin = govde.decode("utf-8", "replace") if isinstance(govde, bytes) else (govde or "")
    except Exception:
        metin = ""
    mesaj = metin[:500]
    tur = ""
    try:
        veri = json.loads(metin)
        hata = veri.get("error") if isinstance(veri, dict) else None
        if isinstance(hata, dict):
            mesaj = str(hata.get("message") or mesaj)[:500]
            tur = str(hata.get("code") or hata.get("type") or "")
        elif isinstance(hata, str):
            mesaj = hata[:500]
    except Exception:
        pass
    bekle = None
    if basliklar is not None:
        try:
            bekle = gemini._sure_coz(basliklar.get("Retry-After"))
        except Exception:
            bekle = None
    kucuk = mesaj.lower()

    if kod == 402 or tur == "insufficient_quota" or "insufficient balance" in kucuk or "insufficient credits" in kucuk:
        return ApiHatasi(gemini.KREDI, "Hesapta bakiye/kredi kalmadı", kod, ham=mesaj)
    if kod == 401:
        return ApiHatasi(gemini.GECERSIZ_ANAHTAR, "API anahtarı geçersiz", kod, ham=mesaj)
    if kod == 403:
        return ApiHatasi(gemini.GECERSIZ_ANAHTAR, "Anahtarın yetkisi yok: " + mesaj[:150], kod, ham=mesaj)
    if kod == 404:
        return ApiHatasi(gemini.MODEL_YOK, "Model bulunamadı: " + mesaj[:150], kod, ham=mesaj)
    if kod == 429:
        return ApiHatasi(gemini.KOTA_DAKIKA, "Hız sınırı aşıldı", kod, bekle=bekle, ham=mesaj)
    if kod == 413:
        return ApiHatasi(gemini.GECERSIZ_ISTEK, "İstek çok büyük", kod, ham=mesaj)
    if kod in (400, 422):
        if "model" in kucuk and ("not exist" in kucuk or "not found" in kucuk or "invalid model" in kucuk):
            return ApiHatasi(gemini.MODEL_YOK, "Model desteklenmiyor: " + mesaj[:150], kod, ham=mesaj)
        return ApiHatasi(gemini.GECERSIZ_ISTEK, mesaj[:300], kod, ham=mesaj)
    if kod is not None and kod >= 500:
        return ApiHatasi(gemini.SUNUCU, "Sunucu hatası / aşırı yoğunluk", kod, bekle=bekle, ham=mesaj)
    return ApiHatasi(gemini.SUNUCU, "Beklenmeyen yanıt: " + mesaj[:200], kod, bekle=bekle, ham=mesaj)


def _openai_basliklar(anahtar):
    return {"Authorization": "Bearer " + anahtar, "Accept": "application/json"}


def _openai_uret(sag, model, anahtar, istek, ayar, ozl):
    sistem = istek.sistem + ("\n\n" + istek.degisken if istek.degisken else "")
    govde = {
        "model": model,
        "messages": [{"role": "system", "content": sistem}, {"role": "user", "content": istek.kullanici}],
    }
    if ozl.get("json", True):
        govde["response_format"] = {"type": "json_object"}
    if ozl.get("sicaklik", True):
        govde["temperature"] = ayar.get("sicaklik", 0.35)
    if ozl.get("en_fazla", True):
        govde["max_tokens"] = min(int(ayar.get("en_fazla_cikti_token", 16384)), 8192)
    veri = json.dumps(govde, ensure_ascii=False).encode("utf-8")
    ham = gemini.http_istek(_taban(sag) + "/chat/completions", _openai_basliklar(anahtar), veri,
                            ayar.get("zaman_asimi_sn", 240), _openai_hata_coz)
    try:
        yanit = json.loads(ham.decode("utf-8", "replace"))
    except Exception:
        raise ApiHatasi(gemini.BOS_YANIT, "Yanıt JSON olarak çözülemedi")
    if not isinstance(yanit, dict):
        raise ApiHatasi(gemini.BOS_YANIT, "Yanıt JSON nesnesi değil")
    if isinstance(yanit.get("error"), dict):
        h = yanit["error"]
        raise _openai_hata_coz(int(h.get("code") or 500) if str(h.get("code") or "").isdigit() else 500,
                               json.dumps({"error": h}).encode("utf-8"))
    secenekler = yanit.get("choices") or []
    if not secenekler or not isinstance(secenekler[0], dict):
        raise ApiHatasi(gemini.BOS_YANIT, "Yanıtta seçenek yok")
    secenek = secenekler[0]
    metin = ((secenek.get("message") or {}).get("content")) or ""
    if not isinstance(metin, str):
        metin = ""
    neden = secenek.get("finish_reason")
    if neden == "content_filter":
        raise ApiHatasi(gemini.ENGELLENDI, "Yanıt içerik filtresine takıldı", kismi=metin)
    if neden == "length":
        raise ApiHatasi(gemini.KESILDI, "Yanıt token sınırında kesildi", kismi=metin)
    if not metin.strip():
        raise ApiHatasi(gemini.BOS_YANIT, "Boş yanıt (neden: %s)" % neden)
    u = yanit.get("usage") or {}
    toplam = int(u.get("prompt_tokens", 0) or 0)
    okuma = int(u.get("prompt_cache_hit_tokens", 0) or 0) or \
        int(((u.get("prompt_tokens_details") or {}).get("cached_tokens", 0)) or 0)
    return metin, _kullanim(max(0, toplam - okuma), u.get("completion_tokens", 0), okuma, 0, yanit.get("model") or model)


def _openai_modeller(sag, anahtar):
    ham = gemini.http_istek(_taban(sag) + "/models", _openai_basliklar(anahtar), None, 30, _openai_hata_coz)
    try:
        veri = json.loads(ham.decode("utf-8", "replace"))
    except Exception:
        raise ApiHatasi(gemini.BOS_YANIT, "Model listesi çözülemedi")
    return [str(m.get("id")) for m in (veri.get("data") or []) if isinstance(m, dict) and m.get("id")]


def modelleri_listele(saglayici, anahtar):
    """Anahtarın erişebildiği modeller. Ücret/kota harcamaz; anahtar denemesi için de kullanılır."""
    if saglayici == "gemini":
        return gemini.modelleri_listele(anahtar)
    if saglayici == "claude":
        return _claude_modeller(anahtar)
    return _openai_modeller(saglayici, anahtar)


# ---------------------------------------------------------------------------
# Maliyet
# ---------------------------------------------------------------------------


def fiyat_bul(hedef, fiyatlar=None):
    """Modelin fiyatı [girdi, çıktı, önbellek okuma, önbellek yazma] (1M token başına $) ya da None."""
    sag, model = hedef_coz(hedef)
    if not ucretli_mi(sag):
        return [0.0, 0.0, 0.0, 0.0]
    tablo = dict(VARSAYILAN_FIYATLAR)
    if isinstance(fiyatlar, dict):
        tablo.update(fiyatlar)
    adaylar = [model, model.split("/")[-1]]
    for a in adaylar:
        f = tablo.get(a)
        if isinstance(f, (list, tuple)) and len(f) >= 2:
            try:
                f = [float(x) for x in f]
            except Exception:
                return None
            if len(f) == 2:
                f.append(f[0] * 0.1)        # önbellekten okuma ~ girdinin %10'u
            if len(f) == 3:
                f.append(f[0] * 1.25)       # önbelleğe yazma ~ girdinin 1,25 katı
            return f[:4]
    # Tarih ekli ya da benzer adlı model: en uzun önek eşleşmesi
    for anahtar in sorted(tablo, key=len, reverse=True):
        if model.startswith(anahtar):
            return fiyat_bul(hedef_adi(sag, anahtar), fiyatlar)
    return None


def maliyet(hedef, kullanim, fiyatlar=None):
    """Bir isteğin yaklaşık maliyeti (ABD doları). Fiyat bilinmiyorsa None."""
    f = fiyat_bul(hedef, fiyatlar)
    if f is None:
        return None
    return (kullanim.get("girdi", 0) * f[0] + kullanim.get("cikti", 0) * f[1] +
            kullanim.get("onbellek_okuma", 0) * f[2] + kullanim.get("onbellek_yazma", 0) * f[3]) / 1e6


def maliyet_tahmini(hedef, ayar, kaynak_karakter, satir_sayisi, editor_orani=0.0, fiyatlar=None):
    """Bir oyunun çevirisinin kabaca maliyet tahmini (ABD doları) ya da None."""
    f = fiyat_bul(hedef, fiyatlar)
    if f is None:
        return None
    if not satir_sayisi:
        return 0.0
    paket = max(1.0, float(ayar.get("paket_satir", 40)))
    istek_sayisi = (satir_sayisi / paket) * (1.0 + editor_orani) + 2
    kaynak_token = kaynak_karakter / 3.6
    sistem_token = 6000.0
    baglam_token = 900.0
    sag, _m = hedef_coz(hedef)
    dusunme = {"low": 600.0, "medium": 1800.0, "high": 4000.0, "xhigh": 8000.0, "max": 12000.0}.get(
        ayar.get("claude_efor", "medium"), 1800.0) if sag == "claude" else 0.0
    girdi = istek_sayisi * baglam_token + kaynak_token * 1.3 * (1.0 + editor_orani)
    okuma = istek_sayisi * sistem_token
    cikti = kaynak_token * 1.7 * (1.0 + editor_orani) + istek_sayisi * dusunme
    return (girdi * f[0] + okuma * f[2] + cikti * f[1]) / 1e6
