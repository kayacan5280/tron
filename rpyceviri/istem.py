"""Yapay zekaya gönderilen talimatlar (istemler), çıktı şemaları ve yanıt çözümleme."""

import copy
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

# ---------------------------------------------------------------------------
# Üslup kuralları (çevirmen ve editör ortak kullanır)
# ---------------------------------------------------------------------------

USLUP_KURALLARI = """## ÜSLUP KURALLARI
1. Kelime kelime çeviri YAPMA. Anlamı, duyguyu, tonu, mizahı ve niyeti aktar; cümleyi Türkçenin doğal söz dizimine göre baştan kur. Türkçede yüklem genellikle sondadır; İngilizce cümle yapısını kopyalama.
2. Diyaloglar günlük konuşma dilinde olsun; karakterler gerçek insanlar gibi konuşsun. Kitabi, resmî, yapay ifadelerden kaçın.
   - Kötü: "Ne yapmaktasın?", "Bu benim için büyük bir zevk olurdu." / İyi: "Ne yapıyorsun?", "Seve seve!"
   - Kötü: "Ben iyiyim, teşekkür ederim. Ya sen?" / İyi: "İyiyim, sağ ol. Sen nasılsın?"
   - Gereksiz "ben/sen/biz/benim/senin" zamirlerini kullanma; Türkçede fiil ve iyelik ekleri kişiyi zaten belirtir. Zamiri sadece vurgu gerekiyorsa kullan.
   - İngilizcedeki her "the/a/it/this" için "bu/o/bir" yazma. "have" fiilini "sahip olmak" diye değil "var" ile kur.
   - Konuşmada "-mektedir/-maktadır" ve cümle sonunda gereksiz "-dır/-dir" kullanma.
3. HİTAP: Arkadaşlar, aile, sevgililer, çocuklar, yaşıtlar birbirine "sen" der. Yabancılar, öğretmen, patron, müşteri, yaşça büyükler ve resmî ilişkiler "siz" ile konuşur. Verilen hitap tablosuna uy; tabloda yoksa ilişkiyi bağlamdan çıkar ve tutarlı kal. Arayüz/sistem metinlerinde "siz" kullan.
4. Deyimleri, argoyu, esprileri, kelime oyunlarını birebir çevirme; Türkçede aynı etkiyi yaratan karşılığı bul.
   - "It's raining cats and dogs" → "Bardaktan boşanırcasına yağıyor", "Break a leg!" → "Bol şans!", "No way!" → "Olamaz!/Hadi canım!", "What the hell?" → "Ne oluyor be?", "I'm screwed" → "Yandım/Hapı yuttum", "Good job!" → "Aferin!/Eline sağlık!", "Get a room!" → "Gidin bir odaya kapanın!"
5. Ünlem ve sesleri Türkçeleştir: "Ugh" → "Of/Ay", "Huh?" → "Ha?/Hı?", "Wow" → "Vay!/Vay be!", "Oops" → "Hay aksi/Eyvah", "Ow!/Ouch!" → "Ah!/Ay!", "Yay!" → "Yaşasın!", "Uh.../Um..." → "Şey...", "Hmph" → "Hıh", "Ew" → "Iyy", "Shh" → "Şşş", "Okay" → "Tamam".
6. Küfür, argo, şiddet ve cinsellik içeren ifadeleri sansürlemeden, orijinaldeki yoğunlukta çevir; yumuşatma da, abartma da. Bu, yetişkinlere yönelik bir kurgu eserinin çevirisidir.
7. Karakterin kişiliğini ve konuşma tarzını koru: kaba, utangaç, kibar, alaycı, çocuksu, kekeleyen ("W-wait" → "B-bekle") vb. Karakter kartı verilmişse ona uy.
8. Özel isimleri (kişi, yer, marka) ÇEVİRME ve Türkçe harflere dönüştürme. Japonca hitap ekleri (-san, -kun, -chan, -senpai, -sensei, -sama) aynen kalır. "Mom, Dad, Teacher, Stranger, Boss, Girl, Guard" gibi unvan/tanımlar Türkçeye çevrilir (Anne, Baba, Öğretmen, Yabancı, Patron, Kız, Muhafız).
9. Türkçe yazım ve noktalama kurallarına (TDK) uy: "de/da" ve "ki" bağlaçlarının ayrı yazımı, soru eki "mı/mi"nin ayrı yazımı, özel isimlere gelen eklerde kesme işareti (Sylvie'nin), I/ı ve İ/i harflerinin doğru kullanımı.
10. Anlatıcı satırlarını (konuşmacısı olmayanlar) akıcı, sade ve okunaklı bir anlatımla çevir. Birinci şahıs anlatımı korunur; zaman (geçmiş/şimdiki) tutarlı olsun.
11. Bir cümle sonraki satırda devam ediyorsa ("extend" ya da yarım kalan cümle) çeviriyi de devam edecek şekilde kur. "sonraki" satırlar bunu anlaman içindir.
12. Menü seçeneklerini kısa ve net tut; kaynağın yapısına uy (emir kipi, birinci şahıs vb.).
13. Hitap kelimeleri: "Mr. Smith" → "Smith Bey", "Mrs./Ms. Smith" → "Smith Hanım", "sir/ma'am" → "efendim", "dude/bro/man" → "dostum/kanka/abi" (karaktere göre), "honey/sweetie" → "tatlım/canım", "babe" → "bebeğim".
14. Kaynakta tamamı BÜYÜK HARFLE yazılmış (bağırma) ifadeleri çeviride de büyük harfle yaz (i → İ, ı → I).
15. Sayı ve birimler: "50%" → "%50"; para birimi ve ölçü birimlerini değiştirme.
16. Türkçe çeviri kaynaktan çok uzun olmasın; oyunun metin kutusu sınırlıdır. Aynı anlamı daha kısa söyleyebiliyorsan kısa olanı seç."""

TEKNIK_KURALLAR = """## TEKNİK KURALLAR (ÇOK ÖNEMLİ — ihlal edilirse oyun çöker)
A. Köşeli parantez içindeki değişkenler ([name], [mc], [player_name!t], [points] vb.) harfi harfine AYNEN kalmalı; çevirme, silme, değiştirme. Değişkenin değeri (ör. oyuncunun adı) çeviri sırasında BİLİNMEZ; bu yüzden değişkene ek gelecekse eki tahmin etme, şu işaretlerden birini değişkenin HEMEN ardına yaz (kesme işareti koyma):
   {ek=in} ilgi (Ali'nin) · {ek=i} belirtme (Ali'yi) · {ek=e} yönelme (Ali'ye) · {ek=de} bulunma (Ali'de) · {ek=den} ayrılma (Ali'den) · {ek=le} ile (Ali'yle) · {ek=ler} çoğul · {ek=dir} (Ali'dir) · soru eki için boşluk bırakıp {ek=mi} (Ali mi?)
   Program oyun sırasında bunu ismin sesine göre doğru eke çevirir. Örnek: "[name]'s room" → "[name]{ek=in} odası", "Give it to [name]." → "Bunu [name]{ek=e} ver.", "Is that [name]?" → "Bu [name] {ek=mi}?". Ekten sonra devam eden ek varsa normal yaz: "[name]{ek=in}ki".
B. Süslü parantez etiketleri ({i}, {/i}, {b}, {/b}, {w}, {w=0.5}, {p}, {nw}, {fast}, {color=#f00}, {/color}, {size=+10}, {a=...} vb.) AYNEN korunmalı. Açma-kapama etiketleri, çeviride karşılık gelen kelimeleri sarmalı. {w}, {p} gibi duraklamalar cümlede doğal bir yerde kalmalı. Kendi başına yeni etiket UYDURMA ({ek=...} dışında).
C. "[[" ve "{{" çiftleri ve "%s", "%(ad)s" gibi biçimlendirmeler aynen kalmalı.
D. Satır sonu karakteri (\\n) varsa yerini koru.
E. Yalnızca çeviriyi yaz: açıklama, not, alternatif çeviri, ekstra tırnak işareti EKLEME.
F. Zaten Türkçe olan, sadece isim/sayı/sembol olan ya da çevrilmesi anlamsız metinleri aynen bırak.
G. Her satırı ayrı çevir: satırları birleştirme, bölme veya atlama. Girdideki HER "id" için tam olarak bir çeviri döndür.
H. "baglam" (önceki) ve "sonraki" listelerindeki satırlar SADECE bağlamı anlaman içindir; onları çevirip döndürme.
I. Bazı satırlar <t0>, <t1> gibi belirteçler içerebilir: bunlar korunması gereken parçalardır; her birini çeviride tam olarak bir kez ve doğru yerde kullan."""

ORNEKLER = """## ÖRNEK ÇEVİRİLER (üslup için; birebir kopyalama)
- "Hey! Long time no see. How've you been?" → "Selam! Görüşmeyeli uzun zaman oldu. Nasılsın, ne var ne yok?"
- "I don't know what you're talking about." → "Neden bahsettiğini anlamıyorum."
- "Don't beat around the bush. Just tell me." → "Lafı dolandırma da söyle şunu."
- "Ugh, this is so annoying. I can't believe he did that!" → "Of, çok sinir bozucu. Bunu yaptığına inanamıyorum!"
- "You look really cute when you blush, you know." → "Kızarınca çok tatlı oluyorsun, biliyor musun?"
- "W-wait! That's not what I meant!" → "B-bekle! Öyle demek istemedim!"
- "Excuse me, could you tell me where the station is?" → "Affedersiniz, istasyon ne tarafta acaba?"
- "Oh? Is someone jealous?" → "Ooo? Birileri kıskanıyor mu yoksa?"
- "It's not like I like you or anything!" → "Senden hoşlandığımdan falan değil, yanlış anlama!"
- "What the hell are you doing here?" → "Senin burada ne işin var be?"
- "No way! Seriously?" → "Hadi canım! Ciddi misin?"
- "Thanks, man. I owe you one." → "Sağ ol dostum, sana bir borçluyum."
- "Make yourself at home." → "Kendi evin gibi rahat ol."
- "I have a lot of work to do." → "Bir sürü işim var."
- "Fuck! I forgot my keys." → "Siktir! Anahtarlarımı unuttum."
- "Hmph. Whatever." → "Hıh. Neyse ne."
- "Good morning, Mrs. Johnson." → "Günaydın Johnson Hanım."
- (anlatıcı) "The rain hadn't stopped all night, and the streets were empty." → "Yağmur bütün gece dinmemişti; sokaklar bomboştu."
- (anlatıcı) "I couldn't help but smile." → "Gülümsememe engel olamadım."
- (seçenek) "Ask her out." → "Ona çıkma teklif et." · "Stay silent." → "Sessiz kal."
- "[name]'s room is upstairs." → "[name]{ek=in} odası üst katta."
- "I'll give it to [name] later." → "Sonra [name]{ek=e} veririm."
- "{i}Why{/i} would you do that?" → "Bunu {i}neden{/i} yaptın ki?"
- "I... {w}I love you." → "Ben... {w}seni seviyorum.\""""

CEVIRMEN_GIRIS = """Sen, görsel roman (visual novel) oyunlarını Türkçeye uyarlayan, anadili Türkçe olan, yılların deneyimine sahip profesyonel bir oyun yerelleştirme uzmanısın. Görevin, Ren'Py oyunundan gelen metinleri, oyuncunun bunun bir çeviri olduğunu fark etmeyeceği kadar doğal, akıcı ve gerçek bir Türk'ün konuşacağı gibi Türkçeye çevirmek."""

CEVIRMEN_GIRDI_CIKTI = """## GİRDİ / ÇIKTI
Girdi bir JSON nesnesidir:
{"baglam": [önceki satırlar: {"k": konuşan, "m": kaynak, "c": önceki çeviri}], "satirlar": [{"id": kimlik, "k": konuşan (yoksa anlatıcı), "t": tür, "m": çevrilecek metin, "not": varsa önceki denemeyle ilgili uyarı}], "sonraki": [sonra gelen satırlar: {"k", "m"}]}
Çıktı SADECE şu biçimde bir JSON nesnesidir (başka hiçbir şey yazma):
{"ceviriler": [{"id": "kimlik", "c": "Türkçe çeviri"}]}"""

ANA_TALIMAT = "\n\n".join([CEVIRMEN_GIRIS, USLUP_KURALLARI, TEKNIK_KURALLAR, ORNEKLER, CEVIRMEN_GIRDI_CIKTI])

EDITOR_TALIMATI = "\n\n".join([
    """Sen, oyun çevirilerini son kez okuyup düzelten titiz, anadili Türkçe olan kıdemli bir editörsün. Sana İngilizce (veya başka dildeki) kaynak satırlar, bunların Türkçe taslak çevirileri ve otomatik denetimin bulduğu olası sorunlar verilecek.

Görevin: Her taslağı kaynağıyla ve bağlamıyla karşılaştır; gerekiyorsa daha doğal, akıcı, anlamca doğru, bir Türk'ün gerçekten söyleyeceği biçimde yeniden yaz. Çeviri kokan, kelime kelime çevrilmiş, kitabi ifadeleri; gereksiz zamirleri; yanlış hitabı (sen/siz); hatalı deyim çevirilerini; yazım ve noktalama hatalarını düzelt. Kutuya sığmayacak kadar uzun satırları anlamı koruyarak kısalt. Taslak zaten iyiyse AYNEN döndür; sırf değiştirmek için değiştirme.""",
    USLUP_KURALLARI,
    TEKNIK_KURALLAR,
    """## GİRDİ / ÇIKTI
Girdi: {"baglam": [...önceki satırlar], "satirlar": [{"id", "k": konuşan, "t": tür, "m": kaynak, "taslak": taslak çeviri, "sorunlar": [olası sorunlar]}], "sonraki": [...]}
Çıktı SADECE JSON nesnesi: {"ceviriler": [{"id": "kimlik", "c": "son hali"}]}""",
])

SOZLUK_TALIMATI = """Sen, görsel roman oyunlarını Türkçeye yerelleştiren deneyimli bir çevirmensin. Çeviriye başlamadan önce oyunda geçen karakter adları, unvanlar ve önemli terimler için tutarlı bir sözlük hazırlıyoruz.

Her terim için:
- Kişi adıysa (Sylvie, John, Akira...) AYNEN bırak.
- Unvan/tanım/lakap ise (Mom, Teacher, Stranger, Boss, Mysterious Girl, Narrator, Me...) doğal Türkçe karşılığını yaz (Anne, Öğretmen, Yabancı, Patron, Gizemli Kız, Anlatıcı, Ben...).
- Yer, kurum, eşya veya oyuna özgü terimse: özel isimse aynen bırak; anlamlı bir ifadeyse Türkçeye uyarla (ör. "Student Council" → "Öğrenci Konseyi").
- "???", sayı veya sembol ise aynen bırak.
- Mümkünse cinsiyeti tahmin et (kadın / erkek / belirsiz). Örnek cümleler bağlam içindir.

Çıktı SADECE JSON nesnesi: {"terimler": [{"m": "kaynak terim", "c": "Türkçe karşılık", "tur": "isim|unvan|yer|terim", "cinsiyet": "kadın|erkek|belirsiz"}]}"""

KARAKTER_TALIMATI = """Sen, görsel roman oyunlarını Türkçeye yerelleştiren deneyimli bir çevirmen ve dramaturgsun. Çeviriye başlamadan önce karakterlerin sesini ve birbirlerine hitap şekillerini belirleyeceğiz; böylece binlerce satır boyunca tutarlı kalacağız.

Sana her karakterin örnek replikleri ve karakterler arası örnek konuşmalar verilecek.

1. Her karakter için kısa bir KART yaz:
   - cinsiyet: kadın / erkek / belirsiz
   - yas: tahmini yaş grubu (çocuk, genç, genç yetişkin, yetişkin, yaşlı)
   - uslup: Türkçe çeviride bu karakterin NASIL konuşması gerektiğini 1-2 cümleyle anlat: kişiliği, resmîlik düzeyi, argo kullanımı, sevdiği kalıplar, kime nasıl seslendiği (ör. "Enerjik ve şakacı; kısa, argolu cümleler kurar, arkadaşlarına 'kanka' der.").
2. HİTAP tablosu: Verilen her konuşma çifti için konuşanın dinleyene "sen" mi "siz" mi diyeceğini belirle (Türk kültürüne göre: yakınlar, yaşıtlar, aile, sevgililer sen; yabancı, üst, öğretmen, patron, yaşlı, resmî ilişki siz). İki yönü de (A→B ve B→A) düşün; farklı olabilir (ör. öğrenci öğretmene "siz", öğretmen öğrenciye "sen").

Çıktı SADECE JSON nesnesi:
{"karakterler": [{"ad": "...", "cinsiyet": "...", "yas": "...", "uslup": "..."}], "hitap": [{"konusan": "...", "dinleyen": "...", "hitap": "sen|siz"}]}"""

# ---------------------------------------------------------------------------
# Çıktı şemaları (JSON Schema). Gemini için ayrıca kendi biçimine çevrilir.
# ---------------------------------------------------------------------------


def _nesne(ozellikler, zorunlu):
    return {"type": "object", "properties": ozellikler, "required": zorunlu, "additionalProperties": False}


SEMALAR = {
    "ceviri": _nesne({"ceviriler": {"type": "array", "items": _nesne(
        {"id": {"type": "string"}, "c": {"type": "string"}}, ["id", "c"])}}, ["ceviriler"]),
    "sozluk": _nesne({"terimler": {"type": "array", "items": _nesne(
        {"m": {"type": "string"}, "c": {"type": "string"}, "tur": {"type": "string"}, "cinsiyet": {"type": "string"}},
        ["m", "c", "tur", "cinsiyet"])}}, ["terimler"]),
    "karakter": _nesne({
        "karakterler": {"type": "array", "items": _nesne(
            {"ad": {"type": "string"}, "cinsiyet": {"type": "string"}, "yas": {"type": "string"}, "uslup": {"type": "string"}},
            ["ad", "cinsiyet", "yas", "uslup"])},
        "hitap": {"type": "array", "items": _nesne(
            {"konusan": {"type": "string"}, "dinleyen": {"type": "string"}, "hitap": {"type": "string"}},
            ["konusan", "dinleyen", "hitap"])},
    }, ["karakterler", "hitap"]),
}


def gemini_semasi(sema):
    """JSON Schema'yı Gemini'nin responseSchema biçimine çevirir (büyük harf tipler, additionalProperties yok)."""
    s = copy.deepcopy(sema)

    def donustur(d):
        if isinstance(d, dict):
            d.pop("additionalProperties", None)
            if isinstance(d.get("type"), str):
                d["type"] = d["type"].upper()
            for v in d.values():
                donustur(v)
        elif isinstance(d, list):
            for v in d:
                donustur(v)
    donustur(s)
    return s


# Geriye uyumluluk (eski adlar)
CIKTI_SEMASI = gemini_semasi(SEMALAR["ceviri"])
SOZLUK_SEMASI = gemini_semasi(SEMALAR["sozluk"])

GUVENLIK_KATEGORILERI = [
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT",
]


# ---------------------------------------------------------------------------
# Oyuna özel bilgi bölümleri
# ---------------------------------------------------------------------------


def oyun_bilgisi_metni(oyun_adi, oyun_notu, sozluk_satirlari=None, karakter_satirlari=None, kullanici_ornekleri=None,
                       hitap_satirlari=None):
    """Oyun boyunca değişmeyen bilgiler (önbelleğe alınabilir kısım)."""
    parcalar = []
    if oyun_adi:
        parcalar.append("Oyunun adı: " + oyun_adi + " (oyun adını çevirme).")
    if oyun_notu:
        parcalar.append("Oyun hakkında not (çevirmenin dikkat etmesi gerekenler): " + oyun_notu.strip())
    if karakter_satirlari:
        parcalar.append("Karakterler (ses tonlarını ve konuşma tarzlarını koru):\n"
                        + "\n".join("- " + s for s in karakter_satirlari))
    if hitap_satirlari:
        parcalar.append("Hitap tablosu (konuşan → dinleyen: sen/siz). Buna uy:\n"
                        + "\n".join("- " + s for s in hitap_satirlari))
    if sozluk_satirlari:
        parcalar.append(
            "Sözlük (bu karşılıkları HER ZAMAN aynen kullan; Türkçe ekler cümleye göre uyarlanabilir):\n"
            + "\n".join("- " + s for s in sozluk_satirlari))
    if kullanici_ornekleri:
        parcalar.append(
            "Kullanıcının bu oyun için kendisi düzelttiği çeviriler (üslubunu ve tercihlerini bunlara benzet):\n"
            + "\n".join('- "%s" → "%s"' % (k.replace("\n", " "), c.replace("\n", " ")) for k, c in kullanici_ornekleri))
    if not parcalar:
        return ""
    return "\n\n## BU OYUNA ÖZEL BİLGİLER\n" + "\n\n".join(parcalar)


def paket_bilgisi_metni(sozluk_satirlari, kart_satirlari, hitap_satirlari):
    """Pakete göre değişen bilgiler (önbelleğe alınmayan kısım)."""
    parcalar = []
    if kart_satirlari:
        parcalar.append("Bu bölümde konuşan karakterler: " + ", ".join(kart_satirlari))
    if hitap_satirlari:
        parcalar.append("Bu bölümdeki hitaplar (konuşan → dinleyen: sen/siz):\n" + "\n".join("- " + s for s in hitap_satirlari))
    if sozluk_satirlari:
        parcalar.append("Bu bölümde geçen sözlük terimleri (aynen kullan):\n" + "\n".join("- " + s for s in sozluk_satirlari))
    if not parcalar:
        return ""
    return "## BU PAKETE ÖZEL BİLGİLER\n" + "\n\n".join(parcalar)


# ---------------------------------------------------------------------------
# Gemini istek gövdesi
# ---------------------------------------------------------------------------


def istek_govdesi(sistem, kullanici, ayar, ozellikler, model, sema=None):
    """Gemini generateContent istek gövdesini oluşturur.

    sema: Gemini biçiminde responseSchema (gemini_semasi ile üretilmiş) ya da None.
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
    if "response_mime_type" in m or "responsemimetype" in m or "mime" in m or "json mode" in m or "response_format" in m:
        return "json"
    if "system_instruction" in m or "systeminstruction" in m or "developer instruction" in m or "system instruction" in m:
        return "sistem"
    if "safety" in m or "harm_category" in m or "threshold" in m:
        return "guvenlik"
    if "temperature" in m:
        return "sicaklik"
    return None


# ---------------------------------------------------------------------------
# Yanıt çözümleme
# ---------------------------------------------------------------------------


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
    # Önce metinde ilk görünen yapı denenir: "[{...}]" listesinde içteki ilk nesneyi
    # tek başına almamak için.
    adaylar = sorted((("{", "}"), ("[", "]")), key=lambda ak: (t.find(ak[0]) == -1, t.find(ak[0])))
    for ac, kapa in adaylar:
        i = t.find(ac)
        j = t.rfind(kapa)
        if i != -1 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except Exception:
                continue
    return None


def liste_al(veri, *anahtarlar):
    """Yanıt bir liste ya da {"anahtar": [...]} nesnesi olabilir; listeyi döndürür."""
    if isinstance(veri, list):
        return veri
    if isinstance(veri, dict):
        for a in anahtarlar:
            if isinstance(veri.get(a), list):
                return veri[a]
        for v in veri.values():
            if isinstance(v, list):
                return v
    return []


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
