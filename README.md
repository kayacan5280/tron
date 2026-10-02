# Ren'Py Türkçe Çeviri Motoru  (v2.0)

Ren'Py ile yapılmış görsel roman oyunlarını **doğal ve akıcı Türkçeye** çeviren program. Kod bilmenize gerek yok.
Varsayılan olarak Google'ın Gemini yapay zekası kullanılır (**ücretsiz**). İsterseniz kredi yüklediğiniz
**Claude, DeepSeek, OpenAI** veya **OpenRouter** hesabınızı da kullanabilirsiniz.

- Oyunun dosyalarına **dokunmaz**; sadece küçük bir Türkçe yama ekler. İstediğiniz an tek tıkla kaldırılır.
- `.rpa` arşivli, kaynak kodu olmayan oyunlarda da çalışır. Ren'Py 6.99, 7.x ve 8.x ile test edilmiştir.
- Birden fazla API anahtarı girebilirsiniz; birinin kotası bitince otomatik olarak diğerine geçer.
- Kota biterse, internet giderse veya programı kapatırsanız **kaldığı yerden devam eder**, hiçbir çeviri kaybolmaz.
- Türkçe harf (ğ, ş, ı, İ) desteklemeyen oyun fontlarını otomatik olarak düzeltir.
- Oyun içinde **Alt+T** ile Türkçe / orijinal metin arasında geçiş yapabilirsiniz.

### Çeviriyi "Türkçe yazılmış gibi" yapan özellikler
- **Karakter kartları ve sen/siz tablosu:** Çeviriden önce her karakterin konuşma tarzı (neşeli, kaba, resmî...)
  ve kimin kime "sen", kime "siz" dediği belirlenir; binlerce satır boyunca ses tonu ve hitap tutarlı kalır.
- **Önceki ve sonraki satırlar:** Her satır, öncesindeki konuşmayla ve devamındaki birkaç satırla birlikte çevrilir;
  yarım kalan cümleler doğru bağlanır.
- **Türk editör geçişi:** "Ne cehennem", "sahibim", "beklemekteyiz", gereksiz "ben/sen" gibi çeviri kokan satırlar
  otomatik bulunur ve ikinci kez bir "Türk editör" tarafından doğallaştırılır.
- **Doğru Türkçe ekler:** Oyuncunun girdiği isme gelen ekler oyun sırasında isme göre seçilir:
  `Elif'in`, `Ali'nin`, `Mike'ın`, `Kate'in`, `Ali'ye`, `Elif'e`...
- **Sizin düzeltmeleriniz:** Çevirileri Not Defteri'nde düzeltebilirsiniz; düzelttikleriniz korunur ve yapay zekaya
  "bu oyunda böyle çevir" örneği olarak gösterilir.
- **Bağıran (BÜYÜK HARF) satırlar** Türkçe kurallarla büyük yazılır (`İ`, `I`); kutudan taşacak kadar uzayan satırların
  yazısı biraz küçültülür.

---

## 1. Kurulum (bir kez yapılır)

### 1.1 Python'u kurun
1. https://www.python.org/downloads/ adresine gidin, sarı **Download Python** butonuna basın.
2. İnen dosyayı açın. **İlk ekranda en alttaki "Add python.exe to PATH" kutusunu mutlaka işaretleyin.**
3. **Install Now**'a basın ve kurulumun bitmesini bekleyin.

### 1.2 Programı bir klasöre çıkarın
İndirdiğiniz zip dosyasını **Masaüstü** veya **Belgeler** gibi bir klasöre çıkarın.
(`C:\Program Files` içine çıkarmayın; orada yazma izni olmaz.)

> **Eski sürümden geçiyorsanız:** Yeni zip'i aynı klasörün üzerine çıkarın (dosyaların üzerine yazın).
> `api_anahtarlari.txt`, `ayarlar.json` ve `projeler` klasörünüz korunur; yarım kalan çeviriler kaldığı yerden devam eder.

### 1.3 Gemini API anahtarı alın (ücretsiz)
1. https://aistudio.google.com/apikey adresine gidin ve Google hesabınızla giriş yapın.
2. **Create API key** (API anahtarı oluştur) butonuna basın.
3. Çıkan uzun anahtarı (`AIza...` ile başlar) kopyalayın.

> **Önemli ipucu:** Aynı Google hesabından alınan bütün anahtarlar **aynı kotayı paylaşır**.
> Daha hızlı çeviri için **farklı Google hesaplarından** (sizin, arkadaşınızın...) anahtar alın.
> 10 farklı hesaptan 10 anahtar = yaklaşık 10 kat daha fazla ücretsiz çeviri.

### 1.4 (İsteğe bağlı) Ücretli servisler
Daha yüksek kalite isterseniz kredi yüklediğiniz bir hesabın anahtarını da girebilirsiniz. Program anahtarın
hangi servise ait olduğunu kendisi tanır:

| Servis | Anahtar nereden alınır | Not |
|---|---|---|
| Anthropic Claude | https://console.anthropic.com/settings/keys | `sk-ant-...` ile başlar. Varsayılan model `claude-opus-5-5` (en kaliteli). |
| DeepSeek | https://platform.deepseek.com/api_keys | Çok ucuz. |
| OpenAI | https://platform.openai.com/api-keys | |
| OpenRouter | https://openrouter.ai/keys | Birçok modele tek anahtarla erişim. |

- Claude için gereken `anthropic` Python paketi kurulu değilse program bunu **kendisi kurmayı önerir**.
- Ücretli servis kullanılacaksa her çeviriden önce **tahmini maliyet** gösterilir ve **bütçe** sorulur
  (ör. "en fazla 10 $"). Bütçe dolunca ücretli servis durur; Gemini anahtarınız varsa çeviri onunla devam eder.
- Claude'da sunucu taraflı **yedek model** (`fallbacks`) açıktır: bir istek Claude'un güvenlik sınıflandırıcısına
  takılırsa Anthropic'in önerdiği modelle otomatik olarak yeniden denenir.
- Yapılan harcama `projeler/<oyun>/maliyet.json` dosyasında tutulur ve sonuç ekranında gösterilir.

---

## 2. Kullanım

1. Çevireceğiniz **oyunu kapatın**.
2. Program klasöründeki **`BASLAT.bat`** dosyasına çift tıklayın.
3. **İlk açılışta** sizden API anahtarlarını ister: her satıra bir anahtar yapıştırın, bitince boş satırda Enter'a basın.
   Anahtarlar kaydedilir, bir daha sorulmaz. (Sonradan menüdeki **"API anahtarlarını yönet"** ile ekleyip silebilirsiniz.)
4. Menüden **1 (Oyun çevir)** seçin.
5. Oyunun klasörünü (içinde `game` klasörü ve oyunun `.exe` dosyası olan klasör) siyah pencereye **sürükleyip bırakın** ve Enter'a basın.
6. Birden fazla servisin anahtarı varsa hangisinin kullanılacağını, ardından **kalite modunu** sorar:
   - **Hızlı:** tek geçiş, en az istek.
   - **Dengeli (önerilen):** çeviri kokan satırlar ikinci kez editörden geçer (~%10-30 ek istek).
   - **En iyi:** bütün diyaloglar editörden geçer (yaklaşık 2 kat istek).
7. Program sırasıyla şunları yapar:
   1. Oyunu birkaç saniyeliğine açıp kapatarak bütün metinleri okur (oyun penceresi açılıp kendiliğinden kapanır, normaldir).
   2. İsterseniz oyun hakkında kısa bir not ister (tür, karakterlerin hitap şekli vb. — boş bırakabilirsiniz).
   3. Karakter adları ve terimler için bir **sözlük**, karakterler için **kartlar ve sen/siz tablosu** hazırlar.
   4. Çeviriyi yapar (ilerleme çubuğundan takip edebilirsiniz).
   5. Kalite modunuza göre çeviri kokan satırları **editör geçişinden** geçirir.
   6. Sonunda Türkçe yamayı oyuna kurar.
8. Oyunu normal şekilde açın. Artık Türkçe!

**Kısayol:** Oyun klasörünü doğrudan `BASLAT.bat` dosyasının üzerine sürükleyip bırakırsanız o oyun hemen çevrilmeye başlar.

### Oyun içinde
- **Alt+T**: Türkçe ↔ orijinal metin geçişi.
- Yamayı kaldırmak için programı açıp **4 (Oyundan Türkçe yamayı kaldır)** seçin. Oyun orijinal haline döner; kayıt dosyalarınız bozulmaz.

### Ana menü
| Seçenek | Ne yapar |
|---|---|
| 1 Oyun çevir | Yeni oyunu çevirir ya da yarım kalanı devam ettirir. |
| 2 API anahtarlarını yönet | Anahtar ekle/sil, dene (kota/ücret harcamaz), "kota doldu" işaretlerini sıfırla. |
| 3 Kayıtlı çeviriyi oyuna yeniden uygula | API kullanmadan yamayı yeniden kurar (sözlük/düzeltme sonrası). |
| 4 Oyundan Türkçe yamayı kaldır | Oyunu orijinal haline döndürür. |
| 5 Çevirileri elle düzenle | Bütün çevirileri oyundaki sırayla Not Defteri'nde açar; düzelttikleriniz kaydedilir. |
| 6 Kalite testi | İki yapay zekanın çevirisini **kör** karşılaştırır (aşağıya bakın). |

---

## 3. Kota bitince / internet gidince ne olur?

Google ücretsiz kullanımda her anahtar için **dakikalık** ve **günlük** istek sınırı koyar (sınırlar zaman zaman değişir).

- Dakikalık sınıra takılınca program kısa süre bekleyip devam eder.
- Bir anahtarın günlük kotası bitince otomatik olarak sıradaki anahtara, hepsi bitince sıradaki (daha hafif) modele geçer.
- Hepsinin kotası bitince program durur, o ana kadar yapılanları kaydeder ve kotaların **Türkiye saatiyle ne zaman yenileneceğini** söyler (genelde sabah 10:00–11:00 arası).
- O saatten sonra programı tekrar çalıştırıp aynı oyunu seçin: **kaldığı yerden devam eder.**
- **İnternet giderse** çeviri durmaz: program bağlantının geri gelmesini bekler (varsayılan en fazla 20 dakika,
  `internet_bekleme_dk` ayarı) ve geri gelince kaldığı yerden devam eder. Kesinti yüzünden hiçbir satır "çevrilemedi" sayılmaz.
- Yarım kalan çeviriyi de oyuna uygulayabilirsiniz; çevrilmemiş satırlar orijinal dilde görünür.

---

## 4. Çeviri kalitesi için ipuçları

Oyunun bütün dosyaları `projeler/<oyun>/` klasöründedir:

| Dosya | Ne işe yarar |
|---|---|
| `oyun_notu.txt` | İlk çeviride yazdığınız not (tür, ortam, hitap). Örnek: *"Üniversitede geçen romantik komedi. Ana karakter erkek. Arkadaşlar birbirine 'sen' der, öğretmenlere 'siz' denir."* |
| `sozluk.txt` | Karakter adları ve terimler (`Mom = Anne`). Değiştirebilirsiniz; çevirilerde bu karşılıklar kullanılır. |
| `karakterler.txt` | Karakter kartları ve sen/siz tablosu (`Sylvie -> Me = sen`). Değiştirebilirsiniz. |
| `ceviri_duzenle.txt` | "Çevirileri elle düzenle" ile açılan düzenleme dosyası. |
| `ek_istisnalari.txt` | Bir isimde yanlış ek çıkarsa (ör. `Mike'in` yerine `Mike'ın` olmalı) okunuşunu yazın: `Mike = mayk`. |
| `rapor.txt` | Çevrilemeyen, kontrol önerilen ve kutudan taşabilecek satırlar. |
| `kalite_testi.html` | Kör test sayfası. |

### Çevirileri elle düzeltme
Menüden **5**'i seçin. Bütün çeviriler oyundaki sırayla Not Defteri'nde açılır:
```
[12] Sylvie
EN: Hi there! How was class?
TR: Selam! Ders nasıldı?
```
Sadece `TR:` satırlarını değiştirin, kaydedin (Ctrl+S) ve programa dönüp Enter'a basın.
- Düzelttiğiniz satırlar **"elle"** olarak işaretlenir; hiçbir otomatik işlem (editör geçişi, yeniden çeviri) bunları değiştirmez.
- Oyunu bozacak bir düzeltme (ör. `[name]` değişkenini silmek) kaydedilmez, size hangi satır olduğu söylenir.
- Düzeltmeleriniz sonraki çevirilerde yapay zekaya üslup örneği olarak gösterilir.
- Dosyayı programı açmadan düzenlediyseniz, bir sonraki "Oyun çevir"de değişiklikler otomatik alınır.

### Kör kalite testi
Menüden **6**'yı seçin. Oyundan 30 satır seçilir ve iki seçeneğe (ör. kayıtlı çeviriler ile Claude, ya da iki
Gemini modeli) çevrilir. Tarayıcıda açılan sayfada hangi çevirinin hangi modele ait olduğu gizlidir; her satırda
daha doğal olanı seçip **Sonucu göster**'e basınca kazanan açıklanır. Hangi servisin bu oyun için daha iyi Türkçe
yazdığını önyargısız görmenin en kolay yolu budur. Test çevirileri gerçek çevirilerinize karışmaz.

### Ortak çeviri hafızası
"Yes", "Load Game", "Thank you!" gibi kısa ve bağlamdan bağımsız metinler bütün oyunlarınız arasında paylaşılır
(`hafiza/ortak_ceviri_hafizasi.json`). Başka bir oyunda aynı metin geçerse API harcanmadan kullanılır.
Uzun diyaloglar paylaşılmaz; her oyunda kendi bağlamıyla çevrilir.

### Çeviride kullanılan güvenlik kontrolleri
Yapay zekanın her çevirisi oyuna yazılmadan önce kontrol edilir:
- Oyundaki değişkenler (`[isim]`) ve yazı etiketleri (`{i}`, `{w}`, `{color=...}`) eksiksiz ve aynen korunmuş mu?
  (Bunlar bozulursa oyun çöker; bu yüzden bozuk çeviri **asla** oyuna yazılmaz, tekrar çevrilir.)
- Boş, aşırı uzun/kısa, çevrilmeden bırakılmış veya hâlâ İngilizce görünen çeviriler tekrar denenir.
- Yapay zekanın güvenlik filtresine takılan satırlar başka bir modelle denenir; yine olmazsa o satır orijinal kalır.
- Editörün önerisi de aynı kontrolden geçer; bozuk öneri reddedilir, önceki çeviri kalır.

---

## 5. Sık karşılaşılan durumlar

| Durum | Çözüm |
|---|---|
| "Python bulunamadı" | Python'u kurun; kurulumda **"Add python.exe to PATH"** kutusunu işaretleyin. Gerekirse bilgisayarı yeniden başlatın. |
| "Bu klasörde Ren'Py oyunu bulunamadı" | İçinde `game` klasörü olan **ana oyun klasörünü** seçin. |
| "Oyun klasörüne yazılamıyor" | Oyunu `Program Files` dışında bir klasöre kopyalayın veya `BASLAT.bat`'ı yönetici olarak çalıştırın. |
| "Oyun açılırken hata verdi" | Oyunun kendisinin normal açıldığından emin olun. Oyun açıksa kapatıp tekrar deneyin. |
| Oyun otomatik açılmadı | Program sizden oyunu elle açmanızı ister; oyunu çift tıklayarak açın, birkaç saniye içinde kendiliğinden kapanır. |
| "SSL / güvenli bağlantı hatası" | Bilgisayarın tarih-saatini kontrol edin; antivirüsün "HTTPS tarama" özelliğini kapatın; Python'u güncelleyin. |
| "İnternet bağlantısı ... dakikadır yok" | Bağlantıyı kontrol edip tekrar çalıştırın; kaldığı yerden devam eder. |
| "Hesapta kredi kalmadı" (Claude/DeepSeek...) | Hesabınıza kredi yükleyin ya da o anahtarı silin; Gemini anahtarınız varsa çeviri onunla sürer. |
| "anthropic paketi kurulu değil" | Programın önerdiği kurulumu onaylayın ya da komut isteminde `py -m pip install anthropic` çalıştırın. |
| Bir isimde yanlış ek (Mike'in) | `projeler/<oyun>/ek_istisnalari.txt` dosyasına `Mike = mayk` yazıp menüden **3**'ü seçin. |
| Bazı yazılar İngilizce kaldı | Resimlerin içine gömülü yazılar (logo, butonlar resimse) çevrilemez. Diğerleri için `rapor.txt`'ye bakın ve programı tekrar çalıştırın. |
| Türkçe harfler kutu (□) görünüyor | Program bunu otomatik düzeltir. Yine de olursa `ayarlar.json` içindeki `yedek_font` ayarına Türkçe destekli bir `.ttf` dosyasının yolunu yazın. |
| Oyun güncellendi | Programı tekrar çalıştırın; metinleri yeniden çıkarır, sadece yeni/değişen satırları çevirir. |

Bir hata olursa program klasöründe `hata_raporu.txt`, oyunun proje klasöründe de `gunluk.txt` oluşur.

---

## 6. Ayarlar (`ayarlar.json`)

Program ilk açılışta `ayarlar.json` dosyasını oluşturur. Her ayarın açıklaması dosyanın içinde yazar. Önemlileri:

| Ayar | Açıklama |
|---|---|
| `modeller` | Sırayla kullanılacak Gemini modelleri. İlk model en kalitelisi kabul edilir. |
| `kalite_modu` | `hizli` / `dengeli` / `en_iyi` (her çeviride sorulur, son seçim hatırlanır). |
| `paket_satir` | Bir istekte çevrilecek satır sayısı (büyük = daha az istek, kota tasarrufu). |
| `paralel` | Aynı anda gönderilecek istek sayısı. |
| `baglam_satir` / `sonraki_baglam_satir` | Her pakete eklenen önceki / sonraki satır sayısı. |
| `internet_bekleme_dk` | İnternet kesilirse en fazla kaç dakika bekleneceği (varsayılan 20). |
| `claude_modeli` / `claude_efor` | Claude modeli (`claude-opus-5-5` ya da daha ucuz `claude-sonnet-5-5`) ve düşünme eforu (`low` / `medium` / `high`). |
| `deepseek_modeli`, `openai_modeli`, `openrouter_modeli` | Diğer ücretli servislerin modelleri. |
| `butce_usd` | Ücretli servisler için oyun başına en fazla harcama ($). 0 = her çeviride sorulur. |
| `saglayici_sirasi` | Birden fazla servis varsa "hepsi sırayla" seçeneğindeki sıra. |
| `uzun_satir_kucult` | Çok uzayan diyalog satırlarının yazısını biraz küçült. |
| `ortak_hafiza` | Oyunlar arası ortak çeviri hafızası. |
| `python_metinleri` | Oyunun kod içindeki metinlerini (görev, eşya açıklaması vb.) de çevir. |
| `kisayol` | Oyun içi Türkçe/orijinal geçiş tuşu (varsayılan `alt_K_t` = Alt+T). |
| `yedek_font` | Türkçe harf desteği olmayan fontların yerine kullanılacak font dosyası. |

---

## 7. Güvenlik ve gizlilik

- API anahtarlarınız sadece kendi bilgisayarınızda, `api_anahtarlari.txt` dosyasında saklanır. **Bu dosyayı kimseyle paylaşmayın.**
- Oyun metinleri çeviri için seçtiğiniz yapay zeka servisine (Google, Anthropic, DeepSeek, OpenAI, OpenRouter) gönderilir.

---

## 8. Nasıl çalışır? (meraklısı için)

1. Oyuna geçici olarak küçük bir Ren'Py betiği eklenir; oyun kendi motoruyla açılır ve bütün diyalog, seçenek ve
   arayüz metinlerini bir dosyaya yazıp kapanır. Betik hemen silinir.
2. Karakterlerin örnek replikleri incelenerek karakter kartları ve sen/siz tablosu çıkarılır.
3. Metinler oyundaki sırasıyla, önceki/sonraki satırlar, sözlük ve karakter kartlarıyla birlikte paketler halinde
   yapay zekaya gönderilir. Oyun boyunca değişmeyen talimatlar önbelleğe alınır (Claude/DeepSeek'te daha ucuz).
4. Her çeviri doğrulanır ve `projeler/<oyun>/ceviriler.json` dosyasına anında kaydedilir.
5. Çeviri kokusu dedektörü (yapay zeka kullanmaz) şüpheli satırları bulur; bunlar editör isteğinden geçer.
6. Oyuncunun adı gibi değişkenlere gelecek ekler çeviride `[name]{ek=in}` biçiminde işaretlenir; oyundaki yama
   ismin okunuşuna bakarak doğru eki seçer (ünlü/ünsüz uyumu, yabancı isimlerin okunuşu, sayılar, kısaltmalar).
7. Oyuna şu dosyalar **eklenir** (hiçbir oyun dosyası değiştirilmez):
   - `game/zzzz_trceviri_yama.rpy` — çeviriyi oyun içinde uygulayan küçük betik
   - `game/trceviri/ceviri.json` — çeviriler
8. Menüler, kayıt ekranı, ayarlar gibi standart Ren'Py arayüz metinleri için Ren'Py'ın resmi Türkçe çevirileri
   (MIT lisanslı) düzeltilerek hazır olarak kullanılır; bunlar için API harcanmaz.

### Geliştiriciler için
```
python ceviri.py                    # menülü kullanım
python ceviri.py "OYUN_KLASORU"     # doğrudan çevir
python ceviri.py "OYUN" --evet      # soru sormadan, varsayılanlarla
python ceviri.py "OYUN" --uygula    # kayıtlı çeviriyi API kullanmadan oyuna yaz
python ceviri.py "OYUN" --kaldir    # yamayı kaldır
python -m unittest discover -s testler   # testler
```
Sadece Python standart kütüphanesi kullanılır. Claude için resmî `anthropic` paketi gerekir
(program gerektiğinde kurmayı önerir).
