# Deneme Verisi Kontrol Listesi

Elinde MARC ve akademisyen verisi olan biri için: **neyi hangi biçimde** vermek
gerekir, ne gerekmez, ve neden.

---

## 0. Önce iki pratik şey

**Boyut.** TO-KAT'ın %30'u milyonlarca kayıttır ✗. Boru hattını sınamak için
**1.000 kayıt fazlasıyla yeter** ✓; performans için 100.000 ✓. Yüz binlerce kayıtla
başlamak, hatayı bulmayı kolaylaştırmaz, **zorlaştırır** ✗ — çünkü hangi kaydın
neden reddedildiğini göremezsiniz.

**Önerilen sıra:** 100 kayıt → boru hattı çalışıyor mu → 1.000 → 100.000 → gerisi.

**Hukuki taraf.** robots.txt otomatik erişimi yasaklıyor ✗ (o yüzden kazımayız ✓).
Kurumsal erişimle alınan veri ayrı bir şeydir ✓ — ama **anlaşmada bu verinin
kaynağı ve lisansı yazılmalı** ✓, çünkü `source_systems` tablosunda `license` ve
`attribution` **zorunlu** ✓ ve boş bırakılamaz.

---

## 1. MARC kayıtları — biçim önemli

| ✓ Doğru | ✗ Yanlış |
|---|---|
| `.mrc` (ISO 2709, ikili) | Ekran görüntüsü |
| `.xml` (MARCXML) | PDF |
| `.txt` (satır başına bir MARC) | Excel'e yapıştırılmış hâli |

**İçinde şu alanlar olmalı** — yoksa sahne çalışmaz:

| Alan | Ne | Neden gerekli |
|---|---|---|
| `245` | Başlık | Eser kaydı |
| `100` / `700` | Yazar | Kişi + akademisyen bağı |
| `260` / `264` | Yayın bilgisi | Manifestation (baskı) |
| **`020`** | ISBN | ISBN ajansı eşleşmesi |
| `041` | Dil | İfade |
| `650` | Konu | **Sahne 4** (Ayşe→Ayşe araması) |
| `082` / `050` | Yer numarası | Katalog |
| **`852`** | **Kütüphane + yer** | **Holding — "kimde var"** |
| **`876` / `877`** | **Nüsha** | **Barkod, raf, durum** |
| `310` / `362` | Süreli yayın | Cilt/sayı |

**Kritik:** `852` ve `876/877` **yoksa** sistem yalnızca eser ve baskı kaydı
oluşturur ✗, **hiçbir kütüphane görünmez** ✗ — yani gösterimin 1, 3 ve 5.
sahneleri çalışmaz ✗. TO-KAT verisi ağırlıklı olarak **holding** düzeyindedir ✓;
nüsha varsa çok daha iyi ✓.

---

## 2. Kütüphane kimlik listesi — **en çok atlanan ve en gerekli**

MARC'ta kütüphane bir **koddur** (`852$b`, örn. `TR-KKU`). O kodu çözecek liste
verilmezse `852` **anlamsız bir dizedir** ✗ ve ekranda kütüphane adı yerine
`TR-KKU` yazar ✗.

**Gereken CSV:**

```
kod, kurum_adı, şube_adı, şehir, kurum_türü
TR-KKU, Kırıkkale Üniversitesi, Merkez Kütüphane, Kırıkkale, universite
TR-HAC, Hacettepe Üniversitesi, Beytepe Kütüphanesi, Ankara, universite
```

`kurum_türü` = `universite | kamu | okul | ozel | arastirma`

**Bu liste olmadan `852` bir holding yaratamaz** ✗ — ve holding, yayınevi
ekranının saydığı şeydir ✗.

---

## 3. Akademisyen verisi

| ✓ Gerekli | Neden |
|---|---|
| **ORCID iD** | **Birleştirme anahtarı.** ORCID yoksa isim eşleştirmeye düşeriz ✗ ve "Ayşe Demir" iki kişi olur |
| Ad, soyad | Kişi kaydı |
| Kurum | Bağlantı |
| **Yayın listesi + DOI/ISBN** | Eserlere bağlanmanın yolu |

**ORCID olmadan bu iş yapılmaz** ✗. İsimle eşleştirme, aynı adı taşıyan iki
akademisyeni birleştirir ve bu **geri alması zor** bir hatadır ✗.

---

## 4. Altın küme — **en değerli ve en ucuz istek**

**20–30 kayıt**, bir kütüphaneci tarafından **elle doğrulanmış**: "bu kaydın
doğrusu şudur."

**Neden:** sistemin eşlemesinin **insan yargısıyla** aynı olduğunu sınamanın tek
yolu budur ✓. Aksi hâlde "çalışıyor" demek, "çökmüyor" demekten öteye gitmez ✗.

Bir kütüphaneci bunu **yarım günde** hazırlar ✓ ve karşılığı, tüm boru hattının
doğrulanabilir olmasıdır ✓.

---

## 5. Gerek olmayanlar — ve söylenmesi gerekenler

| ✗ İstemiyoruz | Neden |
|---|---|
| **Okuyucu / üye verisi** | Kişisel veri. Asla. |
| **Ödünç / iade kaydı** | Kimin ne okuduğu. Asla. |
| Ceza / borç kaydı | Kişisel veri |
| Sistem yedekleri | İhtiyaç yok |

**"Okuyucu verisi istemiyoruz" cümlesi baştan söylenmeli** ✓ — bir kütüphanenin
en hassas verisi budur ve ona dokunmadığımızı söylemek, geri kalan her şeyi
mümkün kılar ✓.

---

## 6. Test için gereken hesaplar

| Hesap | Ne yapar |
|---|---|
| `tenant_staff` | Kütüphane personeli — holding/nüsha yönetir |
| `publisher` | Yayınevi — "kitabım kimde" |
| `academician` | Akademisyen — ORCID profili |
| `isbn_agency` | Basılmamış yayın bildirir |
| `vendor` | E-betim + erişim linki |
| `platform` | Küratör |

**Bugün hiçbiri açılamıyor** ✗ — `create_user.py` kiracısız paydaş hesabı
yaratamıyor ve hesap kalkanı paydaş hesabını `admin` olarak reddediyor ✗. Bu
düzelmeden hiçbir gösterim sahnesi denenemez ✗.

---

## 7. Özet liste — ne istenecek

| # | Veri | Biçim | Zorunlu mu |
|---|---|---|---|
| 1 | MARC kayıtları | `.mrc` / MARCXML | ✓ |
| 2 | **Kütüphane kod listesi** | CSV | ✓ **şart** |
| 3 | Akademisyen + **ORCID** | CSV / JSON | ✓ |
| 4 | Altın küme (20–30 elle doğrulanmış kayıt) | CSV | ✓ çok değerli |
| 5 | Yayınevi kod listesi (`260$b`) | CSV | faydalı |
| 6 | Konu başlığı sözlüğü (kullanılanlar) | CSV | faydalı |
| 7 | Okuyucu / ödünç verisi | — | ✗ **asla** |

---

## 8. Veri gelmeden önce yapılacaklar

Veri geldiğinde **hemen işlenemez** ✗ — önce boru hattının çalışması gerekir:

| # | İş | Durum |
|---|---|---|
| **A** | Üç engeli kapat (hesap, kalkan, `POST /tenant/holdings` 500) | ✗ |
| **B** | `.mrc` ayrıştırıcı (ISO 2709) | ✗ |
| **C** | Yükleme ekranı + `ingestion_batches` kaydı | ✗ |
| **D** | Uyum raporu — kaç kayıt, hangi alan eşleşmedi | ✗ |
| **E** | **MARC dışa aktarma** | ✗ |

**E olmadan anlaşma konuşulmaz** ✓ — kurumun ilk sorusu "geri alabilir miyim"dir.

**Veri beklerken yapılabilecek en iyi şey A–E'yi yazmaktır** ✓. Veri elimizde
olduğunda boru hattı hazır olur ve aynı gün çalıştırabiliriz ✓.
