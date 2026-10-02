"""Testler için sahte yapay zeka sunucusu (Gemini, Claude, OpenAI uyumlu).

Gerçek API'lerin yanıt biçimini taklit eder ve hata senaryolarını canlandırır:
geçersiz anahtar, günlük/dakikalık kota, sunucu hatası, güvenlik engeli,
bozuk JSON, eksik satır, bozulmuş değişken, desteklenmeyen özellik, bakiye
bitmesi, Claude'un reddetmesi.

Yollar:
  Gemini : /v1beta/models, /v1beta/models/<model>:generateContent
  Claude : /v1/models, /v1/messages (akış/SSE dahil)
  OpenAI : /oa/models, /oa/chat/completions   (DeepSeek/OpenAI/OpenRouter taklidi)
"""

import http.server
import json
import re
import threading

_TOKEN_RE = re.compile(r"\{\{|\{[^{}]*\}|\[\[|\[[^\[\]]*\]|<t\d+>|%%|%\([A-Za-z_]\w*\)[sdif]|%[sdifr](?![A-Za-z])")


def sahte_cevir(metin, ek_isaretle=False):
    """Korunan parçalara dokunmadan kelimeleri ters çevirir ve sonuna 'ş' ekler.

    ek_isaretle: "[name]'s" -> "[name]{ek=in}" (yapay zekanın ek işareti yazmasını taklit eder)
    """
    if ek_isaretle:
        metin = re.sub(r"(\[[^\[\]]+\])'s\b", r"\1{ek=in}", metin)
    parcalar = []
    konum = 0
    for m in _TOKEN_RE.finditer(metin):
        parcalar.append(_kelimeler(metin[konum:m.start()]))
        parcalar.append(m.group(0))
        konum = m.end()
    parcalar.append(_kelimeler(metin[konum:]))
    return "".join(parcalar)


def _kelimeler(s):
    return re.sub(r"[A-Za-z]{2,}", lambda m: m.group(0)[::-1].lower() + "ş", s)


class Senaryo(object):

    def __init__(self):
        self.kilit = threading.RLock()
        self.modeller = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
        self.claude_modeller = ["claude-opus-5-5", "claude-sonnet-5-5"]
        self.oa_modeller = ["deepseek-chat", "gpt-5-mini"]
        self.gecersiz_anahtarlar = set()
        self.kredisiz_anahtarlar = set()   # Claude/OpenAI uyumlu: bakiye bitti
        self.gunluk_biten = set()          # (anahtar, model)
        self.gunluk_sonra = {}             # (anahtar, model) -> kaç başarılı istekten sonra günlük kota bitsin
        self.dakika_hatasi = {}            # anahtar -> kaç kez 429 dakikalık verilsin
        self.sunucu_hatasi = 0
        self.ag_kesik = 0                  # kaç istek bağlantı kesilerek yanıtsız bırakılsın
        self.engelli_kelimeler = []
        self.reddeden_modeller = set()     # bu modeller her isteği "invalid argument" ile reddeder
        self.engelli_sadece_model = None   # verilirse engel sadece bu modelde uygulanır
        self.bozuk_json = 0
        self.eksik_id = 0
        self.token_boz = {}                # kaynak alt metni -> kaç kez bozulsun
        self.desteklenmeyen = {}           # model -> {"dusunme", "sema", ...}
        self.ek_isaretle = False
        self.editor_eki = " eh"            # editör isteğinde taslağın sonuna eklenen
        self.istekler = []                 # (anahtar, model, satir_sayisi)
        self.istek_turleri = []            # "ceviri" / "editor" / "sozluk" / "karakter"
        self.claude_govdeleri = []         # Claude'a gelen istek gövdeleri (test denetimi için)
        self.claude_basliklari = []
        self.oa_govdeleri = []
        self.basarili = {}                 # (anahtar, model) -> sayı
        self.gecikme = 0.0


def _cevap_uret(s, anahtar, model, kullanici):
    """Kullanıcı mesajına (JSON) göre yanıt metni üretir.

    Döndürür: ("tamam", metin, satır_sayısı) | ("engel", None, 0)
    """
    veri = json.loads(kullanici)

    if "terimler" in veri:
        with s.kilit:
            s.istek_turleri.append("sozluk")
        cikti = [{"m": t["m"], "c": ("Anne" if t["m"] == "Mom" else t["m"]), "tur": "isim", "cinsiyet": "kadın"}
                 for t in veri["terimler"]]
        return "tamam", json.dumps({"terimler": cikti}, ensure_ascii=False), len(cikti)

    if "ciftler" in veri and "karakterler" in veri:
        with s.kilit:
            s.istek_turleri.append("karakter")
        kartlar = [{"ad": k["ad"], "cinsiyet": "kadın", "yas": "genç yetişkin", "uslup": "Neşeli ve samimi; kısa cümleler."}
                   for k in veri["karakterler"]]
        hitap = [{"konusan": c["konusan"], "dinleyen": c["dinleyen"], "hitap": "sen"} for c in veri["ciftler"]]
        return "tamam", json.dumps({"karakterler": kartlar, "hitap": hitap}, ensure_ascii=False), len(kartlar)

    satirlar = veri.get("satirlar", [])
    editor = any("taslak" in st for st in satirlar)
    with s.kilit:
        s.istekler.append((anahtar, model, len(satirlar)))
        s.istek_turleri.append("editor" if editor else "ceviri")

    for st in satirlar:
        if any(k in st["m"] for k in s.engelli_kelimeler) and s.engelli_sadece_model in (None, model):
            return "engel", None, 0

    with s.kilit:
        if s.bozuk_json > 0:
            s.bozuk_json -= 1
            return "tamam", "Bu bir JSON değil :)", 0

    cikti = []
    for st in satirlar:
        if editor:
            c = st["taslak"] + s.editor_eki
        else:
            c = sahte_cevir(st["m"], s.ek_isaretle)
        with s.kilit:
            for parca, kalan in list(s.token_boz.items()):
                if parca in st["m"] and kalan > 0:
                    s.token_boz[parca] = kalan - 1
                    c = re.sub(r"\[[^\[\]]*\]", "[isim]", c)
        cikti.append({"id": st["id"], "c": c})

    with s.kilit:
        if s.eksik_id > 0 and len(cikti) > 1:
            s.eksik_id -= 1
            cikti = cikti[:-1]

    return "tamam", json.dumps({"ceviriler": cikti}, ensure_ascii=False), len(satirlar)


class _Isleyici(http.server.BaseHTTPRequestHandler):

    senaryo = None
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _gonder(self, kod, veri, basliklar=None):
        govde = json.dumps(veri).encode("utf-8") if not isinstance(veri, bytes) else veri
        self.send_response(kod)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(govde)))
        for k, v in (basliklar or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(govde)

    def _hata(self, kod, durum, mesaj, ayrintilar=None):
        self._gonder(kod, {"error": {"code": kod, "status": durum, "message": mesaj, "details": ayrintilar or []}})

    def _anahtar_kontrol(self):
        anahtar = self.headers.get("x-goog-api-key", "")
        if anahtar in self.senaryo.gecersiz_anahtarlar or not anahtar:
            self._hata(400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key.",
                       [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID"}])
            return None
        return anahtar

    def _govde_oku(self):
        uzunluk = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(uzunluk)

    def _ag_kes(self):
        """Bağlantıyı yanıt vermeden kapatır (internet kesintisi taklidi)."""
        s = self.senaryo
        with s.kilit:
            if s.ag_kesik > 0:
                s.ag_kesik -= 1
                self.close_connection = True
                try:
                    self.connection.shutdown(2)
                except Exception:
                    pass
                return True
        return False

    # ------------------------------------------------------------------

    def do_GET(self):
        s = self.senaryo
        yol = self.path.split("?", 1)[0]
        if yol.startswith("/v1/models"):
            if not self._claude_anahtar():
                return
            veri = [{"id": m, "type": "model", "display_name": m, "created_at": "2026-01-01T00:00:00Z"}
                    for m in s.claude_modeller]
            return self._gonder(200, {"data": veri, "has_more": False,
                                      "first_id": veri[0]["id"], "last_id": veri[-1]["id"]})
        if yol.startswith("/oa/models"):
            if not self._oa_anahtar():
                return
            return self._gonder(200, {"object": "list", "data": [{"id": m, "object": "model"} for m in s.oa_modeller]})
        if not yol.startswith("/v1beta/models"):
            return self._hata(404, "NOT_FOUND", "yok")
        if self._anahtar_kontrol() is None:
            return
        self._gonder(200, {"models": [
            {"name": "models/" + m, "supportedGenerationMethods": ["generateContent", "countTokens"]} for m in s.modeller
        ] + [{"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]}]})

    def do_POST(self):
        yol = self.path.split("?", 1)[0]
        ham = self._govde_oku()
        if self._ag_kes():
            return
        if yol == "/v1/messages":
            return self._claude(ham)
        if yol == "/oa/chat/completions":
            return self._oa(ham)
        return self._gemini(yol, ham)

    # ------------------------------------------------------------------
    # Gemini

    def _gemini(self, yol, ham):
        s = self.senaryo
        m = re.match(r"^/v1beta/models/([^:]+):generateContent$", yol)
        if not m:
            return self._hata(404, "NOT_FOUND", "yol yok")
        model = m.group(1)
        anahtar = self._anahtar_kontrol()
        if anahtar is None:
            return
        if model not in s.modeller:
            return self._hata(404, "NOT_FOUND", "models/%s is not found for API version v1beta" % model)

        if model in s.reddeden_modeller:
            return self._hata(400, "INVALID_ARGUMENT", "Request contains an invalid argument.")
        govde = json.loads(ham.decode("utf-8"))
        gen = govde.get("generationConfig", {})
        desteklenmeyen = s.desteklenmeyen.get(model, set())
        if "dusunme" in desteklenmeyen and "thinkingConfig" in gen:
            return self._hata(400, "INVALID_ARGUMENT", "Invalid JSON payload received. Unknown name \"thinkingConfig\" at 'generation_config'")
        if "sema" in desteklenmeyen and "responseSchema" in gen:
            return self._hata(400, "INVALID_ARGUMENT", "response_schema is not supported for this model")

        with s.kilit:
            if (anahtar, model) in s.gunluk_biten:
                return self._hata(429, "RESOURCE_EXHAUSTED", "You exceeded your current quota.", [
                    {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
                        {"quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
                         "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
                    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "30s"}])
            if s.dakika_hatasi.get(anahtar, 0) > 0:
                s.dakika_hatasi[anahtar] -= 1
                return self._hata(429, "RESOURCE_EXHAUSTED", "Quota exceeded per minute", [
                    {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
                        {"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},
                    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "0.2s"}])
            if s.sunucu_hatasi > 0:
                s.sunucu_hatasi -= 1
                return self._hata(503, "UNAVAILABLE", "The model is overloaded. Please try again later.")

        if "systemInstruction" in govde:
            kullanici = govde["contents"][0]["parts"][0]["text"]
        else:
            kullanici = govde["contents"][0]["parts"][0]["text"].split("\n\n---\n\n", 1)[-1]

        durum, metin, n = _cevap_uret(s, anahtar, model, kullanici)
        if durum == "engel":
            return self._gonder(200, {"candidates": [{"finishReason": "SAFETY", "content": {"parts": []}}]})
        return self._basarili_yanit(anahtar, model, metin, n)

    def _basarili_yanit(self, anahtar, model, metin, n):
        s = self.senaryo
        with s.kilit:
            s.basarili[(anahtar, model)] = s.basarili.get((anahtar, model), 0) + 1
            sinir = s.gunluk_sonra.get((anahtar, model))
            if sinir is not None and s.basarili[(anahtar, model)] >= sinir:
                s.gunluk_biten.add((anahtar, model))
        self._gonder(200, {
            "candidates": [{"content": {"parts": [{"text": metin}], "role": "model"}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 10 * n},
        })

    # ------------------------------------------------------------------
    # Claude (Anthropic Messages API)

    def _claude_hata(self, kod, tur, mesaj):
        self._gonder(kod, {"type": "error", "error": {"type": tur, "message": mesaj}})

    def _claude_anahtar(self):
        s = self.senaryo
        anahtar = self.headers.get("x-api-key", "")
        if not anahtar or anahtar in s.gecersiz_anahtarlar:
            self._claude_hata(401, "authentication_error", "invalid x-api-key")
            return None
        return anahtar

    def _claude(self, ham):
        s = self.senaryo
        anahtar = self._claude_anahtar()
        if anahtar is None:
            return
        govde = json.loads(ham.decode("utf-8"))
        with s.kilit:
            s.claude_govdeleri.append(govde)
            s.claude_basliklari.append(dict(self.headers.items()))
        model = govde.get("model")
        if anahtar in s.kredisiz_anahtarlar:
            return self._claude_hata(400, "invalid_request_error",
                                     "Your credit balance is too low to access the Anthropic API. "
                                     "Please go to Plans & Billing to upgrade or purchase credits.")
        if model not in s.claude_modeller:
            return self._claude_hata(404, "not_found_error", "model: %s" % model)
        with s.kilit:
            if s.dakika_hatasi.get(anahtar, 0) > 0:
                s.dakika_hatasi[anahtar] -= 1
                return self._gonder(429, {"type": "error", "error": {"type": "rate_limit_error", "message": "rate limited"}},
                                    {"retry-after": "1"})
            if s.sunucu_hatasi > 0:
                s.sunucu_hatasi -= 1
                return self._claude_hata(529, "overloaded_error", "Overloaded")
        kullanici = govde["messages"][0]["content"]
        if isinstance(kullanici, list):
            kullanici = "".join(b.get("text", "") for b in kullanici)
        durum, metin, n = _cevap_uret(s, anahtar, model, kullanici)
        neden = "end_turn"
        if durum == "engel":
            metin, neden = "", "refusal"
        usage = {"input_tokens": 1000, "output_tokens": 20 * max(1, n),
                 "cache_read_input_tokens": 5000, "cache_creation_input_tokens": 0}
        if govde.get("stream"):
            return self._claude_akis(model, metin, neden, usage)
        icerik = [{"type": "text", "text": metin}] if metin else []
        self._gonder(200, {"id": "msg_1", "type": "message", "role": "assistant", "model": model, "content": icerik,
                           "stop_reason": neden, "stop_sequence": None, "usage": usage})

    def _claude_akis(self, model, metin, neden, usage):
        olaylar = [("message_start", {"type": "message_start", "message": {
            "id": "msg_1", "type": "message", "role": "assistant", "model": model, "content": [],
            "stop_reason": None, "stop_sequence": None,
            "usage": dict(usage, output_tokens=1)}})]
        if metin:
            olaylar.append(("content_block_start", {"type": "content_block_start", "index": 0,
                                                    "content_block": {"type": "text", "text": ""}}))
            yari = len(metin) // 2
            for parca in (metin[:yari], metin[yari:]):
                olaylar.append(("content_block_delta", {"type": "content_block_delta", "index": 0,
                                                        "delta": {"type": "text_delta", "text": parca}}))
            olaylar.append(("content_block_stop", {"type": "content_block_stop", "index": 0}))
        olaylar.append(("message_delta", {"type": "message_delta", "delta": {"stop_reason": neden, "stop_sequence": None},
                                          "usage": {"output_tokens": usage["output_tokens"]}}))
        olaylar.append(("message_stop", {"type": "message_stop"}))
        govde = "".join("event: %s\ndata: %s\n\n" % (ad, json.dumps(v, ensure_ascii=False)) for ad, v in olaylar)
        govde = govde.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)

    # ------------------------------------------------------------------
    # OpenAI uyumlu

    def _oa_anahtar(self):
        s = self.senaryo
        yetki = self.headers.get("Authorization", "")
        anahtar = yetki[7:] if yetki.startswith("Bearer ") else ""
        if not anahtar or anahtar in s.gecersiz_anahtarlar:
            self._gonder(401, {"error": {"message": "Authentication Fails (invalid key)", "type": "authentication_error"}})
            return None
        return anahtar

    def _oa(self, ham):
        s = self.senaryo
        anahtar = self._oa_anahtar()
        if anahtar is None:
            return
        govde = json.loads(ham.decode("utf-8"))
        with s.kilit:
            s.oa_govdeleri.append(govde)
        if anahtar in s.kredisiz_anahtarlar:
            return self._gonder(402, {"error": {"message": "Insufficient Balance", "type": "unknown_error"}})
        model = govde.get("model")
        if model not in s.oa_modeller:
            return self._gonder(400, {"error": {"message": "Model Not Exist", "type": "invalid_request_error"}})
        if "en_fazla" in s.desteklenmeyen.get(model, set()) and "max_tokens" in govde:
            return self._gonder(400, {"error": {"message": "Unsupported parameter: 'max_tokens'", "type": "invalid_request_error"}})
        kullanici = govde["messages"][-1]["content"]
        durum, metin, n = _cevap_uret(s, anahtar, model, kullanici)
        neden = "stop"
        if durum == "engel":
            metin, neden = "", "content_filter"
        self._gonder(200, {"id": "c1", "object": "chat.completion", "model": model,
                           "choices": [{"index": 0, "message": {"role": "assistant", "content": metin}, "finish_reason": neden}],
                           "usage": {"prompt_tokens": 1000, "completion_tokens": 20 * max(1, n), "prompt_cache_hit_tokens": 800}})


class SahteGemini(object):
    """with SahteGemini() as sunucu: ... sunucu.taban (Gemini API adresi), sunucu.kok, sunucu.senaryo"""

    def __init__(self, port=0):
        self.senaryo = Senaryo()
        isleyici = type("Isleyici", (_Isleyici,), {"senaryo": self.senaryo})
        self.sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", port), isleyici)
        self.sunucu.daemon_threads = True
        self.kok = "http://127.0.0.1:%d" % self.sunucu.server_address[1]
        self.taban = self.kok + "/v1beta"
        self.oa_taban = self.kok + "/oa"
        self._is = threading.Thread(target=self.sunucu.serve_forever, daemon=True)

    def __enter__(self):
        self._is.start()
        return self

    def __exit__(self, *a):
        self.sunucu.shutdown()
        self.sunucu.server_close()


if __name__ == "__main__":
    # Elle deneme / uçtan uca test için: python sahte_gemini.py 8765 [ek]
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    s = SahteGemini(port)
    s.senaryo.ek_isaretle = "ek" in sys.argv[2:]
    print("Sahte sunucu: %s (Gemini: %s, OpenAI uyumlu: %s)" % (s.kok, s.taban, s.oa_taban))
    s.sunucu.serve_forever()
