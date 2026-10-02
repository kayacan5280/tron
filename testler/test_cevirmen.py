"""Çeviri motoru ve anahtar yöneticisinin sahte Gemini sunucusuyla testleri."""

import datetime
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
os.environ["no_proxy"] = os.environ.get("no_proxy", "") + ",127.0.0.1,localhost"

from rpyceviri import anahtarlar, ayarlar, cevirmen, gemini, koruma, proje, zaman  # noqa: E402
from rpyceviri.sozluk import Sozluk  # noqa: E402
from sahte_gemini import SahteGemini, sahte_cevir  # noqa: E402

ANAHTAR_A = "AIzaSyA_test_anahtari_birinci_000000000"
ANAHTAR_B = "AIzaSyB_test_anahtari_ikinci_1111111111"
ANAHTAR_C = "AIzaSyC_test_anahtari_ucuncu_2222222222"


class AnahtarYoneticisiTestleri(unittest.TestCase):

    def setUp(self):
        self.saat = [1000.0]
        self.utc = [datetime.datetime(2026, 10, 2, 12, 0, tzinfo=zaman.UTC)]
        self.gecici = tempfile.mkdtemp()
        self.durum = os.path.join(self.gecici, "durum.json")

    def tearDown(self):
        shutil.rmtree(self.gecici, ignore_errors=True)

    def _yon(self, anahtarlar_=None, modeller=None):
        return anahtarlar.AnahtarYoneticisi(
            anahtarlar_ or [ANAHTAR_A, ANAHTAR_B], modeller or ["m1", "m2"], lambda m: 6.0, self.durum,
            saat=lambda: self.saat[0], utc_saat=lambda: self.utc[0])

    def test_sirayla_kullanim(self):
        y = self._yon()
        i1, _a, m1 = y.al()
        i2, _a, m2 = y.al()
        self.assertEqual((m1, m2), ("m1", "m1"))
        self.assertNotEqual(i1, i2)

    def test_gunluk_kota_sonraki_modele_gecer_ve_hatirlanir(self):
        y = self._yon()
        for i in range(2):
            y.hata(i, "m1", gemini.ApiHatasi(gemini.KOTA_GUNLUK, "bitti"))
        _i, _a, m = y.al()
        self.assertEqual(m, "m2")
        # Program yeniden açılınca da hatırlanmalı.
        y2 = self._yon()
        _i, _a, m = y2.al()
        self.assertEqual(m, "m2")
        # Kota sıfırlanma zamanı geçince tekrar m1 kullanılmalı.
        self.utc[0] = self.utc[0] + datetime.timedelta(days=1)
        y3 = self._yon()
        _i, _a, m = y3.al()
        self.assertEqual(m, "m1")

    def test_hepsi_bitince_hata(self):
        y = self._yon()
        for i in range(2):
            for m in ("m1", "m2"):
                y.hata(i, m, gemini.ApiHatasi(gemini.KOTA_GUNLUK, "bitti"))
        with self.assertRaises(anahtarlar.TumKotalarBitti) as ctx:
            y.al()
        self.assertIsNotNone(ctx.exception.en_erken)

    def test_gecersiz_anahtar_atlanir(self):
        y = self._yon()
        y.hata(0, "m1", gemini.ApiHatasi(gemini.GECERSIZ_ANAHTAR, "geçersiz"))
        for _ in range(3):
            i, _a, _m = y.al()
            self.assertEqual(i, 1)
            self.saat[0] += 10
        self.assertEqual(y.kullanilabilir_anahtar_sayisi(), 1)
        y.hata(1, "m1", gemini.ApiHatasi(gemini.GECERSIZ_ANAHTAR, "geçersiz"))
        with self.assertRaises(anahtarlar.TumKotalarBitti):
            y.al()

    def test_dakikalik_sinir_bekletir_ama_model_dusurmez(self):
        y = anahtarlar.AnahtarYoneticisi([ANAHTAR_A], ["m1", "m2"], lambda m: 0.3, None)
        _i, _a, m = y.al()
        bas = time.monotonic()
        _i, _a, m2 = y.al()
        self.assertEqual(m2, "m1")
        self.assertGreaterEqual(time.monotonic() - bas, 0.25)

    def test_haric_model(self):
        y = self._yon()
        _i, _a, m = y.al(haric={"m1"})
        self.assertEqual(m, "m2")
        y.hata(0, "m2", gemini.ApiHatasi(gemini.KOTA_GUNLUK, "x"))
        y.hata(1, "m2", gemini.ApiHatasi(gemini.KOTA_GUNLUK, "x"))
        self.saat[0] += 100
        _i, _a, m = y.al(haric={"m1"})
        self.assertEqual(m, "m1")

    def test_iptal(self):
        y = anahtarlar.AnahtarYoneticisi([ANAHTAR_A], ["m1"], lambda m: 100.0, None)
        y.al()
        olay = threading.Event()
        threading.Timer(0.2, olay.set).start()
        with self.assertRaises(anahtarlar.IptalEdildi):
            y.al(iptal=olay)

    def test_anahtar_dosyasi(self):
        yol = os.path.join(self.gecici, "a.txt")
        anahtarlar.anahtarlari_yaz(yol, [ANAHTAR_A, ANAHTAR_B])
        with open(yol, "a", encoding="utf-8") as f:
            f.write("\n  %s   # arkadaşımın\n%s\n" % (ANAHTAR_C, ANAHTAR_A))
        self.assertEqual(anahtarlar.anahtarlari_oku(yol), [ANAHTAR_A, ANAHTAR_B, ANAHTAR_C])
        self.assertFalse(anahtarlar.anahtar_bicimi_uygun_mu("kısa"))
        self.assertTrue(anahtarlar.anahtar_bicimi_uygun_mu(ANAHTAR_A))


class CevirmenTestleri(unittest.TestCase):

    def setUp(self):
        self.gecici = tempfile.mkdtemp()
        self._eski_proje = proje.PROJE_KLASORU
        proje.PROJE_KLASORU = os.path.join(self.gecici, "projeler")
        self.sunucu = SahteGemini().__enter__()
        self._eski_taban = gemini.API_TABANI
        gemini.API_TABANI = self.sunucu.taban
        self.ayar = dict(ayarlar.VARSAYILAN)
        self.ayar.update({"modeller": ["gemini-2.5-flash", "gemini-2.5-flash-lite"], "paket_satir": 5, "paralel": 2,
                          "dakikalik_istek": {"varsayilan": 6000}})

    def tearDown(self):
        gemini.API_TABANI = self._eski_taban
        proje.PROJE_KLASORU = self._eski_proje
        self.sunucu.__exit__()
        shutil.rmtree(self.gecici, ignore_errors=True)

    def _calistir(self, metinler, anahtarlar_=(ANAHTAR_A, ANAHTAR_B), arayuz=()):
        p = proje.Proje(os.path.join(self.gecici, "oyun"))
        yon = anahtarlar.AnahtarYoneticisi(list(anahtarlar_), self.ayar["modeller"], lambda m: 0.0,
                                           os.path.join(self.gecici, "durum.json"))
        c = cevirmen.Cevirmen(p, yon, self.ayar, Sozluk(), "Test Oyunu", "")
        ogeler = [cevirmen.Oge(i + 1, m, "diyalog", "Sylvie" if i % 2 else "") for i, m in enumerate(metinler)]
        arayuz_ogeleri = [cevirmen.Oge(1000 + i, m, "arayuz") for i, m in enumerate(arayuz)]
        c.calistir(ogeler, arayuz_ogeleri, ogeler)
        return p, c, yon

    def test_basit_ceviri(self):
        metinler = ["Hello [name]!", "{i}Really{/i}? I can't believe it.", "Wait{w} what?"] + ["Line number %d here." % i for i in range(12)]
        p, c, _y = self._calistir(metinler, arayuz=["Start", "Load Game"])
        for m in metinler + ["Start", "Load Game"]:
            self.assertEqual(p.ceviri_al(m), sahte_cevir(m), m)
        self.assertEqual(c.istatistik["basarisiz"], 0)
        # Diske kaydedildi mi?
        p2 = proje.Proje(os.path.join(self.gecici, "oyun"))
        self.assertEqual(p2.ceviri_al("Hello [name]!"), sahte_cevir("Hello [name]!"))

    def test_kota_dolunca_anahtar_ve_model_degisir(self):
        s = self.sunucu.senaryo
        s.gunluk_sonra[(ANAHTAR_A, "gemini-2.5-flash")] = 1
        s.gunluk_biten.add((ANAHTAR_B, "gemini-2.5-flash"))
        metinler = ["Sentence number %d is here." % i for i in range(30)]
        p, c, _y = self._calistir(metinler)
        for m in metinler:
            self.assertIsNotNone(p.ceviri_al(m), m)
        modeller = {m for _a, m, _n in s.istekler}
        self.assertIn("gemini-2.5-flash-lite", modeller)

    def test_tum_kotalar_bitince_durur_ve_kaydeder(self):
        s = self.sunucu.senaryo
        for a in (ANAHTAR_A, ANAHTAR_B):
            s.gunluk_sonra[(a, "gemini-2.5-flash")] = 1
            s.gunluk_sonra[(a, "gemini-2.5-flash-lite")] = 1
        metinler = ["Sentence number %d is here." % i for i in range(60)]
        p, c, _y = self._calistir(metinler)
        self.assertIsInstance(c.durdurma_nedeni, anahtarlar.TumKotalarBitti)
        cevrilen = [m for m in metinler if p.ceviri_al(m)]
        self.assertGreaterEqual(len(cevrilen), 15)
        self.assertLess(len(cevrilen), 60)
        # Yarın (kota sıfırlanınca) kaldığı yerden devam: kalanlar çevrilir.
        s.gunluk_biten.clear()
        s.gunluk_sonra.clear()
        os.remove(os.path.join(self.gecici, "durum.json"))
        kalan = [m for m in metinler if not p.ceviri_al(m)]
        p2, c2, _y = self._calistir(kalan)
        for m in metinler:
            self.assertIsNotNone(p2.ceviri_al(m), m)

    def test_gecersiz_anahtar_ve_hatalar(self):
        s = self.sunucu.senaryo
        s.gecersiz_anahtarlar.add(ANAHTAR_A)
        s.dakika_hatasi[ANAHTAR_B] = 2
        s.sunucu_hatasi = 2
        s.bozuk_json = 1
        s.eksik_id = 2
        metinler = ["Text %d with [var] inside." % i for i in range(12)]
        p, c, y = self._calistir(metinler)
        for m in metinler:
            self.assertEqual(p.ceviri_al(m), sahte_cevir(m), m)
        self.assertIn(0, y.gecersiz)

    def test_bozuk_degisken_tekrar_denenir(self):
        s = self.sunucu.senaryo
        s.token_boz["[money]"] = 1
        metinler = ["You have [money] coins.", "Another normal line here."]
        p, c, _y = self._calistir(metinler)
        self.assertEqual(p.ceviri_al("You have [money] coins."), sahte_cevir("You have [money] coins."))

    def test_inatci_bozuk_degisken_maskelenir_veya_basarisiz(self):
        s = self.sunucu.senaryo
        s.token_boz["[gold]"] = 3  # 3 kez bozuk; 4. deneme maskeli olur ve başarılı olmalı
        metinler = ["You have [gold] gold."]
        p, c, _y = self._calistir(metinler)
        c_ = p.ceviri_al("You have [gold] gold.")
        self.assertIsNotNone(c_)
        _x, ciddi, _s = koruma.dogrula("You have [gold] gold.", c_)
        self.assertEqual(ciddi, [])

    def test_guvenlik_engeli_sadece_o_satiri_etkiler(self):
        s = self.sunucu.senaryo
        s.engelli_kelimeler.append("YASAK")
        metinler = ["Normal line %d here." % i for i in range(9)] + ["This YASAK line is blocked."]
        p, c, _y = self._calistir(metinler)
        for m in metinler[:-1]:
            self.assertIsNotNone(p.ceviri_al(m), m)
        self.assertIsNone(p.ceviri_al(metinler[-1]))
        self.assertEqual(p.durum_al(metinler[-1]), proje.BASARISIZ)

    def test_engellenen_satir_diger_modelle_cevrilir(self):
        s = self.sunucu.senaryo
        s.engelli_kelimeler.append("HASSAS")
        s.engelli_sadece_model = "gemini-2.5-flash"
        metinler = ["Normal line %d here." % i for i in range(4)] + ["This HASSAS line."]
        p, c, _y = self._calistir(metinler)
        for m in metinler:
            self.assertEqual(p.ceviri_al(m), sahte_cevir(m), m)

    def test_internet_kesintisi_satirlari_basarisiz_saymaz(self):
        import types
        eski_random = anahtarlar.random
        anahtarlar.random = types.SimpleNamespace(uniform=lambda a, b: 0.01)
        gemini.API_TABANI = "http://127.0.0.1:9/v1beta"   # kapalı port: bağlantı reddedilir
        try:
            metinler = ["Line %d is here." % i for i in range(12)]
            p, c, _y = self._calistir(metinler)
        finally:
            anahtarlar.random = eski_random
        self.assertIsInstance(c.kritik_hata, cevirmen.BaglantiKesildi)
        for m in metinler:
            self.assertIsNone(p.durum_al(m), m)

    def test_istekleri_reddeden_model_birakilir(self):
        self.sunucu.senaryo.reddeden_modeller.add("gemini-2.5-flash")
        metinler = ["Line number %d is right here." % i for i in range(12)]
        p, c, y = self._calistir(metinler)
        for m in metinler:
            self.assertEqual(p.ceviri_al(m), sahte_cevir(m), m)
        self.assertEqual(c.istatistik["basarisiz"], 0)
        self.assertIn("gemini-2.5-flash", y.model_kapali)

    def test_desteklenmeyen_ozellik_kapatilir(self):
        s = self.sunucu.senaryo
        s.desteklenmeyen["gemini-2.5-flash"] = {"dusunme", "sema"}
        metinler = ["Hello there friend."]
        p, c, y = self._calistir(metinler)
        self.assertEqual(p.ceviri_al(metinler[0]), sahte_cevir(metinler[0]))
        self.assertFalse(y.ozellik("gemini-2.5-flash").get("dusunme", True))

    def test_sozluk(self):
        p = proje.Proje(os.path.join(self.gecici, "oyun"))
        yon = anahtarlar.AnahtarYoneticisi([ANAHTAR_A], self.ayar["modeller"], lambda m: 0.0, None)
        s = Sozluk()
        c = cevirmen.Cevirmen(p, yon, self.ayar, s, "Test", "")
        n = c.sozluk_olustur(["Sylvie", "Mom", "???"], ["I saw Lucy today.", "Lucy is nice.", "Then Lucy left."], lambda k: "")
        self.assertGreaterEqual(n, 2)
        self.assertEqual(s.karsilik("Mom"), "Anne")
        self.assertEqual(s.karsilik("Sylvie"), "Sylvie")
        self.assertIsNone(s.karsilik("???"))


if __name__ == "__main__":
    unittest.main()
