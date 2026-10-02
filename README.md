# Ren'Py Türkçe Çeviri Motoru

Ren'Py ile yapılmış görsel roman oyunlarını **ücretsiz** olarak, **doğal ve akıcı Türkçeye** çeviren program.
Çeviri için Google'ın Gemini yapay zekası kullanılır (ücretsiz katman). Kod bilmenize gerek yok.

- Oyunun dosyalarına **dokunmaz**; sadece küçük bir Türkçe yama ekler. İstediğiniz an tek tıkla kaldırılır.
- `.rpa` arşivli, kaynak kodu olmayan oyunlarda da çalışır.
- Ren'Py 6.99, 7.x ve 8.x sürümleriyle test edilmiştir.
- Birden fazla API anahtarı girebilirsiniz; birinin kotası bitince otomatik olarak diğerine geçer.
- Kota biterse veya programı kapatırsanız **kaldığı yerden devam eder**, hiçbir çeviri kaybolmaz.
- Türkçe harf (ğ, ş, ı, İ) desteklemeyen oyun fontlarını otomatik olarak düzeltir.
- Oyun içinde **Alt+T** ile Türkçe / orijinal metin arasında geçiş yapabilirsiniz.

---

## 1. Kurulum (bir kez yapılır)

### 1.1 Python'u kurun
1. https://www.python.org/downloads/ adresine gidin, sarı **Download Python** butonuna basın.
2. İnen dosyayı açın. **İlk ekranda en alttaki "Add python.exe to PATH" kutusunu mutlaka işaretleyin.**
3. **Install Now**'a basın ve kurulumun bitmesini bekleyin.

### 1.2 Programı bir klasöre çıkarın
İndirdiğiniz zip dosyasını **Masaüstü** veya **Belgeler** gibi bir klasöre çıkarın.
(`C:\Program Files` içine çıkarmayın; orada yazma izni olmaz.)

### 1.3 Gemini API anahtarı alın (ücretsiz)
1. https://aistudio.google.com/apikey adresine gidin ve Google hesabınızla giriş yapın.
2. **Create API key** (API anahtarı oluştur) butonuna basın.
3. Çıkan uzun anahtarı (`AIza...` ile başlar) kopyalayın.

> **Önemli ipucu:** Aynı Google hesabından alınan bütün anahtarlar **aynı kotayı paylaşır**.
> Daha hızlı çeviri için **farklı Google hesaplarından** (sizin, arkadaşınızın...) anahtar alın.
> 10 farklı hesaptan 10 anahtar = yaklaşık 10 kat daha fazla ücretsiz çeviri.

---

## 2. Kullanım

1. Çevireceğiniz **oyunu kapatın**.
2. Program klasöründeki **`BASLAT.bat`** dosyasına çift tıklayın.
3. **İlk açılışta** sizden API anahtarlarını ister: her satıra bir anahtar yapıştırın, bitince boş satırda Enter'a basın.
   Anahtarlar kaydedilir, bir daha sorulmaz. (Sonradan menüdeki **"API anahtarlarını yönet"** ile ekleyip silebilirsiniz.)
4. Menüden **1 (Oyun çevir)** seçin.
5. Oyunun klasörünü (içinde `game` klasörü ve oyunun `.exe` dosyası olan klasör) siyah pencereye **sürükleyip bırakın** ve Enter'a basın.
6. Program sırasıyla şunları yapar:
   - Oyunu birkaç saniyeliğine açıp kapatarak bütün metinleri okur (oyun penceresi açılıp kendiliğinden kapanır, normaldir).
   - İsterseniz oyun hakkında kısa bir not ister (tür, karakterlerin hitap şekli vb. — boş bırakabilirsiniz).
   - Karakter adları ve terimler için bir **sözlük** hazırlar (tutarlı çeviri için).
   - Çeviriyi yapar (ilerleme çubuğundan takip edebilirsiniz).
   - Sonunda Türkçe yamayı oyuna kurar.
7. Oyunu normal şekilde açın. Artık Türkçe!

**Kısayol:** Oyun klasörünü doğrudan `BASLAT.bat` dosyasının üzerine sürükleyip bırakırsanız o oyun hemen çevrilmeye başlar.

### Oyun içinde
- **Alt+T**: Türkçe ↔ orijinal metin geçişi.
- Yamayı kaldırmak için programı açıp **4 (Oyundan Türkçe yamayı kaldır)** seçin. Oyun orijinal haline döner; kayıt dosyalarınız bozulmaz.

---

## 3. Kota bitince ne olur?

Google ücretsiz kullanımda her anahtar için **dakikalık** ve **günlük** istek sınırı koyar (sınırlar zaman zaman değişir).

- Dakikalık sınıra takılınca program kısa süre bekleyip devam eder.
- Bir anahtarın günlük kotası bitince otomatik olarak sıradaki anahtara, hepsi bitince sıradaki (daha hafif) modele geçer.
- Hepsinin kotası bitince program durur, o ana kadar yapılanları kaydeder ve kotaların **Türkiye saatiyle ne zaman yenileneceğini** söyler (genelde sabah 10:00–11:00 arası).
- O saatten sonra programı tekrar çalıştırıp aynı oyunu seçin: **kaldığı yerden devam eder.**
- Yarım kalan çeviriyi de oyuna uygulayabilirsiniz; çevrilmemiş satırlar orijinal dilde görünür.

---

## 4. Çeviri kalitesi için ipuçları

- **Oyun notu:** İlk çeviride sorulan nota oyunun türünü ve ortamını yazın. Örnek:
  *"Üniversitede geçen romantik komedi. Ana karakter erkek. Arkadaşlar birbirine 'sen' der, öğretmenlere 'siz' denir."*
  Not, `projeler/<oyun>/oyun_notu.txt` dosyasında durur; değiştirebilirsiniz.
- **Sözlük:** `projeler/<oyun>/sozluk.txt` dosyasında karakter adları ve terimler bulunur (`Mom = Anne` gibi).
  İstediğiniz gibi düzenleyebilirsiniz; sonraki çevirilerde bu karşılıklar kullanılır.
- **Rapor:** `projeler/<oyun>/rapor.txt` dosyasında çevrilemeyen ve kontrol edilmesi önerilen satırlar listelenir.
  Çevrilemeyen satırlar programı tekrar çalıştırdığınızda yeniden denenir.

### Çeviride kullanılan güvenlik kontrolleri
Yapay zekanın her çevirisi oyuna yazılmadan önce kontrol edilir:
- Oyundaki değişkenler (`[isim]`) ve yazı etiketleri (`{i}`, `{w}`, `{color=...}`) eksiksiz ve aynen korunmuş mu?
  (Bunlar bozulursa oyun çöker; bu yüzden bozuk çeviri **asla** oyuna yazılmaz, tekrar çevrilir.)
- Boş, aşırı uzun/kısa, çevrilmeden bırakılmış veya hâlâ İngilizce görünen çeviriler tekrar denenir.
- Yapay zekanın güvenlik filtresine takılan satırlar başka bir modelle denenir; yine olmazsa o satır orijinal kalır.

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
| "İnternet bağlantısı yok" | Bağlantıyı kontrol edip tekrar çalıştırın; kaldığı yerden devam eder. |
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
| `paket_satir` | Bir istekte çevrilecek satır sayısı (büyük = daha az istek, kota tasarrufu). |
| `paralel` | Aynı anda gönderilecek istek sayısı. |
| `baglam_satir` | Tutarlılık için her pakete eklenen önceki satır sayısı. |
| `python_metinleri` | Oyunun kod içindeki metinlerini (görev, eşya açıklaması vb.) de çevir. |
| `kisayol` | Oyun içi Türkçe/orijinal geçiş tuşu (varsayılan `alt_K_t` = Alt+T). |
| `yedek_font` | Türkçe harf desteği olmayan fontların yerine kullanılacak font dosyası. |

---

## 7. Güvenlik ve gizlilik

- API anahtarlarınız sadece kendi bilgisayarınızda, `api_anahtarlari.txt` dosyasında saklanır. **Bu dosyayı kimseyle paylaşmayın.**
- Oyun metinleri çeviri için Google Gemini API'ye gönderilir.

---

## 8. Nasıl çalışır? (meraklısı için)

1. Oyuna geçici olarak küçük bir Ren'Py betiği eklenir; oyun kendi motoruyla açılır ve bütün diyalog, seçenek ve
   arayüz metinlerini bir dosyaya yazıp kapanır. Betik hemen silinir.
2. Metinler oyundaki sırasıyla, önceki satırların bağlamı ve sözlükle birlikte paketler halinde Gemini'ye gönderilir.
3. Her çeviri doğrulanır ve `projeler/<oyun>/ceviriler.json` dosyasına anında kaydedilir.
4. Oyuna şu dosyalar **eklenir** (hiçbir oyun dosyası değiştirilmez):
   - `game/zzzz_trceviri_yama.rpy` — çeviriyi oyun içinde uygulayan küçük betik
   - `game/trceviri/ceviri.json` — çeviriler
5. Menüler, kayıt ekranı, ayarlar gibi standart Ren'Py arayüz metinleri için Ren'Py'ın resmi Türkçe çevirileri
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
Sadece Python standart kütüphanesi kullanılır; ek paket kurulumu gerekmez.
