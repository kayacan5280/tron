"""Zaman yardımcıları.

Gemini API'nin ücretsiz günlük kotası ABD Pasifik saatine (America/Los_Angeles)
göre gece yarısı sıfırlanır. Windows'taki Python'da saat dilimi veritabanı
(tzdata) olmayabildiği için yaz saati kuralını burada elle hesaplıyoruz.
"""

import datetime

UTC = datetime.timezone.utc
TURKIYE = datetime.timezone(datetime.timedelta(hours=3))


def _ayin_n_inci_pazari(yil, ay, n):
    gun = datetime.date(yil, ay, 1)
    # weekday(): Pazartesi=0 ... Pazar=6
    ilk_pazar = 1 + (6 - gun.weekday()) % 7
    return ilk_pazar + 7 * (n - 1)


def pasifik_yaz_saati_mi(an_utc):
    """Verilen UTC anında ABD Pasifik bölgesinde yaz saati (PDT) uygulanıyor mu?

    Kural (2007'den beri): Mart'ın ikinci Pazarı 02:00 yerel saatte başlar,
    Kasım'ın ilk Pazarı 02:00 yerel saatte biter.
    """
    yil = an_utc.year
    baslangic_gun = _ayin_n_inci_pazari(yil, 3, 2)
    bitis_gun = _ayin_n_inci_pazari(yil, 11, 1)
    # 02:00 PST = 10:00 UTC ; 02:00 PDT = 09:00 UTC
    baslangic = datetime.datetime(yil, 3, baslangic_gun, 10, 0, tzinfo=UTC)
    bitis = datetime.datetime(yil, 11, bitis_gun, 9, 0, tzinfo=UTC)
    return baslangic <= an_utc < bitis


def pasifik_fark(an_utc):
    return datetime.timedelta(hours=-7 if pasifik_yaz_saati_mi(an_utc) else -8)


def simdi_utc():
    return datetime.datetime.now(UTC)


def sonraki_kota_sifirlama(an_utc=None):
    """Bir sonraki Pasifik gece yarısının UTC karşılığını döndürür."""
    an_utc = an_utc or simdi_utc()
    yerel = an_utc + pasifik_fark(an_utc)
    yarin = (yerel + datetime.timedelta(days=1)).date()
    gece_yarisi_yerel = datetime.datetime(yarin.year, yarin.month, yarin.day)
    # Gece yarısı anındaki farkı kullan (yaz saati geçişleri 02:00'de olur).
    tahmini_utc = gece_yarisi_yerel.replace(tzinfo=UTC) + datetime.timedelta(hours=8)
    fark = pasifik_fark(tahmini_utc)
    return (gece_yarisi_yerel - fark).replace(tzinfo=UTC)


def turkiye_saati_metni(an_utc):
    yerel = an_utc.astimezone(TURKIYE)
    return yerel.strftime("%d.%m.%Y %H:%M")


def iso(an_utc):
    return an_utc.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_coz(metin):
    try:
        return datetime.datetime.strptime(metin, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except Exception:
        return None
