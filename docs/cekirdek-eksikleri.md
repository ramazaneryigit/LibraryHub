# Çekirdeğe Eklenebilecekler

Kurulu yapının üstüne ne eklenebileceği değil, **çekirdekte neyin eksik olduğu**.
Her madde bir özellik değil bir **boşluk**; ve her biri bugün ölçülebilir.

---

## Katman 1 — Yapısal boşluklar

### 1. Bir işçi (worker) ve zamanlayıcı — **en büyük boşluk**

Outbox var ✓, indeksleyici var ✓, `reindex` var ✓ — ama **hepsi elle
çalıştırılıyor** ✗. Bugün bir kütüphane holding eklediğinde arama indeksi
**kendiliğinden güncellenmiyor** ✗; `reindex.py --consume` çalıştıran biri gerekiyor.

Bunu bu oturumda yaşadım: ISBN ile iki yayın bildirdim, **arama bulmadı** ✗, çünkü
indeksleyici çalışmamıştı.

**Ne gerekir:** outbox'ı düzenli tüketen bir süreç. Ayrıca ileride: hasat
işlerinin zamanlanması, e-posta doğrulama kuyruğu, periyodik `reindex`.

**Neden çekirdek:** veri **yazıldığı anda değil, birinin script çalıştırdığı anda**
tutarlı hâle geliyor ✗. Bu bir gecikme değil, bir **belirsizlik**.

---

### 2. Otorite kontrolü ve tekilleştirme — **toplu katalog için en kritik**

1000 kütüphane aynı yazarı **40 farklı yazımla** getirir: `Dostoyevski, Fyodor` ·
`Dostoevsky, Fyodor` · `Fyodor Dostoyevski` · `Достоевский, Фёдор` ✓.

Bugün `reconciliation` ve `entity_merges` var ✓ — ama **otomatik eşleştirme yok** ✗.
Yani 40 kayıt gelir, 40 kişi olur ✗.

**Ne gerekir:** normalize edilmiş ad + doğum/ölüm yılı + ORCID/ISBN ile
**aday üretme** ve **güven eşiğine göre** otomatik birleştirme; eşiğin altındakiler
insan kuyruğuna ✓.

**Neden çekirdek:** bu çözülmezse katalog, kütüphanelerin kendi kataloglarından
**daha kötü** olur ✗ — çünkü en azından her kütüphane kendi içinde tutarlıdır ✗.

---

### 3. Alımın tekrarsız olması (idempotency)

`source_records` var ✓ ama "aynı dosya iki kez yüklenirse" davranışı **tanımlı
değil** ✗. Bir kütüphane aylık güncelleme gönderir; ikinci ayında ilk ayın
kayıtları da gelir ✓.

**Ne gerekir:** `(source_system_id, external_id)` üzerinde tekillik + "görülen
kayıt" işareti. Görülmeyenler **silinmiş adayı** olur, hemen silinmez ✓.

**Neden çekirdek:** yoksa her güncelleme katalogu **çoğaltır** ✗.

---

### 4. Kendi OAI-PMH ucumuzu yayınlamak

Standartları **tüketmeyi** planlıyoruz ✓ (OAI-PMH, SRU, MARC ✓). Ama ekosistemin
parçası olmak **yayınlamayı** da gerektirir ✓.

**Ne gerekir:** `/oai` uç noktası — `Identify`, `ListRecords`, `GetRecord`,
`ListSets`, artımlı `from`/`until` ✓. Ve bir `/sru` hedefi ✓.

**Neden çekirdek:** 1000 kütüphane verisini **elle dosya yükleyerek** güncellemez ✗.
Hasat edilebilir olmak, entegrasyonun tek ölçeklenebilir yoludur ✓. Ayrıca
TO-KAT/ANKOS görüşmesinde en güçlü argümanlardan biri: *"bizden de hasat
edebilirsiniz"* ✓.

---

### 5. Aramada yüzeyleme (facet) ve sayfalama — API TAMAMLANDI

`GET /search` artık `total`, `next_cursor`, `has_more` ve facet sayaçları döndürür.
Keyset cursor eşleşme skoru ve work kimliğine göre kararlıdır; sorgu veya
filtreler değiştiğinde yeniden kullanılamaz. Mevcut `count`, `limit` ve
`truncated` alanları geriye uyumluluk için korunur.

Desteklenen filtreler ve facet grupları: `work_type`, `language`, `year`,
`library`, `subject`. Facet sayaçları sorgunun tam eşleşme kümesinden hesaplanır;
cursor yalnızca filtrelenmiş sonuç sayfasını ilerletir.

**Kalan:** kamu kataloğunda facet seçim kontrolleri ve sonraki sayfayı yükleyen
arayüz. API ile görsel yüzeyleme ayrı adımlar olarak tutulur.

---

## Katman 2 — Hesap verebilirlik ve işletme

### 6. **Kim** değiştirdi — değer değil, eylem

Outbox **neyin** değiştiğini yazıyor ✓; `field_assertions` **kimin iddia ettiğini**
tutuyor ✓. Ama doğrudan yazmalarda (kabul edilen öneri ✓) **eylemi yapan** kayıtlı
değil ✗.

**Ne gerekir:** yazma yollarında aktör + gerekçe. Paylaşılan bir kayıtta
*"bunu kim değiştirdi"* bir kolaylık değil, **hesap verebilirlik** ✓.

---

### 7. Silme ve geri çekme anlamı

Bir kütüphane holdingini çektiğinde ne olur ✗? Bir eser birleştirildiğinde ✗?
`entity_merges` var ✓ ama **holding geri çekme** tanımlı değil ✗.

**Ne gerekir:** mezar taşı (tombstone) — kayıt silinmez, **görünmez** olur ve
OAI-PMH bunu `deleted` olarak bildirir ✓.

**Neden çekirdek:** silmek, hasat edilen tarafta **sessiz tutarsızlık** yaratır ✗.

---

### 8. Yedekleme, geri yükleme, felaket kurtarma

1000 kütüphane bu katalogdan **kendi kaydını** okuyacak ✓. Yedeği alınmamış bir
katalog, bir **tek nokta arızasıdır** ✗.

**Ne gerekir:** düzenli yedek ✓, geri yükleme **denenmiş** ✓ (denenmemiş yedek
yedek değildir ✗), ve `reindex` zaten tam yeniden üretim veriyor ✓ — bu büyük
avantaj ✓.

---

### 9. Gözlemlenebilirlik

Bugün `/health` var ✓, o kadar ✗. 1000 kütüphanede *"arama yavaşladı"* nasıl
görülür ✗?

**Ne gerekir:** yapılandırılmış günlük ✓, ölçümler (istek süresi, outbox gecikmesi,
eşleşmeyen kayıt oranı ✓), ve uyarılar.

**Özellikle:** **outbox gecikmesi** bir ölçüm olmalı ✓ — bir kütüphane yazdı, arama
ne zaman gördü ✓. Bugün bu süre **tanımsız** ✗.

---

### 10. Hız sınırlama ve kötüye kullanım koruması

Kamuya açık bir katalog kazınır ✓ ve dövülür ✓.

**Ne gerekir:** IP/kimlik başına hız sınırı, sorgu maliyeti sınırı (çok geniş
`LIKE` ✓), ve bot politikası ✓.

---

## Katman 3 — Cila

| # | Ne | Neden sonra |
|---|---|---|
| 11 | Çok dillilik (TR/EN) | Ulusal platform için gerekli olacak, acil değil |
| 12 | Erişilebilirlik denetimi (WCAG) | Kamu hizmeti; ama önce çalışması gerek |
| 13 | API sürümleme ve kullanımdan kaldırma politikası | `/api/v1` var ✓, politika yok |
| 14 | Şema dokümantasyonu (OpenAPI açıklamaları) | Var ✓, zenginleştirilebilir |

---

## Ama önce: üç engel

Yukarıdakilerin **hiçbiri**, aşağıdaki üç şey düzelmeden denenemez ✗:

| # | Engel |
|---|---|
| **A** | `create_user.py` kiracısız paydaş hesabı açamıyor ✗ |
| **B** | Hesap kalkanı paydaş hesabını `admin` olarak reddediyor ✗ |
| **C** | **`POST /tenant/holdings` 500 veriyor** ✗ |

Ve MARC boru hattı (ayrıştırıcı ✓, yükleme ✓, uyum raporu ✓, **dışa aktarma** ✓).

**Gerekçe:** Katman 1'in tamamı **veri akışıyla** ilgili ✓. Veri giremiyorsa
otorite kontrolünün, idempotency'nin, facet'lerin **sınanacak bir şeyi olmaz** ✗.

---

## Önerilen sıra

| Sıra | İş | Neden burada |
|---|---|---|
| 1 | **A, B, C** + MARC içe/dışa | Her şeyin önkoşulu |
| 2 | **İşçi + outbox tüketimi** | Yazma ile görünürlük arasındaki belirsizliği kaldırır |
| 3 | **Alım idempotency** | MARC verisi gelmeden önce olmalı |
| 4 | **Otorite kontrolü** | MARC verisi **ile birlikte** gerekir, sonra değil |
| 5 | **Facet + sayfalama** | İndeks hazır ✓, ucuz ✓ |
| 6 | **OAI-PMH sunucusu** | Entegrasyonun ölçeklenebilir yolu |
| 7 | Gözlemlenebilirlik, hız sınırı | Yük gelmeden önce |
| 8 | Yedekleme/DR, silme anlamı | Üretim öncesi |
| 9 | Cila | En son |

**4 numara kritik:** otorite kontrolü MARC verisinden **sonra** yapılırsa, 40
yazımla gelmiş 40 kişiyi **elle** birleştirmek gerekir ✗. Veriyle **birlikte**
kurulursa, ilk alımda doğru birleşir ✓.
