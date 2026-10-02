"""Testler için sahte Gemini API sunucusu.

Gerçek API'nin yanıt biçimini taklit eder ve hata senaryolarını canlandırır:
geçersiz anahtar, günlük/dakikalık kota, sunucu hatası, güvenlik engeli,
bozuk JSON, eksik satır, bozulmuş değişken, desteklenmeyen özellik.
"""

import http.server
import json
import re
import threading

_TOKEN_RE = re.compile(r"\{\{|\{[^{}]*\}|\[\[|\[[^\[\]]*\]|<t\d+>|%%|%\([A-Za-z_]\w*\)[sdif]|%[sdifr](?![A-Za-z])")


def sahte_cevir(metin):
    """Korunan parçalara dokunmadan kelimeleri ters çevirir ve sonuna 'ş' ekler."""
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
        self.gecersiz_anahtarlar = set()
        self.gunluk_biten = set()          # (anahtar, model)
        self.gunluk_sonra = {}             # (anahtar, model) -> kaç başarılı istekten sonra günlük kota bitsin
        self.dakika_hatasi = {}            # anahtar -> kaç kez 429 dakikalık verilsin
        self.sunucu_hatasi = 0
        self.engelli_kelimeler = []
        self.reddeden_modeller = set()     # bu modeller her isteği "invalid argument" ile reddeder
        self.engelli_sadece_model = None   # verilirse engel sadece bu modelde uygulanır
        self.bozuk_json = 0
        self.eksik_id = 0
        self.token_boz = {}                # kaynak alt metni -> kaç kez bozulsun
        self.desteklenmeyen = {}           # model -> {"dusunme", "sema", ...}
        self.istekler = []                 # (anahtar, model, satir_sayisi)
        self.basarili = {}                 # (anahtar, model) -> sayı
        self.gecikme = 0.0


class _Isleyici(http.server.BaseHTTPRequestHandler):

    senaryo = None

    def log_message(self, *a):
        pass

    def _gonder(self, kod, veri):
        govde = json.dumps(veri).encode("utf-8") if not isinstance(veri, bytes) else veri
        self.send_response(kod)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(govde)))
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

    def do_GET(self):
        s = self.senaryo
        if not self.path.startswith("/v1beta/models"):
            return self._hata(404, "NOT_FOUND", "yok")
        if self._anahtar_kontrol() is None:
            return
        self._gonder(200, {"models": [
            {"name": "models/" + m, "supportedGenerationMethods": ["generateContent", "countTokens"]} for m in s.modeller
        ] + [{"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]}]})

    def do_POST(self):
        s = self.senaryo
        uzunluk = int(self.headers.get("Content-Length", "0"))
        ham = self.rfile.read(uzunluk)
        m = re.match(r"^/v1beta/models/([^:]+):generateContent$", self.path)
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
        veri = json.loads(kullanici)

        if "terimler" in veri:
            cikti = [{"m": t["m"], "c": ("Anne" if t["m"] == "Mom" else t["m"]), "tur": "isim", "cinsiyet": "kadın"}
                     for t in veri["terimler"]]
            return self._basarili_yanit(anahtar, model, json.dumps(cikti, ensure_ascii=False), len(cikti))

        satirlar = veri.get("satirlar", [])
        with s.kilit:
            s.istekler.append((anahtar, model, len(satirlar)))

        for st in satirlar:
            if any(k in st["m"] for k in s.engelli_kelimeler) and s.engelli_sadece_model in (None, model):
                return self._gonder(200, {"candidates": [{"finishReason": "SAFETY", "content": {"parts": []}}]})

        with s.kilit:
            if s.bozuk_json > 0:
                s.bozuk_json -= 1
                return self._basarili_yanit(anahtar, model, "Bu bir JSON değil :)", 0)

        cikti = []
        for st in satirlar:
            c = sahte_cevir(st["m"])
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

        return self._basarili_yanit(anahtar, model, json.dumps(cikti, ensure_ascii=False), len(satirlar))

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


class SahteGemini(object):
    """with SahteGemini() as sunucu: ... sunucu.taban (API adresi), sunucu.senaryo"""

    def __init__(self):
        self.senaryo = Senaryo()
        isleyici = type("Isleyici", (_Isleyici,), {"senaryo": self.senaryo})
        self.sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), isleyici)
        self.sunucu.daemon_threads = True
        self.taban = "http://127.0.0.1:%d/v1beta" % self.sunucu.server_address[1]
        self._is = threading.Thread(target=self.sunucu.serve_forever, daemon=True)

    def __enter__(self):
        self._is.start()
        return self

    def __exit__(self, *a):
        self.sunucu.shutdown()
        self.sunucu.server_close()


if __name__ == "__main__":
    # Elle deneme / uçtan uca test için: python sahte_gemini.py 8765
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    s = SahteGemini()
    s.sunucu.server_close()
    isleyici = type("Isleyici", (_Isleyici,), {"senaryo": s.senaryo})
    sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", port), isleyici)
    print("Sahte Gemini: http://127.0.0.1:%d/v1beta" % port)
    sunucu.serve_forever()
