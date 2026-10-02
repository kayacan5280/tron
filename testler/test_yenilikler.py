"""Yeni özelliklerin testleri: ek uyumu, doğallık dedektörü, karakter kartları,
ortak hafıza, elle düzenleme, sağlayıcılar (Claude / OpenAI uyumlu), editör
geçişi, bütçe, internet kesintisi, yama kurulumu, kör test.

Çalıştırma: python -m unittest discover -s testler
"""

import collections
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
os.environ["no_proxy"] = os.environ.get("no_proxy", "") + ",127.0.0.1,localhost"

from rpyceviri import (anahtarlar, ayarlar, cevirmen, dogallik, duzenleme, ekler, gemini, hafiza,  # noqa: E402
                       istem, karakterler, koruma, kortest, kurulum, proje, saglayicilar)
from rpyceviri.sozluk import Sozluk  # noqa: E402
from sahte_gemini import SahteGemini, sahte_cevir  # noqa: E402

GEMINI_A = "AIzaSyA_test_anahtari_birinci_000000000"
CLAUDE_A = "sk-ant-api03-test-anahtari-birinci-0000000000"
CLAUDE_B = "sk-ant-api03-test-anahtari-ikinci-11111111111"
DEEPSEEK_A = "sk-" + "0123456789abcdef" * 2   # biçimce DeepSeek anahtarı (sahte)


# ---------------------------------------------------------------------------
# Ek uyumu
# ---------------------------------------------------------------------------


class EkUyumuTestleri(unittest.TestCase):

    def test_ilgi_eki(self):
        beklenen = {
            "Ali": "nin", "Elif": "in", "Kate": "in", "Mike": "ın", "Peter": "ın", "Sylvie": "nin",
            "George": "un", "Ece": "nin", "Kutay": "ın", "Ayşe": "nin", "Gül": "ün", "Umut": "un",
            "10": "un", "100": "ün", "3": "ün", "MC": "nin", "Lucy": "nin", "Drew": "nun", "Mark": "ın",
        }
        for ad, ek in beklenen.items():
            self.assertEqual(ekler.ek_bul(ad, "in"), ek, ad)

    def test_diger_ekler(self):
        self.assertEqual(ekler.ek_bul("Ali", "e"), "ye")
        self.assertEqual(ekler.ek_bul("Elif", "e"), "e")
        self.assertEqual(ekler.ek_bul("Mark", "de"), "ta")
        self.assertEqual(ekler.ek_bul("Ayşe", "den"), "den")
        self.assertEqual(ekler.ek_bul("Murat", "den"), "tan")
        self.assertEqual(ekler.ek_bul("Ali", "le"), "yle")
        self.assertEqual(ekler.ek_bul("Elif", "i"), "i")
        self.assertEqual(ekler.ek_bul("Ali", "i"), "yi")
        self.assertEqual(ekler.ek_bul("Murat", "dir"), "tır")
        self.assertEqual(ekler.ek_bul("Elif", "mi"), "mi")
        self.assertEqual(ekler.ek_bul("Umut", "mi"), "mu")
        self.assertIsNone(ekler.ek_bul("", "in"))
        self.assertIsNone(ekler.ek_bul(None, "in"))

    def test_isaret_cozme(self):
        degerler = {"[name]": "Elif", "[mc]": "Mike", "[x]": None}
        metin = "[name]{ek=in} odası, [mc]{ek=e} ver, [x]{ek=nin} kitabı, [name] {ek=mi}?"
        sonuc = ekler.isaretleri_coz(metin, degerler.get)
        self.assertEqual(sonuc, "[name]'in odası, [mc]'a ver, [x]'nin kitabı, [name] mi?")
        self.assertEqual(ekler.isaretleri_sabitle("[name]{ek=nin} evi"), "[name]'nin evi")

    def test_ozel_okunus(self):
        try:
            ekler.OZEL_OKUNUS["siobhan"] = "şivon"
            self.assertEqual(ekler.ek_bul("Siobhan", "in"), "un")
        finally:
            ekler.OZEL_OKUNUS.pop("siobhan", None)

    def test_koruma_isaretleri(self):
        c, ciddi, _s = koruma.dogrula("[name]'s room is upstairs.", "[name]'{ek=in} odası üst katta.")
        self.assertEqual(ciddi, [])
        self.assertEqual(c, "[name]{ek=in} odası üst katta.")
        _c, ciddi, _s = koruma.dogrula("Is that [name]?", "Bu [name]{ek=mi}?")
        self.assertEqual(ciddi, [])
        self.assertEqual(_c, "Bu [name] {ek=mi}?")
        _c, ciddi, _s = koruma.dogrula("[name]'s room.", "[name]{ek=xyz} odası.")
        self.assertTrue(ciddi)
        _c, ciddi, _s = koruma.dogrula("The room.", "Oda{ek=in}.")
        self.assertTrue(ciddi)

    def test_maske_ek_korunur(self):
        maskeli, harita = koruma.maskele("[name]'s book.")
        self.assertEqual(koruma.maske_kaldir(maskeli.replace("'s book.", "{ek=in} kitabı."), harita),
                         "[name]{ek=in} kitabı.")

    def test_turkce_buyuk_harf(self):
        c, ciddi, _s = koruma.dogrula("WHAT IS THIS?!", "bu ne böyle, inanılmaz?!")
        self.assertEqual(ciddi, [])
        self.assertEqual(c, "BU NE BÖYLE, İNANILMAZ?!")
        c, _ci, _s = koruma.dogrula("STOP [name]!", "dur [name]!")
        self.assertEqual(c, "DUR [name]!")

    def test_ozel_karakter_normallestirme(self):
        c, _ci, _s = koruma.dogrula('He said "wait"...', "“Bekle” dedi…")
        self.assertEqual(c, '"Bekle" dedi...')
        c, _ci, _s = koruma.dogrula("Well… okay.", "Şey… tamam.")
        self.assertEqual(c, "Şey… tamam.")


# ---------------------------------------------------------------------------
# Doğallık dedektörü
# ---------------------------------------------------------------------------


class DogallikTestleri(unittest.TestCase):

    def test_ceviri_kokan_satirlar(self):
        kotu = [
            ("I think you are right.", "Ben senin haklı olduğunu düşünüyorum, sen haklısın."),
            ("What the hell is this?", "Bu ne cehennem böyle?"),
            ("I have a car.", "Ben bir arabaya sahibim."),
            ("We are waiting for you.", "Biz seni beklemekteyiz."),
            ("Good job!", "İyi iş!"),
            ("Thanks, okay.", "Teşekkürler, okay."),
        ]
        for kaynak, ceviri in kotu:
            self.assertTrue(dogallik.isaretli_mi(kaynak, ceviri, "diyalog", "Sylvie"), ceviri)

    def test_dogal_satirlar_isaretlenmez(self):
        iyi = [
            ("I think you are right.", "Bence haklısın."),
            ("What the hell is this?", "Bu da ne böyle?"),
            ("I have a car.", "Arabam var."),
            ("Good job!", "Eline sağlık!"),
            ("Let's go home.", "Hadi eve gidelim."),
        ]
        for kaynak, ceviri in iyi:
            self.assertFalse(dogallik.isaretli_mi(kaynak, ceviri, "diyalog", "Sylvie"), ceviri)

    def test_arayuz_dikkate_alinmaz(self):
        self.assertEqual(dogallik.koku("Start", "Ben sen biz", "arayuz"), (0, []))

    def test_tasma(self):
        kaynak = "x" * 150
        ceviri = "y" * 230
        puan, nedenler = dogallik.koku(kaynak, ceviri, "diyalog", "A")
        self.assertGreaterEqual(puan, 2)
        self.assertTrue(any("sığmayabilir" in n for n in nedenler))
        self.assertTrue(dogallik.tasma_riski(kaynak, ceviri))
        self.assertFalse(dogallik.tasma_riski("x" * 150, "y" * 170))


# ---------------------------------------------------------------------------
# Karakter kartları, ortak hafıza, proje
# ---------------------------------------------------------------------------


class KarakterTestleri(unittest.TestCase):

    def test_yaz_oku(self):
        k = karakterler.Karakterler()
        k.kart_ekle("Sylvie", "kadın", "genç yetişkin", "Neşeli, samimi.")
        k.kart_ekle("Mr. Smith", "erkek", "yetişkin", "Resmî bir öğretmen.")
        k.hitap_ekle("Sylvie", "Me", "sen")
        k.hitap_ekle("Me", "Mr. Smith", "siz")
        k.hitap_ekle("Me", "Me", "sen")          # kendine hitap atlanır
        k.hitap_ekle("Me", "Sylvie", "belki")    # geçersiz değer atlanır
        gecici = tempfile.mkdtemp()
        try:
            yol = os.path.join(gecici, "k.txt")
            k.yaz(yol)
            k2 = karakterler.Karakterler.oku(yol)
        finally:
            shutil.rmtree(gecici)
        self.assertEqual(k2.kartlar["Sylvie"]["uslup"], "Neşeli, samimi.")
        self.assertEqual(k2.cinsiyet("Mr. Smith"), "erkek")
        self.assertEqual(dict(k2.hitap), {("Sylvie", "Me"): "sen", ("Me", "Mr. Smith"): "siz"})
        kartlar, hitap = k2.istem_satirlari(["Me", "Sylvie"])
        self.assertTrue(any(s.startswith("Sylvie (kadın, genç yetişkin): Neşeli") for s in kartlar))
        self.assertIn("Me → Mr. Smith: siz", hitap)

    def test_analiz_verisi(self):
        ogeler = []
        for i in range(30):
            ogeler.append({"m": "Sylvie line number %d is long enough." % i, "k": "Sylvie"})
            ogeler.append({"m": "Me answering number %d here." % i, "k": "Me"})
        ogeler.append({"m": "continued", "k": "extend"})
        v = karakterler.analiz_verisi(ogeler)
        adlar = [c["ad"] for c in v["karakterler"]]
        self.assertEqual(sorted(adlar), ["Me", "Sylvie"])
        self.assertLessEqual(len(v["karakterler"][0]["ornekler"]), 8)
        ciftler = {(c["konusan"], c["dinleyen"]) for c in v["ciftler"]}
        self.assertIn(("Sylvie", "Me"), ciftler)
        self.assertIn(("Me", "Sylvie"), ciftler)


class HafizaTestleri(unittest.TestCase):

    def test_uygunluk_ve_oncelik(self):
        gecici = tempfile.mkdtemp()
        try:
            yol = os.path.join(gecici, "h.json")
            h = hafiza.Hafiza(yol)
            self.assertTrue(hafiza.uygun_mu("Load Game", "arayuz"))
            self.assertTrue(hafiza.uygun_mu("Thank you!", "diyalog"))
            self.assertFalse(hafiza.uygun_mu("I really think we should go home now.", "diyalog"))
            self.assertFalse(hafiza.uygun_mu("Hello [name]", "arayuz"))
            h.ekle("Thank you!", "Sağ ol!", "diyalog")
            h.ekle("Thank you!", "Teşekkür ederim!", "diyalog", elle=True)
            h.ekle("Thank you!", "Teşekkürler!", "diyalog")       # elle olanı ezmez
            h.ekle("Yes", "Yes", "secenek")                        # aynısı eklenmez
            h.kaydet()
            h2 = hafiza.Hafiza(yol)
            self.assertEqual(h2.al("Thank you!", "diyalog"), "Teşekkür ederim!")
            self.assertIsNone(h2.al("Yes", "secenek"))
            with open(yol, "w", encoding="utf-8") as f:
                f.write("{bozuk")
            self.assertEqual(len(hafiza.Hafiza(yol)), 0)
        finally:
            shutil.rmtree(gecici)


class ProjeTestleri(unittest.TestCase):

    def setUp(self):
        self.gecici = tempfile.mkdtemp()
        self._eski = proje.PROJE_KLASORU
        proje.PROJE_KLASORU = os.path.join(self.gecici, "projeler")

    def tearDown(self):
        proje.PROJE_KLASORU = self._eski
        shutil.rmtree(self.gecici, ignore_errors=True)

    def test_elle_korunur(self):
        p = proje.Proje(os.path.join(self.gecici, "oyun"))
        p.ceviri_kaydet("Hi", "Selam", proje.ELLE, model="elle")
        self.assertFalse(p.ceviri_kaydet("Hi", "Merhaba", proje.TAMAM))
        self.assertEqual(p.ceviri_al("Hi"), "Selam")
        p.basarisiz_kaydet("Hi", "x")
        self.assertEqual(p.ceviri_al("Hi"), "Selam")
        self.assertTrue(p.ceviri_kaydet("Hi", "Merhaba", proje.ELLE, zorla=True))
        self.assertEqual(p.elle_duzeltilenler(), [("Hi", "Merhaba")])
        p.ceviri_kaydet("Bye", "Hoşça kal", proje.HAFIZA)
        self.assertEqual(p.ceviri_al("Bye"), "Hoşça kal")
        self.assertFalse(p.incelendi_mi("Bye"))
        p.incelendi_isaretle("Bye")
        self.assertTrue(p.incelendi_mi("Bye"))

    def test_maliyet(self):
        p = proje.Proje(os.path.join(self.gecici, "oyun"))
        self.assertEqual(p.maliyet_al(), 0.0)
        p.maliyet_ekle(0.25)
        p.maliyet_ekle(0.5)
        self.assertAlmostEqual(proje.Proje(os.path.join(self.gecici, "oyun")).maliyet_al(), 0.75)


class DuzenlemeTestleri(unittest.TestCase):

    def setUp(self):
        self.gecici = tempfile.mkdtemp()
        self._eski = proje.PROJE_KLASORU
        proje.PROJE_KLASORU = os.path.join(self.gecici, "projeler")
        self.p = proje.Proje(os.path.join(self.gecici, "oyun"))
        self.p.ceviri_kaydet("Hello [name].", "Merhaba [name].")
        self.p.ceviri_kaydet("Line\ntwo", "Satır\niki")
        self.p.ceviri_kaydet("  Indented", "  Girintili")
        self.ogeler = [("Hello [name].", "Sylvie", "diyalog"), ("Line\ntwo", "", "diyalog"),
                       ("  Indented", "", "diyalog"), ("Untranslated", "", "secenek")]

    def tearDown(self):
        proje.PROJE_KLASORU = self._eski
        shutil.rmtree(self.gecici, ignore_errors=True)

    def _degistir(self, eski, yeni):
        with open(self.p.duzenleme_yolu, "r", encoding="utf-8-sig") as f:
            metin = f.read()
        self.assertIn(eski, metin)
        with open(self.p.duzenleme_yolu, "w", encoding="utf-8-sig") as f:
            f.write(metin.replace(eski, yeni, 1))

    def test_gidis_donus(self):
        n = duzenleme.disari_aktar(self.p, self.ogeler, "Oyun")
        self.assertEqual(n, 4)
        with open(self.p.duzenleme_yolu, "rb") as f:
            ham = f.read()
        self.assertTrue(ham.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"\r\n", ham)
        degisen, hatalar, _c = duzenleme.iceri_al(self.p, set(o[0] for o in self.ogeler))
        self.assertEqual((degisen, hatalar), (0, []))

        self._degistir("TR: Merhaba [name].", "TR: Selam [name], nasılsın?")
        self._degistir("TR: Satır\\niki", "TR: Satır\\nikinci")
        self._degistir("TR: \n\n", "TR: Çevrilmemiş seçenek\n\n")
        degisen, hatalar, ciftler = duzenleme.iceri_al(self.p, set(o[0] for o in self.ogeler))
        self.assertEqual(hatalar, [])
        self.assertEqual(degisen, 3)
        self.assertEqual(self.p.ceviri_al("Hello [name]."), "Selam [name], nasılsın?")
        self.assertEqual(self.p.ceviri_al("Line\ntwo"), "Satır\nikinci")
        self.assertEqual(self.p.ceviri_al("Untranslated"), "Çevrilmemiş seçenek")
        self.assertEqual(self.p.durum_al("Hello [name]."), proje.ELLE)
        self.assertEqual(self.p.ceviri_al("  Indented"), "  Girintili")
        self.assertEqual(len(ciftler), 3)

    def test_bozuk_duzeltme_reddedilir(self):
        duzenleme.disari_aktar(self.p, self.ogeler, "Oyun")
        self._degistir("TR: Merhaba [name].", "TR: Merhaba [isim].")
        degisen, hatalar, _c = duzenleme.iceri_al(self.p)
        self.assertEqual(degisen, 0)
        self.assertEqual(len(hatalar), 1)
        self.assertEqual(self.p.ceviri_al("Hello [name]."), "Merhaba [name].")

    def test_program_iyilestirmesi_ezilmez(self):
        duzenleme.disari_aktar(self.p, self.ogeler, "Oyun")
        # Dosya yazıldıktan sonra editör geçişi çeviriyi iyileştirdi; kullanıcı dosyaya dokunmadı.
        self.p.ceviri_kaydet("Hello [name].", "Selam [name].")
        degisen, _h, _c = duzenleme.iceri_al(self.p)
        self.assertEqual(degisen, 0)
        self.assertEqual(self.p.ceviri_al("Hello [name]."), "Selam [name].")

    def test_degismis_mi(self):
        duzenleme.disari_aktar(self.p, self.ogeler, "Oyun")
        self.assertFalse(duzenleme.degismis_mi(self.p))
        gelecek = time.time() + 10
        os.utime(self.p.duzenleme_yolu, (gelecek, gelecek))
        self.assertTrue(duzenleme.degismis_mi(self.p))


# ---------------------------------------------------------------------------
# Sağlayıcılar
# ---------------------------------------------------------------------------


class SaglayiciYardimciTestleri(unittest.TestCase):

    def test_anahtar_coz(self):
        self.assertEqual(saglayicilar.anahtar_coz(GEMINI_A), ("gemini", GEMINI_A))
        self.assertEqual(saglayicilar.anahtar_coz(CLAUDE_A), ("claude", CLAUDE_A))
        self.assertEqual(saglayicilar.anahtar_coz("claude: " + CLAUDE_A), ("claude", CLAUDE_A))
        self.assertEqual(saglayicilar.anahtar_coz("deepseek:" + DEEPSEEK_A), ("deepseek", DEEPSEEK_A))
        self.assertEqual(saglayicilar.anahtar_coz(DEEPSEEK_A), ("deepseek", DEEPSEEK_A))
        self.assertEqual(saglayicilar.anahtar_coz("sk-or-v1-abcdefabcdefabcdefabcdef")[0], "openrouter")
        self.assertEqual(saglayicilar.anahtar_coz("sk-proj-abcdefabcdefabcdefabcdef")[0], "openai")
        self.assertIsNone(saglayicilar.anahtar_turu_tahmin("sk-" + "a" * 48))

    def test_anahtar_dosyasi_karisik(self):
        gecici = tempfile.mkdtemp()
        try:
            yol = os.path.join(gecici, "a.txt")
            anahtarlar.anahtarlari_yaz(yol, [GEMINI_A, ("claude", CLAUDE_A), ("deepseek", DEEPSEEK_A)])
            okunan = anahtarlar.anahtarlari_oku(yol)
            self.assertEqual(okunan, [("gemini", GEMINI_A), ("claude", CLAUDE_A), ("deepseek", DEEPSEEK_A)])
            with open(yol, encoding="utf-8") as f:
                metin = f.read()
            self.assertIn("claude: " + CLAUDE_A, metin)
            self.assertIn("\n" + GEMINI_A + "\n", metin)
        finally:
            shutil.rmtree(gecici)

    def test_hedef(self):
        self.assertEqual(saglayicilar.hedef_coz("claude/claude-opus-5-5"), ("claude", "claude-opus-5-5"))
        self.assertEqual(saglayicilar.hedef_coz("gemini-2.5-flash"), ("gemini", "gemini-2.5-flash"))
        self.assertEqual(saglayicilar.hedef_coz("openrouter/deepseek/deepseek-chat"), ("openrouter", "deepseek/deepseek-chat"))
        self.assertTrue(saglayicilar.ucretli_mi("claude/x"))
        self.assertFalse(saglayicilar.ucretli_mi("gemini-2.5-flash"))

    def test_maliyet(self):
        k = {"girdi": 1000000, "cikti": 100000, "onbellek_okuma": 1000000, "onbellek_yazma": 0}
        self.assertAlmostEqual(saglayicilar.maliyet("claude/claude-opus-5-5", k), 4.0 + 2.0 + 0.2)
        self.assertAlmostEqual(saglayicilar.maliyet("claude/claude-opus-5-5-20261001", k), 6.2)
        self.assertEqual(saglayicilar.maliyet("gemini/gemini-2.5-flash", k), 0.0)
        self.assertIsNone(saglayicilar.maliyet("openai/bilinmeyen-model", k))
        self.assertAlmostEqual(saglayicilar.maliyet("openai/ozel", k, {"ozel": [1.0, 2.0]}), 1.0 + 0.2 + 0.1)
        t = saglayicilar.maliyet_tahmini("claude/claude-opus-5-5", dict(ayarlar.VARSAYILAN), 400000, 5000, 0.25)
        self.assertTrue(1.0 < t < 40.0, t)

    def test_kapatilacak_ozellik(self):
        self.assertEqual(saglayicilar.kapatilacak_ozellik("claude/x", "fallbacks: Extra inputs are not permitted"), "yedek")
        self.assertEqual(saglayicilar.kapatilacak_ozellik("claude/x", "output_config.effort: invalid"), "efor")
        self.assertEqual(saglayicilar.kapatilacak_ozellik("deepseek/x", "Invalid max_tokens value"), "en_fazla")
        self.assertEqual(saglayicilar.kapatilacak_ozellik("openai/x", "Unsupported value: 'temperature'"), "sicaklik")
        self.assertEqual(saglayicilar.kapatilacak_ozellik("gemini/x", "thinking_budget is not supported"), "dusunme")

    def test_eski_surum_anahtar_durumu(self):
        """v1'in öneksiz model adlarıyla kaydettiği 'günlük kota bitti' bilgisi v2'de de geçerli olmalı."""
        import datetime
        from rpyceviri import zaman
        gecici = tempfile.mkdtemp()
        try:
            yol = os.path.join(gecici, "durum.json")
            simdi = datetime.datetime(2026, 10, 2, 12, 0, tzinfo=zaman.UTC)
            yarin = zaman.iso(simdi + datetime.timedelta(hours=10))
            with open(yol, "w", encoding="utf-8") as f:
                json.dump({"anahtarlar": {anahtarlar.anahtar_kimligi(GEMINI_A): {
                    "gecersiz": None, "modeller": {"gemini-2.5-flash": {"gunluk_bitis": yarin}}}}}, f)
            y = anahtarlar.AnahtarYoneticisi([("gemini", GEMINI_A), ("claude", CLAUDE_A)],
                                             ["gemini/gemini-2.5-flash", "gemini/gemini-2.5-flash-lite", "claude/claude-opus-5-5"],
                                             lambda m: 0.0, yol, utc_saat=lambda: simdi)
            i, a, h = y.al()
            self.assertEqual((a, h), (GEMINI_A, "gemini/gemini-2.5-flash-lite"))
            y.hata(i, h, gemini.ApiHatasi(gemini.KOTA_GUNLUK, "bitti"))
            i, a, h = y.al()
            self.assertEqual((a, h), (CLAUDE_A, "claude/claude-opus-5-5"))
            y.hata(i, h, gemini.ApiHatasi(gemini.KREDI, "kredi yok"))
            with self.assertRaises(anahtarlar.TumKotalarBitti) as ctx:
                y.al()
            self.assertTrue(any("kredi yok" in n for n in ctx.exception.nedenler))
            self.assertEqual(y.kullanilabilir_anahtar_sayisi(), 1)
        finally:
            shutil.rmtree(gecici)

    def test_ayar_birlestirme(self):
        gecici = tempfile.mkdtemp()
        eski = ayarlar.AYAR_DOSYASI
        try:
            ayarlar.AYAR_DOSYASI = os.path.join(gecici, "ayarlar.json")
            with open(ayarlar.AYAR_DOSYASI, "w", encoding="utf-8") as f:
                json.dump({"dakikalik_istek": {"flash": 5, "varsayilan": 6}, "kalite_modu": "bozuk"}, f)
            a, _s = ayarlar.yukle()
            self.assertEqual(a["dakikalik_istek"]["flash"], 5)
            self.assertEqual(a["dakikalik_istek"]["claude"], 40)
            self.assertEqual(a["kalite_modu"], "dengeli")
        finally:
            ayarlar.AYAR_DOSYASI = eski
            shutil.rmtree(gecici)


class SunuculuTestTabani(unittest.TestCase):

    def setUp(self):
        self.gecici = tempfile.mkdtemp()
        self._eski_proje = proje.PROJE_KLASORU
        proje.PROJE_KLASORU = os.path.join(self.gecici, "projeler")
        self.sunucu = SahteGemini().__enter__()
        self._eski_taban = gemini.API_TABANI
        gemini.API_TABANI = self.sunucu.taban
        self._eski_ortam = {k: os.environ.get(k) for k in ("TRCEVIRI_CLAUDE_URL", "TRCEVIRI_DEEPSEEK_URL")}
        os.environ["TRCEVIRI_CLAUDE_URL"] = self.sunucu.kok
        os.environ["TRCEVIRI_DEEPSEEK_URL"] = self.sunucu.oa_taban
        saglayicilar._claude_istemciler.clear()
        self.ayar = dict(ayarlar.VARSAYILAN)
        self.ayar.update({"modeller": ["gemini-2.5-flash"], "paket_satir": 5, "paralel": 2,
                          "dakikalik_istek": {"varsayilan": 6000}, "zaman_asimi_sn": 30})

    def tearDown(self):
        gemini.API_TABANI = self._eski_taban
        proje.PROJE_KLASORU = self._eski_proje
        for k, v in self._eski_ortam.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        saglayicilar._claude_istemciler.clear()
        self.sunucu.__exit__()
        shutil.rmtree(self.gecici, ignore_errors=True)

    def _cevirmen(self, anahtarlar_, hedefler, karakterler_=None):
        p = proje.Proje(os.path.join(self.gecici, "oyun"))
        yon = anahtarlar.AnahtarYoneticisi(list(anahtarlar_), hedefler, lambda m: 0.0, None)
        c = cevirmen.Cevirmen(p, yon, self.ayar, Sozluk(), "Test Oyunu", "", karakterler=karakterler_)
        return p, c, yon


@unittest.skipUnless(saglayicilar.claude_sdk_var_mi(), "anthropic paketi kurulu değil")
class ClaudeTestleri(SunuculuTestTabani):

    def test_uret_ve_istek_bicimi(self):
        kullanici = json.dumps({"satirlar": [{"id": "1", "t": "diyalog", "m": "Hello there."}]})
        istek = saglayicilar.Istek("SABİT TALİMAT", kullanici, "ceviri", degisken="PAKET BİLGİSİ")
        metin, k = saglayicilar.uret("claude/claude-opus-5-5", CLAUDE_A, istek, self.ayar, {})
        self.assertEqual(istem.ceviri_haritasi(istem.json_cozumle(metin)), {"1": sahte_cevir("Hello there.")})
        self.assertEqual((k["girdi"], k["onbellek_okuma"]), (1000, 5000))
        govde = self.sunucu.senaryo.claude_govdeleri[-1]
        basliklar = {a.lower(): b for a, b in self.sunucu.senaryo.claude_basliklari[-1].items()}
        self.assertTrue(govde["stream"])
        self.assertEqual(govde["fallbacks"], "default")
        self.assertIn("server-side-fallback-2026-07-01", basliklar.get("anthropic-beta", ""))
        self.assertEqual(govde["output_config"]["effort"], "medium")
        self.assertEqual(govde["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(govde["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(govde["system"][0]["text"], "SABİT TALİMAT")
        self.assertEqual(govde["system"][1]["text"], "PAKET BİLGİSİ")
        self.assertNotIn("temperature", govde)
        self.assertNotIn("thinking", govde)

    def test_hatalar(self):
        s = self.sunucu.senaryo
        istek = saglayicilar.Istek("S", json.dumps({"satirlar": [{"id": "1", "m": "Hi YASAK"}]}), "ceviri")
        s.kredisiz_anahtarlar.add(CLAUDE_B)
        with self.assertRaises(gemini.ApiHatasi) as h:
            saglayicilar.uret("claude/claude-opus-5-5", CLAUDE_B, istek, self.ayar, {})
        self.assertEqual(h.exception.tur, gemini.KREDI)
        s.gecersiz_anahtarlar.add("sk-ant-api03-gecersiz-anahtar-000000000000")
        with self.assertRaises(gemini.ApiHatasi) as h:
            saglayicilar.uret("claude/claude-opus-5-5", "sk-ant-api03-gecersiz-anahtar-000000000000", istek, self.ayar, {})
        self.assertEqual(h.exception.tur, gemini.GECERSIZ_ANAHTAR)
        with self.assertRaises(gemini.ApiHatasi) as h:
            saglayicilar.uret("claude/claude-yok", CLAUDE_A, istek, self.ayar, {})
        self.assertEqual(h.exception.tur, gemini.MODEL_YOK)
        s.engelli_kelimeler.append("YASAK")
        with self.assertRaises(gemini.ApiHatasi) as h:
            saglayicilar.uret("claude/claude-opus-5-5", CLAUDE_A, istek, self.ayar, {})
        self.assertEqual(h.exception.tur, gemini.ENGELLENDI)
        s.sunucu_hatasi = 1
        with self.assertRaises(gemini.ApiHatasi) as h:
            saglayicilar.uret("claude/claude-opus-5-5", CLAUDE_A, istek, self.ayar, {})
        self.assertEqual(h.exception.tur, gemini.SUNUCU)
        s.dakika_hatasi[CLAUDE_A] = 1
        with self.assertRaises(gemini.ApiHatasi) as h:
            saglayicilar.uret("claude/claude-opus-5-5", CLAUDE_A, istek, self.ayar, {})
        self.assertEqual(h.exception.tur, gemini.KOTA_DAKIKA)
        self.assertEqual(saglayicilar.modelleri_listele("claude", CLAUDE_A), ["claude-opus-5-5", "claude-sonnet-5-5"])

    def test_ozellik_kapatma_parametreleri(self):
        kw, ek = saglayicilar._claude_parametreleri(
            "m", saglayicilar.Istek("S", "K", "ceviri"), self.ayar, {"yedek": False, "sema": False, "onbellek": False})
        self.assertNotIn("fallbacks", ek)
        self.assertNotIn("format", ek["output_config"])
        self.assertNotIn("cache_control", kw["system"][0])

    def test_claude_ile_ceviri_kredi_biten_anahtar_birakilir_ve_maliyet(self):
        self.sunucu.senaryo.kredisiz_anahtarlar.add(CLAUDE_B)
        p, c, yon = self._cevirmen([("claude", CLAUDE_B), ("claude", CLAUDE_A)], ["claude/claude-opus-5-5"])
        metinler = ["Claude line number %d here." % i for i in range(12)]
        ogeler = [cevirmen.Oge(i + 1, m, "diyalog", "Sylvie") for i, m in enumerate(metinler)]
        c.calistir(ogeler, [], ogeler)
        for m in metinler:
            self.assertEqual(p.ceviri_al(m), sahte_cevir(m), m)
        self.assertIn(0, yon.oturum_kapali)
        self.assertGreater(c.maliyet, 0)
        self.assertEqual(c.istatistik["basarisiz"], 0)

    def test_butce_dolunca_ucretli_durur_gemini_devam_eder(self):
        p, c, yon = self._cevirmen([("claude", CLAUDE_A), ("gemini", GEMINI_A)],
                                    ["claude/claude-opus-5-5", "gemini/gemini-2.5-flash"])
        c.butce = 0.001
        self.ayar["paralel"] = 1
        metinler = ["Budget line number %d here." % i for i in range(20)]
        ogeler = [cevirmen.Oge(i + 1, m, "diyalog") for i, m in enumerate(metinler)]
        c.calistir(ogeler, [], ogeler)
        for m in metinler:
            self.assertIsNotNone(p.ceviri_al(m), m)
        self.assertIn("claude/claude-opus-5-5", yon.model_kapali)
        self.assertGreater(c.istatistik["hedef:gemini/gemini-2.5-flash"], 0)


class OpenAIUyumluTestleri(SunuculuTestTabani):

    def test_deepseek_ceviri_ve_ozellik_kapatma(self):
        self.sunucu.senaryo.desteklenmeyen["deepseek-chat"] = {"en_fazla"}
        p, c, yon = self._cevirmen([("deepseek", DEEPSEEK_A)], ["deepseek/deepseek-chat"])
        metinler = ["DeepSeek line %d is here." % i for i in range(7)]
        ogeler = [cevirmen.Oge(i + 1, m, "diyalog") for i, m in enumerate(metinler)]
        c.calistir(ogeler, [], ogeler)
        for m in metinler:
            self.assertEqual(p.ceviri_al(m), sahte_cevir(m), m)
        self.assertFalse(yon.ozellik("deepseek/deepseek-chat").get("en_fazla", True))
        govde = self.sunucu.senaryo.oa_govdeleri[-1]
        self.assertEqual(govde["response_format"], {"type": "json_object"})
        self.assertEqual(govde["messages"][0]["role"], "system")
        self.assertGreater(c.maliyet, 0)

    def test_bakiye_bitti(self):
        self.sunucu.senaryo.kredisiz_anahtarlar.add(DEEPSEEK_A)
        istek = saglayicilar.Istek("S", json.dumps({"satirlar": []}), "ceviri")
        with self.assertRaises(gemini.ApiHatasi) as h:
            saglayicilar.uret("deepseek/deepseek-chat", DEEPSEEK_A, istek, self.ayar, {})
        self.assertEqual(h.exception.tur, gemini.KREDI)
        self.assertEqual(saglayicilar.modelleri_listele("deepseek", "sk-baska-0000000000000000000000"),
                         ["deepseek-chat", "gpt-5-mini"])


# ---------------------------------------------------------------------------
# Çevirmen: bağlam, karakter analizi, editör, kesinti
# ---------------------------------------------------------------------------


class CevirmenYenilikTestleri(SunuculuTestTabani):

    def test_sonraki_baglam_ve_hitap_istemde(self):
        k = karakterler.Karakterler()
        k.kart_ekle("Sylvie", "kadın", "genç", "Neşeli.")
        k.hitap_ekle("Sylvie", "Me", "sen")
        p, c, _y = self._cevirmen([GEMINI_A], ["gemini-2.5-flash"], k)
        ogeler = [cevirmen.Oge(i + 1, "Sentence %d goes here." % i, "diyalog", "Sylvie" if i % 2 else "Me")
                  for i in range(8)]
        c._sira_listesi = ogeler
        c._sira_konum = {o.id: i for i, o in enumerate(ogeler)}
        istek = c._ceviri_istegi(ogeler[2:5])
        veri = json.loads(istek.kullanici)
        self.assertEqual([b["m"] for b in veri["sonraki"]], ["Sentence 5 goes here.", "Sentence 6 goes here.",
                                                            "Sentence 7 goes here."])
        self.assertEqual(len(veri["baglam"]), 2)
        self.assertNotIn("_k", veri["baglam"][0])
        self.assertIn("Sylvie → Me: sen", istek.degisken)
        self.assertIn("Sylvie (kadın, genç): Neşeli.", istek.sistem)
        self.assertTrue(istek.sistem.startswith(istem.CEVIRMEN_GIRIS))

    def test_karakter_analizi(self):
        p, c, _y = self._cevirmen([GEMINI_A], ["gemini-2.5-flash"])
        ogeler = []
        for i in range(10):
            ogeler.append({"m": "Hey, how are you doing today %d?" % i, "k": "Sylvie"})
            ogeler.append({"m": "I'm fine, thanks %d." % i, "k": "Me"})
            ogeler.append({"m": "Narration %d." % i, "k": "narrator"})
        k = c.karakter_analizi(ogeler)
        self.assertEqual(set(k.kartlar), {"Sylvie", "Me"})
        self.assertEqual(k.hitap[("Sylvie", "Me")], "sen")
        self.assertIn("karakter", self.sunucu.senaryo.istek_turleri)

    def test_editor_gecisi(self):
        p, c, _y = self._cevirmen([GEMINI_A], ["gemini-2.5-flash"])
        kaynaklar = {
            "I think you are right.": "Ben senin haklı olduğunu düşünüyorum, sen haklısın.",
            "Good job!": "İyi iş!",
            "Let's go home.": "Hadi eve gidelim.",
            "Thanks for coming.": "Geldiğin için sağ ol.",
        }
        ogeler = []
        for i, (k, v) in enumerate(kaynaklar.items()):
            p.ceviri_kaydet(k, v)
            ogeler.append(cevirmen.Oge(i + 1, k, "diyalog", "Sylvie"))
        p.ceviri_kaydet("Thanks for coming.", "Gelmene sevindim.", proje.ELLE)
        adaylar = c.inceleme_adaylari(ogeler, "dengeli")
        self.assertEqual(sorted(o.m for o, _n in adaylar), ["Good job!", "I think you are right."])
        c.incele(adaylar, ogeler)
        self.assertEqual(p.ceviri_al("Good job!"), "İyi iş! eh")
        self.assertTrue(p.incelendi_mi("Good job!"))
        self.assertEqual(p.ceviri_al("Let's go home."), "Hadi eve gidelim.")
        self.assertEqual(p.ceviri_al("Thanks for coming."), "Gelmene sevindim.")
        self.assertEqual(c.istatistik["editor_duzeltti"], 2)
        # İncelenen satır bir daha editöre gitmez.
        self.assertEqual(c.inceleme_adaylari(ogeler, "dengeli"), [])
        # En iyi modda yapay zekanın çevirdiği her satır incelenir (elle olan hariç).
        self.assertEqual([o.m for o, _n in c.inceleme_adaylari(ogeler, "en_iyi")], ["Let's go home."])

    def test_editor_bozuk_oneriyi_reddeder(self):
        self.sunucu.senaryo.editor_eki = " [bozuk]"
        p, c, _y = self._cevirmen([GEMINI_A], ["gemini-2.5-flash"])
        p.ceviri_kaydet("Good job!", "İyi iş!")
        o = cevirmen.Oge(1, "Good job!", "diyalog", "A")
        c.incele(c.inceleme_adaylari([o], "dengeli"), [o])
        self.assertEqual(p.ceviri_al("Good job!"), "İyi iş!")
        self.assertTrue(p.incelendi_mi("Good job!"))

    def test_internet_kesintisi_bekler_ve_devam_eder(self):
        self.sunucu.senaryo.ag_kesik = 4
        self.ayar["paralel"] = 1
        p, c, _y = self._cevirmen([GEMINI_A], ["gemini-2.5-flash"])
        metinler = ["Outage line %d here." % i for i in range(6)]
        ogeler = [cevirmen.Oge(i + 1, m, "diyalog") for i, m in enumerate(metinler)]
        bildirimler = []
        c.bildir = lambda tur, mesaj: bildirimler.append(mesaj)
        bas = time.monotonic()
        c.calistir(ogeler, [], ogeler)
        for m in metinler:
            self.assertEqual(p.ceviri_al(m), sahte_cevir(m), m)
        self.assertIsNone(c.kritik_hata)
        self.assertEqual(c.istatistik["basarisiz"], 0)
        self.assertEqual(c.kesinti_sayisi, 1)
        self.assertTrue(any("Bağlantı geri geldi" in b for b in bildirimler), bildirimler)
        self.assertLess(time.monotonic() - bas, 60)

    def test_zaman_asimi_kesinti_sirasinda_satiri_dusurmez(self):
        p, c, _y = self._cevirmen([GEMINI_A], ["gemini-2.5-flash"])
        c._ardisik_ag = 5
        c._ardisik_saf_ag = 2
        c._kesinti_baslangic = time.monotonic()
        self.assertTrue(c._kesinti_var())
        c._istek_basarili()
        self.assertFalse(c._kesinti_var())
        self.assertEqual(c._ardisik_ag, 0)


# ---------------------------------------------------------------------------
# Yama kurulumu, kör test
# ---------------------------------------------------------------------------


class KurulumTestleri(unittest.TestCase):

    def test_yama_metni_gomulu(self):
        t = kurulum.yama_metni()
        self.assertNotIn(kurulum.EKLER_ISARETI, t)
        self.assertIn("def isaretleri_coz", t)
        govde = t.split("init 999 python in trceviri:\n", 1)[1]
        import textwrap
        compile(textwrap.dedent(govde), "yama", "exec")
        for satir in govde.splitlines():
            self.assertTrue(not satir.strip() or satir.startswith("    "), satir)

    def test_uzun_satir_kucult(self):
        c, n = kurulum.uzun_satiri_kucult("x" * 140, "y" * 200)
        self.assertEqual((c, n), ("{size=-2}" + "y" * 200 + "{/size}", 2))
        c, n = kurulum.uzun_satiri_kucult("x" * 140, "y" * 240 + "{nw}")
        self.assertEqual(n, 4)
        self.assertTrue(c.endswith("{/size}{nw}"))
        self.assertEqual(kurulum.uzun_satiri_kucult("x" * 140, "y" * 150), ("y" * 150, 0))
        self.assertEqual(kurulum.uzun_satiri_kucult("x" * 100, "{size=20}" + "y" * 300 + "{/size}")[1], 0)
        self.assertTrue(koruma._etiket_dizilimi_dogru_mu(c))

    def test_ek_istisnalari(self):
        gecici = tempfile.mkdtemp()
        try:
            yol = os.path.join(gecici, "e.txt")
            kurulum.ek_istisna_sablonu_yaz(yol)
            self.assertEqual(kurulum.ek_istisnalari_oku(yol), {})
            with open(yol, "a", encoding="utf-8") as f:
                f.write("Mike = mayk\nMary Jane = ceyn  # açıklama\nbozuk satır\nİREM = irem\n")
            self.assertEqual(kurulum.ek_istisnalari_oku(yol), {"mike": "mayk", "jane": "ceyn", "irem": "irem"})
        finally:
            shutil.rmtree(gecici)

    def test_yama_yaz(self):
        gecici = tempfile.mkdtemp()
        eski = proje.PROJE_KLASORU
        try:
            proje.PROJE_KLASORU = os.path.join(gecici, "projeler")
            oyun_kok = os.path.join(gecici, "Oyun")
            os.makedirs(os.path.join(oyun_kok, "game"))
            OyunNesnesi = collections.namedtuple("OyunNesnesi", "kok game ad")
            oyun_ = OyunNesnesi(oyun_kok, os.path.join(oyun_kok, "game"), "Oyun")
            p = proje.Proje(oyun_kok)
            uzun = "This is a fairly long line of dialogue that keeps going and going for the test. " * 2
            p.ceviri_kaydet("[name]'s room.", "[name]{ek=in} odası.")
            p.ceviri_kaydet("Hi [name]", "Selam [name]{ek=e} bak")
            p.ceviri_kaydet(uzun, "Ç" * 260)
            p.ceviri_kaydet("[mc]'s Quest", "[mc]{ek=in} Görevi")
            cikti = {"ogeler": [{"m": "[name]'s room.", "tur": "diyalog"}, {"m": uzun, "tur": "diyalog"},
                                {"m": "Hi [name]", "tur": "secenek"}],
                     "metinler": [{"m": "[mc]'s Quest", "tur": "ekran"}], "fontlar": []}
            with open(p.ek_istisna_yolu, "w", encoding="utf-8") as f:
                f.write("Mike = mayk\n")
            ist = kurulum.yamayi_yaz(oyun_, cikti, p, dict(ayarlar.VARSAYILAN))
            with open(os.path.join(oyun_.game, "trceviri", "ceviri.json"), encoding="utf-8") as f:
                veri = json.load(f)
            self.assertEqual(veri["diyalog"]["[name]'s room."], "[name]{ek=in} odası.")
            self.assertEqual(veri["diyalog"]["Hi [name]"], "Selam [name]{ek=e} bak")
            self.assertTrue(veri["diyalog"][uzun].startswith("{size=-4}"))
            self.assertEqual(veri["metinler"]["[mc]'s Quest"], "[mc]'in Görevi")
            self.assertEqual(veri["ek_istisnalari"], {"mike": "mayk"})
            self.assertEqual(ist["kucultulen"], 1)
            with open(os.path.join(oyun_.game, kurulum.YAMA_AD), encoding="utf-8") as f:
                self.assertIn("def ek_bul", f.read())
            self.assertGreaterEqual(kurulum.yamayi_kaldir(oyun_), 2)
            self.assertEqual(os.listdir(oyun_.game), [])
        finally:
            proje.PROJE_KLASORU = eski
            shutil.rmtree(gecici)


class KorTestTestleri(unittest.TestCase):

    def test_ornek_ve_html(self):
        sira = [cevirmen.Oge(i, "Dialogue line number %d is here." % i, "diyalog", "A") for i in range(200)]
        ornek = kortest.ornek_sec(sira, 30, 10, tohum=1)
        self.assertEqual(len(ornek), 30)
        self.assertEqual(len(set(o.id for o in ornek)), 30)
        gecici = tempfile.mkdtemp()
        try:
            yol = os.path.join(gecici, "t.html")
            n = kortest.html_yaz(yol, "Oyun <1>", [("A", "Hi <b>", "Selam", "Merhaba"), ("", "Yes", "Evet", "Olur")],
                                 "gemini-2.5-flash", "claude-opus-5-5", tohum=3)
            with open(yol, encoding="utf-8") as f:
                h = f.read()
            self.assertEqual(n, 2)
            self.assertIn("Hi &lt;b&gt;", h)
            self.assertIn("Oyun &lt;1&gt;", h)
            self.assertIn("claude-opus-5-5", h)
            self.assertNotIn("@@", h)
        finally:
            shutil.rmtree(gecici)

    def test_bellek_proje_diske_yazmaz(self):
        gecici = tempfile.mkdtemp()
        eski = proje.PROJE_KLASORU
        try:
            proje.PROJE_KLASORU = os.path.join(gecici, "projeler")
            p = proje.Proje(os.path.join(gecici, "oyun"))
            p.ceviri_kaydet("Context", "Bağlam")
            p.kaydet()
            b = kortest.BellekProje(p, ["Sample"])
            b.ceviri_kaydet("Sample", "Örnek")
            b.kaydet()
            self.assertEqual(b.ceviri_al("Sample"), "Örnek")
            self.assertEqual(b.ceviri_al("Context"), "Bağlam")
            self.assertIsNone(proje.Proje(os.path.join(gecici, "oyun")).ceviri_al("Sample"))
        finally:
            proje.PROJE_KLASORU = eski
            shutil.rmtree(gecici)


if __name__ == "__main__":
    unittest.main()
