# Havuz ve Omurga — Vizyona Karşı Ölçüm

**Hedef:** bilgi taşıyan her türde kaynağı tek havuzda toplamak; herkesin
**kendisine tanınan yetki ve sahiplik** ölçüsünde işlem yapması; ve bunun **en son
teknolojik ve mesleki standartlara bağlı, sağlam bir omurga** üzerinde durması.

Bu belge hedefi **onaylamak için değil, ölçmek için** yazıldı ✓. Nerede zaten
karşılanıyor, nerede karşılanmıyor, ve "yüksekten uçmak" endişesinin ölçüdeki
karşılığı ne.

---

## 1. Omurga kaynak türüne **zaten** bağlı değil

En önemli tespit bu ✓:

> **FRBR/LRM kitap modeli değildir; kaynak modelidir.**

LRM; kitap ✓, makale ✓, süreli yayın ✓, görsel ✓, ses ✓, hareketli görüntü ✓,
veri seti ✓, üç boyutlu nesne ✓ — **hepsini** kapsayacak şekilde tasarlandı ✓.

Yani `Work → Expression → Manifestation → Item` zinciri **kitaplar için yazılmış
bir zincir değil** ✓. `Manifestation` **taşıyıcıyı** anlatır ✓ (`carrier_type` ✓);
kaynağın **türü** orada bir **değerdir** ✓, yapıyı değiştirmez ✗.

**Somut sonuç:** "her tür kaynak" hedefi, çoğu durumda **yeni tablo değil yeni
değer** demektir ✓ — ve bu, ölçülebilir bir farktır ✓.

---

## 2. Zaten karşılanan kısım

| Hedefin parçası | Bugün |
|---|---|
| Paylaşılan bilgi havuzu | ✅ `public` düzlemi (35 tablo) |
| Kimin neyi tuttuğu | ✅ `tenant` düzlemi, RLS ile |
| **Kim yetkili** | ✅ üç düzlem + roller + grant'ler, **veritabanında** |
| **Kim söyledi** (provenance) | ✅ `field_assertions`, `source_systems.trust_level` |
| Otorite kontrolü | ✅ `authority` + kuyruk |
| Kaynak türü ayrımı | ✅ `work_type`, `carrier_type` |
| Elektronik kaynak | ✅ `holding_type='electronic'`, `access_url` |
| Standartlar | ✅ MARC21 içe/**dışa**, OAI-PMH hedefi, DC planı |
| Eser/ifade/baskı/nüsha ayrımı | ✅ (RDA'nın veri modeli) |
| Türetilmiş her şey yeniden üretilebilir | ✅ arama indeksi + `reindex` |
| İşçi (otomatik akış) | ✅ `libraryhub-worker` |

**Bu liste, hedefin büyük kısmının *omurgada* değil *kullanımda* eksik olduğunu
gösteriyor** ✓.

---

## 3. Gerçek **yapısal** boşluk: süreli yayınlar

Tek bir tanesi yapısal ✓ — ve dürüst olmam gereken yer burası ✓.

**Bir kitap:** `Work → Expression → Manifestation` ✓ temiz ✓.

**Bir dergi:** öyle değil ✗. Bir dergi, **bir dizi sayıyı üretme planıdır** ✓.
`Cilt 12, Sayı 3, 2026` — bu bir **baskı değil** ✓, planın bir **örneğidir** ✓.

LRM bunu **kapsar** ✓ ama bizim şemamızda **karşılığı yok** ✗:

| Gereken | Bizde |
|---|---|
| Süreli yayın (plan) | ⚠️ `Work` olabilir ✓ ama numaralandırma yok ✗ |
| Cilt / sayı / yıl | ❌ |
| **Makale** (içindeki eser) | ⚠️ `Work` olabilir ✓ ama **hangi sayıda** bağı yok ✗ |
| Analitik bağ (makale → sayı → dergi) | ❌ |

**Bu, "kitap değil makale dergi" hedefinin tam kalbi** ✓ — ve **yeni varlık tipi
gerektirmiyor** ✓, **yeni bir *desen*** gerektiriyor ✓: süreli yayın ↔ sayı ↔
makale bağları için üç tablo ✓.

**Ve SOBİAD tam bu boşluğa oturuyor** ✓ — atıf dizini makale düzeyinde çalışır ✓.

---

## 4. Gerçek **kavramsal** boşluk: sahiplik

"Herkes kendisine tanınan yetki ve **sahiplik** durumuna göre" ✓ — *yetki* kısmı
çözülmüş ✓; *sahiplik* kısmı değil ✗.

Bugün bir kütüphane bir kaynağı **tutar** ✓ (`Holding` ✓) ama **hak sahibi** olduğu
kayıtlı değil ✗:

| Soru | Bugün |
|---|---|
| Bu kütüphane bu e-dergiye **abone mi**? | ⚠️ `access_url` var ✓, **hak** yok ✗ |
| Hangi yıllar kapsanıyor? | ❌ (`license_note` serbest metin ✗) |
| Kimler **erişebilir**? | ❌ |
| Hakkın **süresi** doldu mu? | ❌ |

**Kitapta sahiplik = nüsha ✓. E-kaynakta sahiplik = lisans ✓.** İkincisi için
**hak/eriişim katmanı** gerekli ✓ — ve bu, veritabanı şirketlerinin paydaş olmasının
da önkoşulu ✓ (KBART ✓).

---

## 5. "Yüksekten uçmak" endişesinin ölçüdeki karşılığı

Hedef yüksek değil ✗ — **sıralaması yanlış olabilir** ✓. Ayrım şu:

| Tür | Örnek | Maliyet |
|---|---|---|
| **Değer** genişlemesi | yeni `carrier_type`, yeni `work_type` | **sıfıra yakın** ✓ |
| **Desen** genişlemesi | süreli yayınlar, makale bağı | **üç tablo** ✓ |
| **Katman** genişlemesi | hak/erişim, KBART | **birkaç tablo** ✓ |
| **Yeniden yazım** | düz MARC'a dönmek, ikinci otorite tablosu | **omurgayı kırar** ✗ |

**İlk üçü hedefi büyütür** ✓; **dördüncüsü küçültür** ✗ — çünkü havuzun değeri
**tek doğruluk kaynağı** olmasıdır ✓.

---

## 6. Korunması gereken disiplin

*"En son teknolojik"* bir **gerekçe değil**, bir **araç** olmalı ✓. Bu projede her
yeni teknoloji bir **ölçülmüş tetikleyiciye** bağlandı ✓:

| Teknoloji | Tetikleyici | Bugün |
|---|---|---|
| Arama motoru (Elasticsearch vb.) | p95 > 500 ms | **18–130 ms** ✗ uzak |
| Bölümleme | ~50M satır | **79 satır** ✗ altı mertebe |
| Harici kuyruk (Kafka) | — | outbox + işçi **yetiyor** ✓ |

**Bu disiplin vizyonu zayıflatmaz** ✗ — **korur** ✓. 1000 kütüphaneli bir havuzda
**kararlılık bir özelliktir** ✓: bir kütüphane, kendi kataloğunun yerine koyduğu
sistemin **yarın da çalışacağından** emin olmak ister ✓.

**Ve ölçüm, "yüksekten uçmayı" engellemez** ✗ — yalnızca *hangi sırayla* uçulacağını
söyler ✓.

---

## 7. Vizyona karşı sıralama

| # | İş | Tür | Neden burada |
|---|---|---|---|
| 1 | **Süreli yayın deseni** (dergi → sayı → makale) | desen ✓ | "kitap değil" hedefinin kalbi |
| 2 | **Hak / erişim katmanı** ("sahiplik") | katman ✓ | e-kaynak ve sağlayıcı paydaşının önkoşulu |
| 3 | **Kuyruk ekranı + genel kelime gürültüsü** | cila ✓ | otorite kuyruğu şu an tepede yanıltıcı |
| 4 | **`cites` yüklemi** | değer ✓ | SOBİAD verisi **şema değiştirmeden** girer |
| 5 | **MARC dışa aktarma ucu** | eksik ✓ | anlaşmanın önkoşulu |
| 6 | **OAI-PMH + `oai_dc`** | katman ✓ | hasat edilebilirlik = ölçeklenen entegrasyon |

**Hiçbiri omurgayı yeniden yazmıyor** ✓ — ve 1 ile 2, hedefin gerçekten yeni olan
kısmı ✓.

---

## 8. Kapanış — dürüst cümle

Hedef, **mevcut omurganın kaldıramayacağı** bir şey istemiyor ✓. İstediği şey
**iki yeni desen** ✓ (süreli yayın ✓, hak ✓) ve **bir sürü yeni değer** ✓.

Yani endişe yerinde değil ✗ — **ama sıra önemli** ✓. Yanlış sıra, doğru hedefi
kırar ✗: otorite kontrolü olmadan çok türlü havuz, **kimin kim olduğu belirsiz** bir
havuz olur ✗; provenance olmadan çok kaynaklı havuz, **kaynağı bilinmeyen** bir havuz
olur ✗; ikisi de bu projede **önce** yapıldı ✓.

**Omurga hazır; sırada iki desen var.**
