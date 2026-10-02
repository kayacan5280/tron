"""Birim testleri: python -m unittest discover -s testler"""

import datetime
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rpyceviri import ayarlar, fontlar, gemini, istem, koruma, oyun, sozluk, zaman  # noqa: E402


class KorumaTestleri(unittest.TestCase):

    def test_dogru_ceviri_gecer(self):
        c, ciddi, suphe = koruma.dogrula("Hello, [name]! {i}Nice{/i} to meet you.", "Merhaba [name]! Seninle {i}tanıştığıma{/i} sevindim.")
        self.assertEqual(ciddi, [])
        self.assertIn("[name]", c)

    def test_degisken_cevrilirse_reddedilir(self):
        _c, ciddi, _s = koruma.dogrula("Hello, [name]!", "Merhaba, [isim]!")
        self.assertTrue(ciddi)

    def test_degisken_silinirse_reddedilir(self):
        _c, ciddi, _s = koruma.dogrula("You have [money] dollars.", "Hiç paran yok.")
        self.assertTrue(ciddi)

    def test_etiket_silinirse_reddedilir(self):
        _c, ciddi, _s = koruma.dogrula("Wait{w} what?", "Bekle, ne?")
        self.assertTrue(ciddi)

    def test_bilinmeyen_etiket_reddedilir(self):
        _c, ciddi, _s = koruma.dogrula("Hello.", "{gülüyor} Merhaba.")
        self.assertTrue(ciddi)

    def test_etiket_sirasi_bozuksa_reddedilir(self):
        _c, ciddi, _s = koruma.dogrula("{b}{i}Hey{/i}{/b}", "{b}{i}Hey{/b}{/i}")
        self.assertTrue(ciddi)
        _c, ciddi, _s = koruma.dogrula("{i}Hey{/i} you", "Sen {/i}hey{i}")
        self.assertTrue(ciddi)

    def test_tek_koseli_parantez_kacislanir(self):
        c, ciddi, _s = koruma.dogrula("He smiled.", "[gülümsedi] O gülümsedi.")
        # '[gülümsedi]' bir değişken gibi görünür ve kaynakta yok -> reddedilmeli (oyun çöker).
        self.assertTrue(ciddi)
        c, ciddi, _s = koruma.dogrula("Look at this.", "Şuna bak [ve gül.")
        self.assertEqual(ciddi, [])
        self.assertIn("[[ve", c)
        c, ciddi, _s = koruma.dogrula("Smile.", "Gülümse { lütfen.")
        self.assertEqual(ciddi, [])
        self.assertIn("{{", c)

    def test_kacis_ciftleri_korunur(self):
        c, ciddi, _s = koruma.dogrula("Use [[brackets]] and {{braces}.", "[[Köşeli]] ve {{süslü} kullan.")
        self.assertEqual(ciddi, [])
        # Yapay zeka çiftleri teke indirirse: tek '[' kaçışlanıp '[[' olur, eşleşir.
        c, ciddi, _s = koruma.dogrula("Use [[this.", "Şunu [ kullan.")
        self.assertEqual(ciddi, [])
        self.assertIn("[[", c)

    def test_bosluklar_korunur(self):
        c, ciddi, _s = koruma.dogrula("  Hello ", "Merhaba")
        self.assertEqual(c, "  Merhaba ")
        c, _ciddi, _s = koruma.dogrula("Version [config.version!t]\n", "Sürüm [config.version!t]")
        self.assertTrue(c.endswith("\n"))

    def test_tirnak_ve_onek_temizlenir(self):
        c, ciddi, _s = koruma.dogrula("Hello there.", '"Merhaba."')
        self.assertEqual(c, "Merhaba.")
        c, ciddi, _s = koruma.dogrula("Hello there.", "Çeviri: Merhaba.")
        self.assertEqual(c, "Merhaba.")
        c, ciddi, _s = koruma.dogrula('"Hi," she said.', '"Selam," dedi.')
        self.assertEqual(c, '"Selam," dedi.')

    def test_bos_ceviri_reddedilir(self):
        _c, ciddi, _s = koruma.dogrula("Hello", "   ")
        self.assertTrue(ciddi)

    def test_cevrilmemis_supheli(self):
        _c, ciddi, suphe = koruma.dogrula("This is an untranslated sentence.", "This is an untranslated sentence.")
        self.assertEqual(ciddi, [])
        self.assertTrue(suphe)

    def test_ingilizce_kalmis_supheli(self):
        _c, ciddi, suphe = koruma.dogrula("I think this is the best day of my life.", "I think it is the best day of your life ever.")
        self.assertEqual(ciddi, [])
        self.assertTrue(suphe)
        _c, ciddi, suphe = koruma.dogrula("I think this is the best day of my life.", "Bence bu hayatımın en güzel günü.")
        self.assertEqual(suphe, [])

    def test_cok_uzun_supheli(self):
        _c, ciddi, suphe = koruma.dogrula("Hi.", "Selam. " * 40)
        self.assertTrue(suphe)

    def test_yuzde(self):
        _c, ciddi, _s = koruma.dogrula("Saved as %s.", "%s olarak kaydedildi.")
        self.assertEqual(ciddi, [])
        _c, ciddi, _s = koruma.dogrula("50% off!", "%50 indirim!")
        self.assertEqual(ciddi, [])

    def test_cevrilecek_mi(self):
        self.assertFalse(koruma.cevrilecek_mi("..."))
        self.assertFalse(koruma.cevrilecek_mi("[name]"))
        self.assertFalse(koruma.cevrilecek_mi("{w=1.0}"))
        self.assertFalse(koruma.cevrilecek_mi("A"))
        self.assertFalse(koruma.cevrilecek_mi("123 !!!"))
        self.assertTrue(koruma.cevrilecek_mi("Hi"))
        self.assertTrue(koruma.cevrilecek_mi("[name]? Is that you?"))

    def test_maske(self):
        kaynak = "Hey [name], {b}look{/b}!"
        maskeli, harita = koruma.maskele(kaynak)
        self.assertNotIn("[", maskeli)
        self.assertEqual(len(harita), 3)
        geri = koruma.maske_kaldir("Hey <t0>, <t1>bak<t2>!", harita)
        self.assertEqual(geri, "Hey [name], {b}bak{/b}!")
        self.assertIsNone(koruma.maske_kaldir("Hey <t0>, bak<t2>!", harita))
        self.assertIsNone(koruma.maske_kaldir("<t0><t0><t1><t2>", harita))
        # Maske dışındaki serbest köşeli parantez kaçışlanır.
        self.assertEqual(koruma.maske_kaldir("<t0> [x <t1><t2>", harita), "[name] [[x {b}{/b}")

    def test_etiket_turleri(self):
        for k in ["{color=#ff0000}red{/color}", "{size=+10}big{/size}", "{a=https://x.com}link{/a}", "A{w=0.5}B{p}C{nw}",
                  "{#file_time}%A", "{image=heart.png} love", "{font=x.ttf}y{/font}", "{cps=20}slow{/cps}"]:
            _c, ciddi, _s = koruma.dogrula(k, k.replace("red", "kırmızı").replace("big", "büyük"))
            self.assertEqual(ciddi, [], k)


class IstemTestleri(unittest.TestCase):

    def test_json_cozumle(self):
        self.assertEqual(istem.json_cozumle('[{"id": "1", "c": "a"}]'), [{"id": "1", "c": "a"}])
        self.assertEqual(istem.json_cozumle('```json\n[{"id": "1", "c": "a"}]\n```'), [{"id": "1", "c": "a"}])
        self.assertEqual(istem.json_cozumle('İşte: [{"id": "1", "c": "a"}] tamam'), [{"id": "1", "c": "a"}])
        self.assertIsNone(istem.json_cozumle("json değil"))

    def test_ceviri_haritasi(self):
        self.assertEqual(istem.ceviri_haritasi([{"id": 1, "c": "a"}, {"id": "2", "ceviri": "b"}, {"x": 1}]), {"1": "a", "2": "b"})
        self.assertEqual(istem.ceviri_haritasi({"ceviriler": [{"id": "3", "c": "c"}]}), {"3": "c"})
        self.assertEqual(istem.ceviri_haritasi({"4": "d"}), {"4": "d"})

    def test_govde(self):
        ayar = dict(ayarlar.VARSAYILAN)
        g = istem.istek_govdesi("SİSTEM", "KULLANICI", ayar, {}, "gemini-2.5-flash", istem.CIKTI_SEMASI)
        self.assertIn("systemInstruction", g)
        self.assertEqual(g["generationConfig"]["thinkingConfig"], {"thinkingBudget": 0})
        self.assertEqual(g["generationConfig"]["responseSchema"]["type"], "OBJECT")
        self.assertNotIn("additionalProperties", json.dumps(g["generationConfig"]["responseSchema"]))
        self.assertEqual(len(g["safetySettings"]), 4)
        g = istem.istek_govdesi("S", "K", ayar, {"sistem": False, "dusunme": False, "json": False, "guvenlik": False}, "x")
        self.assertNotIn("systemInstruction", g)
        self.assertNotIn("thinkingConfig", g["generationConfig"])
        self.assertNotIn("responseMimeType", g["generationConfig"])
        self.assertNotIn("safetySettings", g)
        self.assertTrue(g["contents"][0]["parts"][0]["text"].startswith("S"))

    def test_kapatilacak_ozellik(self):
        self.assertEqual(istem.kapatilacak_ozellik("Unknown name \"thinkingConfig\""), "dusunme")
        self.assertEqual(istem.kapatilacak_ozellik("response_schema is not supported"), "sema")
        self.assertEqual(istem.kapatilacak_ozellik("Developer instruction is not enabled"), "sistem")
        self.assertIsNone(istem.kapatilacak_ozellik("Request contains an invalid argument."))


class ZamanTestleri(unittest.TestCase):

    def test_kota_sifirlama_yaz(self):
        an = datetime.datetime(2026, 7, 10, 12, 0, tzinfo=zaman.UTC)  # PDT (UTC-7)
        s = zaman.sonraki_kota_sifirlama(an)
        self.assertEqual(s, datetime.datetime(2026, 7, 11, 7, 0, tzinfo=zaman.UTC))

    def test_kota_sifirlama_kis(self):
        an = datetime.datetime(2026, 1, 10, 12, 0, tzinfo=zaman.UTC)  # PST (UTC-8)
        s = zaman.sonraki_kota_sifirlama(an)
        self.assertEqual(s, datetime.datetime(2026, 1, 11, 8, 0, tzinfo=zaman.UTC))

    def test_gece_yarisindan_once(self):
        an = datetime.datetime(2026, 7, 11, 6, 59, tzinfo=zaman.UTC)  # PDT 23:59
        self.assertEqual(zaman.sonraki_kota_sifirlama(an), datetime.datetime(2026, 7, 11, 7, 0, tzinfo=zaman.UTC))

    def test_yaz_saati_gecisleri(self):
        # 2026: 8 Mart başlar, 1 Kasım biter
        self.assertFalse(zaman.pasifik_yaz_saati_mi(datetime.datetime(2026, 3, 8, 9, 59, tzinfo=zaman.UTC)))
        self.assertTrue(zaman.pasifik_yaz_saati_mi(datetime.datetime(2026, 3, 8, 10, 0, tzinfo=zaman.UTC)))
        self.assertTrue(zaman.pasifik_yaz_saati_mi(datetime.datetime(2026, 11, 1, 8, 59, tzinfo=zaman.UTC)))
        self.assertFalse(zaman.pasifik_yaz_saati_mi(datetime.datetime(2026, 11, 1, 9, 0, tzinfo=zaman.UTC)))

    def test_iso(self):
        an = datetime.datetime(2026, 10, 2, 7, 0, tzinfo=zaman.UTC)
        self.assertEqual(zaman.iso_coz(zaman.iso(an)), an)
        self.assertIsNone(zaman.iso_coz("bozuk"))


class GeminiHataTestleri(unittest.TestCase):

    def _hata(self, kod, veri):
        return gemini.hata_coz(kod, json.dumps(veri).encode("utf-8"))

    def test_gecersiz_anahtar(self):
        h = self._hata(400, {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT",
                                       "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID"}]}})
        self.assertEqual(h.tur, gemini.GECERSIZ_ANAHTAR)

    def test_gunluk_kota(self):
        h = self._hata(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "You exceeded your current quota",
                                       "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
                                           {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
                                           {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "41s"}]}})
        self.assertEqual(h.tur, gemini.KOTA_GUNLUK)
        self.assertEqual(h.bekle, 41)

    def test_dakikalik_kota(self):
        h = self._hata(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "x",
                                       "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
                                           {"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]}]}})
        self.assertEqual(h.tur, gemini.KOTA_DAKIKA)
        h = self._hata(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "x",
                                       "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
                                           {"quotaId": "GenerateContentInputTokensPerModelPerMinute-FreeTier"}]}]}})
        self.assertEqual(h.tur, gemini.KOTA_DAKIKA)

    def test_belirsiz_kota(self):
        h = self._hata(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "Resource has been exhausted"}})
        self.assertEqual(h.tur, gemini.KOTA)

    def test_sifir_limit(self):
        h = self._hata(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded for metric: x, limit: 0"}})
        self.assertEqual(h.tur, gemini.KOTA_GUNLUK)

    def test_diger(self):
        self.assertEqual(self._hata(404, {"error": {"code": 404, "message": "models/x is not found", "status": "NOT_FOUND"}}).tur, gemini.MODEL_YOK)
        self.assertEqual(self._hata(503, {"error": {"code": 503, "message": "overloaded", "status": "UNAVAILABLE"}}).tur, gemini.SUNUCU)
        self.assertEqual(self._hata(500, {}).tur, gemini.SUNUCU)
        self.assertEqual(gemini.hata_coz(502, b"<html>bad gateway</html>").tur, gemini.SUNUCU)
        self.assertEqual(self._hata(403, {"error": {"code": 403, "message": "Your API key was reported as leaked.", "status": "PERMISSION_DENIED"}}).tur, gemini.GECERSIZ_ANAHTAR)
        self.assertEqual(self._hata(400, {"error": {"code": 400, "message": "User location is not supported for the API use.", "status": "FAILED_PRECONDITION"}}).tur, gemini.BOLGE)
        self.assertEqual(self._hata(400, {"error": {"code": 400, "message": "Invalid value at 'x'", "status": "INVALID_ARGUMENT"}}).tur, gemini.GECERSIZ_ISTEK)

    def test_yanit_coz(self):
        metin, _k = gemini.yanit_coz({"candidates": [{"content": {"parts": [{"text": "dü", "thought": True}, {"text": "[1]"}]}, "finishReason": "STOP"}]})
        self.assertEqual(metin, "[1]")
        for veri, tur in [
            ({"promptFeedback": {"blockReason": "PROHIBITED_CONTENT"}}, gemini.ENGELLENDI),
            ({"candidates": [{"finishReason": "SAFETY"}]}, gemini.ENGELLENDI),
            ({"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "[{"}]}}]}, gemini.KESILDI),
            ({"candidates": []}, gemini.BOS_YANIT),
            ({"candidates": [{"finishReason": "STOP", "content": {"parts": []}}]}, gemini.BOS_YANIT),
            ([], gemini.BOS_YANIT),
        ]:
            with self.assertRaises(gemini.ApiHatasi) as ctx:
                gemini.yanit_coz(veri)
            self.assertEqual(ctx.exception.tur, tur)


class OyunTestleri(unittest.TestCase):

    def setUp(self):
        self.gecici = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.gecici, ignore_errors=True)

    def _oyun_yap(self, ad):
        kok = os.path.join(self.gecici, ad)
        os.makedirs(os.path.join(kok, "game"))
        os.makedirs(os.path.join(kok, "renpy"))
        with open(os.path.join(kok, "game", "script.rpyc"), "wb") as f:
            f.write(b"x")
        with open(os.path.join(kok, ad + ".py"), "w") as f:
            f.write("#")
        with open(os.path.join(kok, ad + ".sh"), "w") as f:
            f.write("#")
        return kok

    def test_yol_temizle(self):
        self.assertEqual(oyun.yol_temizle('"C:/Oyunlar/Oyun"'), os.path.normpath("C:/Oyunlar/Oyun"))
        self.assertEqual(oyun.yol_temizle("& 'C:/Oyun Klasoru/X'"), os.path.normpath("C:/Oyun Klasoru/X"))
        self.assertEqual(oyun.yol_temizle("  /tmp/x/  "), os.path.normpath("/tmp/x"))
        self.assertEqual(oyun.yol_temizle(""), "")

    def test_oyun_bul(self):
        kok = self._oyun_yap("Benim Oyunum")
        self.assertEqual(oyun.oyun_bul(kok).kok, os.path.abspath(kok))
        self.assertEqual(oyun.oyun_bul(os.path.join(kok, "game")).kok, os.path.abspath(kok))
        self.assertEqual(oyun.oyun_bul(os.path.join(kok, "Benim Oyunum.py")).kok, os.path.abspath(kok))
        # Üst klasör verilirse ve içinde tek oyun varsa bulunur.
        self.assertEqual(oyun.oyun_bul(self.gecici).kok, os.path.abspath(kok))

    def test_birden_fazla_oyun(self):
        self._oyun_yap("A")
        self._oyun_yap("B")
        with self.assertRaises(oyun.OyunHatasi):
            oyun.oyun_bul(self.gecici)

    def test_oyun_yok(self):
        with self.assertRaises(oyun.OyunHatasi):
            oyun.oyun_bul(self.gecici)
        with self.assertRaises(oyun.OyunHatasi):
            oyun.oyun_bul(os.path.join(self.gecici, "olmayan"))

    def test_baslatma_komutu(self):
        kok = self._oyun_yap("Oyun")
        komut = oyun.baslatma_komutu(kok)
        if os.name != "nt":
            self.assertEqual(komut[0], "sh")
            self.assertTrue(komut[1].endswith("Oyun.sh"))


    def test_windows_exe_secimi(self):
        kok = self._oyun_yap("Harika Oyun")
        for ad in ("Harika Oyun.exe", "Harika Oyun-32.exe", "python.exe", "UnityCrashHandler64.exe", "zsync.exe"):
            with open(os.path.join(kok, ad), "wb") as f:
                f.write(b"MZ")
        eski = oyun.os.name
        oyun.os.name = "nt"
        try:
            komut = oyun.baslatma_komutu(kok)
        finally:
            oyun.os.name = eski
        self.assertEqual(os.path.basename(komut[0]), "Harika Oyun.exe")


class SozlukTestleri(unittest.TestCase):

    def test_yaz_oku(self):
        s = sozluk.Sozluk()
        s.ekle("Mom", "Anne", "kadın")
        s.ekle("Sylvie", "Sylvie", None)
        s.ekle("", "x")
        yol = os.path.join(tempfile.mkdtemp(), "s.txt")
        s.yaz(yol)
        s2 = sozluk.Sozluk.oku(yol)
        self.assertEqual(s2.karsilik("Mom"), "Anne")
        self.assertEqual(s2.cinsiyet("Mom"), "kadın")
        self.assertEqual(s2.karsilik("Sylvie"), "Sylvie")
        self.assertEqual(len(s2), 2)
        with open(yol, "a", encoding="utf-8") as f:
            f.write("Teacher=Öğretmen\n# yorum = değil\n")
        self.assertEqual(sozluk.Sozluk.oku(yol).karsilik("Teacher"), "Öğretmen")

    def test_ilgili_satirlar(self):
        s = sozluk.Sozluk()
        s.ekle("Mom", "Anne")
        s.ekle("Al", "Al")
        satirlar = s.ilgili_satirlar(["Hi Mom!", "Also good."])
        self.assertEqual(satirlar, ["Mom → Anne"])

    def test_terim_adaylari(self):
        d = ["I met Lucy at Hilltop Academy.", "Then Lucy left.", "We saw Lucy again.", "The Hilltop Academy is big.",
             "See you at Hilltop Academy tomorrow."]
        adaylar = dict(sozluk.terim_adaylari(d))
        self.assertIn("Lucy", adaylar)
        self.assertIn("Hilltop Academy", adaylar)
        self.assertNotIn("I", adaylar)


def _sahte_ttf(karakterler):
    """Sadece verilen karakterleri içeren minimal bir TrueType (cmap format 4) üretir."""
    kodlar = sorted(ord(c) for c in karakterler) + [0xFFFF]
    segler = [(k, k) for k in kodlar]
    segx2 = len(segler) * 2
    alt = struct.pack(">HHHHHHH", 4, 0, 0, segx2, 0, 0, 0)
    alt += b"".join(struct.pack(">H", e) for _s, e in segler) + b"\0\0"
    alt += b"".join(struct.pack(">H", s) for s, _e in segler)
    alt += b"".join(struct.pack(">H", (1 - s) & 0xFFFF) for s, _e in segler)  # glif 1
    alt += b"".join(struct.pack(">H", 0) for _ in segler)
    cmap = struct.pack(">HH", 0, 1) + struct.pack(">HHI", 3, 1, 12) + alt
    baslik = struct.pack(">IHHHH", 0x00010000, 1, 16, 0, 0)
    kayit = b"cmap" + struct.pack(">III", 0, 12 + 16, len(cmap))
    return baslik + kayit + cmap


class FontTestleri(unittest.TestCase):

    def test_eksik_harfler(self):
        tam = _sahte_ttf("abcçÇğĞıİöÖşŞüÜ")
        self.assertEqual(fontlar.eksik_harfler(tam), "")
        eksik = _sahte_ttf("abcçÇöÖüÜ")
        self.assertEqual(fontlar.eksik_harfler(eksik), "ğĞıİşŞ")
        self.assertIsNone(fontlar.eksik_harfler(b"bozuk veri"))


class AyarTestleri(unittest.TestCase):

    def test_dakikalik_sinir(self):
        ayar = dict(ayarlar.VARSAYILAN)
        self.assertEqual(ayarlar.dakikalik_sinir(ayar, "gemini-2.5-flash-lite"), 12)
        self.assertEqual(ayarlar.dakikalik_sinir(ayar, "gemini-2.5-flash"), 8)
        self.assertEqual(ayarlar.dakikalik_sinir(ayar, "gemini-2.5-pro"), 4)
        self.assertEqual(ayarlar.dakikalik_sinir(ayar, "gemma-3"), 6)


if __name__ == "__main__":
    unittest.main()
