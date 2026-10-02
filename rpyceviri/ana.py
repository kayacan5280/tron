"""Programın ana akışı ve menüleri."""

import argparse
import collections
import importlib
import math
import os
import re
import subprocess
import sys
import time

from . import SURUM
from . import anahtarlar as anahtar_mod
from . import arayuz as ui
from . import ayarlar as ayar_mod
from . import cevirmen as cevirmen_mod
from . import dogallik
from . import duzenleme
from . import gemini
from . import hafiza as hafiza_mod
from . import karakterler as karakter_mod
from . import koruma
from . import kortest
from . import kurulum
from . import oyun as oyun_mod
from . import proje as proje_mod
from . import saglayicilar
from . import zaman
from .sozluk import Sozluk

# Dil seçim ekranlarındaki dil adları çevrilmez.
DIL_ADLARI = {
    "English", "Français", "Francais", "Deutsch", "Español", "Espanol", "Italiano", "Português", "Portugues",
    "Português (Brasil)", "Русский", "日本語", "한국어", "简体中文", "繁體中文", "中文", "Polski", "Türkçe", "Turkce",
    "Česky", "Čeština", "Dansk", "Bahasa Melayu", "Bahasa Indonesia", "Українська", "Tiếng Việt", "Nederlands",
    "Svenska", "Suomi", "Norsk", "Magyar", "Română", "Ελληνικά", "العربية", "فارسی", "ไทย", "Español (Latinoamérica)",
    "Filipino", "Hrvatski", "Slovenčina", "Български", "Srpski", "Српски", "עברית", "हिन्दी", "Lietuvių", "Latviešu", "Eesti",
}

TUR_ESLEME = {"cevir": "arayuz", "ekran": "arayuz", "isim": "isim", "python": "python"}

KALITE_MODLARI = [
    ("hizli", "Hızlı", "tek geçiş, en az istek"),
    ("dengeli", "Dengeli", "çeviri kokan satırları ikinci kez bir 'Türk editör' düzeltir (önerilen, ~%10-30 ek istek)"),
    ("en_iyi", "En iyi", "bütün diyaloglar editörden geçer (yaklaşık 2 kat istek / maliyet)"),
]
EDITOR_ORANI = {"hizli": 0.0, "dengeli": 0.25, "en_iyi": 1.0}


# ---------------------------------------------------------------------------
# API anahtarları
# ---------------------------------------------------------------------------


def _anahtar_nasil_alinir():
    ui.ara_baslik("Gemini API anahtarı nasıl alınır? (ücretsiz)")
    ui.yaz("  1. Tarayıcıda şu adrese gidin:  " + ui.renk("https://aistudio.google.com/apikey", "kalin"))
    ui.yaz("  2. Google hesabınızla giriş yapın.")
    ui.yaz("  3. 'Create API key' (API anahtarı oluştur) butonuna basın ve anahtarı kopyalayın.")
    ui.yaz("  " + ui.renk("İpucu:", "sari") + " Her anahtarı FARKLI bir Google hesabından alın. Aynı hesabın")
    ui.yaz("  anahtarları aynı kotayı paylaşır; farklı hesaplar = daha fazla ücretsiz çeviri.")


def _ucretli_bilgi():
    ui.ara_baslik("Ücretli servisler (isteğe bağlı, daha yüksek kalite)")
    ui.yaz("  Kredi yüklediğiniz bir hesabın anahtarını da girebilirsiniz; program otomatik tanır:")
    for sag, bilgi in saglayicilar.SAGLAYICILAR.items():
        if bilgi["ucretli"]:
            ui.yaz("   - %-17s %s" % (bilgi["ad"], bilgi["site"]))
    ui.yaz("  Ücretli servis kullanılırsa her çeviriden önce tahmini maliyet gösterilir ve bütçe sorulur.")


def _anahtarlari_test_et(anahtarlar):
    """Her anahtarı ücret/kota harcamadan (model listesi isteğiyle) dener.

    anahtarlar: (sağlayıcı, anahtar) ikilileri. Döndürür: [(ikili, durum True/False/None)]
    """
    sonuc = []
    for sag, a in anahtarlar:
        etiket = "%s %s" % (saglayicilar.saglayici_adi(sag), anahtar_mod.anahtar_etiketi(a))
        try:
            modeller = saglayicilar.modelleri_listele(sag, a)
            ui.basari("%s  geçerli (%d model erişilebilir)" % (etiket, len(modeller)))
            sonuc.append(((sag, a), True))
        except gemini.ApiHatasi as h:
            if h.tur == gemini.SDK_YOK:
                ui.uyari("%s  denenemedi (Claude paketi kurulu değil; çeviri başlarken kurulması önerilecek)." % etiket)
                sonuc.append(((sag, a), None))
            elif h.tur in (gemini.AG, gemini.ZAMAN_ASIMI, gemini.SUNUCU, gemini.SSL, gemini.KOTA_DAKIKA, gemini.KREDI):
                ui.uyari("%s  denenemedi (%s). Yine de kaydedilecek." % (etiket, h.mesaj))
                sonuc.append(((sag, a), None))
            else:
                ui.hata("%s  GEÇERSİZ: %s" % (etiket, h.mesaj))
                sonuc.append(((sag, a), False))
    return sonuc


def _belirsiz_anahtar_turu(parca):
    ui.yaz("  '%s' ile başlayan anahtar hangi servise ait?" % parca[:6])
    secim = ui.secim("Servis", [("1", "DeepSeek"), ("2", "OpenAI (ChatGPT)"), ("3", "OpenRouter")], "1")
    return {"1": "deepseek", "2": "openai", "3": "openrouter"}[secim]


def _anahtar_gir():
    """Kullanıcıdan anahtarları alır. Döndürür: (sağlayıcı, anahtar) ikilileri."""
    ui.yaz("")
    ui.yaz("API anahtarlarınızı yapıştırın (her satıra bir tane; birden fazla girebilirsiniz).")
    ui.yaz("Bitirince " + ui.renk("boş satırda Enter", "kalin") + "'a basın.")
    yeni = []
    while True:
        satir = ui.sor("Anahtar %d" % (len(yeni) + 1))
        if not satir:
            break
        onek = None
        for parca in satir.replace(",", " ").replace(";", " ").split():
            parca = parca.strip().strip('"').strip("'")
            if not parca:
                continue
            # "claude: sk-ant-..." biçimi: önek ayrı parça olarak gelebilir.
            if parca.endswith(":") and parca[:-1].lower() in saglayicilar.SAGLAYICILAR:
                onek = parca[:-1].lower()
                continue
            if onek:
                sag, deger = onek, parca
                onek = None
            else:
                sag, deger = saglayicilar.anahtar_coz(parca)
                if ":" not in parca and saglayicilar.anahtar_turu_tahmin(deger) is None:
                    sag = _belirsiz_anahtar_turu(deger)
            if not anahtar_mod.anahtar_bicimi_uygun_mu(deger):
                ui.uyari("Bu bir API anahtarına benzemiyor, atlandı: %s" % deger[:12])
                continue
            if all(deger != a for _s, a in yeni):
                yeni.append((sag, deger))
                ui.yaz("     → " + saglayicilar.saglayici_adi(sag))
    return yeni


def anahtarlari_hazirla():
    """Kayıtlı anahtarları döndürür; yoksa kullanıcıdan bir kez ister ve kaydeder."""
    anahtarlar = anahtar_mod.anahtarlari_oku(ayar_mod.ANAHTAR_DOSYASI)
    if anahtarlar:
        return anahtarlar

    ui.baslik("İlk kurulum: API anahtarları")
    ui.yaz("Çeviri için Google'ın ücretsiz Gemini yapay zekasını kullanıyoruz.")
    ui.yaz("Anahtarları bir kez girersiniz; program onları hatırlar (api_anahtarlari.txt).")
    _anahtar_nasil_alinir()
    _ucretli_bilgi()

    while True:
        yeni = _anahtar_gir()
        if not yeni:
            ui.uyari("Hiç anahtar girilmedi. Anahtar olmadan çeviri yapılamaz.")
            if not ui.evet_mi("Tekrar denemek ister misiniz?", True):
                return []
            continue
        ui.bilgi("Anahtarlar deneniyor (kota/ücret harcanmaz)...")
        sonuc = _anahtarlari_test_et(yeni)
        gecerli = [ikili for ikili, durum in sonuc if durum is not False]
        if not gecerli:
            ui.hata("Geçerli anahtar yok. Anahtarı doğru kopyaladığınızdan emin olun.")
            continue
        anahtar_mod.anahtarlari_yaz(ayar_mod.ANAHTAR_DOSYASI, gecerli)
        ui.basari("%d anahtar kaydedildi." % len(gecerli))
        return gecerli


def anahtar_menusu():
    while True:
        anahtarlar = anahtar_mod.anahtarlari_oku(ayar_mod.ANAHTAR_DOSYASI)
        ui.baslik("API anahtarları (%d adet)" % len(anahtarlar))
        ayar, _ = ayar_mod.yukle()
        yon = anahtar_mod.AnahtarYoneticisi(anahtarlar, ayar["modeller"], lambda m: 1, ayar_mod.ANAHTAR_DURUM_DOSYASI)
        for i, s in enumerate(yon.ozet()):
            ui.yaz("  %2d) %s" % (i + 1, s))
        if not anahtarlar:
            ui.yaz("  (kayıtlı anahtar yok)")
        ui.yaz("")
        secim = ui.secim("Seçiminiz", [
            ("1", "Anahtar ekle (Gemini ücretsiz; Claude/DeepSeek/OpenAI ücretli)"),
            ("2", "Anahtar sil"),
            ("3", "Tüm anahtarları dene (kota/ücret harcamaz)"),
            ("4", "'Kota doldu' / 'geçersiz' işaretlerini sıfırla"),
            ("5", "Anahtar nasıl alınır?"),
            ("0", "Geri"),
        ], "0")
        if secim == "0":
            return
        if secim == "1":
            yeni = _anahtar_gir()
            yeni = [ikili for ikili in yeni if all(ikili[1] != a for _s, a in anahtarlar)]
            if yeni:
                ui.bilgi("Yeni anahtarlar deneniyor...")
                sonuc = _anahtarlari_test_et(yeni)
                ekle = [ikili for ikili, d in sonuc if d is not False]
                anahtar_mod.anahtarlari_yaz(ayar_mod.ANAHTAR_DOSYASI, anahtarlar + ekle)
                ui.basari("%d anahtar eklendi." % len(ekle))
        elif secim == "2":
            if not anahtarlar:
                continue
            no = ui.sor("Silinecek anahtarın numarası (iptal için boş bırakın)")
            if no.isdigit() and 1 <= int(no) <= len(anahtarlar):
                silinen = anahtarlar.pop(int(no) - 1)
                anahtar_mod.anahtarlari_yaz(ayar_mod.ANAHTAR_DOSYASI, anahtarlar)
                ui.basari("Silindi: %s" % anahtar_mod.anahtar_etiketi(silinen[1]))
        elif secim == "3":
            sonuc = _anahtarlari_test_et(anahtarlar)
            gecersiz = [ikili for ikili, d in sonuc if d is False]
            if gecersiz and ui.evet_mi("%d geçersiz anahtar listeden silinsin mi?" % len(gecersiz), True):
                anahtar_mod.anahtarlari_yaz(ayar_mod.ANAHTAR_DOSYASI, [a for a in anahtarlar if a not in gecersiz])
        elif secim == "4":
            yon.durumu_sifirla()
            ui.basari("Sıfırlandı.")
        elif secim == "5":
            _anahtar_nasil_alinir()
            _ucretli_bilgi()
            ui.bekle()


def _claude_paketini_hazirla(otomatik=False):
    """Claude için resmî 'anthropic' paketini denetler; yoksa kurmayı önerir."""
    if saglayicilar.claude_sdk_var_mi():
        return True
    ui.uyari("Claude'u kullanmak için 'anthropic' Python paketi gerekiyor (bir kerelik kurulum).")
    if not otomatik and not ui.evet_mi("Şimdi kurulsun mu? (internet gerekir, ~1 dk)", True):
        return False
    ui.bilgi("Kuruluyor: pip install anthropic ...")
    try:
        sonuc = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "anthropic"],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
        cikti = sonuc.stdout.decode("utf-8", "replace") if sonuc.stdout else ""
    except Exception as e:
        cikti = str(e)
        sonuc = None
    importlib.invalidate_caches()
    if saglayicilar.claude_sdk_var_mi():
        ui.basari("Claude paketi kuruldu.")
        return True
    ui.hata("Kurulum başarısız oldu. Komut isteminde şunu çalıştırmayı deneyin:  py -m pip install anthropic")
    if cikti:
        ui.yaz("   " + cikti.strip().splitlines()[-1][:200])
    return False


# ---------------------------------------------------------------------------
# Oyun seçimi
# ---------------------------------------------------------------------------


def oyun_sec(ayar, verilen=None):
    if verilen:
        return oyun_mod.oyun_bul(oyun_mod.yol_temizle(verilen))

    son = [y for y in ayar.get("son_oyunlar", []) if isinstance(y, str) and os.path.isdir(y)]
    ui.ara_baslik("Oyun seçimi")
    if son:
        ui.yaz("Son oyunlar:")
        for i, y in enumerate(son[:9]):
            ui.yaz("  " + ui.renk("[%d]" % (i + 1), "kalin") + " " + y)
    ui.yaz("Oyunun klasörünü bu pencereye " + ui.renk("sürükleyip bırakın", "kalin") + " ve Enter'a basın")
    ui.yaz("(veya klasör yolunu yazın" + (" / listeden numara seçin" if son else "") + "). İptal için boş bırakın.")
    while True:
        girdi = ui.sor("Oyun klasörü")
        if not girdi:
            return None
        if girdi.isdigit() and son and 1 <= int(girdi) <= min(9, len(son)):
            girdi = son[int(girdi) - 1]
        try:
            return oyun_mod.oyun_bul(oyun_mod.yol_temizle(girdi))
        except oyun_mod.OyunHatasi as e:
            ui.hata(str(e))


def _son_oyunlara_ekle(ayar, kok):
    liste = [y for y in ayar.get("son_oyunlar", []) if y != kok]
    ayar["son_oyunlar"] = [kok] + liste[:8]
    try:
        ayar.kaydet()
    except Exception:
        pass


def _dosyayi_ac(yol):
    try:
        if os.name == "nt":
            os.startfile(yol)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", yol])
        else:
            subprocess.Popen(["xdg-open", yol], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def _ac_ve_bekle(yol, mesaj="Düzenleyip kaydettikten sonra Enter'a basın"):
    if not _dosyayi_ac(yol):
        ui.yaz("Dosyayı elle açın: " + yol)
    ui.bekle(mesaj)


# ---------------------------------------------------------------------------
# Metin listeleri
# ---------------------------------------------------------------------------


class Metinler(object):
    """ogeleri_hazirla() sonucu."""

    def __init__(self):
        self.diyalog_sira = []        # tüm benzersiz diyaloglar (oyundaki sırayla; bağlam için)
        self.diyaloglar = []          # çevrilmesi gereken diyaloglar
        self.metin_ogeleri = []       # tüm arayüz/kod metinleri
        self.metinler = []            # çevrilmesi gereken arayüz/kod metinleri
        self.isimler = []             # karakter adı türündeki metinler
        self.konusan_sayaci = collections.Counter()
        self.hazir = 0

    def tumu(self):
        return self.diyalog_sira + self.metin_ogeleri

    def gerekli_ayikla(self, proje):
        self.diyaloglar = [o for o in self.diyaloglar if proje.ceviri_al(o.m) is None]
        self.metinler = [o for o in self.metinler if proje.ceviri_al(o.m) is None]


def ogeleri_hazirla(cikti, proje, ayar):
    """Çıktıdan çevrilecek Oge listelerini hazırlar; hazır tablolardan doldurur."""
    ortak, ek = kurulum.arayuz_tablosu()
    s = Metinler()
    diyalog_kume = {}
    sayac = 0

    # Çıkarıcı, oyundaki sırayı korur (dosyalar Ren'Py yükleme sırasında, satırlar dosya içi sırada).
    for o in cikti.get("ogeler") or []:
        m = o.get("m")
        if not isinstance(m, str):
            continue
        if o.get("k"):
            s.konusan_sayaci[o["k"]] += 1
        if m in diyalog_kume:
            continue
        sayac += 1
        oge = cevirmen_mod.Oge(sayac, m, o.get("tur") or "diyalog", o.get("k") or "")
        diyalog_kume[m] = oge
        s.diyalog_sira.append(oge)

    # Karakter adları (Character tanımları ve konuşmacılar): sözlükle tutarlı çevrilir.
    karakter_adlari = set(k for k in s.konusan_sayaci if k and k != "extend")
    for c in cikti.get("karakterler") or []:
        if isinstance(c.get("ad"), str):
            karakter_adlari.add(c["ad"])

    metin_kume = set()
    for x in cikti.get("metinler") or []:
        m = x.get("m")
        if not isinstance(m, str) or m in diyalog_kume or m in metin_kume:
            continue
        tur = TUR_ESLEME.get(x.get("tur"), "arayuz")
        if m in karakter_adlari:
            tur = "isim"
        if tur == "python" and not ayar.get("python_metinleri", True):
            continue
        metin_kume.add(m)
        sayac += 1
        s.metin_ogeleri.append(cevirmen_mod.Oge(sayac, m, tur, ""))

    # Oyunun 'translate None strings' ile değiştirdiği metinler de çevrilmeli.
    for _eski, yeni in (cikti.get("none_ozel") or {}).items():
        if isinstance(yeni, str) and yeni not in diyalog_kume and yeni not in metin_kume:
            metin_kume.add(yeni)
            sayac += 1
            s.metin_ogeleri.append(cevirmen_mod.Oge(sayac, yeni, "arayuz", ""))

    # Hazır tablolar ve çevrilmesi gerekmeyenler.
    for o in s.tumu():
        if proje.ceviri_al(o.m) is not None:
            continue
        tablo = ortak.get(o.m) or ek.get(o.m)
        if tablo:
            proje.ceviri_kaydet(o.m, tablo, proje_mod.HAZIR, model="tablo")
            s.hazir += 1

    def gerekli(o):
        if proje.ceviri_al(o.m) is not None:
            return False
        if not koruma.cevrilecek_mi(o.m):
            return False
        if o.m.strip() in DIL_ADLARI:
            return False
        return True

    s.diyaloglar = [o for o in s.diyalog_sira if gerekli(o)]
    s.metinler = [o for o in s.metin_ogeleri if gerekli(o)]
    s.isimler = [o for o in s.metin_ogeleri if o.tur == "isim"]
    return s


# ---------------------------------------------------------------------------
# Rapor
# ---------------------------------------------------------------------------


def rapor_yaz(proje, cikti, istatistik, oyun, maliyet_metni=""):
    basarisiz = []
    supheli = []
    elle = 0
    for m, k in proje.ceviriler.items():
        if not isinstance(k, dict):
            continue
        if k.get("d") == proje_mod.BASARISIZ:
            basarisiz.append((m, k.get("n", "")))
        elif k.get("d") == proje_mod.ELLE:
            elle += 1
        elif k.get("n") and str(k.get("n")).startswith("şüpheli"):
            supheli.append((m, k.get("c"), k.get("n")))
    tasan = []
    gorulen = set()
    for o in cikti.get("ogeler") or []:
        m = o.get("m")
        if not isinstance(m, str) or m in gorulen or (o.get("tur") or "diyalog") != "diyalog":
            continue
        gorulen.add(m)
        c = proje.ceviri_al(m)
        if c and dogallik.tasma_riski(m, c):
            tasan.append((m, c))
    with open(proje.rapor_yolu, "w", encoding="utf-8") as f:
        f.write("ÇEVİRİ RAPORU - %s\n" % oyun.ad)
        f.write("Oluşturma: %s\n\n" % time.strftime("%d.%m.%Y %H:%M"))
        f.write("İstek sayısı: %d | Girdi token: %d | Çıktı token: %d\n" % (
            istatistik.get("istek", 0), istatistik.get("token_girdi", 0), istatistik.get("token_cikti", 0)))
        if maliyet_metni:
            f.write(maliyet_metni + "\n")
        f.write("Elle düzeltilmiş çeviri: %d\n\n" % elle)
        f.write("=== ÇEVRİLEMEYEN METİNLER (%d) ===\n" % len(basarisiz))
        f.write("Bunlar oyunda orijinal haliyle görünür. Programı tekrar çalıştırınca yeniden denenir.\n\n")
        for m, n in basarisiz:
            f.write("- %r\n    neden: %s\n" % (m, n))
        f.write("\n=== KONTROL EDİLMESİ ÖNERİLEN ÇEVİRİLER (%d) ===\n\n" % len(supheli))
        for m, c, n in supheli:
            f.write("- KAYNAK: %r\n  ÇEVİRİ: %r\n  (%s)\n" % (m, c, n))
        f.write("\n=== METİN KUTUSUNDAN TAŞABİLECEK UZUN SATIRLAR (%d) ===\n" % len(tasan))
        f.write("Bunların yazısı oyunda biraz küçültülür. İsterseniz 'Çevirileri elle düzenle' ile kısaltabilirsiniz.\n\n")
        for m, c in tasan:
            f.write("- KAYNAK: %r\n  ÇEVİRİ: %r\n" % (m, c))
    return len(basarisiz), len(supheli)


# ---------------------------------------------------------------------------
# Model / servis seçimi
# ---------------------------------------------------------------------------


_KARARLI_FLASH = re.compile(r"^gemini-(\d+(?:\.\d+)?)-flash(-lite)?$")
_FLASH_TAKMA = re.compile(r"^gemini-flash(-lite)?-latest$")


def otomatik_modeller(erisilebilir):
    """Erişilebilir modellerden kararlı 'flash' modellerini seçer (yeniden eskiye, önce tam sonra lite)."""
    adaylar = []
    for m in erisilebilir:
        k = _KARARLI_FLASH.match(m)
        if k:
            adaylar.append((1 if k.group(2) else 0, -float(k.group(1)), m))
            continue
        k = _FLASH_TAKMA.match(m)
        if k:
            adaylar.append((1 if k.group(1) else 0, -999.0, m))
    return [m for _l, _s, m in sorted(adaylar)]


def _model_listesini_dogrula(anahtarlar, ayar):
    """Ayarlardaki Gemini modellerinden erişilebilir olanları döndürür.

    Google eski modelleri zamanla kaldırır; ayarlardaki modeller kalkmışsa ya da
    hesapta başka kararlı 'flash' modelleri varsa bunlar da (ek kota olarak)
    listenin sonuna eklenir.
    """
    modeller = list(ayar["modeller"])
    for a in anahtarlar[:3]:
        try:
            erisilebilir = set(gemini.modelleri_listele(a))
        except gemini.ApiHatasi:
            continue
        if not erisilebilir:
            break
        uygun = [m for m in modeller if m in erisilebilir]
        olmayan = [m for m in modeller if m not in erisilebilir]
        if olmayan:
            ui.bilgi("Erişilemeyen modeller atlanacak: " + ", ".join(olmayan))
        ek = [m for m in otomatik_modeller(erisilebilir) if m not in uygun]
        if ek:
            ui.bilgi("Ek kota için eklenen modeller: " + ", ".join(ek))
        if uygun or ek:
            return uygun + ek
        ui.uyari("Ayarlardaki modellerin hiçbiri erişilebilir değil; yine de denenecek.")
        break
    return modeller


def _saglayici_sirasi(anahtarlar, ayar):
    """Anahtarı olan servisler, ayarlardaki sıraya göre."""
    var = []
    for s, _a in anahtarlar:
        if s not in var:
            var.append(s)
    sira = [s for s in ayar.get("saglayici_sirasi") or [] if s in var]
    return sira + [s for s in var if s not in sira]


def _saglayici_sec(anahtarlar, ayar, otomatik):
    """Birden fazla servisin anahtarı varsa hangisinin kullanılacağını sorar."""
    sira = _saglayici_sirasi(anahtarlar, ayar)
    if len(sira) <= 1 or otomatik:
        return sira
    ui.ara_baslik("Hangi yapay zeka kullanılsın?")
    secenekler = []
    for i, s in enumerate(sira):
        etiket = saglayicilar.saglayici_adi(s) + (" (ücretli)" if saglayicilar.ucretli_mi(s) else " (ücretsiz)")
        secenekler.append((str(i + 1), "Sadece " + etiket))
    secenekler.append(("H", "Hepsi sırayla: %s (biri biterse sonrakine geçer)" %
                       " → ".join(saglayicilar.saglayici_adi(s) for s in sira)))
    onceki = ayar.get("son_saglayici_secimi") or "H"
    gecerli = [k for k, _m in secenekler]
    secim = ui.secim("Seçiminiz", secenekler, onceki if onceki in gecerli else "H").upper()
    ayar["son_saglayici_secimi"] = secim
    try:
        ayar.kaydet()
    except Exception:
        pass
    if secim == "H":
        return sira
    return [sira[int(secim) - 1]]


def _hedefleri_hazirla(anahtarlar, ayar, secilen, otomatik):
    """Seçilen servislerin hedef listesi ("sağlayıcı/model")."""
    hedefler = []
    for s in secilen:
        if s == "gemini":
            gemini_anahtarlari = [a for sag, a in anahtarlar if sag == "gemini"]
            hedefler += [saglayicilar.hedef_adi("gemini", m) for m in _model_listesini_dogrula(gemini_anahtarlari, ayar)]
        elif s == "claude":
            if _claude_paketini_hazirla(otomatik):
                hedefler.append(saglayicilar.hedef_adi("claude", ayar["claude_modeli"]))
            else:
                ui.uyari("Claude atlanıyor.")
        else:
            hedefler.append(saglayicilar.hedef_adi(s, ayar[s + "_modeli"]))
    return hedefler


def _kalite_modu_sec(ayar, otomatik):
    if otomatik:
        return ayar.get("kalite_modu", "dengeli")
    ui.ara_baslik("Kalite modu")
    secenekler = [(str(i + 1), "%-8s — %s" % (ad, aciklama)) for i, (_k, ad, aciklama) in enumerate(KALITE_MODLARI)]
    kodlar = [k for k, _a, _c in KALITE_MODLARI]
    varsayilan = str(kodlar.index(ayar.get("kalite_modu", "dengeli")) + 1)
    secim = ui.secim("Seçiminiz", secenekler, varsayilan)
    mod = kodlar[int(secim) - 1]
    if mod != ayar.get("kalite_modu"):
        ayar["kalite_modu"] = mod
        try:
            ayar.kaydet()
        except Exception:
            pass
    return mod


def _sayi_coz(metin):
    try:
        return float(metin.replace("$", "").replace(",", ".").strip())
    except ValueError:
        return None


def _butce_belirle(hedefler, ayar, proje, metinler, mod, otomatik):
    """Ücretli servis seçildiyse tahmini maliyeti gösterir ve bütçeyi belirler. 0 = sınırsız."""
    ucretli = [h for h in hedefler if saglayicilar.ucretli_mi(h)]
    if not ucretli:
        return 0.0
    ui.ara_baslik("Maliyet")
    kaynak = sum(len(o.m) for o in metinler.diyaloglar + metinler.metinler)
    satir = len(metinler.diyaloglar) + len(metinler.metinler)
    for h in ucretli:
        t = saglayicilar.maliyet_tahmini(h, ayar, kaynak, satir, EDITOR_ORANI.get(mod, 0.25), ayar.get("fiyatlar"))
        ad = saglayicilar.model_adi(h)
        if t is None:
            ui.yaz("  %-22s : fiyatı bilinmiyor (ayarlar.json → fiyatlar)" % ad)
        else:
            ui.yaz("  %-22s : tahmini ~%.2f $ (kabaca; gerçek tutar ±%%50 değişebilir)" % (ad, t))
    harcanan = proje.maliyet_al()
    if harcanan:
        ui.yaz("  Bu oyun için şimdiye kadar harcanan: ~%.2f $ (bütçeye dahildir)" % harcanan)
    if any(saglayicilar.hedef_coz(h)[0] == "claude" for h in ucretli):
        ui.yaz("  " + ui.renk("Not:", "gri") + " Claude'da sunucu taraflı yedek model (fallbacks) açık: bir istek")
        ui.yaz("  güvenlik sınıflandırıcısına takılırsa Anthropic'in önerdiği modelle otomatik yeniden denenir.")
    butce = float(ayar.get("butce_usd", 0.0) or 0.0)
    if butce:
        ui.yaz("  Bütçe sınırı (ayarlar): %.2f $" % butce)
        return butce
    if otomatik:
        return 0.0
    while True:
        cevap = ui.sor("Bu oyun için en fazla kaç dolar harcansın? (boş = sınırsız)")
        if not cevap:
            return 0.0
        deger = _sayi_coz(cevap)
        if deger is not None and deger >= 0:
            return deger
        ui.uyari("Sadece sayı yazın (ör. 10 ya da 7.5).")


# ---------------------------------------------------------------------------
# Yardımcı adımlar
# ---------------------------------------------------------------------------


def _isimleri_uygula(sozluk, isim_ogeleri, metinler, proje):
    """Sözlükteki karakter adı karşılıklarını doğrudan uygular (API kullanmaz).

    Sözlük elle düzenlendiyse önceki çevirinin üzerine yazılır.
    """
    for o in isim_ogeleri:
        karsilik = sozluk.karsilik(o.m)
        if not karsilik:
            continue
        c, ciddi, _s = koruma.dogrula(o.m, karsilik)
        if ciddi:
            continue
        proje.ceviri_kaydet(o.m, c, proje_mod.SOZLUK, model="sozluk")
        if o in metinler:
            metinler.remove(o)
    proje.kaydet()


def _hafizadan_doldur(hafiza, proje, metinler):
    """Ortak hafızada (başka oyunlarda) çevrilmiş kısa metinleri API kullanmadan doldurur."""
    n = 0
    for o in metinler.diyaloglar + metinler.metinler:
        c = hafiza.al(o.m, o.tur)
        if not c:
            continue
        c2, ciddi, suphe = koruma.dogrula(o.m, c)
        if ciddi or suphe:
            continue
        if proje.ceviri_kaydet(o.m, c2, proje_mod.HAFIZA, model="hafiza"):
            n += 1
    metinler.gerekli_ayikla(proje)
    proje.kaydet()
    return n


def _hafizayi_guncelle(hafiza, proje, ogeler):
    for o in ogeler:
        k = proje.kayit_al(o.m)
        if not k or not isinstance(k.get("c"), str):
            continue
        if k.get("d") in (proje_mod.TAMAM, proje_mod.ELLE) and not str(k.get("n") or "").startswith("şüpheli"):
            hafiza.ekle(o.m, k["c"], o.tur, elle=k.get("d") == proje_mod.ELLE)
    try:
        hafiza.kaydet()
    except OSError as e:
        proje.gunluge_yaz("Ortak hafıza kaydedilemedi: %s" % e)


def _duzenleme_ogeleri(metinler):
    ogeler = [(o.m, o.k if o.k not in ("extend", "narrator") else "", o.tur) for o in metinler.diyalog_sira]
    ogeler += [(o.m, "", o.tur) for o in metinler.metin_ogeleri]
    return ogeler


def _duzenlemeleri_iceri_al(proje, metinler, hafiza=None, sessiz=False):
    """Düzenleme dosyasındaki değişiklikleri kaydeder. Döndürür: değişen sayısı."""
    gecerli = set(o.m for o in metinler.tumu())
    degisen, hatalar, ciftler = duzenleme.iceri_al(proje, gecerli)
    if degisen or not sessiz:
        ui.basari("Elle düzeltilen %d çeviri kaydedildi (bundan sonra hiçbir otomatik işlem bunları değiştirmez)." % degisen)
    for h in hatalar[:15]:
        ui.uyari(h)
    if len(hatalar) > 15:
        ui.uyari("... ve %d hata daha (ayrıntı: gunluk.txt)" % (len(hatalar) - 15))
    for h in hatalar:
        proje.gunluge_yaz("Düzenleme: " + h)
    if hafiza is not None and ciftler:
        turler = dict((o.m, o.tur) for o in metinler.tumu())
        for k, c in ciftler:
            hafiza.ekle(k, c, turler.get(k, "diyalog"), elle=True)
        try:
            hafiza.kaydet()
        except OSError:
            pass
    return degisen


def _metinleri_cikar(oyun, proje, ayar, otomatik):
    cikti = proje_mod.json_oku(proje.cikti_yolu)
    yeniden = True
    if cikti and not otomatik:
        yeniden = ui.evet_mi("Metinler daha önce çıkarılmış. Oyun güncellenmiş olabilir; yeniden çıkarılsın mı?", True)
    if yeniden or not cikti:
        ui.ara_baslik("1/5  Metinler oyundan çıkarılıyor")
        ui.yaz("Oyun birkaç saniyeliğine açılıp kendiliğinden kapanacak. " + ui.renk("Oyun açıksa önce kapatın.", "sari"))

        def durum(m):
            ui.bilgi(m)

        def manuel():
            ui.uyari("Oyun otomatik başlatılamadı.")
            ui.yaz("Lütfen oyunu NORMAL şekilde (çift tıklayarak) açın. Oyun kısa süre sonra kendiliğinden kapanacak.")
            ui.yaz("Program bekliyor...")

        try:
            cikti = oyun_mod.metinleri_cikar(oyun, proje.cikti_yolu, ayar["oyun_baslatma_bekleme_sn"], durum, manuel)
        except oyun_mod.OyunHatasi as e:
            ui.hata(str(e))
            proje.gunluge_yaz("Çıkarma hatası: %s" % e)
            return None
        ui.basari("Metinler çıkarıldı.")
    return cikti


# ---------------------------------------------------------------------------
# Ana çeviri akışı
# ---------------------------------------------------------------------------


def oyunu_cevir(ayar, oyun_yolu=None, otomatik=False):
    try:
        oyun = oyun_sec(ayar, oyun_yolu)
    except oyun_mod.OyunHatasi as e:
        ui.hata(str(e))
        return False
    if oyun is None:
        return False

    ui.baslik("Oyun: " + oyun.ad)
    ui.bilgi("Klasör: " + oyun.kok)
    if oyun.renpy_surumu:
        ui.bilgi("Ren'Py sürümü: " + oyun.renpy_surumu)
    if kurulum.yama_kurulu_mu(oyun):
        ui.bilgi("Bu oyunda Türkçe yama zaten kurulu (güncellenecek).")
    _son_oyunlara_ekle(ayar, oyun.kok)

    anahtarlar = anahtarlari_hazirla()
    if not anahtarlar:
        return False

    proje = proje_mod.Proje(oyun.kok)
    proje.gunluge_yaz("=== Oturum başladı (sürüm %s) ===" % SURUM)
    hafiza = hafiza_mod.Hafiza() if ayar.get("ortak_hafiza", True) else None

    # 1) Metinleri çıkar
    cikti = _metinleri_cikar(oyun, proje, ayar, otomatik)
    if cikti is None:
        return False
    for u in cikti.get("uyarilar") or []:
        proje.gunluge_yaz("Çıkarıcı uyarısı: %s" % u)

    metinler = ogeleri_hazirla(cikti, proje, ayar)

    # Kullanıcının düzenleme dosyasında yaptığı (henüz alınmamış) değişiklikler
    if os.path.exists(proje.duzenleme_yolu) and duzenleme.degismis_mi(proje):
        ui.bilgi("Düzenleme dosyasında kaydedilmiş değişiklikler bulundu; alınıyor...")
        _duzenlemeleri_iceri_al(proje, metinler, hafiza, sessiz=True)
        metinler.gerekli_ayikla(proje)
    proje.kaydet()

    ui.ara_baslik("Oyun bilgisi")
    ui.yaz("  Ren'Py           : %s" % (cikti.get("renpy_surumu") or "?"))
    ui.yaz("  Oyun adı         : %s" % (cikti.get("oyun_adi") or oyun.ad))
    ui.yaz("  Diyalog/seçenek  : %d satır (%d benzersiz)" % (len(cikti.get("ogeler") or []), len(metinler.diyalog_sira)))
    ui.yaz("  Arayüz/kod metni : %d" % len(cikti.get("metinler") or []))
    ui.yaz("  Hazır çeviri     : %d (yerleşik Türkçe arayüz tablosu)" % metinler.hazir)
    if cikti.get("diller"):
        ui.yaz("  Oyundaki diller  : %s" % ", ".join(cikti["diller"]))
    eksik_font = [f for f in (cikti.get("fontlar") or []) if f.get("eksik")]
    if eksik_font:
        ui.uyari("%d fontta Türkçe harf eksik; bunlar otomatik olarak Türkçe destekli fontla değiştirilecek:" % len(eksik_font))
        for f in eksik_font[:8]:
            ui.yaz("     %s  (eksik: %s)" % (f.get("dosya"), f.get("eksik")))

    sozluk = Sozluk.oku(proje.sozluk_yolu)
    karakterler = karakter_mod.Karakterler.oku(proje.karakter_yolu)
    oyun_notu = proje.oyun_notu()
    if os.path.exists(proje.sozluk_yolu):
        _isimleri_uygula(sozluk, metinler.isimler, metinler.metinler, proje)
    if hafiza is not None and len(hafiza):
        n = _hafizadan_doldur(hafiza, proje, metinler)
        if n:
            ui.yaz("  Ortak hafızadan  : %d kısa metin (başka oyunlarda çevrilmiş, API harcanmaz)" % n)
    ui.yaz("  Çevrilecek       : %s diyalog + %s arayüz/kod metni" % (
        ui.renk(str(len(metinler.diyaloglar)), "kalin"), ui.renk(str(len(metinler.metinler)), "kalin")))

    istatistik = {}
    maliyet_metni = ""
    mod = ayar.get("kalite_modu", "dengeli")
    cev = None
    # Daha önceki çevirilerden kalan, editörden geçmemiş satırlar da kalite geçişine girer.
    toplam = len(metinler.diyaloglar) + len(metinler.metinler)
    inceleme_bekleyen = bool(cevirmen_mod.inceleme_adaylari(proje, metinler.diyalog_sira, mod))

    if toplam or inceleme_bekleyen:
        secilen = _saglayici_sec(anahtarlar, ayar, otomatik)
        hedefler = _hedefleri_hazirla(anahtarlar, ayar, secilen, otomatik)
        if not hedefler:
            ui.hata("Kullanılabilir yapay zeka modeli yok.")
            return False
        mod = _kalite_modu_sec(ayar, otomatik)
        if toplam:
            paket = float(ayar["paket_satir"])
            istek_tahmini = int(math.ceil(len(metinler.diyaloglar) / paket) + math.ceil(len(metinler.metinler) / paket))
            istek_tahmini = int(istek_tahmini * (1 + EDITOR_ORANI.get(mod, 0)))
            ui.yaz("  Tahmini istek    : ~%d (%d anahtar ile)" % (istek_tahmini, len(anahtarlar)))
        butce = _butce_belirle(hedefler, ayar, proje, metinler, mod, otomatik)

        # 2) Oyun notu
        if not oyun_notu and not otomatik and toplam:
            ui.ara_baslik("2/5  Oyun hakkında not (isteğe bağlı)")
            ui.yaz("Çeviriye yardımcı olacak kısa bir not yazabilirsiniz (tür, ortam, hitap tercihi vb.).")
            ui.yaz("Örnek: 'Lisede geçen romantik komedi. Ana karakter erkek. Arkadaşlar birbirine sen der.'")
            ui.yaz("Boş bırakıp Enter'a basarsanız atlanır.")
            oyun_notu = ui.sor("Not")
            proje.oyun_notu_yaz(oyun_notu)

        yonetici = anahtar_mod.AnahtarYoneticisi(
            anahtarlar, hedefler,
            lambda m: 60.0 / ayar_mod.dakikalik_sinir(ayar, m),
            ayar_mod.ANAHTAR_DURUM_DOSYASI,
        )
        ui.bilgi("Model sırası: " + " → ".join(saglayicilar.model_adi(h) for h in hedefler))
        ui.bilgi("Kullanılabilir anahtar: %d / %d" % (yonetici.kullanilabilir_anahtar_sayisi(), len(anahtarlar)))

        ilerleme = ui.Ilerleme(toplam, "Çeviri")

        def ilerleme_fonk(yapilan, top, model):
            ilerleme.toplam = top
            ilerleme.guncelle(yapilan, ek=("| " + model) if model else "")

        def bildir(tur, mesaj):
            {"uyari": ui.uyari, "hata": ui.hata}.get(tur, ui.bilgi)(mesaj)

        cev = cevirmen_mod.Cevirmen(proje, yonetici, ayar, sozluk, cikti.get("oyun_adi") or oyun.ad,
                                    oyun_notu, ilerleme_fonk, bildir, karakterler)
        cev.butce = butce
        cev.onceki_maliyet = proje.maliyet_al()

        try:
            # 3) Sözlük ve karakter kartları
            if not os.path.exists(proje.sozluk_yolu) or (not os.path.exists(proje.karakter_yolu) and toplam):
                ui.ara_baslik("3/5  Sözlük ve karakter kartları hazırlanıyor")
            if not os.path.exists(proje.sozluk_yolu):
                isimler = [k for k, _n in metinler.konusan_sayaci.most_common(60) if k and k != "extend"]
                isimler += [o.m for o in metinler.metinler if o.tur == "isim"]
                isimler += [c.get("ad") for c in (cikti.get("karakterler") or []) if isinstance(c.get("ad"), str)]

                ornekler = {}
                for o in cikti.get("ogeler") or []:
                    k = o.get("k")
                    if k and k not in ornekler:
                        ornekler[k] = o.get("m", "")[:160]
                try:
                    n = cev.sozluk_olustur(isimler, [o.m for o in metinler.diyalog_sira], ornekler.get)
                    sozluk.yaz(proje.sozluk_yolu)
                    ui.basari("Sözlük hazır: %d terim  →  %s" % (n, proje.sozluk_yolu))
                except anahtar_mod.TumKotalarBitti:
                    raise
                except Exception as e:
                    ui.uyari("Sözlük oluşturulamadı (%s); sözlüksüz devam ediliyor." % e)
                    sozluk.yaz(proje.sozluk_yolu)

                if not otomatik and len(sozluk) and ui.evet_mi("Sözlüğü açıp kontrol etmek/düzenlemek ister misiniz?", False):
                    _ac_ve_bekle(proje.sozluk_yolu)
                sozluk = Sozluk.oku(proje.sozluk_yolu)
                cev.bilgileri_guncelle(sozluk=sozluk)

            if not os.path.exists(proje.karakter_yolu) and toplam:
                ui.bilgi("Karakterlerin konuşma tarzları ve sen/siz hitapları belirleniyor...")
                try:
                    karakterler = cev.karakter_analizi(
                        [{"m": o.get("m"), "k": o.get("k")} for o in (cikti.get("ogeler") or [])])
                    karakterler.yaz(proje.karakter_yolu)
                    if len(karakterler):
                        ui.basari("Karakter kartları hazır: %d karakter, %d hitap  →  %s" % (
                            len(karakterler), len(karakterler.hitap), proje.karakter_yolu))
                    else:
                        ui.bilgi("Konuşan karakter bulunamadı ya da analiz yapılamadı; kartsız devam ediliyor.")
                except anahtar_mod.TumKotalarBitti:
                    raise
                except Exception as e:
                    ui.uyari("Karakter kartları hazırlanamadı (%s); kartsız devam ediliyor." % e)
                    karakter_mod.Karakterler().yaz(proje.karakter_yolu)
                if not otomatik and len(karakterler) and \
                        ui.evet_mi("Karakter kartlarını açıp kontrol etmek/düzenlemek ister misiniz?", False):
                    _ac_ve_bekle(proje.karakter_yolu)
                karakterler = karakter_mod.Karakterler.oku(proje.karakter_yolu)
                cev.bilgileri_guncelle(karakterler=karakterler)

            _isimleri_uygula(sozluk, metinler.isimler, metinler.metinler, proje)
            cev.karakter_satirlarini_hazirla(metinler.konusan_sayaci)

            # 4) Çeviri
            if metinler.diyaloglar or metinler.metinler:
                ui.ara_baslik("4/5  Çeviri")
                ui.yaz(ui.renk("Durdurmak için Ctrl+C", "gri") + " — çeviriler sürekli kaydedilir, sonra kaldığı yerden devam eder.")
                ilerleme.toplam = len(metinler.diyaloglar) + len(metinler.metinler)
                cev.calistir(metinler.diyaloglar, metinler.metinler, metinler.diyalog_sira)
                ilerleme.bitir()

            # 5) Kalite geçişi
            if mod != "hizli" and not cev.iptal.is_set() and cev.durdurma_nedeni is None and cev.kritik_hata is None:
                adaylar = cev.inceleme_adaylari(metinler.diyalog_sira, mod)
                if adaylar:
                    ui.ara_baslik("5/5  Kalite geçişi (Türk editör)")
                    ui.yaz("%d satır ikinci kez okunup doğallaştırılıyor%s." % (
                        len(adaylar), " (çeviri kokan satırlar)" if mod == "dengeli" else ""))
                    ilerleme = ui.Ilerleme(len(adaylar), "Editör")
                    cev.incele(adaylar, metinler.diyalog_sira)
                    ilerleme.bitir()
        except anahtar_mod.TumKotalarBitti as e:
            cev.durdurma_nedeni = e
            ilerleme.bitir()
        except KeyboardInterrupt:
            ilerleme.bitir()
            ui.uyari("Çeviri kullanıcı tarafından durduruldu. Yapılan çeviriler kaydedildi.")
            proje.kaydet()

        proje.kaydet()
        proje.maliyet_ekle(cev.maliyet)
        ist = istatistik = cev.istatistik
        ui.ara_baslik("Sonuç")
        ui.yaz("  Bu oturumda çevrilen : %d" % ist.get("cevrildi", 0))
        ui.yaz("  Çevrilemeyen         : %d" % ist.get("basarisiz", 0))
        if ist.get("editor_duzeltti") or ist.get("editor_onay"):
            ui.yaz("  Editör düzeltti      : %d (onayladı: %d)" % (ist.get("editor_duzeltti", 0), ist.get("editor_onay", 0)))
        ui.yaz("  API isteği           : %d" % ist.get("istek", 0))
        kullanilan = [(k[6:], n) for k, n in ist.items() if k.startswith("hedef:")]
        if len(kullanilan) > 1:
            ui.yaz("  Kullanılan modeller  : " + ", ".join("%s (%d)" % (saglayicilar.model_adi(h), n) for h, n in kullanilan))
        if cev.maliyet or any(saglayicilar.ucretli_mi(h) for h in yonetici.modeller):
            maliyet_metni = "Ücretli servis harcaması (yaklaşık): bu oturum %.3f $, bu oyun toplam %.3f $" % (
                cev.maliyet, proje.maliyet_al())
            ui.yaz("  Harcama (yaklaşık)   : %.3f $ (bu oyun toplam: %.3f $)" % (cev.maliyet, proje.maliyet_al()))
            if cev.fiyati_bilinmeyen:
                ui.yaz("  " + ui.renk("Fiyatı bilinmeyen modeller hesaba katılmadı: ", "gri") +
                       ", ".join(saglayicilar.model_adi(h) for h in cev.fiyati_bilinmeyen))

        if cev.kritik_hata is not None:
            if isinstance(cev.kritik_hata, cevirmen_mod.BaglantiKesildi):
                ui.hata("%s. Çeviri durduruldu; yapılanlar kaydedildi." % cev.kritik_hata)
                if cev.son_hata:
                    ui.yaz("   Son hata: " + cev.son_hata[:300])
                ui.yaz("   İnternet bağlantınızı kontrol edip programı tekrar çalıştırın; kaldığı yerden devam eder.")
            elif isinstance(cev.kritik_hata, gemini.ApiHatasi) and cev.kritik_hata.tur == gemini.SSL:
                ui.hata("Güvenli bağlantı kurulamadı (SSL). Bilgisayarınızın saatini kontrol edin, "
                        "antivirüsün 'HTTPS tarama' özelliğini kapatın veya Python'u güncelleyin.")
            else:
                ui.hata("Beklenmeyen bir hata oluştu: %s (ayrıntı: %s)" % (cev.kritik_hata, proje.gunluk_yolu))

        if cev.durdurma_nedeni is not None:
            e = cev.durdurma_nedeni
            ui.uyari("Kullanılabilir API kotası/bütçesi kalmadı; çeviri burada durduruldu (ilerleme kaydedildi).")
            for n in (e.nedenler or [])[:10]:
                ui.yaz("   - " + n)
            if e.en_erken:
                ui.yaz("   Ücretsiz kotalar yaklaşık %s (Türkiye saati) itibarıyla yenilenir." % zaman.turkiye_saati_metni(e.en_erken))
                ui.yaz("   O zaman programı tekrar çalıştırın; kaldığı yerden devam eder.")
            ui.yaz("   Daha hızlı ilerlemek için farklı Google hesaplarından ek anahtar ekleyebilirsiniz.")

    else:
        ui.basari("Çevrilecek yeni metin yok; tüm metinler zaten çevrilmiş.")

    if hafiza is not None:
        _hafizayi_guncelle(hafiza, proje, metinler.tumu())

    n_basarisiz, n_supheli = rapor_yaz(proje, cikti, istatistik, oyun, maliyet_metni)
    if n_basarisiz or n_supheli:
        ui.bilgi("Rapor: %d çevrilemeyen, %d kontrol önerilen satır → %s" % (n_basarisiz, n_supheli, proje.rapor_yolu))
    ui.bilgi("Çevirileri kendiniz düzeltmek isterseniz ana menüdeki 'Çevirileri elle düzenle' seçeneğini kullanın.")

    # Yamayı uygula
    ui.ara_baslik("Türkçe yamanın oyuna kurulması")
    if otomatik or ui.evet_mi("Çeviriyi şimdi oyuna uygulamak ister misiniz?", True):
        return _yamayi_kur(oyun, cikti, proje, ayar)
    return True


def _yamayi_kur(oyun, cikti, proje, ayar):
    try:
        ist = kurulum.yamayi_yaz(oyun, cikti, proje, ayar, ui.uyari)
    except Exception as e:
        ui.hata("Yama yazılamadı: %s" % e)
        proje.gunluge_yaz("Yama yazma hatası: %s" % e)
        return False
    oran = (100.0 * ist["diyalog"] / ist["toplam_diyalog"]) if ist["toplam_diyalog"] else 100.0
    ui.basari("Türkçe yama kuruldu: %d/%d diyalog (%%%.0f) ve %d arayüz metni." % (
        ist["diyalog"], ist["toplam_diyalog"], oran, ist["metin"]))
    if ist["eksik_fontlar"]:
        ui.bilgi("Türkçe harf desteklemeyen %d font otomatik değiştirilecek." % len(ist["eksik_fontlar"]))
    if ist.get("kucultulen"):
        ui.bilgi("Kutudan taşabilecek %d uzun satırın yazısı biraz küçültüldü (ayrıntı: rapor.txt)." % ist["kucultulen"])
    ui.yaz("")
    ui.yaz("  Oyunu normal şekilde açabilirsiniz.")
    if ayar.get("kisayol"):
        ui.yaz("  Oyun içinde " + ui.renk("Alt+T", "kalin") + " ile Türkçe / orijinal metin arasında geçiş yapılır.")
    ui.yaz("  Yamayı kaldırmak için ana menüdeki 'Yamayı kaldır' seçeneğini kullanın.")
    if oran < 100:
        ui.yaz("  Çevrilmemiş satırlar orijinal dilde görünür; programı tekrar çalıştırarak tamamlayabilirsiniz.")
    return True


def _kayitli_oyun(ayar, oyun_yolu):
    """Daha önce metinleri çıkarılmış bir oyun seçtirir. Döndürür: (oyun, proje, cikti) ya da None."""
    try:
        oyun = oyun_sec(ayar, oyun_yolu)
    except oyun_mod.OyunHatasi as e:
        ui.hata(str(e))
        return None
    if oyun is None:
        return None
    proje = proje_mod.Proje(oyun.kok)
    cikti = proje_mod.json_oku(proje.cikti_yolu)
    if not cikti:
        ui.hata("Bu oyun için kayıtlı çeviri bulunamadı. Önce 'Oyun çevir' seçeneğini kullanın.")
        return None
    return oyun, proje, cikti


def yamayi_yeniden_uygula(ayar, oyun_yolu=None):
    secim = _kayitli_oyun(ayar, oyun_yolu)
    if secim is None:
        return
    oyun, proje, cikti = secim
    try:
        ist = kurulum.yamayi_yaz(oyun, cikti, proje, ayar, ui.uyari)
        ui.basari("Yama uygulandı: %d/%d diyalog, %d arayüz metni." % (ist["diyalog"], ist["toplam_diyalog"], ist["metin"]))
    except Exception as e:
        ui.hata("Yama yazılamadı: %s" % e)


def yamayi_kaldir(ayar, oyun_yolu=None):
    try:
        oyun = oyun_sec(ayar, oyun_yolu)
    except oyun_mod.OyunHatasi as e:
        ui.hata(str(e))
        return
    if oyun is None:
        return
    if not kurulum.yama_kurulu_mu(oyun) and not os.path.isdir(os.path.join(oyun.game, kurulum.VERI_KLASOR_AD)):
        ui.bilgi("Bu oyunda Türkçe yama kurulu değil.")
        return
    if oyun_yolu or ui.evet_mi("'%s' oyunundan Türkçe yama kaldırılsın mı? (Çeviriler programda saklı kalır)" % oyun.ad, True):
        n = kurulum.yamayi_kaldir(oyun)
        ui.basari("Yama kaldırıldı (%d öğe silindi). Oyun orijinal haline döndü." % n)


def cevirileri_duzenle(ayar, oyun_yolu=None):
    """Bütün çevirileri Not Defteri'nde düzenlenebilir bir dosyaya yazar, sonra değişiklikleri alır."""
    secim = _kayitli_oyun(ayar, oyun_yolu)
    if secim is None:
        return
    oyun, proje, cikti = secim
    metinler = ogeleri_hazirla(cikti, proje, ayar)
    hafiza = hafiza_mod.Hafiza() if ayar.get("ortak_hafiza", True) else None

    ui.ara_baslik("Çevirileri elle düzenle")
    if os.path.exists(proje.duzenleme_yolu) and duzenleme.degismis_mi(proje):
        if ui.evet_mi("Düzenleme dosyasında henüz alınmamış değişiklikler var. Önce bunlar alınsın mı?", True):
            _duzenlemeleri_iceri_al(proje, metinler, hafiza)
    n = duzenleme.disari_aktar(proje, _duzenleme_ogeleri(metinler), cikti.get("oyun_adi") or oyun.ad)
    ui.bilgi("%d satır oyundaki sırayla dosyaya yazıldı: %s" % (n, proje.duzenleme_yolu))
    ui.yaz("  Dosya Not Defteri'nde açılacak. Sadece " + ui.renk("TR:", "kalin") +
           " satırlarını değiştirin, kaydedin (Ctrl+S) ve buraya dönün.")
    ui.yaz("  Düzelttikleriniz bundan sonraki çevirilerde yapay zekaya üslup örneği olarak da gösterilir.")
    _ac_ve_bekle(proje.duzenleme_yolu, "Düzenlemeyi bitirip kaydettikten sonra Enter'a basın")
    degisen = _duzenlemeleri_iceri_al(proje, metinler, hafiza)
    if degisen and kurulum.yama_kurulu_mu(oyun) and ui.evet_mi("Değişiklikler oyuna şimdi uygulansın mı?", True):
        _yamayi_kur(oyun, cikti, proje, ayar)


def _test_cevirisi(hedef, ornekler, metinler, proje, anahtarlar, ayar, oyun_adi):
    """Örnek satırları, gerçek çevirilere dokunmadan verilen modelle çevirir. Döndürür: {kaynak: çeviri}."""
    bellek = kortest.BellekProje(proje, [o.m for o in ornekler])
    yon = anahtar_mod.AnahtarYoneticisi(anahtarlar, [hedef], lambda m: 60.0 / ayar_mod.dakikalik_sinir(ayar, m),
                                        ayar_mod.ANAHTAR_DURUM_DOSYASI)
    ilerleme = ui.Ilerleme(len(ornekler), saglayicilar.model_adi(hedef)[:18])

    def ilerleme_fonk(yapilan, top, model):
        ilerleme.toplam = top
        ilerleme.guncelle(yapilan)

    def bildir(tur, mesaj):
        {"uyari": ui.uyari, "hata": ui.hata}.get(tur, ui.bilgi)(mesaj)

    cev = cevirmen_mod.Cevirmen(bellek, yon, ayar, Sozluk.oku(proje.sozluk_yolu), oyun_adi, proje.oyun_notu(),
                                ilerleme_fonk, bildir, karakter_mod.Karakterler.oku(proje.karakter_yolu))
    cev.karakter_satirlarini_hazirla(metinler.konusan_sayaci)
    kopya = [cevirmen_mod.Oge(o.id, o.m, o.tur, o.k) for o in ornekler]
    try:
        cev.calistir(kopya, [], metinler.diyalog_sira)
        mod = ayar.get("kalite_modu", "dengeli")
        if mod != "hizli" and not cev.iptal.is_set():
            cev.incele(cev.inceleme_adaylari(kopya, mod), metinler.diyalog_sira)
    except anahtar_mod.TumKotalarBitti:
        ui.uyari("%s için kullanılabilir kota kalmadı." % saglayicilar.model_adi(hedef))
    finally:
        ilerleme.bitir()
    if cev.maliyet:
        ui.bilgi("Test harcaması (%s): ~%.3f $" % (saglayicilar.model_adi(hedef), cev.maliyet))
    return {o.m: bellek.ceviri_al(o.m) for o in ornekler}


def kalite_testi(ayar, oyun_yolu=None):
    """İki modelin (ya da kayıtlı çevirilerle bir modelin) kör karşılaştırması."""
    secim = _kayitli_oyun(ayar, oyun_yolu)
    if secim is None:
        return
    oyun, proje, cikti = secim
    anahtarlar = anahtarlari_hazirla()
    if not anahtarlar:
        return
    metinler = ogeleri_hazirla(cikti, proje, ayar)
    ornekler = kortest.ornek_sec(metinler.diyalog_sira, 30)
    if len(ornekler) < 5:
        ui.hata("Karşılaştırma için yeterli diyalog yok.")
        return

    ui.ara_baslik("Kör kalite testi")
    ui.yaz("Oyundan %d satır seçildi. İki yolla çevrilip, hangisinin hangi modele ait olduğu gizlenerek" % len(ornekler))
    ui.yaz("yan yana gösterilecek. Siz daha doğal olanı seçersiniz; sonunda kazanan açıklanır.")
    adaylar = []
    if sum(1 for o in ornekler if proje.ceviri_al(o.m)) >= len(ornekler) // 2:
        adaylar.append((kortest.MEVCUT, "Kayıtlı çeviriler (bu oyun için yapılmış olanlar)"))
    for sag in _saglayici_sirasi(anahtarlar, ayar):
        if sag == "gemini":
            for m in ayar["modeller"][:3]:
                adaylar.append((saglayicilar.hedef_adi("gemini", m), m + " (ücretsiz)"))
        else:
            model = ayar["claude_modeli"] if sag == "claude" else ayar[sag + "_modeli"]
            adaylar.append((saglayicilar.hedef_adi(sag, model), model + " (ücretli)"))
            if sag == "claude" and model != "claude-sonnet-5-5":
                adaylar.append((saglayicilar.hedef_adi(sag, "claude-sonnet-5-5"), "claude-sonnet-5-5 (ücretli, daha ucuz)"))
    if len(adaylar) < 2:
        ui.hata("Karşılaştırılacak en az iki seçenek gerekiyor (ör. iki model ya da kayıtlı çeviri + bir model).")
        return
    secenekler = [(str(i + 1), ad) for i, (_h, ad) in enumerate(adaylar)]
    birinci = int(ui.secim("Birinci seçenek", secenekler, "1")) - 1
    ikinci = int(ui.secim("İkinci seçenek", secenekler, "2" if birinci != 1 else "1")) - 1
    if birinci == ikinci:
        ui.hata("Aynı seçenek iki kez seçilemez.")
        return

    sonuclar = []
    for idx in (birinci, ikinci):
        hedef, ad = adaylar[idx]
        if hedef == kortest.MEVCUT:
            sonuclar.append({o.m: proje.ceviri_al(o.m) for o in ornekler})
            continue
        if saglayicilar.hedef_coz(hedef)[0] == "claude" and not _claude_paketini_hazirla():
            return
        ui.bilgi("Çevriliyor: " + ad)
        sonuclar.append(_test_cevirisi(hedef, ornekler, metinler, proje, anahtarlar, ayar, cikti.get("oyun_adi") or oyun.ad))

    satirlar = []
    for o in ornekler:
        c1, c2 = sonuclar[0].get(o.m), sonuclar[1].get(o.m)
        if c1 and c2:
            konusan = o.k if o.k not in ("extend", "narrator") else ""
            satirlar.append((konusan, o.m, ekler_sabitle(c1), ekler_sabitle(c2)))
    if not satirlar:
        ui.hata("Karşılaştırılacak çeviri üretilemedi (ayrıntı: %s)." % proje.gunluk_yolu)
        return
    ad1 = adaylar[birinci][1].split(" (")[0]
    ad2 = adaylar[ikinci][1].split(" (")[0]
    n = kortest.html_yaz(proje.kor_test_yolu, cikti.get("oyun_adi") or oyun.ad, satirlar, ad1, ad2)
    ui.basari("%d satırlık test sayfası hazır: %s" % (n, proje.kor_test_yolu))
    if not _dosyayi_ac(proje.kor_test_yolu):
        ui.yaz("Dosyayı tarayıcıda açın: " + proje.kor_test_yolu)


def ekler_sabitle(metin):
    from . import ekler
    return ekler.isaretleri_sabitle(metin)


# ---------------------------------------------------------------------------
# Giriş noktası
# ---------------------------------------------------------------------------


def _argumanlar(argv):
    p = argparse.ArgumentParser(prog="ceviri", description="Ren'Py Türkçe Çeviri Motoru")
    p.add_argument("oyun", nargs="?", help="Oyun klasörü (verilirse doğrudan çeviriye başlar)")
    p.add_argument("--evet", action="store_true", help="Tüm soruları varsayılanla yanıtla (otomatik mod)")
    p.add_argument("--kaldir", action="store_true", help="Verilen oyundan yamayı kaldır")
    p.add_argument("--uygula", action="store_true", help="Kayıtlı çevirileri API kullanmadan oyuna uygula")
    return p.parse_args(argv)


def main(argv=None):
    if sys.version_info < (3, 8):
        print("Bu program Python 3.8 veya daha yeni bir sürüm gerektirir. https://www.python.org/downloads/")
        return 1

    args = _argumanlar(sys.argv[1:] if argv is None else argv)
    ui.baslik("Ren'Py Türkçe Çeviri Motoru  v" + SURUM)

    if not oyun_mod.yazilabilir_mi(ayar_mod.KOK):
        ui.hata("Program klasörüne yazılamıyor: %s" % ayar_mod.KOK)
        ui.yaz("  Programı 'Masaüstü' veya 'Belgeler' gibi yazılabilir bir klasöre çıkarıp oradan çalıştırın.")
        return 1

    ayar, sorunlar = ayar_mod.yukle()
    for s in sorunlar:
        ui.uyari(s)

    try:
        # İlk açılış: anahtar yoksa en başta bir kez sor (sonra hep hatırlanır).
        if not args.kaldir and not args.uygula and not anahtar_mod.anahtarlari_oku(ayar_mod.ANAHTAR_DOSYASI):
            anahtarlari_hazirla()

        if args.oyun:
            if args.kaldir:
                yamayi_kaldir(ayar, args.oyun)
            elif args.uygula:
                yamayi_yeniden_uygula(ayar, args.oyun)
            else:
                oyunu_cevir(ayar, args.oyun, otomatik=args.evet)
            return 0

        while True:
            ui.ara_baslik("Ana menü")
            secim = ui.secim("Seçiminiz", [
                ("1", "Oyun çevir (yeni ya da kaldığı yerden devam)"),
                ("2", "API anahtarlarını yönet"),
                ("3", "Kayıtlı çeviriyi oyuna yeniden uygula (API kullanmaz)"),
                ("4", "Oyundan Türkçe yamayı kaldır"),
                ("5", "Çevirileri elle düzenle (Not Defteri ile)"),
                ("6", "Kalite testi: iki yapay zekayı kör karşılaştır"),
                ("0", "Çıkış"),
            ], "1")
            if secim == "0":
                return 0
            try:
                if secim == "1":
                    oyunu_cevir(ayar)
                elif secim == "2":
                    anahtar_menusu()
                elif secim == "3":
                    yamayi_yeniden_uygula(ayar)
                elif secim == "4":
                    yamayi_kaldir(ayar)
                elif secim == "5":
                    cevirileri_duzenle(ayar)
                elif secim == "6":
                    kalite_testi(ayar)
            except KeyboardInterrupt:
                ui.yaz("")
                ui.uyari("İşlem iptal edildi.")
    except KeyboardInterrupt:
        ui.yaz("")
        ui.uyari("Çıkılıyor.")
        return 130
