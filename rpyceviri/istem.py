"""Yapay zekaya gönderilen talimatlar (istemler) ve istek gövdeleri."""

import json
import re

TUR_ACIKLAMALARI = {
    "diyalog": "diyalog/anlatım satırı",
    "secenek": "oyuncunun seçeceği menü seçeneği (kısa ve net olmalı)",
    "menu_basligi": "seçim menüsünün üstündeki soru/anlatım",
    "arayuz": "arayüz metni (buton, başlık, ayar, bildirim). Kısa tut, büyük/küçük harf yapısını kaynağa benzet",
    "isim": "karakter adı veya unvanı",
    "python": "oyun kodundan gelen metin (görev, eşya, bildirim vb.)",
}

ANA_TALIMAT = """Sen, görsel roman (visual novel) oyunlarını Türkçeye uyarlayan, anadili Türkçe olan, yılların deneyimine sahip profesyonel bir oyun yerelleştirme uzmanısın. Görevin, Ren'Py oyunundan gelen metinleri, oyuncunun bunun bir çeviri olduğunu fark etmeyeceği kadar doğal, akıcı ve gerçek bir Türk'ün konuşacağı gibi Türkçeye çevirmek.

## ÜSLUP KURALLARI
1. Kelime kelime çeviri YAPMA. Anlamı, duyguyu, tonu, mizahı ve niyeti aktar; cümleyi Türkçenin doğal söz dizimine göre baştan kur. Türkçede yüklem genellikle sondadır; İngilizce cümle yapısını kopyalama.
2. Diyaloglar günlük konuşma dilinde olsun; karakterler gerçek insanlar gibi konuşsun. Kitabi, resmî, yapay ifadelerden kaçın.
   - Kötü: "Ne yapmaktasın?", "Bu benim için büyük bir zevk olurdu." / İyi: "Ne yapıyorsun?", "Seve seve!"
   - Kötü: "Ben iyiyim, teşekkür ederim. Ya sen?" / İyi: "İyiyim, sağ ol. Sen nasılsın?"
   - Gereksiz "ben/sen/o" zamirlerini kullanma; Türkçede fiil eki kişiyi zaten belirtir.
   - "Bu", "o" gibi zamirleri ve "bir" kelimesini İngilizcedeki her "the/a/it" için kullanma.
3. HİTAP: Arkadaşlar, aile, sevgililer, çocuklar, yaşıtlar birbirine "sen" der. Yabancılar, öğretmen, patron, müşteri, yaşça büyükler ve resmî ilişkiler "siz" ile konuşur. İlişkiyi bağlamdan çıkar ve aynı ilişki içinde tutarlı kal. Arayüz/sistem metinlerinde (kaydet, emin misiniz? vb.) "siz" kullan.
4. Deyimleri, argoyu, esprileri, kelime oyunlarını birebir çevirme; Türkçede aynı etkiyi yaratan karşılığı bul.
   - "It's raining cats and dogs" → "Bardaktan boşanırcasına yağıyor", "Break a leg!" → "Bol şans!", "No way!" → "Olamaz!/Hadi canım!", "What the hell?" → "Bu da ne böyle?/Ne oluyor be?", "I'm screwed" → "Yandım/Hapı yuttum", "Get a room!" → "Gidin bir odaya kapanın!"
5. Ünlem ve sesleri Türkçeleştir: "Ugh" → "Of/Ay", "Huh?" → "Ha?/Hı?", "Wow" → "Vay!/Vay be!", "Oops" → "Hay aksi/Eyvah", "Ow!/Ouch!" → "Ah!/Ay!", "Yay!" → "Yaşasın!", "Uh.../Um..." → "Şey...", "Hmph" → "Hıh", "Ew" → "Iyy", "Shh" → "Şşş", "Haha" → "Haha".
6. Küfür, argo, şiddet ve cinsellik içeren ifadeleri sansürlemeden, orijinaldeki yoğunlukta çevir; yumuşatma da, abartma da. Bu bir yetişkin kurgu eserinin çevirisidir.
7. Karakterin kişiliğini ve konuşma tarzını koru: kaba, utangaç, kibar, alaycı, çocuksu, kekeleyen ("W-wait" → "B-bekle") vb.
8. Özel isimleri (kişi, yer, marka) ÇEVİRME ve Türkçe harflere dönüştürme. Japonca hitap ekleri (-san, -kun, -chan, -senpai, -sensei, -sama) aynen kalır. "Mom, Dad, Teacher, Stranger, Boss, Girl, Guard" gibi unvan/tanımlar Türkçeye çevrilir (Anne, Baba, Öğretmen, Yabancı, Patron, Kız, Muhafız).
9. Türkçe yazım ve noktalama kurallarına (TDK) uy: "de/da" ve "ki" bağlaçlarının ayrı yazımı, soru eki "mı/mi"nin ayrı yazımı, özel isimlere gelen eklerde kesme işareti (Sylvie'nin), I/ı ve İ/i harflerinin doğru kullanımı, cümle sonu noktalama.
10. Anlatıcı satırlarını (konuşmacısı olmayanlar) akıcı, sade ve okunaklı bir anlatımla çevir. Birinci şahıs anlatımı (I → ben) korunur; zaman (geçmiş/şimdiki) tutarlı olsun.
11. Bir cümle sonraki satırda devam ediyorsa ("extend" ile ya da yarım kalan cümleyle) çeviriyi de devam edecek şekilde kur.
12. Menü seçeneklerini kısa ve net tut; kaynağın yapısına uy (emir kipi, birinci şahıs vb.).
13. Hitap kelimelerini doğal karşılıklarıyla çevir: "Mr. Smith" → "Smith Bey", "Mrs./Ms. Smith" → "Smith Hanım" (resmî ortamda "Bay/Bayan Smith" da olur), "sir/ma'am" → "efendim", "dude/bro/man" → "dostum/kanka/abi" (karaktere ve ortama göre), "honey/sweetie" → "tatlım/canım", "babe" → "bebeğim".
14. Kaynakta tamamı BÜYÜK HARFLE yazılmış (bağırma/vurgu) ifadeleri çeviride de büyük harfle yaz; Türkçe büyük harf kuralına uy (i → İ, ı → I).
15. Birimleri ve sayıları Türkçeye uygun yaz: "50%" → "%50", ondalık ayırıcı virgül olabilir; para birimi ve ölçü birimlerini değiştirme.

## TEKNİK KURALLAR (ÇOK ÖNEMLİ — ihlal edilirse oyun çöker)
A. Köşeli parantez içindeki değişkenler ([isim], [mc], [player_name!t], [points] vb.) harfi harfine AYNEN kalmalı; çevirme, silme, değiştirme, boşluk ekleme. Bir değişkene Türkçe ek gerekiyorsa kesme işaretiyle ekle (ör. "[name]'s house" → "[name]'in evi") ya da cümleyi eke gerek kalmayacak biçimde kur.
B. Süslü parantez etiketleri ({i}, {/i}, {b}, {/b}, {w}, {w=0.5}, {p}, {nw}, {fast}, {color=#f00}, {/color}, {size=+10}, {a=...} vb.) AYNEN korunmalı. Açma-kapama etiketleri, çeviride karşılık gelen kelimeleri sarmalı. {w}, {p} gibi duraklamalar cümlede doğal bir yerde kalmalı.
C. "[[" ve "{{" çiftleri ve "%s", "%(ad)s" gibi biçimlendirmeler aynen kalmalı.
D. Satır sonu karakteri (\\n) varsa yerini koru.
E. Yalnızca çeviriyi yaz: açıklama, not, alternatif çeviri, ekstra tırnak işareti EKLEME.
F. Zaten Türkçe olan, sadece isim/sayı/sembol olan ya da çevrilmesi anlamsız metinleri aynen bırak.
G. Her satırı ayrı çevir: satırları birleştirme, bölme veya atlama. Girdideki HER "id" için tam olarak bir çeviri döndür.
H. "baglam" listesindeki satırlar SADECE bağlamı anlaman içindir; onları çevirip döndürme.
I. Bazı satırlar <t0>, <t1> gibi belirteçler içerebilir: bunlar korunması gereken parçalardır; her birini çeviride tam olarak bir kez ve doğru yerde kullan.

## GİRDİ / ÇIKTI
Girdi bir JSON nesnesidir:
{"baglam": [{"k": konuşan, "m": kaynak, "c": önceki çeviri}], "satirlar": [{"id": kimlik, "k": konuşan (boşsa anlatıcı), "t": tür, "m": çevrilecek metin, "not": varsa önceki denemeyle ilgili uyarı}]}
Çıktı SADECE şu biçimde bir JSON dizisidir (başka hiçbir şey yazma):
[{"id": "kimlik", "c": "Türkçe çeviri"}]"""


SOZLUK_TALIMATI = """Sen, görsel roman oyunlarını Türkçeye yerelleştiren deneyimli bir çevirmensin. Çeviriye başlamadan önce oyunda geçen karakter adları, unvanlar ve önemli terimler için tutarlı bir sözlük hazırlıyoruz.

Her terim için:
- Kişi adıysa (Sylvie, John, Akira...) AYNEN bırak.
- Unvan/tanım/lakap ise (Mom, Teacher, Stranger, Boss, Mysterious Girl, Narrator, Me...) doğal Türkçe karşılığını yaz (Anne, Öğretmen, Yabancı, Patron, Gizemli Kız, Anlatıcı, Ben...).
- Yer, kurum, eşya veya oyuna özgü terimse: özel isimse aynen bırak; anlamlı bir ifadeyse Türkçeye uyarla (ör. "Student Council" → "Öğrenci Konseyi").
- "???", sayı veya sembol ise aynen bırak.
- Mümkünse cinsiyeti tahmin et (kadın / erkek / belirsiz). Örnek cümleler bağlam içindir.

Çıktı SADECE JSON dizi: [{"m": "kaynak terim", "c": "Türkçe karşılık", "tur": "isim|unvan|yer|terim", "cinsiyet": "kadın|erkek|belirsiz"}]"""


CIKTI_SEMASI = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id": {"type": "STRING"},
            "c": {"type": "STRING"},
        },
        "required": ["id", "c"],
    },
}

SOZLUK_SEMASI = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "m": {"type": "STRING"},
            "c": {"type": "STRING"},
            "tur": {"type": "STRING"},
            "cinsiyet": {"type": "STRING"},
        },
        "required": ["m", "c"],
    },
}

GUVENLIK_KATEGORILERI = [
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT",
]


def oyun_bilgisi_metni(oyun_adi, oyun_notu, sozluk_satirlari, karakter_satirlari):
    parcalar = []
    if oyun_adi:
        parcalar.append("Oyunun adı: " + oyun_adi + " (oyun adını çevirme).")
    if oyun_notu:
        parcalar.append("Oyun hakkında not (çevirmenin dikkat etmesi gerekenler): " + oyun_notu.strip())
    if karakter_satirlari:
        parcalar.append("Karakterler:\n" + "\n".join("- " + s for s in karakter_satirlari))
    if sozluk_satirlari:
        parcalar.append(
            "Sözlük (bu karşılıkları HER ZAMAN aynen kullan; büyük/küçük harf ve Türkçe ekler cümleye göre uyarlanabilir):\n"
            + "\n".join("- " + s for s in sozluk_satirlari)
        )
    if not parcalar:
        return ""
    return "\n\n## BU OYUNA ÖZEL BİLGİLER\n" + "\n\n".join(parcalar)


def istek_govdesi(sistem, kullanici, ayar, ozellikler, model, sema=CIKTI_SEMASI):
    """Gemini generateContent istek gövdesini oluşturur.

    ozellikler: modelin desteklemediği anlaşılan özellikler kapatılır
    (sistem, json, sema, dusunme, guvenlik).
    """
    gen = {
        "temperature": ayar.get("sicaklik", 0.35),
        "maxOutputTokens": ayar.get("en_fazla_cikti_token", 16384),
        "candidateCount": 1,
    }
    if ozellikler.get("json", True):
        gen["responseMimeType"] = "application/json"
        if ozellikler.get("sema", True) and sema is not None:
            gen["responseSchema"] = sema
    if ozellikler.get("dusunme", True):
        # Desteklemeyen model 400 hatası verirse bu özellik o model için kapatılır.
        butce = ayar.get("dusunme_butcesi", 0)
        if isinstance(butce, int) and not isinstance(butce, bool) and butce >= -1:
            gen["thinkingConfig"] = {"thinkingBudget": butce}

    govde = {"generationConfig": gen}

    if ozellikler.get("sistem", True):
        govde["systemInstruction"] = {"parts": [{"text": sistem}]}
        govde["contents"] = [{"role": "user", "parts": [{"text": kullanici}]}]
    else:
        govde["contents"] = [{"role": "user", "parts": [{"text": sistem + "\n\n---\n\n" + kullanici}]}]

    if ozellikler.get("guvenlik", True):
        govde["safetySettings"] = [{"category": k, "threshold": "BLOCK_NONE"} for k in GUVENLIK_KATEGORILERI]

    return govde


def kapatilacak_ozellik(hata_mesaji):
    """400 hatasının mesajından hangi özelliğin desteklenmediğini tahmin eder."""
    m = (hata_mesaji or "").lower()
    if "thinking" in m or "thinking_budget" in m or "thinkingbudget" in m:
        return "dusunme"
    if "response_schema" in m or "responseschema" in m or "schema" in m:
        return "sema"
    if "response_mime_type" in m or "responsemimetype" in m or "mime" in m or "json mode" in m:
        return "json"
    if "system_instruction" in m or "systeminstruction" in m or "developer instruction" in m or "system instruction" in m:
        return "sistem"
    if "safety" in m or "harm_category" in m or "threshold" in m:
        return "guvenlik"
    return None


def json_cozumle(metin):
    """Yapay zeka yanıtından JSON çıkarır; kod bloğu, fazladan yazı vb. tolere edilir."""
    if metin is None:
        return None
    t = metin.strip()
    t = re.sub(r"^```(?:json|JSON)?\s*", "", t)
    t = re.sub(r"\s*```\s*$", "", t)
    try:
        return json.loads(t)
    except Exception:
        pass
    for ac, kapa in (("[", "]"), ("{", "}")):
        i = t.find(ac)
        j = t.rfind(kapa)
        if i != -1 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except Exception:
                continue
    return None


def ceviri_haritasi(veri):
    """Çözümlenmiş yanıtı {id: çeviri} sözlüğüne çevirir. Çeşitli biçimleri kabul eder."""
    sonuc = {}
    if isinstance(veri, dict):
        for anahtar in ("ceviriler", "satirlar", "translations", "items", "sonuc"):
            if isinstance(veri.get(anahtar), list):
                veri = veri[anahtar]
                break
        else:
            # {"12": "çeviri", ...} biçimi
            for k, v in veri.items():
                if isinstance(v, str):
                    sonuc[str(k)] = v
            return sonuc
    if isinstance(veri, list):
        for e in veri:
            if not isinstance(e, dict):
                continue
            kimlik = e.get("id", e.get("kimlik"))
            ceviri = e.get("c", e.get("ceviri", e.get("tr", e.get("translation"))))
            if kimlik is None or not isinstance(ceviri, str):
                continue
            sonuc[str(kimlik)] = ceviri
    return sonuc
