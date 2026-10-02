"""Programın ana akışı ve menüleri."""

import argparse
import collections
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
from . import gemini
from . import koruma
from . import kurulum
from . import oyun as oyun_mod
from . import proje as proje_mod
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


def _anahtarlari_test_et(anahtarlar):
    """Her anahtarı kota harcamadan (model listesi isteğiyle) dener."""
    sonuc = []
    for a in anahtarlar:
        etiket = anahtar_mod.anahtar_etiketi(a)
        try:
            modeller = gemini.modelleri_listele(a)
            ui.basari("%s  geçerli (%d model erişilebilir)" % (etiket, len(modeller)))
            sonuc.append((a, True, modeller))
        except gemini.ApiHatasi as h:
            if h.tur in (gemini.AG, gemini.ZAMAN_ASIMI, gemini.SUNUCU, gemini.SSL):
                ui.uyari("%s  denenemedi (bağlantı sorunu: %s). Yine de kaydedilecek." % (etiket, h.mesaj))
                sonuc.append((a, None, []))
            else:
                ui.hata("%s  GEÇERSİZ: %s" % (etiket, h.mesaj))
                sonuc.append((a, False, []))
    return sonuc


def _anahtar_gir():
    ui.yaz("")
    ui.yaz("API anahtarlarınızı yapıştırın (her satıra bir tane; birden fazla girebilirsiniz).")
    ui.yaz("Bitirince " + ui.renk("boş satırda Enter", "kalin") + "'a basın.")
    yeni = []
    while True:
        satir = ui.sor("Anahtar %d" % (len(yeni) + 1))
        if not satir:
            break
        for parca in satir.replace(",", " ").replace(";", " ").split():
            parca = parca.strip().strip('"').strip("'")
            if not parca:
                continue
            if not anahtar_mod.anahtar_bicimi_uygun_mu(parca):
                ui.uyari("Bu bir API anahtarına benzemiyor, atlandı: %s" % parca[:12])
                continue
            if parca not in yeni:
                yeni.append(parca)
    return yeni


def anahtarlari_hazirla():
    """Kayıtlı anahtarları döndürür; yoksa kullanıcıdan bir kez ister ve kaydeder."""
    anahtarlar = anahtar_mod.anahtarlari_oku(ayar_mod.ANAHTAR_DOSYASI)
    if anahtarlar:
        return anahtarlar

    ui.baslik("İlk kurulum: Gemini API anahtarları")
    ui.yaz("Çeviri için Google'ın ücretsiz Gemini yapay zekasını kullanıyoruz.")
    ui.yaz("Anahtarları bir kez girersiniz; program onları hatırlar (api_anahtarlari.txt).")
    _anahtar_nasil_alinir()

    while True:
        yeni = _anahtar_gir()
        if not yeni:
            ui.uyari("Hiç anahtar girilmedi. Anahtar olmadan çeviri yapılamaz.")
            if not ui.evet_mi("Tekrar denemek ister misiniz?", True):
                return []
            continue
        ui.bilgi("Anahtarlar deneniyor (kota harcanmaz)...")
        sonuc = _anahtarlari_test_et(yeni)
        gecerli = [a for a, durum, _m in sonuc if durum is not False]
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
            ("1", "Anahtar ekle"),
            ("2", "Anahtar sil"),
            ("3", "Tüm anahtarları dene (kota harcamaz)"),
            ("4", "'Kota doldu' / 'geçersiz' işaretlerini sıfırla"),
            ("5", "Anahtar nasıl alınır?"),
            ("0", "Geri"),
        ], "0")
        if secim == "0":
            return
        if secim == "1":
            yeni = _anahtar_gir()
            yeni = [a for a in yeni if a not in anahtarlar]
            if yeni:
                ui.bilgi("Yeni anahtarlar deneniyor...")
                sonuc = _anahtarlari_test_et(yeni)
                ekle = [a for a, d, _m in sonuc if d is not False]
                anahtar_mod.anahtarlari_yaz(ayar_mod.ANAHTAR_DOSYASI, anahtarlar + ekle)
                ui.basari("%d anahtar eklendi." % len(ekle))
        elif secim == "2":
            if not anahtarlar:
                continue
            no = ui.sor("Silinecek anahtarın numarası (iptal için boş bırakın)")
            if no.isdigit() and 1 <= int(no) <= len(anahtarlar):
                silinen = anahtarlar.pop(int(no) - 1)
                anahtar_mod.anahtarlari_yaz(ayar_mod.ANAHTAR_DOSYASI, anahtarlar)
                ui.basari("Silindi: %s" % anahtar_mod.anahtar_etiketi(silinen))
        elif secim == "3":
            sonuc = _anahtarlari_test_et(anahtarlar)
            gecersiz = [a for a, d, _m in sonuc if d is False]
            if gecersiz and ui.evet_mi("%d geçersiz anahtar listeden silinsin mi?" % len(gecersiz), True):
                anahtar_mod.anahtarlari_yaz(ayar_mod.ANAHTAR_DOSYASI, [a for a in anahtarlar if a not in gecersiz])
        elif secim == "4":
            yon.durumu_sifirla()
            ui.basari("Sıfırlandı.")
        elif secim == "5":
            _anahtar_nasil_alinir()
            ui.bekle()


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


# ---------------------------------------------------------------------------
# Metin listeleri
# ---------------------------------------------------------------------------


def ogeleri_hazirla(cikti, proje, ayar):
    """Çıktıdan çevrilecek Oge listelerini hazırlar; hazır tablolardan doldurur."""
    ortak, ek = kurulum.arayuz_tablosu()

    diyalog_sira = []          # tüm benzersiz diyaloglar (bağlam için)
    diyalog_kume = {}
    konusan_sayaci = collections.Counter()
    sayac = 0

    # Çıkarıcı, oyundaki sırayı korur (dosyalar Ren'Py yükleme sırasında, satırlar dosya içi sırada).
    for o in cikti.get("ogeler") or []:
        m = o.get("m")
        if not isinstance(m, str):
            continue
        if o.get("k"):
            konusan_sayaci[o["k"]] += 1
        if m in diyalog_kume:
            continue
        sayac += 1
        oge = cevirmen_mod.Oge(sayac, m, o.get("tur") or "diyalog", o.get("k") or "")
        diyalog_kume[m] = oge
        diyalog_sira.append(oge)

    # Karakter adları (Character tanımları ve konuşmacılar): sözlükle tutarlı çevrilir.
    karakter_adlari = set(k for k in konusan_sayaci if k and k != "extend")
    for c in cikti.get("karakterler") or []:
        if isinstance(c.get("ad"), str):
            karakter_adlari.add(c["ad"])

    metin_ogeleri = []
    metin_kume = set()
    for s in cikti.get("metinler") or []:
        m = s.get("m")
        if not isinstance(m, str) or m in diyalog_kume or m in metin_kume:
            continue
        tur = TUR_ESLEME.get(s.get("tur"), "arayuz")
        if m in karakter_adlari:
            tur = "isim"
        if tur == "python" and not ayar.get("python_metinleri", True):
            continue
        metin_kume.add(m)
        sayac += 1
        metin_ogeleri.append(cevirmen_mod.Oge(sayac, m, tur, ""))

    # Oyunun 'translate None strings' ile değiştirdiği metinler de çevrilmeli.
    for _eski, yeni in (cikti.get("none_ozel") or {}).items():
        if isinstance(yeni, str) and yeni not in diyalog_kume and yeni not in metin_kume:
            metin_kume.add(yeni)
            sayac += 1
            metin_ogeleri.append(cevirmen_mod.Oge(sayac, yeni, "arayuz", ""))

    # Hazır tablolar ve çevrilmesi gerekmeyenler.
    hazir = 0
    for o in diyalog_sira + metin_ogeleri:
        if proje.ceviri_al(o.m) is not None:
            continue
        tablo = ortak.get(o.m) or ek.get(o.m)
        if tablo:
            proje.ceviri_kaydet(o.m, tablo, proje_mod.HAZIR, model="tablo")
            hazir += 1

    def gerekli(o):
        if proje.ceviri_al(o.m) is not None:
            return False
        if not koruma.cevrilecek_mi(o.m):
            return False
        if o.m.strip() in DIL_ADLARI:
            return False
        return True

    diyaloglar = [o for o in diyalog_sira if gerekli(o)]
    metinler = [o for o in metin_ogeleri if gerekli(o)]
    isimler = [o for o in metin_ogeleri if o.tur == "isim"]
    return diyalog_sira, diyaloglar, metinler, konusan_sayaci, hazir, isimler


# ---------------------------------------------------------------------------
# Rapor
# ---------------------------------------------------------------------------


def rapor_yaz(proje, cikti, istatistik, oyun):
    basarisiz = []
    supheli = []
    for m, k in proje.ceviriler.items():
        if not isinstance(k, dict):
            continue
        if k.get("d") == proje_mod.BASARISIZ:
            basarisiz.append((m, k.get("n", "")))
        elif k.get("n") and str(k.get("n")).startswith("şüpheli"):
            supheli.append((m, k.get("c"), k.get("n")))
    with open(proje.rapor_yolu, "w", encoding="utf-8") as f:
        f.write("ÇEVİRİ RAPORU - %s\n" % oyun.ad)
        f.write("Oluşturma: %s\n\n" % time.strftime("%d.%m.%Y %H:%M"))
        f.write("İstek sayısı: %d | Girdi token: %d | Çıktı token: %d\n\n" % (
            istatistik.get("istek", 0), istatistik.get("token_girdi", 0), istatistik.get("token_cikti", 0)))
        f.write("=== ÇEVRİLEMEYEN METİNLER (%d) ===\n" % len(basarisiz))
        f.write("Bunlar oyunda orijinal haliyle görünür. Programı tekrar çalıştırınca yeniden denenir.\n\n")
        for m, n in basarisiz:
            f.write("- %r\n    neden: %s\n" % (m, n))
        f.write("\n=== KONTROL EDİLMESİ ÖNERİLEN ÇEVİRİLER (%d) ===\n\n" % len(supheli))
        for m, c, n in supheli:
            f.write("- KAYNAK: %r\n  ÇEVİRİ: %r\n  (%s)\n" % (m, c, n))
    return len(basarisiz), len(supheli)


# ---------------------------------------------------------------------------
# Ana çeviri akışı
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
    """Ayarlardaki modellerden erişilebilir olanları döndürür.

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

    # 1) Metinleri çıkar
    cikti = proje_mod.json_oku(proje.cikti_yolu)
    yeniden = True
    if cikti and not otomatik:
        yeniden = ui.evet_mi("Metinler daha önce çıkarılmış. Oyun güncellenmiş olabilir; yeniden çıkarılsın mı?", True)
    if yeniden or not cikti:
        ui.ara_baslik("1/4  Metinler oyundan çıkarılıyor")
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
            return False
        ui.basari("Metinler çıkarıldı.")

    for u in cikti.get("uyarilar") or []:
        proje.gunluge_yaz("Çıkarıcı uyarısı: %s" % u)

    diyalog_sira, diyaloglar, metinler, konusan_sayaci, hazir, isim_ogeleri = ogeleri_hazirla(cikti, proje, ayar)
    proje.kaydet()

    ui.ara_baslik("Oyun bilgisi")
    ui.yaz("  Ren'Py           : %s" % (cikti.get("renpy_surumu") or "?"))
    ui.yaz("  Oyun adı         : %s" % (cikti.get("oyun_adi") or oyun.ad))
    ui.yaz("  Diyalog/seçenek  : %d satır (%d benzersiz)" % (len(cikti.get("ogeler") or []), len(diyalog_sira)))
    ui.yaz("  Arayüz/kod metni : %d" % len(cikti.get("metinler") or []))
    ui.yaz("  Hazır çeviri     : %d (yerleşik Türkçe arayüz tablosu)" % hazir)
    ui.yaz("  Çevrilecek       : %s diyalog + %s arayüz/kod metni" % (
        ui.renk(str(len(diyaloglar)), "kalin"), ui.renk(str(len(metinler)), "kalin")))
    if cikti.get("diller"):
        ui.yaz("  Oyundaki diller  : %s" % ", ".join(cikti["diller"]))
    eksik_font = [f for f in (cikti.get("fontlar") or []) if f.get("eksik")]
    if eksik_font:
        ui.uyari("%d fontta Türkçe harf eksik; bunlar otomatik olarak Türkçe destekli fontla değiştirilecek:" % len(eksik_font))
        for f in eksik_font[:8]:
            ui.yaz("     %s  (eksik: %s)" % (f.get("dosya"), f.get("eksik")))

    toplam = len(diyaloglar) + len(metinler)
    if toplam:
        istek_tahmini = int(math.ceil(len(diyaloglar) / float(ayar["paket_satir"])) + math.ceil(len(metinler) / float(ayar["paket_satir"])))
        ui.yaz("  Tahmini istek    : ~%d (%d anahtar ile)" % (istek_tahmini, len(anahtarlar)))

    sozluk = Sozluk.oku(proje.sozluk_yolu)
    oyun_notu = proje.oyun_notu()
    istatistik = {}
    if os.path.exists(proje.sozluk_yolu):
        _isimleri_uygula(sozluk, isim_ogeleri, metinler, proje)
        toplam = len(diyaloglar) + len(metinler)

    if toplam:
        # 2) Oyun notu ve sözlük
        if not oyun_notu and not otomatik:
            ui.ara_baslik("2/4  Oyun hakkında not (isteğe bağlı)")
            ui.yaz("Çeviriye yardımcı olacak kısa bir not yazabilirsiniz (tür, ortam, hitap tercihi vb.).")
            ui.yaz("Örnek: 'Lisede geçen romantik komedi. Ana karakter erkek. Arkadaşlar birbirine sen der.'")
            ui.yaz("Boş bırakıp Enter'a basarsanız atlanır.")
            oyun_notu = ui.sor("Not")
            proje.oyun_notu_yaz(oyun_notu)

        modeller = _model_listesini_dogrula(anahtarlar, ayar)
        yonetici = anahtar_mod.AnahtarYoneticisi(
            anahtarlar, modeller,
            lambda m: 60.0 / ayar_mod.dakikalik_sinir(ayar, m),
            ayar_mod.ANAHTAR_DURUM_DOSYASI,
        )
        ui.bilgi("Model sırası: " + " → ".join(modeller))
        ui.bilgi("Kullanılabilir anahtar: %d / %d" % (yonetici.kullanilabilir_anahtar_sayisi(), len(anahtarlar)))

        ilerleme = ui.Ilerleme(toplam, "Çeviri")

        def ilerleme_fonk(yapilan, top, model):
            ilerleme.toplam = top
            ilerleme.guncelle(yapilan, ek=("| " + model) if model else "")

        def bildir(tur, mesaj):
            {"uyari": ui.uyari, "hata": ui.hata}.get(tur, ui.bilgi)(mesaj)

        cev = cevirmen_mod.Cevirmen(proje, yonetici, ayar, sozluk, cikti.get("oyun_adi") or oyun.ad,
                                    oyun_notu, ilerleme_fonk, bildir)

        try:
            if not os.path.exists(proje.sozluk_yolu):
                ui.ara_baslik("3/4  Karakter ve terim sözlüğü hazırlanıyor")
                isimler = [k for k, _n in konusan_sayaci.most_common(60) if k and k != "extend"]
                isimler += [o.m for o in metinler if o.tur == "isim"]
                isimler += [c.get("ad") for c in (cikti.get("karakterler") or []) if isinstance(c.get("ad"), str)]

                ornekler = {}
                for o in cikti.get("ogeler") or []:
                    k = o.get("k")
                    if k and k not in ornekler:
                        ornekler[k] = o.get("m", "")[:160]
                try:
                    n = cev.sozluk_olustur(isimler, [o.m for o in diyalog_sira], ornekler.get)
                    sozluk.yaz(proje.sozluk_yolu)
                    ui.basari("Sözlük hazır: %d terim  →  %s" % (n, proje.sozluk_yolu))
                except anahtar_mod.TumKotalarBitti:
                    raise
                except Exception as e:
                    ui.uyari("Sözlük oluşturulamadı (%s); sözlüksüz devam ediliyor." % e)
                    sozluk.yaz(proje.sozluk_yolu)

                if not otomatik and len(sozluk) and ui.evet_mi("Sözlüğü açıp kontrol etmek/düzenlemek ister misiniz?", False):
                    if not _dosyayi_ac(proje.sozluk_yolu):
                        ui.yaz("Dosyayı elle açın: " + proje.sozluk_yolu)
                    ui.bekle("Düzenleyip kaydettikten sonra Enter'a basın")
                sozluk = Sozluk.oku(proje.sozluk_yolu)
                cev.sozluk = sozluk

            _isimleri_uygula(sozluk, isim_ogeleri, metinler, proje)

            cev.karakter_satirlarini_hazirla(konusan_sayaci)

            ui.ara_baslik("4/4  Çeviri")
            ui.yaz(ui.renk("Durdurmak için Ctrl+C", "gri") + " — çeviriler sürekli kaydedilir, sonra kaldığı yerden devam eder.")
            cev.calistir(diyaloglar, metinler, diyalog_sira)
            ilerleme.bitir()
        except anahtar_mod.TumKotalarBitti as e:
            cev.durdurma_nedeni = e
            ilerleme.bitir()
        except KeyboardInterrupt:
            ilerleme.bitir()
            ui.uyari("Çeviri kullanıcı tarafından durduruldu. Yapılan çeviriler kaydedildi.")
            proje.kaydet()

        proje.kaydet()
        ist = istatistik = cev.istatistik
        ui.ara_baslik("Sonuç")
        ui.yaz("  Bu oturumda çevrilen : %d" % ist.get("cevrildi", 0))
        ui.yaz("  Çevrilemeyen         : %d" % ist.get("basarisiz", 0))
        ui.yaz("  API isteği           : %d" % ist.get("istek", 0))

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
            ui.uyari("Kullanılabilir API kotası kalmadı; çeviri burada durduruldu (ilerleme kaydedildi).")
            for n in (e.nedenler or [])[:10]:
                ui.yaz("   - " + n)
            if e.en_erken:
                ui.yaz("   Ücretsiz kotalar yaklaşık %s (Türkiye saati) itibarıyla yenilenir." % zaman.turkiye_saati_metni(e.en_erken))
                ui.yaz("   O zaman programı tekrar çalıştırın; kaldığı yerden devam eder.")
            ui.yaz("   Daha hızlı ilerlemek için farklı Google hesaplarından ek anahtar ekleyebilirsiniz.")

    else:
        ui.basari("Çevrilecek yeni metin yok; tüm metinler zaten çevrilmiş.")

    n_basarisiz, n_supheli = rapor_yaz(proje, cikti, istatistik, oyun)
    if n_basarisiz or n_supheli:
        ui.bilgi("Rapor: %d çevrilemeyen, %d kontrol önerilen satır → %s" % (n_basarisiz, n_supheli, proje.rapor_yolu))

    # Yamayı uygula
    ui.ara_baslik("Türkçe yamanın oyuna kurulması")
    if otomatik or ui.evet_mi("Çeviriyi şimdi oyuna uygulamak ister misiniz?", True):
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
        ui.yaz("")
        ui.yaz("  Oyunu normal şekilde açabilirsiniz.")
        if ayar.get("kisayol"):
            ui.yaz("  Oyun içinde " + ui.renk("Alt+T", "kalin") + " ile Türkçe / orijinal metin arasında geçiş yapılır.")
        ui.yaz("  Yamayı kaldırmak için ana menüdeki 'Yamayı kaldır' seçeneğini kullanın.")
        if oran < 100:
            ui.yaz("  Çevrilmemiş satırlar orijinal dilde görünür; programı tekrar çalıştırarak tamamlayabilirsiniz.")
    return True


def yamayi_yeniden_uygula(ayar, oyun_yolu=None):
    try:
        oyun = oyun_sec(ayar, oyun_yolu)
    except oyun_mod.OyunHatasi as e:
        ui.hata(str(e))
        return
    if oyun is None:
        return
    proje = proje_mod.Proje(oyun.kok)
    cikti = proje_mod.json_oku(proje.cikti_yolu)
    if not cikti:
        ui.hata("Bu oyun için kayıtlı çeviri bulunamadı. Önce 'Oyun çevir' seçeneğini kullanın.")
        return
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
            except KeyboardInterrupt:
                ui.yaz("")
                ui.uyari("İşlem iptal edildi.")
    except KeyboardInterrupt:
        ui.yaz("")
        ui.uyari("Çıkılıyor.")
        return 130
