# Veri Toplama Planı — Scrapy ve ötesi

**Kısa cevap:** Scrapy doğru araç, ama **ilk araç değil**. Kütüphane verisi için
API'ler ve standartlar var; onlar hem daha zengin hem daha kararlı hem de izin
sorunu taşımıyor. Scrapy'yi **API'si olmayan ve izin verilen** kaynaklar için
saklıyoruz.

---

## 0. Önce bir düzeltme

"Eksik kalan yapılar veri olmadığı için kurulamadı" doğru değil. Ölçüm şunu
söylüyor:

| Ne | Neden çalışmadı |
|---|---|
| Yayınevi raporu 0 kütüphane gösteriyor | `POST /tenant/holdings` **500** veriyor — kütüphane kitabı edinemiyor |
| Akademisyen ORCID bağlayamıyor | Hesap kalkanı, `role='admin'` taşıyan hesaba uygulama rolünün dokunmasını reddediyor |
| Yayınevi/akademisyen hesabı açılamıyor | `create_user.py` kiracısız paydaş hesabı yaratamıyor |

**Üçü de kod.** Veri eklemek bunların hiçbirini düzeltmez — 10.000 kitap eklesek
yayınevi ekranı yine 0 gösterir, çünkü gösterdiği şey **holding**'dir ve holding
`POST /tenant/holdings` ile açılır.

**Sıra bu yüzden şu:** üç engeli kapat → sonra veri. Tersi, veriyi boş bir
ekranda biriktirmek olur.

---

## 1. Kaynak hiyerarşisi — Scrapy nerede durur

| Öncelik | Kaynak | Ne verir | Neden bu sırada |
|---|---|---|---|
| **1** | **MARC** (ILS dışa aktarımı) | Bir kütüphanenin **tüm** koleksiyonu | Yordam, Koha, Sierra hepsi verir. Bir kütüphaneyi bağlamanın en kısa yolu |
| **2** | **OAI-PMH** | Toplu üst veri, artımlı (`from`/`until`) | Kütüphane/müze/arşiv dünyasının **toplu hasat standardı**. Sayfalama, silme bildirimi, tarih aralığı hazır |
| **3** | **SRU / Z39.50** | Tek tek veya sorguyla çekme | Canlı katalog sorgusu. `KKU-123456` gibi bir numaradan kayda gitmek |
| **4** | **ORCID API** | Akademisyenin kendi yayın listesi | Akademisyen kendi kaydını güncel tutar. Açık API |
| **5** | **Crossref / OpenAlex** | DOI, yayın künyesi, atıf | Yayınevi ve akademisyen verisini zenginleştirir |
| **6** | **OpenLibrary / Google Books** | ISBN → künye | ISBN'i olan ama künyesi eksik kayıtları tamamlar |
| **7** | **Scrapy** | **API'si olmayan, izin verilen** kaynak | Yayınevinin kendi kataloğu, kamuya açık OPAC (robots.txt'e uyarak) |

**Neden Scrapy son sırada:** kazıma kırılgandır (sayfa değişince bozulur ✗),
hukuken tartışmalı olabilir ✗, ve çoğu durumda zaten bir API varken gereksizdir ✗.
Ama **gerçekten API'si olmayan** kaynaklar var ve orada doğru araçtır ✓.

---

## 2. Altyapı zaten hazır

Bu iş için **yeni tablo gerekmiyor.** Aşama 1'de kurulan üç tablo tam bunun için
var:

```
source_systems      kim getiriyor, ne kadar güvenilir (trust_level)
source_records      ham yük (payload) — henüz yorumlanmamış
ingestion_batches   bir hasat koşusu: ne zaman, kaç kayıt, ne oldu
```

Yani bir Scrapy spider'ının işi **`source_records`'a yazmak** ✓ — yorumlama,
eşleme ve çakışma çözümü zaten var olan hattın işi ✓. Bu ayrım kritik: kazıyıcı
**ham veri** getirir, katalog **kanonik** veriyi kurar ✓.

---

## 3. Scrapy ile ilk adım — somut

### 3.1 Nereye yazılır

```
backend/ingest/
    __init__.py
    settings.py          robots.txt'e uy, gecikme, eşzamanlılık, retry
    pipelines.py         SourceRecordPipeline -> public.source_records
    items.py             RawRecord(url, payload, fetched_at, licence)
    spiders/
        opac.py          kamuya açık OPAC (izin verilen)
        publisher.py     yayınevinin kendi katalog sayfaları
```

### 3.2 Spider'ın sözleşmesi

Bir spider **tek bir şey** yapar: `source_systems.code` ile tanımlı bir kaynak için
`source_records` satırı üretir. Katalogla konuşmaz, `works` yazmaz, karar vermez.

```python
class OpacSpider(scrapy.Spider):
    name = "opac"
    # robots.txt'e uyulur; izin verilmeyen yol taranmaz.
    custom_settings = {
        "ROBOTSTXT_OBEY": True,
        "DOWNLOAD_DELAY": 1.0,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "USER_AGENT": "LibraryHubBot/1.0 (+https://.../bot)",
    }
```

### 3.3 Politika — pazarlık edilemez

1. **robots.txt'e uyulur.** `ROBOTSTXT_OBEY = True`, istisnasız.
2. **Kimlik açık.** User-Agent iletişim adresi taşır; gizlenen bir bot değiliz.
3. **Yavaş.** Varsayılan 1 sn gecikme, alan adı başına 2 eşzamanlı istek. Bir
   kütüphanenin OPAC'ı bizim yüzümüzden yavaşlamamalı.
4. **Lisans kaydedilir.** Her `source_systems` satırında `license` ve
   `attribution` var ve **dolu olmak zorunda** ✓. Kaynağı belirtmeden veri almayız.
5. **İzin belgesiz ticari veri kazınmaz.** Bir veritabanı şirketinin ürünü zaten
   API verir; onu kazımak lisans ihlalidir.
6. **Kişisel veri kazınmaz.** Okuyucu/ödünç verisi hedef değildir.

---

## 4. Gerçekten öncelikli olan: MARC

Scrapy'den önce yapılacak şey **MARC ayrıştırıcı** ✓ — çünkü:

- Bir kütüphane verisini **tek dosyada** verir (`.mrc` / MARCXML)
- MARC21 dünyada ortak ✓ → Yordam, Koha, Sierra, Alma hepsi konuşur
- Eşleme nettir: `245` → Work başlığı, `100/700` → kişi, `260/264` → Manifestation,
  `020` → ISBN, `852` → **Holding**, `876/877` → **Item**
- Ve bu, **1000 kütüphanenin katılım yoludur** ✓

`source_records` şeması MARCXML'i ham olarak taşımaya zaten uygun ✓. Eksik olan
ayrıştırıcı ve eşleme ✓ — bir Scrapy spider'ı değil.

---

## 5. Sıra

| # | İş | Neden bu sırada |
|---|---|---|
| **A** | `create_user.py` kiracısız paydaş hesabı açsın | Paydaş hesapları olmadan hiçbir çalışma alanı denenemez |
| **B** | Paydaş hesabı `admin` olmasın (kalkan kuralı) | ORCID bağlama bunu bekliyor |
| **C** | `POST /tenant/holdings` 500'ü çöz | Yayınevi raporunu canlı veriyle kanıtlamanın tek yolu |
| **D** | **MARC ayrıştırıcı** + `ingestion` hattı | Bir kütüphanenin gerçek koleksiyonu; Yordam'dan geçiş |
| **E** | **OAI-PMH hasat edici** | Artımlı, standart, izin sorunu yok |
| **F** | **ORCID çekici** | Akademisyen profilini kendi kaydından doldurur |
| **G** | **Scrapy** | API'si olmayan, izin verilen kaynaklar |

**A, B, C kod.** Veri toplama planı **D**'den başlar ve Scrapy **G**'de gelir.
Scrapy'yi başa almak, veriyi açılamayan ekranların arkasında biriktirmek olurdu.

---

## 7. TO-KAT — ölçüldü, ve cevap net

`https://toplukatalog.tr/robots.txt`:

```
User-agent: *
Disallow: /
```

**Tüm otomatik erişim yasak.** İstisnasız, makine tarafından okunabilir biçimde,
ve kullanıcı aracısı ayrımı yapmadan. Bu, planın 3.3'teki birinci kuralının ilk
sınavı ve cevap **hayır**: kazımayız.

Bu bir teknik ayrıntı değil. Site, otomatik istemcilere "gelmeyin" diyor; bunu
aşmak için yol aramak, kendi yazdığımız politikayı ilk fırsatta çiğnemek olurdu.

### Doğru yol: protokol, kazıma değil

TO-KAT bir kamu kurumunun (Kültür ve Turizm Bakanlığı) hizmetidir. Veri paylaşımı
için **anlaşma** yolu vardır ve o yoldan:
- bir **OAI-PMH** uç noktası,
- bir **SRU / Z39.50** hedefi,
- ya da toplu **MARC** dışa aktarımı

istenebilir. Bunlar zaten var olabilir de olmayabilir de — **bilmiyoruz**, ve
öğrenmenin yolu robots.txt'i aşmak değil, sormaktır.

### Ama asıl soru bu değil

**TO-KAT zaten Türkiye'nin toplu katalogudur.** Kullanıcının başlangıçtaki hedefi
"1000 kütüphanenin toplu kataloğu" idi ve **o şey halihazırda var.**

Yani bu platformun değeri "bir toplu katalog daha" olamaz ✗. Olabileceği şey,
TO-KAT'ın **yapmadığı** katmandır:

| TO-KAT | Bu platform |
|---|---|
| Holding düzeyi ("hangi kütüphanede var") | **Nüsha düzeyi** (barkod, raf, durum) |
| Arama arayüzü | **Beş paydaş için çalışma alanı** |
| — | **Yayınevi**: "kitabım hangi kütüphanelerde" |
| — | **Akademisyen**: ORCID'e bağlı profil |
| — | **ISBN ajansı**: basılmamış yayın akışı |
| — | **Sağlayıcı**: elektronik üsü veri + erişim linki |
| — | **Provenance**: hangi alanı kim iddia etti |
| Künye kopyalama | **Manifestation / Holding / Item ayrımı** |

**Karar sizin:** ya bu farklılaşma üstüne gidilir, ya TO-KAT ile entegrasyon
hedeflenir (o zaman bu platform bir *üst katman* olur), ya da ikisi birden.
Ama hangisi olursa olsun **robots.txt'e uyulur** ve veri **protokolle** alınır.

---

## 9. MARC nereden alınır — kaynak kaynak

MARC bir **dosya biçimidir**, bir site değil. Onu elinde tutan taraf onu verebilir.
Beş gerçek kaynak var ve **hiçbiri kazıma gerektirmiyor.**

### 9.1 Kütüphanenin kendi sistemi — **birinci yol**

Her Türk üniversite kütüphanesi bir ILS çalıştırır: Yordam, Koha, Sierra, Alma,
Milennium, IDEA, Milas, NetKütüphane. **Hepsi MARC dışa aktarır** — çünkü MARC o
sistemlerin çekirdek veri biçimidir, süs değil.

| Biçim | Ne | Nerede |
|---|---|---|
| `.mrc` | **ISO 2709** ikili MARC21 | Tek dosya, tüm koleksiyon |
| MARCXML | Aynı veri, XML | Tek dosya, okunması kolay |

**İzin sorunu yok**: veri kütüphanenin kendisinin ✓. Yapılacak şey istemek ✓.

Bu, **1000 kütüphanenin katılım yoludur** ✓ ve ilk uygulanacak şey budur ✓:
kütüphaneci `.mrc` dosyasını yükler, platform ayrıştırır.

### 9.2 Z39.50 ve SRU — canlı kopya kataloglama

Kütüphanecilerin hâlihazırda kullandığı yöntem: kaydı **yazmak yerine çekmek** ✓.
Türkiye'deki birçok üniversite kütüphanesi bir Z39.50 hedefi yayınlar.

**SRU önce**, çünkü HTTP üzerinden çalışır ✓; Z39.50 ikili bir protokoldür ✗ ve
uygulaması kat kat pahalıdır ✗.

### 9.3 Açık kaynaklar — izin gerekmez

| Kaynak | Ne verir | Biçim |
|---|---|---|
| **OpenLibrary** | Toplu dumps | MARC + JSON, ücretsiz |
| **Library of Congress** | SRU + toplu indirme | MARC21 |
| **DNB** (Alman Millî Kütüphanesi) | Toplu dumps | MARC21, ücretsiz |
| **BnF** (Fransız Millî Kütüphanesi) | SRU | MARC |
| **K10plus / GBV** | SRU + dumps | MARC21 |
| **OpenAlex / Crossref** | DOI, künye, atıf | JSON (MARC değil) |

Bunlar **zenginleştirme** içindir ✓ — bir Türkçe eserin künyesini tamamlamak ✓ —
ama bir kütüphanenin koleksiyonunu temsil etmez ✗.

**OCLC WorldCat ve SkyRiver hariç** ✗: ikisi de lisanslı ve ücretli ✗.

### 9.4 Sağlayıcılar — **KBART**, MARC değil

Veritabanı şirketlerinin standardı **KBART**'tır ✓ (Knowledge Bases and Related
Tools ✓): hangi e-dergi, hangi yıl aralığı, hangi URL ✓. MARC'tan farklı bir şey
ve **doğru olan o** ✓ — bir e-dergi koleksiyonunu MARC olarak modellemek yanlış
olurdu ✓.

### 9.5 Kurumsal anlaşmalar

| Kurum | Ne |
|---|---|
| **ANKOS** | Anadolu Üniversite Kütüphaneleri Konsorsiyumu — **doğru muhatap** ✓ |
| **ÜNAK** | Üniversite ve Araştırma Kütüphanecileri Derneği |
| **Kültür ve Turizm Bakanlığı** | TO-KAT'ın sahibi |
| **ISBN Ajansı** | Basılmamış yayın verisi |

TO-KAT için yol **anlaşmadır**, kazıma değil ✓ (§7).

---

## 10. Uygulanacak sıra — MARC tarafı

1. **`.mrc` ayrıştırıcı** (ISO 2709) — ikili biçim, ~200 satır, kütüphane yok
2. **MARCXML ayrıştırıcı** — aynı veri, `lxml` ile
3. **`ingestion` ucuna yükleme** — `source_records`'a ham yaz, `ingestion_batches`'e
   koşuyu kaydet
4. **Eşleme** — 245→Work, 100/700→kişi, 264→Manifestation, 020→ISBN,
   **852→Holding**, **876/877→Item**
5. **Rapor** — kaç kayıt alındı, kaçı eşleşti, kaçı reddedildi **ve neden**

Beşinci adım atlanamaz ✓: 500.000 kayıtlık bir dosyada "42.318 kayıt işlendi"
demek yeterli değildir; hangi alan eşleşmedi bilinmeden veri **yarım** kalır ve
yarım olduğu görünmez ✗.

---

## 11. Bugün yapılabilecek en küçük gerçek adım

**Elimizdeki Yordam dosyası bunun için kullanılamaz** — ölçüldü: 33,84 MB'ta şema
adları açıkta değil, sıkıştırılmış/kapalı ✗.

Yapılabilecek şey: **Yordam'dan MARC dışa aktarımı almak** (kendi arayüzünden, bir
`.mrc` dosyası) ve onu `source_records`'a yükleyen ayrıştırıcıyı yazmak. O zaman
platform **gerçek bir kütüphanenin gerçek koleksiyonunu** taşır ve yayınevi ekranı
ilk kez gerçek sayı gösterir.
