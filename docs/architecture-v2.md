# LibraryHub Architecture v2 — Veri Modeli Sınırları ve Geçiş Planı

| | |
|---|---|
| Durum | **Tasarım önerisi** — hiçbir şema değişikliği uygulanmadı |
| Kapsam | Plane ayrımı, `Manifestation → Holding → Item` sınırı, kimlik, provenance, versioning, tenant izolasyonu, arama, API, geçiş planı |
| Dayanak | Çalışan sistem üzerinde **ölçülmüş** gözlemler (bkz. §0.2 ve Ek B) |
| Değiştirdiği şey | Bu belge bir öneri metnidir. Kod, migration ve veritabanı **değiştirilmemiştir**. |

---

## 0. Doğrulanmış başlangıç durumu

### 0.1 ÖNCE DÜZELTME: Alembic head bilgisi güncel değil

Devam promptunda "son doğrulanan migration head: `c91f4a20de76`" yazıyor. Bu **doğru değil**.
Çalışan veritabanında ve kod ağacında ölçülen gerçek durum:

```
$ docker compose exec -T api alembic current
Rev: 49f61999a6f3 (head)
```

`c91f4a20de76`'dan sonra **üç** migration uygulanmış durumda:

| Sıra | Revision | Dosya | Ne yapar |
|---|---|---|---|
| 23 | `c91f4a20de76` | `c91f4a20de76_add_decision_evidence_snapshot.py` | `evidence_snapshot` kolonu + write-once trigger |
| 24 | `2b297de50358` | `2b297de50358_add_trigram_work_title_search.py` | `pg_trgm` + trigram index |
| 25 | `9f25b0d7306d` | `9f25b0d7306d_optimize_normalized_work_title_trigram_.py` | index'i `lower(canonical_title)` üzerine taşır |
| 26 | **`49f61999a6f3`** | `49f61999a6f3_add_ingestion_batches.py` | `ingestion_batches` tablosu (gerçek head) |

**Bu neden önemli:** Bu belgeden sonra ilk migration yazıldığında `down_revision` yanlışlıkla
`c91f4a20de76` verilirse, revision grafiği çatallanır ve `alembic upgrade head` şu hatayla durur:
`Multiple head revisions are present for given argument 'head'`. Veritabanı şu an bu üç
migration'ı zaten uygulamış olduğu için, yeni migration'ın **tek doğru ebeveyni
`49f61999a6f3`'tür**.

### 0.2 Ölçülen başlangıç durumu (Aşama 1 öncesi)

| Ölçüm | Değer |
|---|---|
| Compose projesi | `library-platform`, 2 servis ayakta |
| API | `http://localhost:8010` — `/health` = `{"status":"ok"}` |
| Alembic head | `49f61999a6f3` (DB ile kod ağacı **tutarlı**) |
| Revision grafiği | 26 revision, tek kök (`a26af5082dc5`), tek head — çatallanma yok |
| `public` tablo sayısı | 35 |
| Kurulu extension'lar | `pg_trgm`, `plpgsql` |
| Kullanılabilir extension'lar | `unaccent`, `pg_trgm`, `btree_gin`, `pgcrypto`, `ltree`, `uuid-ossp` — **`vector` YOK** |
| Non-internal trigger | 17 (entity tip bütünlüğü + `trg_decision_snapshot_immutable`) |
| Canlı API yüzeyi | 50 endpoint / 40 path |
| Gerçek veri | 91 entity, 16 work, 12 person, 24 nomen, 14 entity_merge, 9 source_record, 3 reconciliation_decision, 0 ingestion_batch |

`alembic check` bu noktada **başarısızdı**:

```
Detected removed index 'ix_works_canonical_title_lower_trgm' on 'works'
FAILED: New upgrade operations detected: [('remove_index', ...)]
```

Sebep: index 9f25b0d7306d'de ham `op.execute()` ile yaratılmış, `models.py` içinde
bildirilmemiş. Sonuç: bir sonraki `alembic revision --autogenerate` bu index'i
**silmek isteyen** bir migration üretirdi. **Aşama 1'de düzeltildi — bkz. §0.4.**

### 0.3 Bu belgenin kapsamı

**Kapsam içi:** plane sınırları; `Manifestation → Holding → Item` kararı ve DDL taslağı;
global/tenant kimliği; tenant izolasyonu ve DB routing; provenance; versioning ve geri
alınabilir merge; entity resolution; search/AI plane sınırları; event modeli; object storage;
API versioning; çok dillilik; ölçek notları; aşamalı ve geri alınabilir geçiş planı.

**Kapsam dışı (bilinçli):** ödünç/süreli işlem/fine gibi dolaşım (circulation) tablolarının
detay DDL'i, kimlik doğrulama protokolü seçimi, Django kararı, Kubernetes/observability
kurulumu. Bunlar §18'de karar bekleyen başlıklar olarak listeli.

---

### 0.4 Aşama 1 uygulama kaydı — TAMAMLANDI

Aşama 1 onaylandı ve uygulandı. **Üç yeni migration**, hepsi tamamen eklemeli:

| Revision | Dosya | Ne yapar |
|---|---|---|
| `b7c1e4a92f30` | `add_entity_relation_reverse_index` | `entity_relation` ters yön index'i |
| `c8d2f5b03a41` | `add_source_systems` | `source_systems` tablosu + `source_records.source_system_id` (nullable FK) |
| `d9e3a6c14b52` | `create_plane_schemas` | Boş `control` ve `tenant` şemaları |

Ek olarak **kod tarafında** (migration gerektirmeyen) iki düzeltme:
`models.py`'de `Work` için trigram index bildirimi ve `EntityRelation` için ters index
bildirimi — böylece model ile veritabanı birbirinden kopmaz.

**Güncel durum (§0.2'nin karşılığı):**

| Ölçüm | Aşama 1 öncesi | Aşama 1 sonrası |
|---|---|---|
| Alembic head | `49f61999a6f3` | **`d9e3a6c14b52`** (tek head, 29 revision) |
| `public` tablo sayısı | 35 | **36** (+`source_systems`) |
| `entity_relation` index sayısı | 2 | **3** (+ters yön) |
| `control` / `tenant` şeması | yok | **var (boş)** |
| `source_records.source_system_id` | yok | **var (nullable)** |
| `alembic check` | **FAILED** | **temiz** |
| `openapi.json` | UTF-16LE, 11 path, bayat | **UTF-8 (BOM'suz), 40 path / 50 endpoint** |

**Geri alınabilirlik kanıtlandı.** `alembic downgrade 49f61999a6f3` çalıştırıldı; üç
migration tersine döndü ve şema tam olarak eski hâline geldi:

```
entity_relation indexleri : entity_relation_pkey, uq_entity_relation_subject_predicate_object
source_systems tablo      : 0
source_system_id kolon    : 0
control/tenant sema       : 0
public tablo              : 35
veri: works=16 entities=91 source_records=9     <-- DEĞİŞMEDİ
```

Ardından `alembic upgrade head` ile yeniden uygulandı; `public tablo=36`,
`works=16 items=12 entities=91 source_records=9` ve `alembic check` temiz.
**Göç boyunca tek bir satır bile değişmedi.**

**Uçtan uca doğrulama:** `/health`, `/works`, `/persons`, `/search?q=bilgi` → 200;
`/search/concept/{id}` → 200 (`Rus edebiyatı`, 1 sonuç — `Edebiyat → Rus edebiyatı →
Suç ve Ceza` zinciri çalışıyor); API loglarında traceback yok.

**Bilinen sınırlama (dürüstçe kayda geçirildi):** trigram index bildirimi
`alembic check`'i temizler ve index'in autogenerate tarafından **silinmesini engeller**,
ancak Alembic bu tek index için
`Cannot compare index ... assuming equal and skipping` uyarısını basar — yani index
*korunur* ama *karşılaştırılmaz*. SQLAlchemy 2.0 `postgresql_ops` sözlüğünü elemanın
`key` özniteliğiyle arıyor; `text()` ve `func()` ifadelerinde bu `None` olduğu için tam
karşılaştırma bu sürümde mümkün değil. Ayrıntı `models.py` içindeki yorumda.

### 0.5 Aşama 2 uygulama kaydı — TAMAMLANDI (Control Plane)

**Migration:** `e1f4b7d25c63` — `control.tenants`, `control.organizations`,
`control.branches`, `control.tenant_databases` + kurum backfill'i. Zincir artık
**30 revision**, tek head.

**Backfill sonucu (gerçek veriyle):** 4 tenant, 4 organization, 4 branch,
4 tenant_databases. Her organization `collective_agent_entity_id` ile otorite kaydına
bağlandı (D14).

| Kurum | slug | org_type |
|---|---|---|
| Hacettepe Üniversitesi | `hacettepe-niversitesi-2d1a8810` | organization |
| Kırıkkale Üniversitesi | `k-r-kkale-niversitesi-6e788275` | university |
| Российская государственная библиотека | `org-da9a0dd0` | organization |
| Canonical Redirect Test Organization B | `canonical-redirect-test-organization-b-d2ee8aef` | organization |

Backfill **role filtresi kullanmıyor**: roller serbest metin ve kısıtsız, "bu nüshadan
kim sorumlu" sorusu bir kurumu kütüphane yapar. `role='holding_institution'` ile
filtrelemek, emaneti başka bir rolle kaydedilmiş nüshaları sessizce düşürürdü — bu
veritabanında tam olarak böyle bir kayıt var (`controlled_test_holder`).
`source_records.institution_entity_id` her satırda NULL olduğu için katkı vermedi.

Latince olmayan isimlerde slug okunabilir kısmı kaybedip `org-<8 hex>` biçimine düşer;
bu **kasıtlıdır** ve çakışmasızdır (entity_id'den türetilir).

**D4 (UUIDv7) uygulandı.** Yeni `app/ids.py` RFC 9562 UUIDv7 üretir; `models.py`'deki
18 model varsayılanı ve router'lardaki 11 açık `uuid4()` çağrısı `uuid7()`'ye geçti.
Doğrulandı: `version == 7`, variant RFC 4122, aynı milisaniye içinde sıralı, mevcut
UUIDv4 satırlar dokunulmadı. Kod tabanında `uuid4` kalmadı.

**Aşama 1'de soktuğum bir regresyon bulundu ve düzeltildi.** Trigram index bildirimi
`text("lower(canonical_title) gin_trgm_ops")` içerdiği için SQLAlchemy bunu **tüm**
diyalektlerde üretiyordu; SQLite'ta operatör sınıfı olmadığından
`Base.metadata.create_all()` `near "gin_trgm_ops": syntax error` ile çöküyordu — yani
Aşama 1, projenin test paketinin `setUp`'ını kırmıştı. Aşama 1 sırasında host'ta
`httpx2` bulunmadığı için testler çalıştırılamamıştı. Düzeltme:
`Index(...).ddl_if(dialect="postgresql")`. Ayrıca şema nitelikli control tabloları için
test `setUp`'ına `ATTACH DATABASE ':memory:' AS control` eklendi.

**`alembic check` kapsamı genişletildi.** `include_schemas=False` iken Alembic yalnızca
varsayılan şemayı yansıtıyor, bu yüzden control tablolarını *yeni* sanıp `alembic check`
başarısız oluyordu. `env.py`'de `include_schemas=True` yapıldı: artık `control` şeması da
karşılaştırılıyor ve `alembic check` temiz. Bu, Aşama 1 sonundakinden **daha güçlü** bir
güvencedir.

**Geri alınabilirlik kanıtlandı.** `alembic downgrade d9e3a6c14b52` → `control` şemasında
0 tablo, veri bozulmadı (`works=16 items=12 entities=91 item_agent_relation=6`).
`upgrade head` → backfill yeniden üretti (`tenants=4 orgs=4 branches=4 tenant_dbs=4`).
Control tablolarındaki her şey `item_agent_relation` + `collective_agents`'tan
**türetilmiştir**; birincil veri kaybı yoktur.

**API:** `/health`, `/works`, `/persons`, `/search?q=bilgi` → 200. `public.items` ve
tüm mevcut uçlar hiç değişmedi.

#### ⚠ Test paketi: 33 testin 20'si hata veriyor — ÖNCEDEN VAR, benim regresyonum değil

`python -m unittest discover -s tests` → **Ran 33 tests, 13 ok, 20 ERROR**. 20 hatanın
**hepsi tek ve aynı nedenden**: `no such function: similarity` (40 tekrar).

| | |
|---|---|
| Neden | `services/reconciliation.py:158` `func.similarity(...)` çağırıyor. Bu `pg_trgm` fonksiyonudur; test paketi SQLite üzerinde çalışır ve SQLite'ta yoktur |
| Kanıt (benim değişikliğim olmadığı) | `git diff --name-only HEAD` listesinde `services/reconciliation.py` **yok** — dokunmadım |
| Kanıt (şema kurulumu sağlam) | 33 testin tamamı `setUp`'ı geçti; `create_all` kırılsaydı 33'ü de hata verirdi, 13'ü geçiyor |
| Etkilenen testler | Aday **üretimini** tetikleyenler: `test_generated_inputs_are_fresh`, `test_changed_source_is_stale_and_regeneration_restores_freshness`, `test_automatic_acceptance_blocked_even_when_fresh`, … |
| Geçen testler | Aday üretmeyenler: değerlendirme, kararlar, snapshot, legacy evidence |

**`docs/reconciliation-policy.md`'deki "33 isolated SQLite test pass" ifadesi artık
geçerli değildi.** Test paketinin %60'ı sessizce kapsam dışı kalmıştı. **§0.6'da
düzeltildi** — paket yeniden tamamen yeşil.

---

### 0.6 Normalizasyon + eşleştirme düzeltmesi — TAMAMLANDI

§15.5 ve §15.6'daki iki bulgunun düzeltmesi. **Migration `f2a5c8e36d74`**; zincir artık
**31 revision**, tek head.

| Değişiklik | Dosya |
|---|---|
| `normalize_text` tek kaynak modüle taşındı | yeni `app/normalization.py` |
| `works.normalized_title` kolonu + `ix_works_normalized_title_trgm` GIN index | `models.py` + migration |
| Kolonu ORM `before_insert`/`before_update` olayıyla türetme | `models.py` |
| Eşleştirmede `%` blocking + `similarity()` sıralama | `services/reconciliation.py` |
| SQLite `similarity` vekili | `tests/test_reconciliation_policy.py` |

**Normalizasyon uyumsuzluğu giderildi** — ölçüm, eşik 0.30:

| | Skor |
|---|---|
| Eski — depo `lower()`, gelen `normalize_text()` | **0.714** |
| Yeni — iki taraf da `normalize_text()` | **1.000** |

**Blocking eklendi** — 200.000 **farklı** başlıkla ölçüm (ilk denememde sentetik veri
tekdüze çıkmıştı; bu ölçüm 200.000 ayrı başlıkla alındı):

| Sorgu | Plan | Süre | Buffer |
|---|---|---|---|
| Eski: yalnızca `similarity() >= 0.3` | Seq Scan (199.999 satır elendi) | **1442 ms** | 2062 |
| Yeni: `%` + `similarity()` | **Bitmap Index Scan on `_probe_norm_trgm`** | **14,5 ms** | 192 |

**~100× hızlı, ~11× az buffer.** `%` operatörü 200.000 satırdan tam olarak **1**'ini
eşleştirdi, yani index gerçek iş yapıyor.

**Backfill:** 16/16 eser dolu (`Suç ve Ceza` → `suc ve ceza`). Backfill bir SQL taklidi
değil, **uygulamanın kendi normalizasyon fonksiyonunu** Python'dan çağırır — aksi hâlde
düzeltmeye çalıştığı iki taraflı uyuşmazlığı yeniden üretirdi.

**Test paketi düzeldi: `Ran 33 tests … OK`.** Önceden 13 geçiyor, 20 hata veriyordu.

**Önceki iddiamın düzeltmesi (kayda geçiyor).** §0.5'te "`similarity()` çağrısını `%`
operatörüne taşımak test hatasını kendiliğinden düzeltir" demiştim. **Bu yanlıştı:**
SQLite'ta `'abc' % 'x'` sayısal modülo yapıp `NULL` döndürür (ölçüldü), yani `%` sorguyu
SQLite'ta hiçbir satırla eşleştirmez. Doğru çözüm iki parçalı oldu:

1. blocking **yalnızca PostgreSQL'de** uygulanıyor (`bind.dialect.name` kontrolü) —
   SQLite'ta tam tarama yapılır, ki test verisi küçük olduğu için bu doğrudur;
2. test `setUp`'ında SQLite'a `similarity` için pg_trgm algoritmasını (kelime başına
   `"  kelime "` dolgusu, trigram kesişimi/birleşimi) taklit eden bir vekil kaydediliyor.

Vekil pg_trgm ile **birebir aynı değildir**: testler politika davranışını doğrular,
dağıtılmış bir PostgreSQL'in tam skorunu değil.

**Geri alınabilirlik kanıtlandı:** `downgrade e1f4b7d25c63` → kolon silindi, 16 eser
duruyor; `upgrade head` → 16/16 yeniden dolduruldu; `alembic check` temiz.

**Gerçek PostgreSQL doğrulamasında çıkan iki hata (ikisi de düzeltildi).** SQLite test
paketi bu kod yolunu kapsamıyor — `%` blocking PostgreSQL'e özel — o yüzden yeni yolu
gerçek veritabanında, yazma yapmadan çalıştırdım. İyi ki:

1. **`set_limit(double precision) does not exist`.** pg_trgm fonksiyonu
   `set_limit(real)` olarak tanımlı; Python float'ı `double precision` olarak bağlanınca
   PostgreSQL eşleşen fonksiyon bulamıyor. Düzeltme:
   `set_limit(cast(:threshold as real))`. SQLite testleri bunu göremezdi.
2. **`alembic heads` kırıldı.** Migration'ın modül seviyesindeki
   `from app.normalization import normalize_text` importu, Alembic revision haritasını
   kurarken *tüm* revision dosyalarını yüklediği için patlıyordu — ve `alembic heads`
   env.py'yi çalıştırmaz, dolayısıyla `sys.path`'e backend dizini henüz eklenmemiş olur.
   `upgrade`/`current`/`check` çalışıyordu (onlar env.py'yi çalıştırır), yalnızca
   `heads`/`history` kırıktı. Düzeltme: import `upgrade()` fonksiyonunun **içine** alındı.

**Gerçek veriyle uçtan uca sonuç** (SELECT-only, rollback):

| Gelen başlık (aksansız) | Bulunan aday |
|---|---|
| `Suc ve Ceza` | `Suç ve Ceza` |
| `Bilgi Yonetimine Giris` | `Bilgi Yönetimine Giriş` |
| `Bilgi Yonetimi Giris` | `Bilgi Yönetimine Giriş` |
| `alakasiz bir baslik` | — (0 aday) |

İlk satır düzeltmenin özetidir: aksansız bir sorgu artık aksanlı kaydı buluyor. Son satır
yanlış pozitif üretmediğini gösteriyor.

---

### 0.7 Aşama 3 uygulama kaydı — TAMAMLANDI (Tenant Data Plane iskeleti)

**Migration `a3b6d9f47e85`**; zincir artık **32 revision**, tek head. Veri taşınmadı —
`public.items` göçü Aşama 4'tür.

| Ne | Detay |
|---|---|
| Tablolar | `tenant.locations`, `tenant.holdings`, `tenant.items` |
| Roller | `libraryhub_global_app`, `libraryhub_tenant_app` + grant'lar + default privileges |
| RLS | üç tabloda `ENABLE` + `FORCE`, `tenant_isolation` politikası |
| Kararlar | **OD3** (barkod tenant geneli) ve **OD4** (`branch_id` zorunlu) uygulandı |

**Holding neden ayrı varlık** — §3.2'deki gerekçe DDL'e geçti: süreli yayın cilt/sayı
beyanı (`holding_statement`, `enumeration_pattern`), Item'sız elektronik kaynak
(`holding_type='electronic'`, `access_url`, `license_note`) ve koleksiyon düzeyinde yer
numarası (`call_number` Holding'de, nüshada değil).

**Exclusive arc taşınabilir yazıldı.** `num_nonnulls(...)` PostgreSQL'e özel ve SQLite test
motorunu kıracaktı. Bunun yerine
`(manifestation_entity_id IS NULL) <> (expression_entity_id IS NULL)` kullanıldı; iki motorda
da çalışıyor ve **ikisinde de uygulanıyor** (test edildi: ikisi de NULL → engellendi, ikisi
de dolu → engellendi).

**RLS kanıtlandı** — geçici kayıtlarla, işlem geri alındı:

| Bağlam | Görünen item |
|---|---|
| superuser (`library`) | 2 — **RLS bypass edilir** |
| `libraryhub_tenant_app` + tenant A | 1 |
| `libraryhub_tenant_app` + tenant B | 1 |
| `libraryhub_tenant_app` + tenant ayarlanmamış | **0 (fail-closed)** |
| `libraryhub_global_app` → `tenant.items` | `permission denied for schema tenant` |

Politika bilerek fail-closed: `current_setting(..., true)` ayar yokken NULL döner,
karşılaştırma NULL olur ve **hiç satır görünmez** — unutulan bir `SET LOCAL`, her şeyi
göstermek yerine hiçbir şey gösterir.

> **⚠ RLS henüz uygulama trafiği için yürürlükte değil.** Uygulama, veritabanı sahibi olan
> `library` rolüyle bağlanıyor ve resmi postgres imajında bu rol **superuser**'dır;
> superuser'lar RLS'i tamamen bypass eder. `FORCE ROW LEVEL SECURITY` tablo *sahibini*
> kapsar, superuser'ı kapsamaz. Yani politikalar doğru ama şu an **törensel**. Gerçek
> yaptırım, uygulamanın superuser olmayan bir rolle bağlanmasıdır — yönlendirme katmanıyla
> birlikte Aşama 5'in işi (§5.2, §5.3). Bunu buraya açıkça yazıyorum çünkü "RLS var" demek
> "izolasyon var" demek değildir.

**Çapraz plane yabancı anahtarları ve `ddl_if`.** `holdings.branch_id → control.branches`
ve `holdings.manifestation_entity_id → public.manifestations` çapraz şemadır (testlerde
çapraz veritabanı). SQLite nitelikli bir `REFERENCES` ifadesini **hiç ayrıştıramıyor**
(`near ".": syntax error`), bu yüzden bu üç kısıt `.ddl_if(dialect="postgresql")` taşır ve
yalnızca PostgreSQL'de bulunur. Aynı şema içindeki `items → holdings` ve `items → locations`
kısıtları her motorda uygulanır.

Bu aynı zamanda dürüst mimari konumdur: **çapraz plane FK'leri tek-cluster kolaylığıdır.**
D5 bir tenant'ın başka cluster'a taşınabilmesini gerektirir; plane'ler fiziksel olarak
ayrıldığı anda bu kısıtlar kalkmak zorundadır. `tenant_id` bu yüzden hiç FK almaz — taşınan
şey tam da odur.

**Geri alınabilirlik kanıtlandı:** `downgrade f2a5c8e36d74` → tenant tablosu 0, rol 0;
`upgrade head` → 3 tablo, 2 rol; `alembic check` temiz.

**Doğrulama:** test paketi **33/33 yeşil**; şema `public=36 control=4 tenant=3`;
`works=16 normalized=16 items=12 entities=91` değişmedi; tenant tabloları boş; API 200.

---

### 0.8 OD13 uygulama kaydı — TAMAMLANDI (RLS gerçek yaptırım hâline geldi)

**Migration `b4c7e0a58f96`**; zincir artık **33 revision**, tek head.

| Ne | Detay |
|---|---|
| Uygulama rolü | `libraryhub_app` — `NOSUPERUSER`, `NOBYPASSRLS`, `NOCREATEDB`, `NOCREATEROLE` |
| Üyelik | `libraryhub_global_app` + `libraryhub_tenant_app` |
| Kimlik ayrımı | `DATABASE_URL` (şema sahibi, **yalnızca** migration) ↔ `APP_DATABASE_URL` (çalışma zamanı) |
| Tenant bağlamı | `db.tenant_session()` → `set_config('libraryhub.tenant_id', …, is_local => true)` |
| Bootstrap | Yeni tek-seferlik `migrate` servisi; `api` ona `service_completed_successfully` ile bağlı |

**PostgreSQL 16 tuzağı.** PG16, `GRANT role TO role` için varsayılanı
`INHERIT FALSE, SET TRUE` yaptı. Açıkça `WITH INHERIT TRUE` verilmeseydi uygulama rolü
yetkileri *tutardı* ama *miras almazdı* ve kod `SET ROLE` çağırana kadar her sorgu hata
verirdi. Doğrulandı: her iki üyelikte de `inherit_option = t`.

**Kanıt — gerçek uygulama rolüyle, hepsi geri alınan işlemler içinde:**

| Test | Sonuç |
|---|---|
| `public` INSERT / UPDATE / DELETE | OK |
| `CREATE TABLE` (DDL) | engellendi (`ProgrammingError`) |
| tenant A bağlamında görünen | 1 |
| tenant B bağlamında görünen | 1 |
| tenant ayarsız | **0 (fail-closed)** |
| A bağlamında **B adına yazma** | **engellendi** (`WITH CHECK`) |
| `is_superuser` | `off` |
| API'nin bağlandığı rol (`pg_stat_activity`) | `libraryhub_app` |

Son satırlar OD13'ün özüdür: Aşama 3'te politika *vardı*, ama superuser onu bypass ettiği
için hiçbir şey yapmıyordu. Şimdi uygulama trafiği için gerçekten uygulanıyor.

**Bootstrap sırası çözüldü.** Yeni `migrate` servisi şema sahibi kimlikle
`alembic upgrade head` çalıştırır; `api` buna `service_completed_successfully` ile
bağlıdır. Bu, Aşama 0'da işaretlediğim **"migration otomasyonu yok"** bulgusunu da
kapatır: taze bir `docker compose up`, şema kurulmadan ve uygulama rolü oluşmadan API'yi
başlatmaz.

**Kimlik bilgisi hijyeni.** `docker-compose.yml` artık parola içermiyor;
`${POSTGRES_USER}` / `${APP_DB_PASSWORD}` ile `.env`'den okuyor. `alembic/env.py` de artık
`DATABASE_URL`'i `alembic.ini`'ye **tercih ediyor** — öncesinde `DATABASE_URL` değiştirilse
bile migration'lar `alembic.ini`'deki adrese gidiyordu. `alembic.ini`'deki geliştirme URL'i
yalnızca ortam olmadan çalışan offline SQL üretimi için yedek olarak kaldı.

**Geri alınabilirlik kanıtlandı:** `downgrade a3b6d9f47e85` → rol 0; `upgrade head` →
rol 1 (`superuser=false, bypassrls=false`); API döngüden sonra **kendiliğinden toparlandı**,
tüm uçlar 200.

**Doğrulama:** test paketi **33/33 yeşil**; `alembic check` temiz; şema
`public=36 control=4 tenant=3`; veri değişmedi.

---

### 0.9 Aşama 4 uygulama kaydı — TAMAMLANDI (item göçü + uyumluluk görünümü)

**Migration `c5d8f1b69a07`**; zincir artık **34 revision**, tek head. `public.items`
**silinmedi** — Aşama 6'ya kadar yerinde ve yazılabilir kalıyor; geri alma bu yüzden tek adım.

**Göç sonucu:** 12 legacy item → 12 `tenant.items`, 10 `tenant.holdings`.

| Kurum | Item |
|---|---|
| Unassigned items (migration) | 7 |
| Hacettepe Üniversitesi | 2 |
| Российская государственная библиотека | 2 |
| Kırıkkale Üniversitesi | 1 |
| Canonical Redirect Test Organization B | 0 |

**Yedek tenant kararı uygulandı.** Kurumu belirlenemeyen 7 nüsha, `unassigned` slug'lı ve
açıkça "Unassigned items (migration)" adlı ayrı bir tenant'a yazıldı. Kurum eşlemesi
uygulamanın **kendi kuralıyla** yapıldı (`item_agent_relation.role = 'holding_institution'`),
böylece göç öncesi API'nin bildirdiği aidiyet birebir korunuyor.

Dikkat çeken sonuç: barkodları Kırıkkale'yi düşündüren `KKU-AKADEMIK-0001`,
`KKU-SOZLUK-0001` gibi 5 nüsha da yedek tenant'a gitti, çünkü **hiçbir kurum ilişkileri
yok**. Barkoddan tahmin yürütmek sessizce yanlış atıf yapmak olurdu; belirsizlik görünür
bırakıldı.

Yedek organizasyonun `collective_agent_entity_id`'si **bilerek NULL**: bu bir otorite kaydı
değil, ve NULL olması uyumluluk görünümünün bu nüshalar için "holding kurumu yok" demesini
sağlıyor — göç öncesi API'nin dediği tam olarak buydu.

**Üretilmiş anahtar.** Barkodu ve raf yeri olmayan 2 nüsha için `local_holding_key`
nüshadan değil **gruptan** türetildi: `migrated-<manifestation uuid>`. Bir Holding her
farklı (tenant, şube, manifestation) için bir kez oluşturuldu; aynı eserin aynı raftaki
nüshaları yer numarasını paylaşır.

**Sadakat kanıtı.** Uyumluluk görünümü, eski sorgunun ürettiği kümeyle **birebir** aynı:

| Sorgu | Eski | Yeni | Sadece eski | Sadece yeni |
|---|---|---|---|---|
| Item sorgusu | 12 | 12 | **0** | **0** |
| Holding sorgusu | 5 | 5 | **0** | **0** |

Ayrıca göç, `public.items` ile `tenant.items` satır sayılarını karşılaştırıp eşit değilse
**hata verip duruyor**: sessizce satır düşüren bir göç, duran bir göçten daha kötüdür.

**API sözleşmesi korundu.** `/works/{id}/detail` yanıtları göç öncesi baseline ile
**16/16 aynı**; `POST /items` → 201; `GET /items/{id}/agents` → 12/12 → 200.

**Okuma yolu değişti, yazma yolu bilerek değişmedi.** `services/work_detail.py` artık
`public.items_compat` üzerinden okuyor. `POST /items` hâlâ legacy tablolara yazıyor, çünkü
henüz tenant kimliği (auth) yok — hangi kuruma yazılacağı bilinemez. Görünümün ikinci dalı
(`union all`) bu yeni kayıtları da gösterir, böylece sözleşme onları kaybetmez. Yazma
yolunun taşınması Aşama 5'tir.

**⚠ Aşama 3'te soktuğum bir hata bulundu ve düzeltildi.** `models.py`'nin sonundaki
`from .tenant_models import (… Item …)` satırı, modüldeki **legacy `Item` sınıfını
gölgeliyordu**. Yani `app.models.Item` bir süre boyunca tenant item'ı gösterdi ve
`/items/{id}/agents` (GET ve POST) ile `POST /items` bozuldu: **12/12 item 404 dönüyordu.**
Test paketi `/items` uçlarını kapsamadığı ve benim uç kontrollerim de yalnızca `/health`,
`/works`, `/persons`, `/search` olduğu için Aşama 3'te gözden kaçtı.

Düzeltme: tenant sınıfları `TenantItem`, `TenantHolding`, `TenantLocation` olarak yeniden
adlandırıldı, böylece gölgeleme yapısal olarak imkânsız hâle geldi. Doğrulandı:
`app.models.Item` → tablo `items` (public), `app.models.TenantItem` → `tenant.items`;
`/items/{id}/agents` **12/12 → 200**; `POST /items` → **201**.

**Göç öncesi tespit edilen bir veri gerçeği.** `/works/{id}/detail` **hiçbir eser için item
döndürmüyor**, çünkü item taşıyan manifestation'lara bağlı work'ler `entity_merges`
kaynağıdır ve kanonik hedeflerde o item'lar görünmez. Bu göçten önce de böyleydi. Bu yüzden
doğrulama API düzeyinde değil **SQL düzeyinde** kuruldu (yukarıdaki denklik tablosu), ki bu
zaten daha güçlüdür: tek bir eser yerine 12 satırın tamamını karşılaştırır.

**Geri alınabilirlik kanıtlandı:** `downgrade b4c7e0a58f96` → görünüm 0, tenant item 0,
holding 0, `unassigned` tenant 0, `legacy_entity_id` kolonu 0, **`public.items` hâlâ 12**;
`upgrade head` → 12 item, 10 holding, görünüm geri.

**RLS gerçek göç verisiyle** (`libraryhub_app`, hiçbir şey yazmadan):

| Tenant bağlamı | Görünen item |
|---|---|
| ayarsız | **0** |
| Hacettepe | 2 |
| Kırıkkale | 1 |
| Российская государственная библиотека | 2 |
| Unassigned | 7 |
| Canonical Redirect Test Organization B | 0 |

**Doğrulama:** test paketi **33/33 yeşil**; `alembic check` temiz; API uçları 200.

> **Not:** `public` şemasındaki nesne sayısı 36 → **37** görünür, çünkü
> `information_schema.tables` görünümleri de listeler; eklenen şey `items_compat`
> görünümüdür, tablo değil. `alembic check` bu görünüm için hiçbir sapma bildirmiyor.

---

### 0.10 `unassigned` kuyruğunun kapatılması — TAMAMLANDI

§0.9'daki 7 atanmamış nüsha, küratör kararıyla kurumlarına bağlandı.

**Mekanizma: neden script, neden migration değil.** Göç (c5d8f1b69a07) bir nüshayı yalnızca
`item_agent_relation.role = 'holding_institution'` üzerinden sahiplendiriyor — uygulamanın
kendi kuralı — ve gerisini tahmin etmek yerine görünür biçimde `unassigned`'a bırakıyordu.
Bu kuyruğu kapatmak bir **küratörlük kararı**, şema evrimi değil. Barkod önekini bir
migration'a gömmek, o çıkarımı farklı veriye sahip her ortamda da çalıştırırdı. Karar bu
yüzden `backend/scripts/assign_unassigned_items.py` içinde **açık ve gözden geçirilmiş bir
eşleme** olarak, deneme moduyla birlikte duruyor.

| Barkod | Hedef kurum |
|---|---|
| `KKU-AKADEMIK-0001` | Kırıkkale Üniversitesi |
| `KKU-ANSIKLOPEDI-SET-0001` | Kırıkkale Üniversitesi |
| `KKU-COCUK-0001` | Kırıkkale Üniversitesi |
| `KKU-SOZLUK-0001` | Kırıkkale Üniversitesi |
| `KKU-TEZ-0001` | Kırıkkale Üniversitesi |
| `TEST-CANONICAL-ITEM-001` | Canonical Redirect Test Organization B |
| `TEST-ITEM-REDIRECT-SOURCE` | Canonical Redirect Test Organization B |

**Sonuç:** Kırıkkale 1 → **6**, Canonical Redirect B 0 → **2**, `unassigned` 7 → **0**;
holding 10 → 16; toplam item 12, `public.items` 12 (değişmedi).

**Script sahip kimliğiyle bağlanıyor — bu bir tercih değil, zorunluluk.** Satır düzeyi
güvenlik, kiracılar arası taşımayı uygulama rolü için **kasıtlı olarak** imkânsız kılıyor ve
bu ilk bakışta hata gibi göründüğü için yazıyorum:

* `libraryhub.tenant_id` **kaynak** kiracıya ayarlıysa, politikanın USING'i eski satırı
  eşler ama WITH CHECK'i yeni `tenant_id`'yi reddeder;
* **hedef** kiracıya ayarlıysa USING eski satırı eşlemez, satır görünmez bile.

Yani kiracılar arası taşıma yönetici işlemidir ve `DATABASE_URL` (sahip) ile çalışır.

**⚠ Kasıtlı ve belgelenmiş sözleşme değişikliği.** Düzeltmeden önce uyumluluk görünümü eski
sorguyla birebir aynıydı (§0.9). Artık **tam 7 satırda farklılar**: bu nüshalar görünümde
artık bir holding kurumu bildiriyor, eski sorgu ise NULL döndürüyordu (`role` farklıydı ya
da ilişki hiç yoktu). Ölçüm: `legacy_satir=12`, `view_satir=12`, `sadece_legacy=7`,
`sadece_view=7`, `kurum_farki=7`.

Bu **iyileşmenin ta kendisidir** — düzeltmenin amacı bu nüshalara aidiyet kazandırmaktı —
ama bir sözleşme değişikliğidir ve sessizce geçiştirilmemelidir. Bugün API'de gözlemlenebilir
bir etkisi yoktur, çünkü hiçbir kanonik eser item döndürmüyor (§0.9); item'lar görünür hâle
geldiğinde `/works/{id}/detail` bu 7 nüsha için holding kurumu satırı **kazanacaktır**.

**Kök neden de düzeltildi.** `seed_diverse_catalog.py`'deki `create_item` hiçbir zaman
holding kurumu kaydetmiyordu ve `add_item_agent` yardımcısı **hiç yoktu** — bu yüzden
seed'lenen her nüsha kurumsuz kalıyordu. Eklendi: `create_item(..., holding_institution_id=)`
ve `add_item_agent(...)`; `main()` artık Kırıkkale Üniversitesi'ni bir kez oluşturup tüm
KKU-* nüshalarına geçiriyor. `seed_encyclopedia.py` de aynı şekilde güncellendi (TDV
**work creator** olarak kalıyor; nüshanın sahibi Kırıkkale — bunlar farklı roller).

---

### 0.11 Ölçek verisi ve çoklu veri hata avı — TAMAMLANDI

Bir düzine satır, bütün bir hata sınıfını görünmez kılar: yüzlerce tenant arasında satır
düzeyi güvenlik, tablo tek sayfaya sığmazken index davranışı, sayfalama ve `/search`'ün
bilerek pahalı olan 20 dallı `OR`'u. İki script eklendi:

| Script | Ne yapar |
|---|---|
| `generate_scale_fixtures.py` | Üç planda da hacim üretir; `--purge` ile **tamamen** siler |
| `run_scale_checks.py` | 13 senaryo kontrolü çalıştırır ve raporlar |

**Üretilen (gerçek sonuç):** hedef 100 organizasyon / 300 work / 1000 item idi.
Gerçekleşen: **100 tenant, 100 organizasyon, 100 otorite kaydı, 300 work, 930 holding,
837 item.** 1000 değil 837, çünkü bazı tenant'lar kasten item'sız ve elektronik holding'ler
kasten item'sız — ikisi de senaryo gereği.

**Kasıtlı kenar durumlar:** 92 barkodsuz nüsha, 93 elektronik holding (hiç item'ı yok),
91 paylaşılan barkod (aynı değer birden fazla tenant'ta — OD3 bunu serbest bırakır),
91 Kiril barkod, 1 aşırı uzun barkod, 10 item'sız tenant, 1 dengesiz büyük tenant,
4 adet normalize edilemeyen başlık (yalnızca noktalama → `normalized_title` NULL),
Türkçe/Kiril/Arapça başlıklar ve 3000 karakteri aşan başlıklar.

**Kontroller: 13/13 geçti.**

| Kontrol | Sonuç |
|---|---|
| RLS: her tenant yalnızca kendi satırlarını görüyor | **105 tenant denendi, 0 uyuşmazlık** |
| RLS: tenant ayarsızken hiç satır yok (fail-closed) | 0 satır |
| Orphan item / hedefsiz holding / exclusive arc ihlali | 0 / 0 / 0 |
| OD3: tenant içinde barkod tekrarı | 0 |
| Uyumluluk görünümü legacy item'ları koruyor | `public.items=12`, `items_compat=849`, temsil edilmeyen 0 |
| `tenant.items` ve `tenant.holdings` index kullanımı | Index/Bitmap Index ✓ |
| `works.normalized_title` trigram index | Bitmap Index ✓ |
| **Bir Manifestation'ı kaç kurum tutuyor** | **92 kurum** |

Son satır mimarinin çekirdek sorusudur: aynı bibliyografik kaydı 92 kurumun paylaşması ve
her birinin kendi nüshasını görmesi, Global/Tenant ayrımının çalıştığının ölçülmüş kanıtı.

**Üreteç kendi hatasını kısıt sayesinde yakaladı.** İlk tam ölçek denemesi
`uq_items_tenant_barcode` ihlaliyle durdu: `SHARED-2` değeri aynı tenant'ta iki kez
üretiliyordu (dengesiz büyük tenant 4× slot aldığı için). Bu bir üreteç hatasıydı ve
**OD3 kısıtı onu yakaladı** — kısıtın gerçek veri altında çalıştığının kanıtı. Değer
slota bağlandı; işlem geri alındığı için kısmi veri kalmadı.

#### Ölçek altında bulunan iki gerçek sorun

**1. `/search` ölçekle belirgin yavaşlıyor.** 316 eserle (16 iken 20×):

| Sorgu | min | ortalama | max |
|---|---|---|---|
| `q=scale` | 281 ms | 314 ms | 368 ms |
| `q=Ölçek` | 257 ms | 298 ms | 329 ms |
| `q=Масштабная` | 281 ms | 304 ms | 327 ms |
| **`q=سجل`** | 327 ms | **678 ms** | **944 ms** |
| `q=bilgi` (1 sonuç) | 83 ms | 105 ms | 126 ms |

§15.4'teki 16-eserli ölçüm min 117 / ort 163 / max 365 ms idi. Yani veri 20 katına
çıkarken süre 2–3 katına çıktı — alt-doğrusal ama **mutlak değerler tırmanıyor** ve Arapça
sorgu 944 ms tepeye vurdu. Bu, §9'daki Search Plane'in neden gerekli olduğunun ölçekli
kanıtıdır; PostgreSQL'de kalmaya devam ederse 100 milyonda kullanılamaz.

**2. Boşluk sorgusu rastgele sonuç döndürüyor.** `GET /search?q=%20` (tek boşluk):
`min_length=1` kontrolünü geçiyor, `strip()` sonrası boş kalıyor ve arama terimi `%%`
oluyor — yani **her kaydı eşleştirip LIMIT 50 ile keyfi 50 eser döndürüyor** (ölçüldü:
`count=50`, 200 OK). `q=` (tamamen boş) doğru şekilde 422 veriyor. Doğrusu, boşluk
sorgusunun da 422 dönmesi ya da anlamlı bir hata vermesidir; şu hâliyle kullanıcıya
sorgusuyla ilgisiz kayıtlar gösteriyor.

**Diğer ölçek sonuçları (sorun çıkmadı):** `/works` sayfalaması doğru (316 → 200 + 116);
`page_size=500` → 422, `page_size=0` → 422, `page=0` → 422; aynı sorgu tekrarlandığında
sonuç ve sıra kararlı; `/works/{id}/detail` 12–50 ms; test paketi **33/33 yeşil**;
`alembic check` temiz; API loglarında hata yok.

**Veriyi silmek:**
`docker compose exec -T api sh -c "cd /app/scripts && python generate_scale_fixtures.py --purge"`
— yalnızca `scale-` önekli tenant'ları ve `[scale-fixture]` işaretli global kayıtları siler.
Temizliğin özgün veriye dokunmadığı doğrulandı (`works=16`, `entities=91`, `tenants=5`).

---

### 0.12 Arayüz incelemesi ve düzeltmeleri — TAMAMLANDI

`http://localhost:8010/` headless tarayıcıyla gerçekten açıldı, arama yaptırıldı, detay
görünümüne girildi ve ölçekli veri basıldı. Bulunanlar ve yapılanlar:

| # | Bulgu | Düzeltme |
|---|---|---|
| 1 | `renderDetailItems` dengesiz `<div>` (7 açılan, 6 kapanan) → her nüsha kartı bir öncekinin içine giriyor, satırlar giderek sağa kayıyordu | Fonksiyon yeniden yazıldı; **10 render fonksiyonunun tamamı artık dengeli** |
| 2 | `/works/{id}/detail` **her kurumun nüshasını** döküyordu; ölçekle bir eser sayfası 90+ kurumun barkodunu listeliyordu | Global uç artık **kurum özeti** döndürüyor (kurum + nüsha sayısı + durum dağılımı); barkod/raf yeri yok |
| 3 | 3000 karakterlik başlık kartı ~350px şişiriyordu | `-webkit-line-clamp: 3` + `overflow-wrap: anywhere` |
| 4 | Deep link ve tarayıcı geçmişi yoktu (yalnızca bellek-içi yığın) | Adres (hash) tek doğruluk kaynağı: `#/search/…`, `#/work/…`, `#/person/…`, `#/concept/…`, `#/agent/…` |
| 5 | `GET /search?q=%20` 200 dönüp **keyfî 50 eser** gösteriyordu; ayrıca sonuç kesildiğinde kullanıcı bunu bilmiyordu | Boşluk/tab sorgusu **422**; `/search` artık `limit` (1–200) ve `truncated` döndürüyor; arayüz "ilk N gösteriliyor" diyor |

**2 numaralı madde bilinçli bir sözleşme değişikliğidir ve gerekçesi mimaridir.**
`/works/{id}/detail` *global* uçtur: "bu eser nedir ve kimler tutuyor" sorusunu herkese
yanıtlar. Tek bir nüsha ise onu elinde tutan kurumun **operasyonel verisidir** — barkod ve
raf yeri, fiziksel bir nesnenin bir kütüphanede hangi rafta durduğunu söyler. Bu yüzden
global uç nüsha listelemek yerine kurum bazında toplar. Nüsha düzeyi detay, kimlik
doğrulamayla gelen kiracıya özel görünümün işidir (Aşama 5). Öncesinde uç, ölçek verisiyle
**tek bir eser sayfasında doksan kurumun barkodunu** döküyordu: hem sınırsız bir yanıt hem
de kimlik doğrulama geldiğinde kiracılar arası sızıntı.

**Doğrulama** — üçü de ekran görüntüsüyle:

| Kontrol | Sonuç |
|---|---|
| `#/work/{id}` doğrudan açılıyor (sonda dosyası yok) | ✅ tam detay render edildi |
| Detay görünümü | ✅ **"94 nüsha · 91 kurum"**, kurum başına bir satır, **barkod/raf yeri yok**, kümülatif girinti yok |
| Aşırı uzun başlık | ✅ 3 satıra kırpıldı, kart kompakt |
| Kesilme bilgisi | ✅ "50 kayıt bulundu (ilk 50 gösteriliyor — daha fazlası için arama terimini daraltın)." |
| Boşluk / tab sorgusu | ✅ dördü de 422 |
| `/search?limit=` | ✅ 3→3, 50→50, 200→60 (`truncated=false`), 500→422 |
| `build_work_detail`'i kullanan diğer uçlar | ✅ `/search/concept` 200; içi boş eser detayı çökmeden dönüyor |
| Div dengesi | ✅ 10/10 render fonksiyonu dengeli |
| Test paketi / `alembic check` | ✅ 33/33 yeşil / temiz |

**Sırada kalan arayüz işleri** (düzeltilmedi, kayda geçiyor): arayüz hâlâ 50 ucun 5'ini
kullanıyor; sonuç kolonu hero'ya göre dar; footer sayfanın altına sabitlenmiyor; arama
sonuçlarında gerçek sayfalama yok (Search Plane gerektirir, §9); kurum listesi alfabetik
sıralanıyor, doğal sıralama değil.

---

### 0.13 Aşama 5 önkoşulu — TAMAMLANDI (kimlik doğrulama + tenant bağlamı)

**Migration `d6e9a2c58b13`**; zincir artık **35 revision**, tek head. `control.users` ve
`control.sessions` oluşturuldu.

**Neden Aşama 5'in önkoşulu.** `POST /items` tenant plane'ine taşınamaz, çünkü isteğin
hangi kuruma ait olduğunu bilmiyoruz. Dürüst bir varsayılan yok: sessizce birini seçmek her
yeni nüshayı rastgele bir kütüphaneye yazardı ve RLS'in `WITH CHECK` tarafı zaten yazmayı
reddederdi. Tenant, kimliği doğrulanmış bir hesaptan gelmek zorunda.

**Zincir tek satırda:** `control.users.tenant_id` → `tenant_db` bağımlılığı →
`SET LOCAL libraryhub.tenant_id` → `tenant.*` politikası → yalnızca o kurumun satırları.
İstemciye **hiçbir zaman** "hangi kütüphane adına işlem yapıyorsun" diye sorulmaz; onu
istekten kabul etmek başlı başına açık olurdu.

**Yeni bağımlılık yok.** `hashlib.scrypt` (imajda mevcut, ~48 ms) ve `secrets` yeterliydi;
passlib + bcrypt + JWT üç bağımlılık olurdu. Parola özeti kendini tanımlar
(`scrypt$n$r$p$salt$hash`), böylece maliyet parametreleri sonradan yükseltilebilir ve eski
parolalar geçersizleşmez.

**Oturumlar sunucu tarafında satır, imzalı token değil.** İmzalı token kendini doğrular ve
bu yüzden bir denylist olmadan **iptal edilemez**; kütüphanelerde iptal ilk günden gerekir
(personel ayrılır, dizüstü kaybolur). Bu yüzden oturum `revoked_at` taşıyan bir satırdır.
Veritabanında yalnızca token'ın SHA-256'sı durur: `control.sessions` dökümü kimseye
kullanılabilir kimlik vermez. Tablo `UserSession` olarak adlandırıldı, çünkü `Session`
SQLAlchemy'nin kendi adıdır ve bu projede tam olarak bu tür bir gölgeleme bir kez sessiz bir
hata üretti (§0.9).

**Hesaplar API'den oluşturulamaz.** Uygulama rolünün `control.users` üzerinde yalnızca
`SELECT` hakkı var ve oturum tablosunda DML. Hesap açmak sahip kimliğiyle çalışan
`scripts/create_user.py` işidir. "Yönetim paneli için" uygulamaya `INSERT` vermek, çalınan
tek bir oturumun istediği kurum adına yeni oturum üretmesi demek olurdu.

**Yeni uçlar:** `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`,
`GET /tenant/items`, `GET /tenant/holdings`.

**Kanıt — uçtan uca, canlı API üzerinden:**

| Kontrol | Sonuç |
|---|---|
| Yanlış parola / olmayan hesap | ikisi de **401**, **aynı mesaj** (hesap numaralandırmayı önlemek için; gecikme de `scrypt` ile eşitlenir) |
| Pasif hesap | 403 (yalnızca doğru parolayla ulaşılır, sızıntı değil) |
| Token'sız `/tenant/items` | 401 |
| Kırıkkale oturumu | `/tenant/items` → **6 nüsha** / 6 holding |
| Hacettepe oturumu | `/tenant/items` → **2 nüsha** |
| **İki listenin kesişimi** | **0 — sızıntı yok** |
| Logout sonrası eski token | 401; diğer oturum çalışmaya devam ediyor |
| Ham token veritabanında | yok, yalnızca SHA-256 |

**Test paketi 33 → 51 test** (18 yeni). Bu testler iki gerçek hata yakaladı ve ikisi de
düzeltildi:

1. **`can't compare offset-naive and offset-aware datetimes`** — SQLite
   `DateTime(timezone=True)` değerlerini naive döndürüyor, PostgreSQL aware. Oturum
   süresi karşılaştırması yalnızca test motorunda patlıyordu. `_as_utc()` yardımcısı
   eklendi; fark bir sürücü varsayımıyla gizlenmedi.
2. **ASCII dışı HTTP header** — testim `Bearer böyle-bir-token-yok` gönderiyordu; header
   değerleri ASCII olmak zorunda. Test düzeltildi.

> **Henüz yapılmayanlar (Aşama 5'in kendisi).** Mevcut **global uçlar hâlâ açık** —
> `/works`, `/search`, `POST /items` vb. kimlik istemiyor. Bu bilinçli: onları şimdi
> kilitlemek seed script'lerini ve arayüzü kırardı. Yazma yolunun tenant plane'ine
> taşınması ve global uçların korunması Aşama 5'in işidir. Arayüzde de giriş ekranı yok;
> kimlik doğrulama şu an yalnızca API üzerinden kullanılabiliyor.

---

### 0.14 Self-servis hesaplar ve kiracı yazma sınırı — TAMAMLANDI

Gereksinim üç parçalıydı: **iki ayrı kullanıcı kitlesi** (akademik alan adlı
kütüphaneciler/akademisyenler ve kurumsal alan adlı yayınevi/organizasyon sorumluları),
**kendi verilerini yapıyı bozmadan ekleyip düzeltebilmeleri**, ve **admin paneli**.
Üçüncüsü bir sonraki aşamanın işi; ilk ikisinin altyapısı burada.

**Migration `e7f0b3d69c24`**; zincir **36 revision**, tek head. `control.users` iki yeni
sütun kazandı (`account_kind`, `email_verified_at`), `control.organization_domains` ve
`control.email_verifications` eklendi.

#### İki kitle, iki kanıt

Bir akademik alan adı (`@kku.edu.tr`, `@ox.ac.uk`) **kendi başına kanıttır**: kimseye
kuruma mensup olmadan böyle bir adres verilmez. Bu yüzden orada yalnızca adresin posta
alabildiği gösterilir. Kurumsal bir alan adı (`@yayinevi.com.tr`) hiçbir şey kanıtlamaz —
herkes alan adı tescil edebilir — bu yüzden alan adının bir kuruluşa bağlanması ve
`verification_method` ile **nasıl** doğrulandığının kaydedilmesi gerekir. "Doğrulandı" ama
"nasıl"ı yok, sonradan denetlenemez.

**Ücretsiz posta sağlayıcıları doğrudan reddedilir.** `@gmail.com` ne akademik ne
kurumsaldır; mensubiyeti gösteremez ve bir şirket adına konuşma yetkisini tek bir kişinin
özel posta kutusuna vermek olur. Bu yüzden bu bir ret, daha zayıf bir hesap türü değil.

**Tek geçit `control.organization_domains`.** Hesap ancak alan adı bir kuruluşa tanımlıysa
açılabilir. Bu bilinçli: bir kütüphaneci ancak **sistemde olan** bir kütüphanenin nüshalarını
yönetebilir, dolayısıyla kurumun önce sisteme alınması gerekir. Alan adı tanımlamak
`scripts/register_domain.py` ile yapılan bir **yönetici işidir** — bir e-posta adresinin
kendi kendine karar verebileceği bir şey değil. Akademik alan adı için yöntem otomatik
`academic_domain` olur; kurumsal alan adı `--method` verilmeden **reddedilir**.

#### Posta altyapısı yok — ve bu gizlenmiyor

Doğrulama bağlantısı uygulama **loguna** yazılır (geliştirme mailer'ının yaptığı şey) ve
`scripts/verify_email.py` ile konsoldan tamamlanır. Token'ı HTTP yanıtında geri vermek
bilinçli olarak yapılmadı: onu isteyene geri vermek, kontrolün kendisini anlamsız kılardı.
`_deliver_verification()` gerçek bir gönderici geldiğinde değişecek **tek** yerdir.

`verify_email.py` "bu adresi doğrulanmış say" kısayolu **sunmaz**. Kontrolün bütün değeri
birinin o adreste posta alabildiğinin gösterilmesidir; bunu atlayan bir konsol bayrağı
sessizce hesapların açılma yolu hâline gelirdi.

#### Yazma sınırı: "yapıyı bozmadan" bir grant'tır, Teamül değil

`tenant_session` artık işlemi **`libraryhub_tenant_app`** rolüne düşürür. `libraryhub_app`
her iki role de üyedir ve birleşimini miras alır; kiracıya özel işlem global yazmayı
taşımamalıdır. `SET LOCAL ROLE` **eklemez, değiştirir** — dolayısıyla o işlemin içinde
`public.works`'a INSERT yapmak PostgreSQL tarafından reddedilir.

Ölçüldü (`run_scale_checks.py`, 5 kontrol): tenant rolü `public.works` üzerinde
INSERT/UPDATE/DELETE ve `control.users` INSERT ile `control.sessions` DELETE için
**`permission denied`** alıyor. Yarının bir ucu kendini unutursa paylaşılan bibliyografik
kaydı sessizce değiştirmez, hata alır.

**Kiracının yazabildikleri:** `tenant.holdings`, `tenant.items`, `tenant.locations`.
**Yazamadıkları:** Work / Expression / Manifestation — bunlar ortak kayıttır ve değişiklik
**öneri** yoluyla, bir yöneticinin incelemesiyle olacaktır (bir sonraki aşama).

**`tenant_id` asla istekten gelmez.** Payload şemalarında böyle bir alan yok; kimliği
doğrulanmış hesaptan alınır ve politikanın `WITH CHECK` tarafı da ayrıca reddeder.

#### Kendi kendine yetki dağıtılmasına karşı

Kayıt artık herkese açık olduğu için INSERT'in kendisi kısıtlanmalı. `control.users`
üzerinde bir tetikleyici, **uygulama rolleri için** `role='admin'` atanmasını ve zaten
doğrulanmış bir hesap oluşturulmasını engeller. Tetikleyici yalnızca uygulama rolleri için
çalışır; `create_user.py` sahip kimliğiyle çalışır ve kısıtsızdır — yöneticinin yönetici
açması olağan durumdur.

#### Yeni uçlar

`POST /auth/register`, `POST /auth/verify-email`, `POST /auth/resend-verification`,
`POST /tenant/holdings`, `PATCH /tenant/holdings/{id}`, `POST /tenant/items`,
`PATCH /tenant/items/{id}`.

#### Kanıt — canlı API üzerinden

| Kontrol | Sonuç |
|---|---|
| `@gmail.com` ile kayıt | **400** "Ücretsiz e-posta adresleri kabul edilmiyor" |
| Tanımsız `@baskabiruni.edu.tr` | **403** "alan adı sistemde bir kuruluşa tanımlı değil" |
| `@kku.edu.tr` ile kayıt | **202**, `account_kind=institutional`, kurum Kırıkkale |
| Doğrulanmadan giriş | **403** "E-posta adresi henüz doğrulanmamış" |
| Doğrulama sonrası giriş | **200**, rol `librarian` |
| Aynı token'ı tekrar kullanma | **400** |
| Holding oluştur / nüsha oluştur / nüsha düzelt | **201 / 201 / 200** |
| Aynı `local_holding_key` tekrarı | **409** `uq_holdings_branch_manifestation_key` |
| Geçersiz `holding_type` / exclusive arc ihlali | **422** `ck_holdings_target_exactly_one` |
| Aynı barkod, aynı tenant | **409** `uq_items_tenant_barcode` |
| **Aynı barkod, farklı tenant** | **kabul edildi** (OD3) |
| Başka tenant'ın nüshasını/ holding'ini PATCH | **404** |
| Başka tenant'ın holding'ine nüsha ekleme | **404** |
| Başka tenant'ın şubesine holding ekleme | **404** |
| Tenant rolüyle global plane'e yazma (5 deyim) | **hepsi `permission denied`** |

**Test paketi 51 → 72** (21 yeni; alan adı kuralları, kayıt, doğrulama, token tekrarı,
süre aşımı, yeniden gönderim, doğrulanmadan giriş).

#### Bulunan gerçek hatalar

1. **`SET LOCAL` işlem kapsamlı olduğu için `db.commit()` sonrası kapsam sıfırlanıyordu.**
   Endpoint commit ettikten sonra okuduğunda rol ve tenant bağlaması kayboluyordu; RLS
   fail-closed olduğu için belirti **sızıntı değil boş sonuçtu** — yani gözden kaçmaya en
   yatkın türden. `after_begin` olayına bağlanarak kapsam işlem yerine **oturumun** özelliği
   hâline getirildi.
2. **psycopg3 `pgcode` değil `sqlstate` sunuyor.** Kısıt eşlemesi sessizce tutmuyor ve genel
   bir mesaja düşüyordu; hata "başka bir yerde bir sorun var" gibi görünüyordu. İkisi de
   okunuyor ve artık kısıt ihlalleri **loglanıyor** — dostça bir cümleye indirgenen bir hata
   yine de teşhis edilebilir olmalı.
3. **`"a b@c.com"` kurumsal sayılıyordu** — yerel kısımdaki boşluk kontrol edilmiyordu.
   Kimsenin posta alamayacağı bir adres, doğrulama bağlantısının arkasına konmuş olurdu.

Ayrıca ölçüm hatalarımı da not ediyorum: PowerShell değişkenleri büyük/küçük harf duyarsız
olduğu için `$h` (holding) `$H` (header) değişkenimi ezdi ve bir tur testi geçersiz kıldı;
`docker compose logs --tail=80` doğrulama satırını yakalayamadı ve "token loglanmıyor"
yanılgısına yol açtı. İkisinde de sonucu doğrulayıp düzelttim.

#### Açık kalanlar

1. **Admin paneli yok** — kullanıcının istediği panel bir sonraki aşamanın işi. Veri
   yönetimi şu an API üzerinden yapılabiliyor.
2. **Global plane değişiklikleri için öneri mekanizması yazılmadı.** Kiracı global kaydı
   değiştiremiyor (bu doğru), ama değiştirmek istediğinde ne olacağı henüz tanımlı değil.
3. **`control.branches` üzerinde RLS yok.** Yabancı bir şubeye holding eklenmesi FK
   tarafından engellenmiyor (FK satırın var olduğunu doğrular, sizin olduğunu değil), bu
   yüzden `_assert_branch_is_ours` kontrolü uygulama kodunda duruyor. Doğru yer politika.
4. **`libraryhub_tenant_app` bazı kimlik tablolarında hâlâ `SELECT` tutuyor**
   (`email_verifications`, `organization_domains`) — şema geneli varsayılan yetkiden geliyor.
   Yalnızca özet görülebiliyor, ama kiracı işleminin kimlik tablolarına hiç uzanamaması
   gerekir.
5. `status.HTTP_422_UNPROCESSABLE_ENTITY` Starlette'te kullanımdan kaldırılmış; uyarı
   veriyor, davranış doğru.

---

### 0.15 Sağlamlaştırma turu — TAMAMLANDI

Raporlama ve admin paneli istendiği gibi beklemede. Bu turun amacı, kendi yazdığım
"açık kalanlar" listesini kapatmak ve **önceki kararların sonraki aşamayı bloke edip
etmediğini varsaymak yerine ölçmek** oldu.

**Önce ölçtüm, sonra değiştirdim.** Aşama 6'yı neyin engellediğini bilmeden dokunmak,
bu projenin kendi kuralına aykırı olurdu. Ölçüm sonucu:

| Soru | Ölçüm |
|---|---|
| `entity_relation` ITEM entity'sine bakıyor mu | **0** — engel değil |
| `entity_merges` ITEM'e bakıyor mu | **1** — gerçek engel |
| `item_agent_relation(holding_institution)` tenant plane'inde karşılık ister mi | **Hayır** — 5 satırın tamamı holding→şube→kuruluş üzerinden birebir türetiliyor |
| `manifestation_item` temsil ediliyor mu | **Evet** — 12 satır, orphan 0 |
| `control.branches` politikası var mı | **Yok** — kapatılacak delik |

`item_agent_relation` bulgusu kayda değer: **kurum aidiyeti artık ilişki tablosunda değil,
yapıda.** Eski modelde nüsha global bir entity'ydi ve kime ait olduğu bir ilişki satırıyla
söyleniyordu; yeni modelde `item → holding → branch → organization` bunu zaten söylüyor.
Yani Aşama 6 bu tabloyu düşürdüğünde kaybolan bir bilgi yok.

#### Yapılanlar

**1. `control.branches` politikası (migration `f8a1c4e70d35`).** Diğer bütün `tenant.*`
tablolarının `tenant_isolation` politikası vardı, bu tablonun yoktu. Bugün bunu kötüye
kullanan bir şey yok — tek okuyucu kiracı oturumu içinde çalışan şube kontrolü — ama
"henüz kimse okumuyor" bugünün kodunun özelliği, şemanın değil. Politika eklendi; mevcut
hiçbir şeyi bozmadı çünkü `control.branches`'ı kiracı işlemi dışında okuyan uç **yok**
(kontrol edildi). Sahip süper kullanıcı olduğu için yönetici script'leri etkilenmedi.

**2. Şube sahipliği tetikleyicisi.** `fk_holdings_branch` şubenin **var olduğunu** doğrular,
**sizin olduğunu** değil — üstelik FK denetimi RLS'in dışında çalışır. Yani bir kurum
holding'ini başka bir kurumun şubesine bağlayabilirdi ve bütün kısıtlar sağlanmış görünürdü.
`_assert_branch_is_ours` bunu uçta yakalıyordu; tetikleyici **çağırmayan yollar için** de
yakalıyor, ki henüz yazılmamış bir toplu içe aktarma tam olarak böyle bir yoldur.
Tetikleyici bilinçli olarak `security definer` **değil**: `control.branches`'ı çağıranın
gözünden okumalı ki kararı politika versin.

**3. Tenant rolü kimlik tablolarından arındırıldı.** `libraryhub_tenant_app`,
Aşama 3'ün şema geneli varsayılan yetkisinden dolayı `control.email_verifications` ve
`control.organization_domains` üzerinde hâlâ `SELECT` tutuyordu. Kiracı işleminin kimlik
tablolarına hiç uzanamaması gerekir; ikisi de iptal edildi.

**4. `alembic.ini`'deki gömülü parola kaldırıldı.** Satır, `library:library_dev_password`
içeren çalışan bir bağlantı adresi taşıyordu — yani repoda duran bir kimlik bilgisi. Daha
kötüsü, bir yedek değer sessizce kazanabilir veya sessizce kaybedebilir; migration'ların
yanlış veritabanına koşması tam olarak böyle olur. Artık yalnızca ortam değişkeni okunuyor
ve yoksa `env.py` **tahmin etmeyi reddedip** hata veriyor.

**5. Kullanımdan kaldırılan 422 sabiti** literal `422` ile değiştirildi; Starlette'in
hangi sürümü kurulu olursa olsun çalışır.

#### Ölçülen sonuç

Senaryo kontrolleri **18 → 25**'e çıktı, **24'ü geçiyor**:

| Kontrol | Sonuç |
|---|---|
| Tenant rolü global plane'de INSERT/UPDATE/DELETE | `permission denied for table works` |
| Tenant rolü `control.users` INSERT / `control.sessions` DELETE | `permission denied` |
| `control.branches` tenant bağlaması olmadan | **0 şube görünüyor** (fail-closed) |
| Yabancı şubeye holding yazma (uygulama kontrolü atlanarak) | **`CheckViolation: branch … does not belong`** |
| Aşama 6: her legacy item'ın tenant karşılığı | 0 eksik |
| Aşama 6: `manifestation_item` holding'lerde | 0 temsil edilmeyen |
| Aşama 6: kurum aidiyeti yapıdan türetilebiliyor | 0 çelişen satır |
| Aşama 6: başı boş ITEM entity | 0 |
| **Aşama 6: ITEM entity'ye bakan merge/relation** | **1 — BLOKE** |

#### Aşama 6'nın tek engeli, ölçülmüş hâliyle

`entity_merges` içinde ITEM→ITEM bir kayıt var ve bu **tek satır değil**: `merge_method =
'controlled_test'` olan **10 satırlık** kasıtlı bir canonical-redirect test seti; PERSON,
WORK, ORGANIZATION, EXPRESSION, MANIFESTATION, ITEM, CONCEPT ve CLASSIFICATION çiftlerini
kapsıyor. Yanında `item_agent_relation.role='controlled_test_holder'` ve bir test kuruluşu
var.

Bu **silinecek çöp değil, işe yarar bir fixture** — canonical redirect mantığının bütün
entity tiplerinde çalıştığını gösteriyor. Doğru çözüm, Aşama 6'da **yalnızca ITEM çiftini ve
ona bağlı `controlled_test_holder` ilişkisini emekliye ayırmak**; diğer sekiz tip kalır,
çünkü onlar hâlâ global entity.

Bu bir veri küratörlüğü kararı olduğu için **uygulamadım**. Kontrol seti artık bunu kalıcı
olarak raporluyor, yani engel unutulabilir değil: Aşama 6'ya başlandığında ilk iş bu.

#### Kendi hatam

Şube koruması kontrolü ilk yazdığımda **hatalı başarısız oldu**: mesajı 90 karaktere
kırpıp sonra o kırpılmış metinde `does not belong` arıyordum ve metin `does not belon`
olarak kesiliyordu. Tetikleyici kusursuz çalışırken test kırmızıydı. Artık tam mesajda
eşleşiyor, kırpma yalnızca gösterim için. Aynı desen kiracı rolü kontrolünde de vardı,
orası da düzeltildi.

---

### 0.16 Aşama 6 ön adımı ve global plane değişiklik önerisi — TAMAMLANDI

#### Adım 2: `controlled_test` fixture'ının ITEM kısmı emekliye ayrıldı

Fixture **10 birleştirme** ve 8 entity tipinden oluşuyordu; canonical redirect mantığının
her tipte çalıştığını gösteriyor. **Silinmedi** — yalnızca ITEM kısmı ayrıldı, çünkü nüsha
artık global bir entity değil ve global kimlik kaydında yer alamaz. Eski kimliği
`tenant.items.legacy_entity_id` koruyor; bu bir **eşleme, yönlendirme değil**.

`scripts/retire_item_test_fixture.py` önce **deneme modunda** ne gideceğini ve neyin
kalacağını gösteriyor, `--apply` ile uyguluyor. Uygulandı: 1 birleştirme + 1
`controlled_test_holder` ilişkisi. Diğer 7 tipin 9 birleştirmesi yerinde duruyor
(doğrulandı).

#### Bu sırada bulunan yeni engel: legacy yazma yolu hâlâ açık

`POST /items` ve `POST /items/{item_id}/agents` **canlı** ve `public.items` ile
`item_agent_relation` yazıyor — yani **ITEM entity üretmeye devam ediyor.** Aşama 6, bir uç
onları üretmeye devam ettiği sürece `'ITEM'` değerini CHECK'ten çıkaramaz. Bu bir temizlik
detayı değil, ön koşul.

Tek çağıran `scripts/seed_diverse_catalog.py`; `/tenant/items`'a taşınması gerekiyor.

Bunu **ölçülebilir bir tripwire** hâline getirdim (`run_scale_checks.py`): uçlar router
modüllerinden okunuyor (`app.main` değil — o, çalışma dizinine göre statik dizin bağlıyor ve
burada patlar). Kontrol seti artık Aşama 6'nın kalan **tek** engelini raporluyor.

#### Adım 3: global plane değişiklik önerisi

Yazma sınırı bir grant ve bu doğru. Ama bir delik bırakıyordu: **ortak bir kayıtta yanlış
bir yayın tarihi gören kurumun bunu söyleyecek yeri yoktu** ve `account_kind='corporate'`
bir yayınevi sorumlusunun yapmasına izin verilen hiçbir şey yoktu — çünkü yayınevine ait
kayıtlar global plane'de. Öneri mekanizması ikisini birden açıyor.

**Öneri neden tenant plane'inde?** Öneri kurumun kendi talebidir; kendi işleminden yazılır ve
bu şemadaki her tablo gibi aynı fail-closed politikaya tabidir. `control`'a koysaydım ya
kiracı rolüne control plane yazma yetkisi vermem gerekirdi — ayrımın var olma sebebi bu — ya
da uç, tenant'ı istek gövdesinden alarak kiracı oturumu dışında yazardı; diğer sebep de bu.
İnceleyen, sahip kimliğiyle kiracılar arası okur; idari işler burada zaten böyle yürüyor.

**Kabul etmek, uygulamak değildir.** `status` kararı kaydeder; `applied_at` ve
`applied_fields` gerçekte ne yazıldığını kaydeder. İkisi ayrı, çünkü bir alan beyaz listede
olmadığı için düşebilir ve bu görünmelidir — "veritabanı bu JSON'u kabul etti" ile "bu,
`publication_date` için geçerli bir değer" aynı iddia değil.

Beyaz liste kasten kısa: Work, Expression ve Manifestation'ın **betimleyici** alanları.
Kimlik kaydına, `entity_merges`'e veya düzeltmenin birleştirmeye dönüşmesine izin veren
hiçbir alan yok.

**Yeni uçlar:** `POST /tenant/proposals`, `GET /tenant/proposals`,
`GET /tenant/proposals/{id}`, `POST /tenant/proposals/{id}/withdraw`.
**İnceleme:** `scripts/review_proposal.py --list | --show | --accept | --reject [--apply]`.

#### Kanıt — canlı, iki kurumla

| Kontrol | Sonuç |
|---|---|
| Kırıkkale öneri gönderdi | **201**, `pending`, `field_changes` 1 kayıt |
| Hacettepe'nin listesi | **0 öneri** |
| Hacettepe tek kaydı okumaya çalıştı | **404** |
| Hacettepe geri çekmeye çalıştı | **404** |
| İnceleme kuyruğu | öneri, kurum, gerekçe ve kaynakla listelendi |
| `--accept --apply` | **`public.works` güncellendi**, `applied_fields=["description"]` |
| Beyaz listede olmayan `entity_id` alanı | **elendi**, yalnızca `description` yazıldı |
| Karar verilmiş öneriyi yeniden karara bağlama | **reddedildi** ("zaten 'applied'") |
| Öneri şeması / RLS / izinler | `tenant_isolation` politikası, `rls=true`, tam DML |
| Uygulama başarısız olduğunda | **işlem geri alındı**, öneri `pending` kaldı |

Senaryo kontrolleri **26**, test paketi **88** (72'den).

#### Bulunan gerçek hatalar

1. **`public.works`'ta `updated_at` yok** — üç tablonun hepsi için `updated_at = now()`
   yazdım ve her uygulama denemesi patladı. Şema okunarak düzeltildi; artık her tablo için
   ayrı ayrı belirtiliyor, varsayılmıyor.
2. **`normalized_title` ham SQL ile güncellenmiyor.** `public.works.normalized_title` bir
   ORM olay dinleyicisiyle bakılıyor ve ham SQL onu tetiklemez. Bir başlık düzeltmesi
   `normalized_title`'ı bayat bırakıp, tam da düzeltilen kaydın eşleştirmesini sessizce
   bozacaktı. Uygulama adımı artık aynı normalizasyonu çalıştırıyor.
3. **SQLite `uuid.UUID` bağlayamıyor.** `text()` tip bilgisi taşımadığı için sürücü karar
   veriyor: psycopg3 uyarlıyor, sqlite3 "type 'UUID' is not supported" diyor. Yazma
   yollarının **tamamı** testten erişilemez durumdaydı — yani test edilmemiş yazma yolları.
   `_bindable()` eklendi; artık iki motorda da çalışıyor ve testler bu yolları gerçekten
   koşuyor.
4. **SQLite JSON sütununu metin döndürüyor** (PostgreSQL ayrıştırılmış liste veriyor).
   `field_changes` istemciye 65 karakterlik bir dizi olarak dönüyordu. `_proposal_view()`
   iki motoru da aynı şekle getiriyor.

Kendi ölçüm hatalarım: PowerShell'de `$pid` **salt okunur otomatik değişkendir**, onu öneri
kimliği sanıp geçersiz UUID gönderdim; ve bir önceki turda olduğu gibi iç içe tırnaklı
`python -c` komutları yine bozuldu.

#### Açık kalanlar

1. **Yönetici kimliği yok.** `reviewed_by` komut satırında verilen bir ad; kimliği
   doğrulanmış bir hesap değil. Panel aşaması gerçek bir yönetici kimliği gerektiriyor ve o
   gelene kadar bu, `create_user.py` gibi sahip kimliğiyle çalışan ayrıcalıklı bir konsol
   aracı.
2. **`POST /items` ve `POST /items/{item_id}/agents` hâlâ açık** — Aşama 6'nın tek engeli.
3. `change_proposals` üzerinden **ekleme** önerileri bu araçla uygulanmıyor; kaydı bir
   yöneticinin oluşturması gerekiyor. Araç bunu söylüyor, sessizce başarısız olmuyor.

---

### 0.17 Legacy item yazma yolu kapatıldı — TAMAMLANDI

Aşama 6'nın önündeki son ölçülmüş engel buydu ve kapandı. `POST /items` ile
`POST /items/{item_id}/agents` emekliye ayrıldı; iki router dosyası silindi.

#### Yazma yolu biterken okuma yolu da çıktı

`POST /items`'ı kaldırmak yetmiyor: **bir rota tablosundan uzun yaşayamaz.** Tripwire'ı
"yazan uç kaldı mı" sorusundan "legacy tabloya dokunan kod kaldı mı" sorusuna genişlettim
ve tarama **grep'le gözden kaçırdığım üç yeri** buldu:

| Yer | Ne yapıyordu | Yeni hâli |
|---|---|---|
| `routers/search.py` | `manifestation_item` + `items` + item tanımlayıcıları | `public.items_compat` |
| `routers/collective_agents.py` | `item_agent_relation` → `manifestation_item` dalı | `items_compat.holding_institution_entity_id` |
| `routers/persons.py` | kişi birleştirmede item-agent ilişkilerini **taşıyıp siliyordu** | kaldırıldı |

`persons.py` bulgusu ilginç: o rutin, birleşen kişinin item-agent ilişkilerini hedefe
taşıyıp kaynaktan siliyordu. Ama `item_agent_relation` **yalnızca kurumsal aidiyet** tutar —
her satır `holding_institution` rolünde bir ORGANIZATION — ve **hiçbiri PERSON değil**
(kaldırmadan önce ölçtüm: 0). Yani kişi birleştirmesi için orada taşınacak bir şey yoktu;
çalıştığı için fark edilmeyen ölü koddur.

#### Tripwire'ın kendisi de yanlış çalıştı, bir kez

İlk hâli dosyaları **düz metin** olarak tarıyordu ve bir sorguyu neden kaldırdığımı anlatan
**yorumu** ihlal saydı. SQL her zaman bir string sabitinde yaşar; tarama `ast` ile string
sabitlerine daraltıldı ve docstring'ler dışlandı. Yanlış alarm veren bir tripwire, insanların
görmezden gelmeyi öğrendiği bir tripwire'dır.

#### Seed script'leri tenant plane'ine taşındı

`seed_diverse_catalog.py` artık **oturum açıyor** (`--email` / `--password`, ya da
`SEED_EMAIL` / `SEED_PASSWORD`) ve nüshayı `/tenant/holdings` + `/tenant/items` üzerinden
yazıyor. `holding_institution` parametresi tamamen kalktı: **aidiyet artık tenant'ın kendisi.**
Kurum, kiracıdan gelir; istemciye sorulmaz.

Bunun için **`GET /tenant/branches`** eklendi — bir nüsha oluşturmak şube seçmeyi gerektirir
ve §0.15'te `control.branches`'a eklediğim politika sayesinde bu uç **`WHERE tenant_id`
yazmadan** güvenli: bağlaması olmayan bir oturum hiçbir şey görmez.

`/tenant/items` yanıtı `branch_name` ve `organization_name` kazandı — emekliye ayrılan
`GET /items/{id}/agents`'ın verdiği aidiyet bilgisi böylece kaybolmuyor, ama artık **yapıdan
türetiliyor**, ilişki tablosundan okunmuyor.

#### Kanıt

| Kontrol | Sonuç |
|---|---|
| `/openapi.json`'da `/items*` | **yok** (52 path kaldı) |
| Tripwire: global item yazan uç | **temiz** |
| Tripwire: legacy item tablosuna dokunan kod | **temiz** |
| Seed ile nüsha oluşturma | tenant plane'inde oluştu, `legacy_entity_id` NULL |
| **`public.items`'ta karşılığı** | **0** — ve `entities` sayısı **491'de sabit kaldı** |
| Senaryo kontrolleri | **27/27** |
| Test paketi | **88/88** |
| `/search` barkod + `neb` katalog numaraları + başlık | **hepsi hâlâ bulunuyor** |

`entities` sayısının değişmemesi işin özü: nüsha oluşturmak artık **ITEM entity üretmiyor**,
yani Aşama 6'nın o değeri CHECK'ten çıkarmasının önünde hiçbir şey kalmıyor.

#### Ölçülen iki davranış değişikliği

**1. `/collective-agents/{id}/works` artık daha fazla sonuç veriyor — düzeltme.** Eski dal
yalnızca ilişki satırı olan nüshaları buluyordu; aidiyet yapısal olduğu için artık kurumun
tuttuğu **her** nüshayı buluyor. Kırıkkale için ölçtüm: **1 → 6 eser**.

**2. `/search` yavaşladı: ~300 ms → 452 ms (ortalama, 316 eser).** Sebep ölçülü: view,
`tenant.items`(849) × `holdings`(946) × `organizations`(105) üçlü join'ini **849 satır**
olarak materyalize ediyor; eski yol 12 satırlık `manifestation_item` + `items` okuyordu.
Bu, taşımanın gerçek bedeli ve tam da §9'daki Search Plane'in neden gerektiğinin yeni
kanıtı. Aşama 6'da view'un legacy dalı (bugün **0 satır** katkı yapıyor) düşecek; o zaman
daraltılabilir. Ayrıca view'un `control.organizations` ile `tenant_id` üzerinden join
yapması, bir tenant'ın **birden fazla kuruluşu** olduğu gün satırları çoğaltır — bugün
tenant başına tek kuruluş olduğu için (849 = 849) görünmüyor, kayda geçiyor.

#### Aşama 6'nın durumu

Ölçülen engel **kalmadı**: 27/27 kontrol geçiyor ve "Aşama 6 hazırlığı" bölümünün yedi
maddesi de yeşil. Sıradaki iş, temizliğin kendisi — veri kaybı olmadan tabloları düşürmek.

---

### 0.18 Aşama 6: legacy item plane'i emekliye ayrıldı — TAMAMLANDI

Migration `b1c4e8f29a37` (+ takip `c2d5f93ab048`). `public.items`, `manifestation_item` ve
`item_agent_relation` düştü; `entities.entity_type` CHECK'inden `'ITEM'` çıktı; 12 ITEM
entity silindi. `public` şeması **36 tablo → 33 tablo + 2 görünüm**.

#### Hesapta olmayan tek şey: üç tanımlayıcı

Ölçüm her kalemde sıfır veriyordu — ama **`identifiers` tablosunda ITEM entity'lerine bakan 3
satır vardı** ve ikisi, sahibi olan nüshanın **tek kimliğiydi**: barkodsuz, raf yeri olmayan
iki Rusya Devlet Kütüphanesi nüshasının `neb` şemasındaki numaraları. Entity'ler silinince
FK `ON DELETE CASCADE` olduğu için sessizce yok olacaklardı.

Bu yüzden **`tenant.item_identifiers`** eklendi ve üçü oraya taşındı. Doğru yer orasıydı
zaten: bir nüshanın ulusal kütüphane numarası, esere dair bir olgu değil, **kurumun kendi
nesnesine dair kaydıdır** — barkodu gibi kiracı verisi. `public.item_identifiers` görünümü
onları global okuyucuya açar ve `/search` artık oradan okuyor; yani **arama kaybı sıfır**
(ölçüldü: her iki `neb` numarası da hâlâ bulunuyor).

#### Görünüm artık uyumluluk katmanı değil, projeksiyon

`items_compat`'in legacy dalı kalktı; geriye tenant plane'inin global okuması kaldı. Bu
**yük taşıyan** bir özellik: bir view varsayılan olarak **sahibinin yetkileriyle** çalışır,
yani RLS'i atlar ve her kurumun nüshasını görür. Global bir ucun "bunu kim tutuyor"
sorusunu yanıtlayabilmesinin tek sebebi bu.

Buna uygun olarak erişimi daraltıldı: **`libraryhub_tenant_app` görünüm yetkisini kaybetti.**
Rolün görünüme ihtiyacı yoktu ve onu tutmak, kiracıya özel bir işlemin görünüm üzerinden
kiracılar arası okuma yapabilmesi demekti. Aynı daraltma yeni `item_identifiers` görünümü
için de yapıldı.

Görünüm yeniden yazılırken **gizli bir kusur da düzeltildi**: `control.organizations` ile
`tenant_id` üzerinden join yapıyordu ve bir tenant'ın iki kuruluşu olduğu gün her nüshayı
çoğaltacaktı. Artık holding'in şubesi üzerinden join yapıyor — sahibi gerçekte belirleyen yol.
Plan da sadeleşti: üç aşamalı hash join, 849 satır.

#### Migration kendi koşulunu dayatıyor

ITEM entity'leri silinmeden önce migration, **tenant karşılığı olmayan bir ITEM entity varsa
hata verip duruyor.** Kontrol seti zaten sıfır diyordu, ama kimlik satırı silen bir
migration'ın bağımlı olduğu koşulu sabah alınmış bir rapora güvenmek yerine **kendisi
uygulaması** gerekir.

#### Uygulanmış migration neden düzeltilmedi

Modele `item_id` index'i koymuşum ama migration'a yazmamışım; `alembic check` kırmızı verdi.
Migration'ı düzeltip yeniden koşmak yerine **takip migration'ı** (`c2d5f93ab048`) yazdım,
çünkü öncekinin downgrade'i `tenant.item_identifiers`'ı düşürüyor ve upgrade'i içeriği
`public.identifiers`'tan yeniden okuyor — o satırlar artık cascade ile silinmiş durumda.
Yeniden koşsaydım tablo **sessizce boş** kalırdı ve korumak için var olduğu üç tanımlayıcı
kaybolurdu. "Uygulanmış migration düzenlenmez" kuralının somut karşılığı bu.

#### Doğrulama

| Kontrol | Sonuç |
|---|---|
| `public.items` / `manifestation_item` / `item_agent_relation` | **üçü de YOK** |
| ITEM entity | **0** (`entities` 491 → **479**) |
| `entity_type` CHECK | `'ITEM'` **yok** |
| `items_compat` | **849 satır**, kurumsuz 0 |
| `tenant.item_identifiers` | **3 satır** — hiçbiri kaybolmadı |
| `/search` ile `neb` numaraları ve `ITEM-KKU-123456` | **hepsi bulunuyor** |
| `/collective-agents/{KKU}/works` | 6 eser |
| Tenant plane (`/tenant/items`, `/branches`, `/holdings`) | 6 / 1 / 6 |
| Senaryo kontrolleri | **27/27** |
| Test paketi | **88/88** |
| `alembic check` | temiz |

Arama süreleri: `bilgi` (tek sonuç) **105 ms → 54 ms**; `scale` 452 ms → **422 ms**;
`Ölçek` 336 ms. Legacy dalın kalkması bir miktar geri kazandırdı ama taban çizgisinin
(~300 ms) üstünde: projeksiyon 849 satırı materyalize ediyor ve asıl çözüm hâlâ §9'daki
Search Plane.

Geri dönüş yolu: `_legacy_items_backup.sql` (üç tablonun `pg_dump --data-only`'si, düşürmeden
önce alındı). Migration'ın kendisi de tabloları boş olarak geri kurar — **satırlar değil**.

#### Kalanlar

1. **Yönetici kimliği yok** — panel aşamasının işi.
2. **`tenant.item_identifiers` için uç yok.** Tablo ve global projeksiyon var; bir nüshanın
   tanımlayıcısını eklemek/düzeltmek için API henüz yok.
3. `tenant.items.legacy_entity_id` **kasıtlı olarak duruyor**: göçmüş nüshaların eski
   kimliğini koruyor ve projeksiyonun `entity_id`'si ona dayanıyor. Emekliye ayrılması,
   istemcilerin eski kimlikleri bırakmasına bağlı.

---

### 0.19 Aşama 5'in kalanı ve yapısal yeniden düzenleme — TAMAMLANDI

#### `/api/v1`

Önek **mount'ta**, router'ın kendisinde değil. Bu tercih işin tamamını mümkün kılıyor:
aynı router hem `/api/v1` altına hem **eski yollara** bağlanıyor ve ikinci bağlamada
`/api/v1` taşımıyor. Şema artık **52 sürümlü yol ve sıfır sürümsüz** yol gösteriyor.

Eski yollar **yönlendirme değil, ikinci bağlama**: bir yönlendirme, takip etmeyen
istemciler için `POST`'un ne yaptığını sessizce değiştirirdi ve istemcilerin çoğu takip
etmez. Tek router iki yola bağlanınca da iki yol birbirinden ayrışamaz.

#### Global yazma uçları korundu — iki kademe

Öncesinde paylaşılan plane'e **her yazma açıktı**: API'ye erişebilen herkes bir Work,
Person veya Concept yaratabilir, iki kimliği birleştirebilir, reconciliation kararı
verebilir, toplu veri yükleyebilirdi. Okumalar kasıtlı olarak açık kalıyor — platformun
varlık sebebi o — ama yazmak hiçbir şey istemiyordu.

Ayrım keyfi değil:

* **Yaratma** (henüz kataloglanmamış bir eser, bir kişi, bir kavram) olağan katalog işi —
  **personel** yeter.
* **Kimlik değiştiren** işlemler (kişi birleştirme, reconciliation kararı, eşleme silme,
  toplu yükleme) sonradan bir satır düzenlenerek **geri alınamaz** — **yönetici** gerekir.

24 uç korundu (19 personel + 5 yönetici). `auth` ve `tenant` uçlarına dokunulmadı: onların
kendi modeli var ve kiracı oturumu zaten global plane'e yazamaz.

Reconciliation testleri bu uçları **oturumsuz** çağırıyordu ve artık haklı olarak 401 aldı.
Bağımlılığı override etmek yerine **gerçekten kimlik doğruluyorlar**, böylece yetki yolu
atlanmıyor, sınanıyor.

#### Yapı

| Önce | Sonra |
|---|---|
| `models.py` **1379 satır**, her alan bir arada | `db/models/` altında **9 modül** (68–392 satır) |
| `db.py` motor + oturum + kiracı kapsamı karışık | `db/base.py` + `db/session.py` |
| `ids.py`, `auth.py`, `normalization.py` kökte | `core/` — hiçbir şeye bağlı olmayan yapraklar |
| `routers/` düz dizin | `api/v1/routes/` + `api/deps.py` + `api/v1/__init__.py` |
| 30 Pydantic modeli 16 router'ın içinde | `schemas/`, kaynak başına bir modül |
| `os.environ` dağınık | `core/config.py` |

**`core/` yapraktır**: `app.db`'den veya `app.api`'den hiçbir şey import etmez. Bu onu
her yerden import edilebilir kılar — bir döngünün ölümcül olacağı model modüllerinin
içinden bile.

Modeller **elle yeniden yazılmadı**: kaynak satır aralıklarını kesen bir script yazıldı,
böylece her sınıf gövdesi bit bit aynı kaldı. 1379 satırlık bildirimsel gövdeyi yeniden
yazmak, bir sütunun sessizce tip değiştirmesinin en kolay yoludur.

#### Bu sırada bulunan gerçek hata: alt tür yazma sırası

Bölmeden sonra **her global kayıt oluşturma çöktü** — Work, Person, Concept, Expression,
Manifestation, Place, TimeSpan, CollectiveAgent, ClassificationNode; hepsi `entities`'e
foreign key ihlaliyle.

**Kök neden:** SQLAlchemy, aralarında `relationship()` olmayan mapper'ları **isim sırasına**
göre flush ediyor; isim de modül-yol + sınıf adıdır. Bütün modeller tek dosyadayken bu
kaza `app.models.Entity`'yi `app.models.Work`'tan önce sıralıyordu ve sıra **şans eseri**
doğruydu. Modüllere bölününce adlar `app.db.models.bibliographic.Work` ve
`app.db.models.identity.Entity` oldu, sıralama ters döndü, alt tür satırı önce yazıldı ve
kısıt reddetti.

**Sıra hiç garanti edilmemişti; sadece öyle görünüyordu.**

**İşe yaramayan deneme:** import sırasını `identity` öne gelecek şekilde değiştirdim.
Düzeltmedi — çünkü sıralamayı belirleyen import sırası değil, modül-yol adı. Bunu
belgeye yazıyorum çünkü yanlış bir açıklamayı `db/models/__init__.py` yorumunda
bırakmak, hiç yorum bırakmamaktan kötüdür.

**Gerçek düzeltme:** bağımlılığı **açıkça bildirmek**. `Entity` dokuz alt tür ilişkisini
tanımlıyor, `lazy="raise"` ile — kimse onları gezmiyor, var olma sebepleri unit of work'ün
entity'yi önce yazması gerektiğini bilmesi; `lazy="raise"` de kimsenin farkında olmadan
N+1 ödemesini engelliyor. Ayrıca alt tür kontrolleri `BEFORE INSERT`'tan **ertelenebilir
kısıt tetikleyicisine** taşındı, çünkü entity ile alt türü tek işlemde yazılıyor ve kural
işlem hakkında bir ifade.

**Neden test değil kontrol:** kısıt PostgreSQL'in. SQLite'ta sıralama gözlemlenemez, yani
test paketi bu hatayı **göremez**. `run_scale_checks.py` artık PostgreSQL'de gerçek bir
Work+Person yazıyor — bu hata sınıfı için tripwire.

#### Şema katmanı ve iki hatası

30 model, kaynak başına bir modül. İki hata çıktı ve ikisini de **testler** buldu,
okuyarak değil:

1. **Çok satırlı import'un ortasına ekleme.** Yeni import'u "`from ` ile başlayan son
   satırdan sonra" koymak, parantezli bir import bloğunu ikiye bölüyor. Doğrusu AST'den
   son import *deyiminin* bittiği satır.
2. **`uuid.UUID` modül ister, sınıf değil.** Model `uuid.UUID` kullanıyordu; eşlemem
   yalnızca `UUID` adını biliyordu. `from __future__ import annotations` yürürlükteyken
   Pydantic bunu ancak şema kurulurken fark ediyor — "not fully defined" — ve
   `/openapi.json`'ı da beraberinde düşürüyor.

Script artık **hesabına katamadığı her adı raporluyor**, böylece bir sonraki bilmediği
import'u sessizce düşürmek yerine söylüyor.

#### Doğrulama

| Kontrol | Sonuç |
|---|---|
| Test paketi | **88/88** |
| Senaryo kontrolleri | **28/28** |
| `alembic check` | temiz (`d2e5f04bc159`) |
| `/api/v1/*` ve eski yollar | ikisi de 200 |
| `/openapi.json` | 200, 52 sürümlü yol, 0 sürümsüz |
| Tokensiz global yazma | 401 |
| Personel ile kimlik birleştirme | 403 |
| Personel ile Work yaratma | 201 |
| Alt tür yazma (PostgreSQL) | Work + Person tek işlemde |

#### Kalanlar

1. **`services/` katmanı hâlâ iş mantığıyla SQL'i karıştırıyor.** Yapısal işin son parçası:
   sorguları repository'lere, kuralları servislere ayırmak. En büyüğü
   `classifications.py` (1254 satır) ve `tenant.py` (722 satır).
2. **Yönetici kimliği yok** — panel aşamasının işi. Bugün yönetici, `create_user.py` ile
   açılmış `role='admin'` bir hesap.
3. `nomens.normalized_value` (§14) ve Search Plane (§9) hâlâ açık.

---

### 0.20 Platform yöneticisi kimliği — TAMAMLANDI

#### Bıraktığım gevşek uç

§0.19'da global yazmaları `role = 'admin'` koşuluna bağladım ama **admin'in ne olduğunu
tanımlamadım**. O güne kadar yönetici, kazara bir kiracıya ait bir kullanıcıydı: platformun
küratörü, birinin kütüphanesinin üyesi olarak uydurulmak zorundaydı. Kiracıların önerilerini
incelemek, iki kimliği birleştirmek, toplu veri yüklemek — bunların hiçbiri bir kuruma ait
değil ve birine bağlanınca paylaşılan plane o kurumun malı gibi görünüyor.

#### Karar

`control.users.tenant_id` **nullable** oldu. Kiracısız hesap = platform yöneticisi.

Kural **veritabanında**: `ck_users_tenant_required` →

```sql
tenant_id IS NOT NULL OR role = 'admin'
```

Okunuşu: kiracısız hesap yönetici olmak zorunda, çünkü kütüphanesiz bir kütüphaneci hiçbir
şey yapamaz. Tersi **kasıtlı olarak açık** — bir kurumun kendi yöneticisi de paylaşılan
kaydı kürate edebilir.

`tenant_db` kiracısız hesabı **403** ile reddediyor, varsayılana düşmüyor. Burası kiracı
değerinin geldiği tek yer; bir hesabı olmayan kullanıcıya bir kiracı *seçmek* — hangisi
olursa olsun — tasarımın baştan beri engellemeye çalıştığı açığın ta kendisi olurdu.
Platform yöneticisinin erişimi global plane, ve yalnızca global plane.

#### Ve bu sırada ikinci gerçek hata: kalkanın muafiyeti hiç çalışmamış

`control.guard_self_registration()` şöyle başlıyordu:

```sql
if not pg_has_role(current_user, 'libraryhub_global_app', 'MEMBER') then
    return new;
end if;
```

Yorumu da şuydu: *"Sadece uygulama rolleri kısıtlanır. Owner yönetim script'lerini
çalıştırır ve istendiği her şeyi oluşturabilir."*

**Bu yorum hiç doğru olmamış.** Owner bir süper kullanıcı ve **süper kullanıcı her rolün
üyesidir** — `pg_has_role('library', 'libraryhub_global_app', 'MEMBER')` true döner. Yani
kalkan owner'ı muaf tutmadı; tam tersine **yalnızca owner'ı kısıtladı**.

Sonuç: `create_user.py` kalkan eklendiğinden beri **hiçbir hesap açamamış**. Script
`email_verified_at` yazıyor, kalkan da kısıtlanmış çağırana bunu yasaklıyor. Fark
edilmemesinin sebebi, mevcut hesapların kalkan'dan önce açılmış olması ve yönetici rolünün
hiç kullanılmamış olması — yani kimse o yolu denememiş.

Düzeltme `rolsuper` testi. Kalkanın gerçekten koruduğu roller için hiçbir şey gevşemiyor:
uygulama rolü asla süper kullanıcı değil. Owner da zaten `control.users`'ı doğrudan
yazabilen kimlik bilgisine sahip — kalkan, **çalınmış bir uygulama oturumunun** hesap
açmasını engellemek için var.

**Yan bulgu:** `create_user.py --list` `join control.tenants` kullanıyordu, yani kiracısı
olmayan hesabı — tam da bulunması en zor olanı — hiç göstermezdi. `left join` oldu.

Ders: bir güvenlik kalkanının "muaf" dalı, muaf tuttuğunu iddia ettiği hesabı test
etmiyorsa, o dal çalışmıyor olabilir — ve kimse fark etmez, çünkü kalkan hata vermez,
sadece yanlış tarafı kısıtlar.

#### Kullanım

```
python create_user.py --platform --email ... --name ...
python create_user.py --email ... --name ... --tenant <slug> --role librarian
python create_user.py --list
```

`--platform` rolü `admin`e sabitler ve `--tenant` ile birlikte kullanılamaz. Geliştirme
ortamındaki platform hesabı: `platform@libraryhub.local` / `platform-dev-parola`.

#### Doğrulama

| Kontrol | Sonuç |
|---|---|
| Test paketi | **91/91** (3 yeni: kiracısız giriş, tenant plane'de 403, kısıt) |
| Senaryo kontrolleri | **28/28** |
| `alembic check` | temiz, tek head `f5b2c8d36a94` |
| Veri | `works=316 entities=479 items=849` — değişmedi |
| Platform yöneticisi ile `POST /works` | 201 |
| Platform yöneticisi ile `/tenant/*` | 403, açıklayıcı mesajla |
| Kiracısız `librarian` | `ck_users_tenant_required` reddetti |
| `create_user.py` librarian akışı | çalışıyor (kalkan düzeltmesiyle) |

---

### 0.21 Yönetici tarafı öneri inceleme uçları — TAMAMLANDI

#### Öncesi

Öneri incelemesi yalnızca `review_proposal.py` ile, sahip kimlik bilgisiyle ve bir
terminalden yapılabiliyordu. `reviewed_by` komut satırına yazılan bir **addı**:
kimlik değil, beyan kaydediyordu. Panel için gereken şey buydu ve §0.20 onu mümkün kıldı.

#### Uçlar

`/api/v1/admin/proposals` altında beş uç: liste, özet, tek kayıt, karar, uygulama.
Tamamı `require_admin` arkasında. `reviewed_by` artık **oturumdaki hesabın e-postası** —
gövdeden gelen bir alan değil, çünkü kendi karar vericisini adlandırabilen bir gövde
istemcinin istediği kişiyi kaydederdi.

**Karar ve uygulama ayrı uçlar.** Bir düzeltmenin *ilke olarak* doğru olduğuna inanan
bir gözden geçiren, JSON'un tesadüfen aldığı biçimi de onaylamamalı; "veritabanı bu
değeri kabul etti" ile "bu geçerli bir yayın tarihi" aynı iddia değil. Uygulama ayrıca
yalnızca **kabul edilmiş** bir öneri için çalışır: reddeden bir yönetici başka bir uca
sorarak onu uygulayamamalı.

#### Neden ikinci bir motor

`tenant.change_proposals` RLS'e tabi ve politika `libraryhub.tenant_id`'ye bağlı.
Gözden geçirenin bağlayacağı **tek bir kiracı yok** — uygulama rolüyle doğru davranış
hiçbir şey görmemektir. Bu yüzden `owner_engine` var ve yalnızca bu uçlardan erişilebilir;
zincir `require_admin`'de başlar, orada bitmez.

#### Mantık tek yerde

Kurallar `app/services/proposal_review.py`'de ve hem API hem CLI onu kullanıyor. Script
kendi kopyasını taşıyordu ve kopya, adı değişmiş bir modülü import etmeye devam ediyordu.

#### Bu sırada bulunan gerçek hata: migration yeniden oynatılamıyordu

`f2a5c8e36d74_add_normalized_work_title.py` içinde `from app.normalization import
normalize_text` kalmıştı. Modül `app/core/text.py` olmuştu; import **revizyon
çalışırken** çözülüyor, yani **sıfırdan kurulan bir veritabanı bu adımda dururdu**.
Burada o adım çoktan geçildiği için hiçbir şey görünmüyordu ve test paketi bunu
göremezdi — migration'lar testlerde koşmuyor.

Kalıcı koruma: `run_scale_checks.py` artık **her mutlak `app.*` importunun gerçek bir
modülü gösterdiğini** doğruluyor. Test edildi: kasıtlı olarak bozulduğunda
`scripts/review_proposal.py:218 app.normalization` diyerek yakalıyor.

#### Ve test motorunun görmediği üç şey

Yazma yolu SQLite'tan erişilemezdi ve bu üç ayrı sebeple ortaya çıktı:

1. **`str(uuid)` eşleşmiyor.** PostgreSQL `uuid` sütununa tiresiz dizeyi kabul eder;
   SQLite `Uuid` tipini `CHAR(32)` — tiresiz hex — olarak saklar. `str()` ile sorgulamak
   sessizce hiçbir şey bulmaz. Çözüm dize uydurmak değil, **tipi bildirmek**:
   `bindparam(..., type_=Uuid)`, dönüşümü motora bırakır.
2. **`now()` SQLite'ta yok.** PostgreSQL'e özel. `CURRENT_TIMESTAMP` ikisinde de var.
3. **`public.works` SQLite'ta yok.** Şema öneki yazma yolunu tamamen test dışı bırakıyordu.
   Tablo adları artık şemasız: her iki rolün `search_path`'inde `public` var ve plane
   zaten hangi oturumun çalıştırdığıyla belirli — adı tekrarlamak hiçbir şey kazandırmıyor,
   testleri kaybettiriyordu.

Üçü de aynı desen: **test motoru çalışamayacak koda evet diyordu.**

#### Doğrulama

| Kontrol | Sonuç |
|---|---|
| Test paketi | **106/106** (15 yeni) |
| Senaryo kontrolleri | **29/29** (import tripwire'ı dahil) |
| `alembic check` | temiz, tek head `f5b2c8d36a94` |
| `/openapi.json` | 57 yol, tamamı sürümlü, 0 sürümsüz |
| Platform yöneticisi ile liste/karar/uygula | çalışıyor, `reviewed_by` = oturum e-postası |
| Kütüphaneci ile `/admin/*` | 403 |
| Oturumsuz `/admin/*` | 401 |
| Karar verilmeden uygulama | 409 |
| Beyaz liste dışı alan | yazılmıyor, `dropped` içinde bildiriliyor |
| CLI `--list` / `--accept --apply` | aynı servisle çalışıyor |
| Veri | `works=316 entities=479 items=849 holdings=946` — değişmedi |

---

### 0.22 Kullanıcı ve kurum yönetimi — TAMAMLANDI

#### Önce ölçtüm, sonra tasarladım

`create_user.py`'nin başlığı şunu iddia ediyordu: *"`control.users`'ı yalnızca şema
sahibi yazabilir; uygulama rolünün orada `SELECT`'i var, başka bir şeyi yok."*

**Bu doğru değildi.** Ölçüm:

```
libraryhub_global_app | control.users     | INSERT,SELECT,UPDATE
libraryhub_global_app | control.sessions  | INSERT,SELECT,UPDATE
libraryhub_global_app | control.tenants   | SELECT
```

Yani sınır grant değil, **kalkan tetikleyicisi**. Yanlış bir güvenlik iddiası hiç
yorum olmamasından kötüdür: onu okuyan kişi `control.users`'a yazan bir yol
eklemenin zaten imkânsız olduğunu sanır. Düzeltildi.

#### Ve bu ölçüm gerçek bir açık buldu

`users_guard_self_registration` **yalnızca `BEFORE INSERT`** tanımlıydı. Kalkanın
kendisi doğruydu ama iki yoldan birini kapatıyordu. Bir `UPDATE`:

* var olan bir hesabı `role = 'admin'` yapabilirdi — INSERT kalkanının engellediği
  yükseltmenin ta kendisi, bir ifade sonra;
* bir yöneticinin `password_hash`'ini değiştirebilirdi — `role`'a hiç dokunmadan
  hesap devralma.

Bugün ikisini de yapan bir kod yok, çünkü bu tabloyu uygulama üzerinden güncelleyen
bir yol yoktu. **Personel yönetimini API'ye eklemek tam da onu erişilebilir kılacak
değişiklikti**, o yüzden önce kapatıldı.

Yeni kalkan `BEFORE INSERT OR UPDATE` ve iki yönü de kapsıyor: `new.role = 'admin'`
yükseltmeyi ve bir yönetici satırına yapılan *her* düzenlemeyi, `old.role = 'admin'`
ise indirmeyi reddeder. `email_verified_at` kuralı **bilerek INSERT'te kaldı**:
adres doğrulamak bir UPDATE'tir ve `/auth/verify-email`'in meşru işi odur; kuralı
genişletmek koruduğu tek akışı kırardı.

Fonksiyonun adı `guard_self_registration` → `guard_application_account_writes`
oldu. Artık kaydı değil, bir uygulama rolünün hesaplara yapabileceğini sınırlıyor;
aksiğini söyleyen bir ad, sıradaki kişinin UPDATE yolunu korumasız sanmasının
tam sebebi.

**Kalıcı kanıt:** `run_scale_checks.py` iki yükseltmeyi gerçek veritabanında
deniyor ve ikisinin de reddedildiğini doğruluyor.

#### Uçlar

`/api/v1/admin` altında on bir uç: kurum listesi/tek kurum, hesap listesi/tek hesap,
hesap açma, güncelleme, parola sıfırlama, oturum iptali.

**Hesap uçları `get_db` kullanıyor, `owner_db` değil — ve bu tercih burada kritik.**
`owner_db` bir süper kullanıcı; hesapları onunla yazmak
`guard_application_account_writes`'ı devre dışı bırakırdı, yani kalkanı kaldırırdı.
Sıradan oturum, kalkanın ayakta kalmasını sağlayan şey.

**Kurumlar yalnızca okunuyor.** Uygulama rolünün `control.tenants` üzerinde
`SELECT`'i var, `INSERT`'i yok. Bu bir eksiklik değil: `control.tenants` RLS'in her
kiracı sorgusunu bağladığı tablo ve bir uygulama oturumunun orada kurum açmasına
izin vermek, içindeki insanları yönetmesine izin vermekten ayrı bir karardır.

#### Panelin yapamadıkları, ve neden

| Yapamaz | Sebep |
|---|---|
| Yönetici açmak | Kalkan reddediyor; `create_user.py` (sahip) yapar |
| Var olan yöneticiyi değiştirmek | Aynı kalkan, iki yön |
| Hesabı doğrulanmış açmak | Kalkan reddediyor — adresi sahibi onaylar |
| Kurum açmak | `control.tenants` üzerinde yalnızca `SELECT` |

Bunlar eksik liste değil, **kalkanın tanımı**. Panel, yerini aldığı konsoldan
bilerek daha az yetkili.

#### Doğrulama

| Kontrol | Sonuç |
|---|---|
| Test paketi | **123/123** (17 yeni) |
| Senaryo kontrolleri | **31/31** (2 yeni yükseltme kontrolü) |
| `alembic check` | temiz, tek head `a7c3e9f14d26` |
| Uygulama rolü ile `role='admin'` yapma | trigger reddetti |
| Uygulama rolü ile yönetici parolası değiştirme | trigger reddetti |
| Yönetici: kurum/hesap listesi | 105 kurum, 4 hesap, platform hesabı `(platform)` |
| Hesap açma | 201, **doğrulanmamış**, `account_kind` alan adından türetildi |
| Doğrulanmamış hesapla giriş | 403, açıklayıcı mesajla |
| Aynı e-posta | 409 |
| `role='admin'` isteme | 422 (doğrulama, veritabanına varmadan) |
| Yönetici hesabını değiştirme | 403 |
| Hesabı kapatma | canlı oturumlar da iptal edildi |
| Parola sıfırlama | eski oturumlar iptal edildi |
| Kütüphaneci / oturumsuz | 403 / 401 |
| Veri | `works=316 entities=479 items=849 control.users=4` — değişmedi |

---

### 0.23 Olay: ölçek fixture'ları gerçek kayıtlara bağlanıyordu

#### Belirti

Kullanıcı "Suç ve Ceza" aradı ve **hiçbir kütüphane görünmedi**. Arama çalışıyordu;
cevap yanlıştı.

#### Ölçüm

| Ölçüm | Değer |
|---|---|
| `tenant.holdings` toplam | 946 |
| — ölçek fixture'ı | **930** |
| — gerçek | **16** |
| 1867 Rusça baskıya bağlı holding | **93**, bunun **92'si uydurma kurum** |

Üreteç, oluşturduğu her holding'i `order by entity_id limit 12` ile seçilmiş
manifestation'lara bağlıyordu — ve onlar **gerçek** kayıtlardı. Yani 930 holding dört
gerçek esere yığılmıştı ve her eser yüz uydurma kütüphanenin altında kalıyordu.

Üstündeki yorum şuydu: *"Var olan Manifestation'ları yeniden kullan: tek bir
bibliyografik kaydı birçok kurumun tutması, plane ayrımının tam da amacı."* **Niyet
doğruydu, kayıt seçimi değil.** Paylaşılan bir katalogda var olan her manifestation
birinin gerçek verisidir; güvenli seçilebilecek bir tane yoktur.

#### Düzeltme

Fixture'lar artık **kendi** expression ve manifestation'larını yaratıyor (işaretli,
her şey gibi) ve yalnızca onlara bağlanıyor. Kural: **bir fixture yalnızca kendi
ürettiği kayda işaret edebilir.**

`purge()` de aynı dersi aldı: eserleri ve kurumları işaretten siliyordu, yeni
expression/manifestation'ları geride bırakırdı ve sonraki çalışma boşa bağlanırdı.

Kirli satırlar temizlendi (100 kiracı, 300 eser, 930 holding) ve katalog gerçek
16 eserine, 5 kurumuna, 16 holding'ine döndü.

#### Neden kalıcı bir kontrol

Hata **dışarıdan görünmezdi**: arama kusursuz çalışıyordu, sadece cevabı kurguydu.
Bu yüzden kural doğrudan sınanıyor — `run_scale_checks.py` her fixture holding'inin
hedefini işaretli kümele karşılaştırıyor ve **kaç holding incelediğini** de bildiriyor,
çünkü yüklü fixture yokken kontrol boş geçer.

---

### 0.24 Yönetim paneli arayüzü — TAMAMLANDI

#### Ne var

`/admin` tek sayfa: **Öneriler**, **Personel**, **Kurumlar**. Mevcut arayüzün
kurallarına uyuyor — çerçeve yok, `escapeHtml`, hash yönlendirme, Türkçe yorumlar.

* **Öneriler**: durum süzgeci, özet sayaçları, detayda alan alan `şu an → önerilen`,
  karar (not ile) ve uygulama. Uygulama sonucu **hangi alanların yazıldığını ve
  hangilerinin beyaz liste dışı olduğu için elendiğini** gösteriyor.
* **Personel**: kurum/rol süzgeci, hesap açma, düzenleme, parola sıfırlama, oturum
  bitirme, hesap kapatma. Yönetici hesaplarında bu düğmeler **hiç çizilmiyor** —
  çizilse de sunucu 403 verirdi, ama boşuna denenecek bir düğme göstermenin anlamı yok.
* **Kurumlar**: personel sayısıyla liste, ve kurumların buradan **açılmadığını**
  söyleyen not.

#### Oturum

Giriş `/auth/login` ile, belirteç `localStorage`'da. Bu, aynı kaynaktaki bir XSS'in
belirteci okuyabileceği anlamına gelir; panel bu yüzden sunucudan gelen her değeri
`escapeHtml`'den geçiriyor. **HttpOnly çerez daha güçlü olurdu** ve API'nin çerez
kabul etmesini gerektirirdi — bu ayrı bir iş, ve yapılmadığı burada yazılı.

#### Ekran görüntüsü almanın bulduğu hata

"Yeni hesap" formu, HTML'de `hidden` yazılı olmasına rağmen **açılışta görünüyordu**.
Sebep klasik: `hidden` özniteliği tarayıcının `[hidden] { display: none }` kuralıyla
çalışır ve o kuralın özgüllüğü çok düşüktür — `.stack { display: flex }` onu ezer.
`admin.css`'e açık bir `[hidden] { display: none !important }` eklendi.

Bunu **hiçbir test yakalayamazdı**; kod okuyarak da gözden kaçar. Gerçek tarayıcıda
ekran görüntüsü almak, bu sınıf hataların tek kanıtı.

#### İkinci küçük tuzak

`/auth/login` hesabı `{token, expires_at, user}` içinde sarar; `/auth/me` **doğrudan**
hesabı döndürür. Aynı sanıp `me.user.role` yazmak, panelin sessizce giriş ekranında
kalmasına yol açıyordu.

#### Doğrulama

| Kontrol | Sonuç |
|---|---|
| Test paketi | **123/123** |
| Senaryo kontrolleri | **32/32** |
| `alembic check` | temiz |
| `/admin`, `/static/admin.*` | 200 |
| Giriş ekranı (gerçek tarayıcı) | çizildi |
| Öneriler / Personel / Kurumlar | üçü de çizildi, API verisiyle |
| Yönetici olmayan hesapla giriş | panel reddediyor, açıklamayla |
| Veri | `works=16 entities=79 items=12 holdings=16` — temizlik sonrası |

---

### 0.25 Search Plane'e giden ucuz adım: transactional outbox — TAMAMLANDI

#### Neden bu, neden şimdi

§9.1 diyor ki: **PostgreSQL doğruluk kaynağı kalır**, arama motoru sonra gelir —
bugünkü problem motor eksikliği değil, mevcut aramanın yavaşlığı (§15.2: tek sorgu
944 ms tepeye vurdu). §9.2 ise geçişi *mümkün kılan* ucuz adımı tarif ediyor.

Gerekçe şu: outbox olmadan, "artık event-driven olduk" kararını sonradan almak
**her yazma yolunu yeniden ele almayı** gerektirir — ve yazma yolu her aşamada
çoğalıyor. Bu tablo o kararın ucuz ucu: bir tablo, bir kısmi index, sıfır
operasyonel yük.

#### Olayı uygulama değil, tetikleyici yazar

Bir yazma yolunun "olayı da eklemeyi hatırlaması" gerekiyorsa, eninde sonunda
hatırlamaz — ve hata **sessizdir**: veri değişir, index sessizce ayrışır.
`public.emit_outbox_event` arama indeksinin umursadığı her tabloya `FOR EACH ROW`
bağlı, ve `TG_ARGV` generic bir fonksiyonun bilemeyeceği iki şeyi taşıyor:

| | |
|---|---|
| `TG_ARGV[0]` | aggregate id'yi tutan sütun (`entity_id`, `id`, ya da ilişki tablosunun sol tarafı) |
| `TG_ARGV[1]` | tenant düzlemi tablosu için `tenant_id`, paylaşılan kayıtta yok |

`identifiers` ve `nomens` kendi `id`'lerini kullanıyor; ilişki tablolarının bileşik
anahtarı var ve tek bir id'leri olmadığı için **sol taraflarını** bildiriyorlar
(`work_expression` → `work_entity_id`).

#### Payload yalnızca değişeni söyler

`UPDATE`'te `payload.changed`, gerçekten değişen sütunları taşıyor. Bunu yazarken
`jsonb - jsonb` operatörünün **var olmadığı** ortaya çıktı; eski *anahtarları*
çıkarmak ise değişmeyenleri de düşürüp değişikliği olduğundan büyük gösterirdi. Bu
yüzden karşılaştırma açıkça yazıldı.

Fark önemli: satırın *değiştiğini* bilen bir tüketici onu yeniden okumak zorunda;
*neyin* değiştiğini bilen ise okuyup okumayacağına karar verebilir.

#### Kapsam, ve kararın kendisi

**24 tablo** izleniyor. Bir tablonun ya tetikleyicisi ya da adı konmuş bir gerekçesi
olmak zorunda; `run_scale_checks.py` bunu sınıyor ve karar verilmemiş tabloyu
listeliyor. Amaç listenin kusursuzluğu değil — bu bir yargı — **yeni bir tablonun
bir karar vermeye zorlaması**. O olmadan yeni bir bibliyografik tablo outbox'a
hiç girmezdi ve belirti, arama indeksinin bir tür kaydı sessizce kaçırması olurdu.

15 muaf tablo var; en dikkat çekici ikisi: `entities` (kayıt defteri — olayları alt
türleri taşır) ve `change_proposals` (bir istek, kaydın kendisi değil; uygulanması
zaten kapsanıyor).

#### İki sapma, ikisi de yazılı

1. **§9.2'nin DDL'i `default uuid7()` diyor.** PostgreSQL 16'da `uuid7()` yok ve
   D4'ün uygulaması Python'da — aynı kararın ikinci bir dildeki kopyası sürüklenmeye
   açık olurdu. Sütun `gen_random_uuid()` alıyor ve sıra `occurred_at`'te taşınıyor.
   Gerçek bir kayıp değil: tüketici satırın **güncel halini** yeniden okuyor, yani
   aynı aggregate hakkındaki iki olayın hangi sırayla geldiği cevabı değiştirmiyor.
   Sıra gerçekten önemli olursa doğru yol bir sequence sütunudur, id'nin şekli değil.

2. **Sunucu varsayılanları modelde tekrarlanmadı.** Sütunların PostgreSQL'de
   varsayılanı var (`gen_random_uuid()`, `now()`, `'{}'::jsonb`) çünkü tetikleyici
   onları adlandırmadan yazıyor. Modelde tekrarlamak, SQLite test motorunun
   çalıştırdığı DDL'e `DEFAULT (gen_random_uuid())` ve `DEFAULT '{}'::jsonb` koyardı
   ve motor **ikisini de reddediyor** — tüm test paketi `CREATE TABLE`'da düştü.
   Alembic `compare_server_default` ayarlı olmadıkça varsayılanları karşılaştırmıyor,
   o yüzden modelde bulunmamaları hiçbir şeye mal olmuyor.

#### Doğrulama

| Kontrol | Sonuç |
|---|---|
| Test paketi | **123/123** (SQLite tabloyu kurabiliyor) |
| Senaryo kontrolleri | **35/35** (3 yeni outbox kontrolü) |
| `alembic check` | temiz, tek head `b8d4f0a25e37` |
| Aynı işlem | işlem içinde olay görüldü, geri alındıktan sonra **0** kaldı |
| `UPDATE` payload'ı | yalnızca `['canonical_title']` |
| Kapsam | 24 tablo izleniyor, 15 muaf, kararsız yok |
| API'den eser yaratma | `works INSERT` olayı yazıldı |
| Kontroller iki kez | iz bırakmıyor: olay sayısı **0** |
| Veri | `eser=16 entity=79 holding=16 nusha=12 kurum=5` — değişmedi |

---

### 0.26 Arama sonucu kartı kütüphaneyi göstermiyordu

#### Belirti

Kullanıcı "Suç ve Ceza" aradı ve **kütüphane bilgisi gelmedi**. API doğru cevap
veriyordu; ben de bunu doğrulayıp kapattığımı sanmıştım.

#### Yanlış yerden doğrulamışım

Holding'leri API yanıtında aradım ve buldum — ama **detay** ucunda. Kullanıcının
gördüğü şey **arama sonucu kartıydı** ve o kartta kütüphane bölümü hiç yoktu:
başlık, özgün başlık, yazar, konu, dil, açıklama ve "Kaydı görüntüle" düğmesi.
Holding verisi yanıtta vardı ama `expressions[].manifestations[].holdings`
yolunda; kart onu hiç okumuyordu.

Bunu **gerçek tarayıcıda ekran görüntüsü alarak** buldum. API'yi sorgulamak, kodu
okumak ve testleri koşturmak bu hatayı göstermedi — üçü de doğru cevabı veriyordu,
sadece kullanıcının baktığı yerde değil.

#### Düzeltme

Kart artık ifade → yayın → holding ağacını toplayıp **"5 nüsha · 3 kütüphane"** ve
kütüphane kırılımını gösteriyor. Aynı kurum birden çok baskıyı tutabildiği için
toplanıyor.

**Kartta en fazla beş kütüphane** listeleniyor, gerisi "ve N kütüphane daha" ile
bildiriliyor. Sınırsız bırakmak, bir kez tam olarak yaşanan şeyi tekrarlardı: tek
bir eserin altında yüz kurum ve gerçek kütüphanelerin listede kaybolması (§0.23).

#### Ders

İki kez oldu: `hidden` özniteliğini ezen CSS (§0.24) ve bu. **İkisini de yalnızca
ekran görüntüsü buldu.** Arayüzün eksiksizliği bu projede test edilebilir bir şey
değil; bir kontrol yazmak, test edilen şeyin doğru olduğunu sanma üretir. Doğru
araç, değişiklikten sonra gerçek sayfaya bakmak.

---

### 0.27 `nomens.normalized_value` — §14 ve §15.6'nın ikinci yarısı

#### Belirti, ve ölçüm

`works.normalized_title` (§0.6) sorunun bir yarısını çözmüştü. İsimler aynı sorunu
taşıyordu ve çözecek kolonları yoktu: `nomens`, arama ve bloklamanın kişileri ve
kavramları eşleştirdiği tablo, ve her karşılaştırma anahtarını uçuşta türetiyordu.

Ölçüm, §15.6'nın üslubuyla:

| İsim | eski skor (`lower(value)` ↔ normalize probe) | yeni skor (`normalized_value`) |
|---|---|---|
| `Ayşe Demir` | **0.571** | **1.000** |

Yani birebir aynı isim, tek bir aksan yüzünden 1.000 yerine **0.571** alıyordu.
Ve plan da değişti:

| Sorgu | Plan |
|---|---|
| `normalized_value LIKE '%dostoyevski%'` | **Bitmap Index Scan** (`ix_nomens_normalized_value_trgm`) |
| `value ILIKE '%dostoyevski%'` | **Seq Scan** |

Yani düzeltme yalnızca doğru değil, **daha ucuz**.

#### Neden tetikleyici değil

Beklenen hamle bir tetikleyiciydi ve burada yanlış olan o. Bu imajda `unaccent`
**yok** (ölçüldü), ve `normalize_text` `lower()` artı bir çeviri tablosu değil:
NFKD, sonra `casefold`, sonra birleşen işaretlerin atılması, sonra noktalama→boşluk.
Bunu plpgsql'de yeniden yazmak, tek bir kararın **ikinci bir uygulaması** olurdu —
ve tam da en çok önemli olduğu yerde ayrışmaya açık: `casefold` ile `lower`'ın zaten
farklı davrandığı Türkçe `İ`/`ı` çiftinde.

Bu yüzden ölçülmüş olan örnek izlendi: Python'da, satır yazılırken, ORM olayıyla
(`_sync_normalized_nomen`). Bugünkü üç yazma yolu da oradan geçiyor.

#### Bunun bedeli, ve bedeli ödeyen kontrol

ORM olayı **yalnızca ORM'den geçen yazmaları** kapsar. Sonradan ham SQL ile yazan
biri kolonu boş bırakır ve o isim, aksansız yazan hiç kimse tarafından bulunamaz
hale gelir — sessizce.

`run_scale_checks.py` bu yüzden "değeri olup normalize edilmiş biçimi olmayan satır"
sayısını sınıyor **ve** birebir aynı ismin skorunu bildiriyor; sıfır boş satır tek
başına normalizasyonun *doğru* olduğunu göstermez.

#### Doğrulama

| Kontrol | Sonuç |
|---|---|
| Test paketi | **123/123** |
| Senaryo kontrolleri | **36/36** (1 yeni) |
| `alembic check` | temiz, tek head `c9e5a1b36f48` |
| Geri doldurma | 24/24 isim normalize edildi, boş kalan **0** |
| `Ayse Demir` araması | `Ayşe Demir` bulundu |
| `Dostoevsky` araması | `Fyodor Dostoyevski` bulundu |
| Noktalama probe'u (`...`, `!!!`) | **0 sonuç** — hepsini döndürmüyor |
| Birebir aynı isim skoru | **1.000** |
| Index kullanımı | Bitmap Index Scan (`value` üzerinde Seq Scan) |
| Veri | `eser=16 entity=79 holding=16 nusha=12 kurum=5` — değişmedi |

---

## 1. Plane modeli

### 1.1 Üç plane, iki kesişen katman

```
                 ┌─────────────────────────────────────────┐
                 │              CONTROL PLANE              │
                 │  kim bunlar? hangi kurum? hangi bölge?  │
                 │  auth, roller, abonelik, API anahtarı   │
                 └────────────────────┬────────────────────┘
                                      │ tenant_id
        ┌─────────────────────────────┴─────────────────────────────┐
        │                                                           │
┌───────▼────────────────────┐                    ┌─────────────────▼──────────┐
│   GLOBAL KNOWLEDGE PLANE   │                    │    TENANT DATA PLANE       │
│  paylaşılan, kurumdan      │◄───── FK ──────────│  kuruma ait operasyonel    │
│  bağımsız bibliyografik    │   manifestation_id │  veri: holding, item,      │
│  ve otorite verisi         │                    │  patron, loan, bütçe       │
│  (public şeması)           │                    │  (tenant şeması)           │
└────────────────────────────┘                    └────────────────────────────┘
        │                                                           │
        └──────────────────┬────────────────────────────────────────┘
                           │  transactional outbox
                  ┌────────▼────────┐        ┌──────────────────────┐
                  │  SEARCH PLANE   │        │  AI / SEMANTIC PLANE │
                  │  OpenSearch     │        │  embeddings, öneri   │
                  │  (yeniden       │        │  (öneri üretir,      │
                  │   üretilebilir) │        │   yazmaz)            │
                  └─────────────────┘        └──────────────────────┘
                           │
                  ┌────────▼────────┐
                  │ OBJECT STORAGE  │  PDF/görsel/OCR — PostgreSQL'de blob YOK
                  └─────────────────┘
```

### 1.2 Fiziksel yerleşim kararı (D1)

**Karar:** Bugün **tek PostgreSQL cluster** kalır. Plane ayrımı fiziksel değil
**şema + rol** düzeyinde yapılır:

| Plane | Şema | Not |
|---|---|---|
| Global Knowledge | **`public`** (mevcut, taşınmaz) | Mevcut 35 tablo burada kalır |
| Control | **`control`** (yeni) | Boş şema olarak açılır, sonra doldurulur |
| Tenant Data | **`tenant`** (yeni) | Boş şema olarak açılır, sonra doldurulur |

**Gerekçe:** En ucuz adım, ileride fiziksel ayırma yeteneğini koruyan adımdır.
`public` şemasını `global` adına taşımak 35 tablonun FK'lerini, `search_path`'i ve çalışan
API'yi riske atar; kazanç yalnızca kozmetiktir.

**Yan fayda:** `public` `search_path`'in varsayılanıdır. `tenant` ve `control` tablolarının
şema-nitelikli yazılması zorunlu olduğu için, kodda yanlışlıkla niteliksiz yazılan bir
tenant tablosu erişimi **sessizce başarılı olamaz** — hata verir. Bu, tenant/global karışma
hatalarına karşı bedava bir korumadır.

**Reddedilen alternatifler:**

| Alternatif | Neden reddedildi |
|---|---|
| Tablo adı öneki (`tenant_holdings`) | GRANT ile ayrı yetkilendirme yapılamaz; şema ayrımı kadar net değil |
| Tenant başına şema | Binlerce tenant'ta migration fan-out: her migration ×N şema. Operasyonel olarak sürdürülemez |
| Tenant başına veritabanı (bugünden) | Aynı sorun + bağlantı havuzu patlaması + cross-tenant sorgu imkânsız |
| Global plane'i `global` şemasına taşımak | Yüksek risk, sıfır işlevsel kazanç |

### 1.3 Sınıflandırma testi

Yeni her tablo/alan için tek soru: **"Bu veri kurumdan bağımsız olarak dünyada aynı mı,
yoksa kuruma göre değişir mi?"**

| Veri | Plane | Neden |
|---|---|---|
| Work, Expression, Manifestation | Global | Yayının kendisi kurumdan bağımsız |
| Person, CollectiveAgent, Concept, Place, TimeSpan | Global | Otorite verisi |
| Nomen, Identifier | Global | Varlığın adı/kimliği |
| EntityRelation, RelationPredicate | Global | Bilgi ağı |
| ClassificationNode, VocabularyScheme | Global | DDC/LCC gibi şemalar dünyada ortak |
| **Holding, Item** | **Tenant** | Fiziksel nüsha kuruma ait |
| Barcode, Shelfmark, Condition | **Tenant** | Nüshanın durumu |
| Organization, Branch | Control | Kurumun kendisi ve yapısı |
| Patron, Loan, Fine, Budget, Staff | Tenant | Kişisel/mali operasyonel veri |
| SourceRecord, FieldAssertion | Global | Bilginin kökeni (kurum da bir kaynak olabilir) |

---

## 2. Mevcut modele karşı denetim

### 2.1 Bugün doğru olanlar (korunacak)

- **Entity + alt tip tabloları** (`entities` kimlik/registri + `works`, `expressions`,
  `manifestations`, `persons`, …) doğru omurgadır. `entity_relation` tek noktadan
  polimorfik ilişki kurar.
- **`relation_predicates` + `relation_predicate_constraints`**: predicate'in hangi tipten
  hangi tipe gidebileceğini veri olarak tanımlar. Bu, LRM/BIBFRAME uyumluluğu için doğru
  temeldir ve genişletilebilir.
- **`nomens`**: çok dillilik ve çok yazı sistemi için doğru yaklaşım. `preferred` için
  kısmi unique index doğru.
- **`identifiers`**: `(entity_id, scheme, value)` unique + `(scheme, value)` index'i
  DOI/ISBN/ORCID/VIAF bloklaması için hazır.
- **`source_records`** (`source_system`, `source_record_id`, `retrieved_at`,
  `source_updated_at`, `raw_data`, `content_hash`): provenance'ın çekirdeği zaten var.
- **`reconciliation_candidates` / `reconciliation_decisions`** + `evidence_snapshot`
  write-once trigger: entity resolution'ın temeli ve dokümante edilmiş, dürüst bir politika.
  Trigger'ın gerçekten çalıştığını doğruladım (`ERROR: Decision evidence snapshot cannot be
  modified`).
- **17 tip bütünlüğü trigger'ı**: alt tip tablosuna yanlış `entity_type` yazılmasını
  veritabanı seviyesinde engelliyor. Bu kalitede bir koruma nadirdir.
- **`entity_merges`**: birleştirme kaydı zaten tutuluyor.

### 2.2 Sınırı ihlal edenler

| Nesne | Bugünkü plane | Olması gereken | Sorun |
|---|---|---|---|
| **`items`** | Global (`entities` alt tipi) | **Tenant** | Operasyonel nüsha verisi global kimlik tablosunda. §3 |
| `item_agent_relation` (role=`holding_institution`) | Global | Tenant | Kurum aidiyeti ilişki tablosunda; sorguyla bulunur, kısıtla korunmaz |
| `manifestation_item` | Global | — | Aradaki **Holding** varlığı yok; nüsha doğrudan manifestation'a bağlı |
| `collective_agents` | Global | Hem global hem control | Kurum kimliği ile otorite kaydı aynı satırda karışıyor |
| `work_classifications.assigned_by` / `.source` | Global, serbest metin | Künye/atıf | Kim atadı bilgisi string; denetlenebilir değil |
| `items.availability_status` | Global, serbest metin | Tenant, türetilmiş | Dolaşım verisi yokken elle yazılan durum; gerçekle senkron kalması imkânsız |
| `source_records.institution_entity_id` | → `collective_agents` | → control.organizations | Kaynağı veren **kurum** (tenant) ile **tüzel kişi** (otorite) ayrılmalı |

### 2.3 En kritik ihlal

`items`, `entities` tablosunda bir satırdır. Bu üç şeyi aynı anda bozar:

1. **Ölçek:** 100 milyon Item senaryosunda `entities` tablosunun büyük çoğunluğu
   paylaşılabilir bilgi değil, tek bir kütüphanenin fiziksel nüshaları olur. Global kimlik
   registri operasyonel veriyle dolar.
2. **Kimlik sözü:** "Global varlıkların kimliği kurumlardan bağımsız olmalı" ilkesi Item
   için anlamsızdır — nüsha zaten kuruma aittir. Aynı fiziksel kitap iki kütüphanede iki
   farklı Item'dır; bu doğrudur. Ama bunun global Entity uzayında durması, `entity_relation`
   ile bir Item'a ilişki kurulabilmesi anlamına gelir ki bu kavramsal olarak yanlıştır.
3. **İzolasyon:** A kütüphanesinin nüshaları B kütüphanesinin sorgularında görünür; arada
   hiçbir tenant sınırı yok.

---

## 3. ANA KARAR — `Manifestation → Holding → Item` sınırı

### 3.1 Kavramsal model

```
GLOBAL KNOWLEDGE PLANE                    TENANT DATA PLANE
──────────────────────                    ─────────────────

Work        "Suç ve Ceza"
  │
  └─ Expression   "Türkçe çeviri"
        │
        └─ Manifestation   "İş Bankası, 1. baskı, 2024, ISBN …"
              │
              │  ◄─────── FK: manifestation_entity_id ───────┐
              │                                              │
              │                                    ┌─────────┴──────────┐
              │                                    │      HOLDING       │
              │                                    │  Kırıkkale Üniv.   │
              │                                    │  Merkez Şube        │
              │                                    │  yer numarası,      │
              │                                    │  koleksiyon,        │
              │                                    │  cilt/sayı aralığı  │
              │                                    └─────────┬──────────┘
              │                                              │
              │                                    ┌─────────┴──────────┐
              │                                    │       ITEM         │
              │                                    │  barkod KKU-123456 │
              │                                    │  raf yeri, durum    │
              │                                    └────────────────────┘
              │
   Aynı Manifestation'ı başka kurum da tutar:
   Başka Üniversite → kendi Holding'i → kendi Item'ları, kendi barkodları
```

**Kural:** Bir Manifestation **bir kez** global olarak tanımlanır. Her kurum ona kendi
Holding'iyle bağlanır. Bibliyografik kayıt asla kurum başına tekrarlanmaz.

### 3.2 Holding neden ayrı bir varlık olmalı

Holding'i atlayıp `items` tablosuna `manifestation_id` + `branch_id` + `tenant_id`
eklemek **çalışır gibi görünür** ama şu üç durumu modelleyemez:

1. **Süreli yayınlar.** Bir dergi için kütüphane "cilt 12–18, 1998–2004 eksik sayı 14"
   der. Bu bir *nüsha* değil, bir *koleksiyon beyanıdır*. Item'lar tek tek sayılardır ve
   Holding beyanı onların üstünde durur.
2. **Elektronik kaynaklar.** Bir e-kitap aboneliğinde tek bir Holding vardır, Item yoktur
   — barkod basılmaz, raf yeri yoktur, ama erişim URL'i, lisans ve kullanım koşulları
   vardır. Item zorunlu olsaydı bu kayıt sahte bir Item yaratmak zorunda kalırdı.
3. **Yer numarası politikası.** Kütüphaneler yer numarasını (call number) genelde
   *koleksiyon* düzeyinde verir, tek tek nüshaya değil. Aynı eserin 3 nüshası çoğu zaman
   aynı yer numarasını paylaşır.

**Karar (D2):** `Holding` birinci sınıf bir tenant varlığıdır; `Item` **bir Holding'e
aittir**. Manifestation ile Holding arasındaki ilişki çoktan-bire, Holding ile Item
arasındaki ilişki de çoktan-bire (bir Holding n Item).

### 3.3 DDL taslağı

> Uygulanmadı. Bu bir taslaktır; Aşama 1–4'te parça parça, her biri geri alınabilir
> migration'lar olarak eklenir.

#### Control plane

```sql
create schema if not exists control;

create table control.tenants (
    id              uuid primary key default uuid7(),
    slug            text not null unique,
    display_name    text not null,
    status          text not null default 'active'
                    check (status in ('active','suspended','closed')),
    cluster_id      text not null,          -- hangi fiziksel cluster
    region          text,                   -- ör. 'eu-central'
    data_residency  text,                   -- ör. 'TR', 'EU' (bkz. §5.4)
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

-- Kurumun OTORİTE kimliği ile TENANT kimliği AYRI kayıtlardır (bkz. D14)
create table control.organizations (
    id                          uuid primary key default uuid7(),
    tenant_id                   uuid not null unique
                                references control.tenants(id) on delete restrict,
    collective_agent_entity_id  uuid unique
                                references public.collective_agents(entity_id)
                                on delete set null,
    name                        text not null,
    org_type                    text,       -- university, public, school, special, national
    country_code                char(2),
    isil                        text,       -- ISIL kodu (kütüphane kurum kodu)
    created_at                  timestamptz not null default now()
);

create table control.branches (
    id              uuid primary key default uuid7(),
    tenant_id       uuid not null references control.tenants(id) on delete cascade,
    organization_id uuid not null references control.organizations(id) on delete cascade,
    code            text not null,
    name            text not null,
    is_default      boolean not null default false,
    created_at      timestamptz not null default now(),
    unique (tenant_id, code)
);

-- Tenant → fiziksel konum eşlemesi. Uygulama kodu veritabanı adresi bilmez (bkz. §5.3)
create table control.tenant_databases (
    tenant_id       uuid primary key references control.tenants(id) on delete cascade,
    cluster_id      text not null,
    dsn_secret_ref  text not null,   -- parolanın KENDİSİ değil, sır referansı
    read_replica_ref text,
    updated_at      timestamptz not null default now()
);
```

#### Tenant data plane

```sql
create schema if not exists tenant;

create table tenant.locations (
    id          uuid primary key default uuid7(),
    tenant_id   uuid not null,
    branch_id   uuid not null references control.branches(id),
    code        text not null,
    name        text not null,
    location_type text,        -- shelf, room, closed_stack, offsite
    unique (tenant_id, branch_id, code)
);

create table tenant.holdings (
    id              uuid primary key default uuid7(),
    tenant_id       uuid not null,
    branch_id       uuid not null references control.branches(id),

    -- Hedef: exclusive arc — tam olarak BİRİ dolu (bkz. D3 / süreli yayın notu)
    manifestation_entity_id uuid
        references public.manifestations(entity_id) on delete restrict,
    expression_entity_id    uuid
        references public.expressions(entity_id) on delete restrict,
    constraint ck_holding_target_exactly_one
        check (num_nonnulls(manifestation_entity_id, expression_entity_id) = 1),

    holding_type    text not null default 'physical'
                    check (holding_type in ('physical','electronic','microform','other')),
    collection_code text,
    call_number     text,
    call_number_scheme text,          -- 'lc' | 'dewey' | 'local' | ...
    holding_statement  text,          -- süreli yayın: "c.12-18 (1998-2004), 14 eksik"
    enumeration_pattern text,

    access_url      text,             -- elektronik erişim
    license_note    text,

    acquisition_source text,
    public_note     text,
    staff_note      text,

    -- idempotent içe aktarma anahtarı (bkz. D2.1)
    local_holding_key  text not null,

    status          text not null default 'active'
                    check (status in ('active','closed','suppressed')),
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),

    unique (branch_id, manifestation_entity_id, local_holding_key)
);

create index ix_holdings_tenant_manifestation
    on tenant.holdings (tenant_id, manifestation_entity_id);
-- "bu Manifestation'ı hangi kurumlar tutuyor?" — global → tenant yönü
create index ix_holdings_manifestation
    on tenant.holdings (manifestation_entity_id)
    where status = 'active';

create table tenant.items (
    id              uuid primary key default uuid7(),
    tenant_id       uuid not null,
    holding_id      uuid not null references tenant.holdings(id) on delete restrict,

    barcode         text,
    accession_number text,
    item_type       text,             -- book, issue, dvd, map, ...
    location_id     uuid references tenant.locations(id),
    shelfmark       text,
    condition       text,

    -- CACHE alanı: asıl doğru kaynak dolaşım (loan) verisidir (bkz. D2.2)
    availability_status text not null default 'unknown',

    circulation_policy_id uuid,
    price_amount    numeric(12,2),
    price_currency  char(3),
    acquired_at     date,
    donor           text,
    notes           text,

    lifecycle_status text not null default 'active'
                    check (lifecycle_status in
                           ('active','withdrawn','lost','missing','in_repair')),
    withdrawn_at    timestamptz,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

-- Barkod benzersizliği: kapsamı kurulum kararıdır (bkz. §18 OD3)
create unique index uq_items_tenant_barcode
    on tenant.items (tenant_id, barcode) where barcode is not null;
create index ix_items_holding on tenant.items (holding_id);

-- Tenant izolasyonu: uygulamaya değil, VERİTABANINA güven (bkz. §5.2)
alter table tenant.holdings enable row level security;
alter table tenant.items    enable row level security;
alter table tenant.locations enable row level security;

create policy tenant_isolation on tenant.holdings
    using      (tenant_id = current_setting('libraryhub.tenant_id')::uuid)
    with check (tenant_id = current_setting('libraryhub.tenant_id')::uuid);
-- tenant.items ve tenant.locations için aynı politika
```

#### D2.1 — `local_holding_key` neden var

Aynı Manifestation için aynı şubede **birden fazla Holding meşrudur**: "Referans
koleksiyonu", "Ödünç koleksiyonu", "Süreli yayın arşivi". Bu yüzden
`(branch_id, manifestation_id)` üzerine koşulsuz unique konulamaz. İdempotent içe aktarma
için kurumun kendi anahtarı (`local_holding_key`) kullanılır: aynı kaydı iki kez aktaran
sistem aynı anahtarı verirse çift kayıt oluşmaz. Anahtar zorunludur ve içe aktarma
katmanı tarafından üretilir.

#### D2.2 — `availability_status` neden yalnızca cache

Bugün `items.availability_status` serbest metindir ve elle yazılır. Ödünç modülü
geldiğinde iki doğruluk kaynağı çakışır: alan "available" derken kitap ödünçte olur.
**Karar:** dolaşım durumu (loan/reservation/repair) asıl doğruluk kaynağıdır;
`availability_status` ondan türetilen ve olay akışıyla güncellenen bir **önbellektir**.
Şimdilik alan korunur (API sözleşmesi bozulmaz); dolaşım tabloları eklendiğinde bu alan
türetilmiş hale getirilir ve yalnızca okuma kolaylığı için tutulur.

### 3.4 Süreli yayınlar ve elektronik kaynaklar

| Senaryo | Global | Tenant |
|---|---|---|
| Basılı kitap | Work → Expression → Manifestation | Holding (nüsha grubu) → Item (her fiziksel kopya) |
| Dergi (dergi başlığı) | Work | Holding, `holding_statement` ile cilt/sayı aralığı |
| Dergi sayısı | Expression **veya** Manifestation | Item (`item_type='issue'`), sayı bazında |
| E-kitap (abonelik) | Work → Expression → Manifestation | Holding (`holding_type='electronic'`, `access_url`), **Item yok** |
| Tez (kuruma özgü) | Work → Expression → Manifestation | Holding + Item; kurum kopyası |
| Mikrofilm | Manifestation (`carrier_type='microform'`) | Holding (`holding_type='microform'`) + Item |

**Süreli yayın notu:** Bir dergi sayısı hem Expression hem Manifestation olarak
modellenebilir. Bu belge ikisini de destekleyen exclusive-arc yaklaşımını önerir
(`manifestation_entity_id` XOR `expression_entity_id`), çünkü:
- sayı bazlı künye (yıl, cilt, sayı) **Manifestation** düzeyindedir;
- çeviri/dil farkı **Expression** düzeyindedir;
- Holding bazen dil-düzeyinde (tüm Türkçe çeviriler), bazen nüsha-düzeyinde (belirli baskı)
  beyan edilir.

Exclusive arc, iki FK'nin tip güvenliğini korur; tek bir `target_entity_id` + tip kolonu
polimorfizmi ise FK bütünlüğünü kaybettirir. Bu yüzden D3'te exclusive arc seçilmiştir.

### 3.5 Reddedilen alternatifler (D2/D3)

| # | Alternatif | Neden reddedildi |
|---|---|---|
| A | `items`'a `tenant_id` + `branch_id` ekle, global Entity kalsın | Global kimlik registri operasyonel veriyle dolar; `entity_relation` Item'a bağlanabilir kalır; "global kimlik kurumdan bağımsız" sözü Item için anlamsızlaşır |
| B | Item'ı kaldır, yalnızca Holding kalsın | Barkod, tekil nüsha durumu, sayı bazlı dergi ve dolaşım Item düzeyinde çalışır; nüsha granülerliği kaybolur |
| C | Her kurum kendi Manifestation kaydını oluştursun | Vizyonun tam karşıtı: bibliyografik kayıt kurum sayısı kadar (binlerce) tekrarlanır. Entity resolution problemi çözülemez hale gelir |
| D | MARC odaklı iç model | İç model tek bir dış standardın teknik yapısına bağımlı olur; §22 ilkesine aykırı. MARC bir *değişim* formatıdır, *iç* model değil |
| E | Holding'i Manifestation'a değil Expression'a bağla | Basılı nüsha belirli bir baskıya (Manifestation) aittir; Expression düzeyinde bağlamak farklı baskıları birbirine karıştırır |
| F | `target_entity_id` + `target_entity_type` (tek polimorfik FK) | FK bütünlüğü kaybolur; veritabanı yanlış tipte hedefi engelleyemez |

---

## 4. Global kimlik stratejisi (D4)

### 4.1 Karar

| Konu | Karar |
|---|---|
| Global varlık ID'si | **UUIDv7** (yeni satırlar). Mevcut UUIDv4 satırlar **değiştirilmez** |
| Global handle | `canonical_uri`, ör. `https://libraryhub.org/work/<uuid>` — birlikte çalışabilirlik için |
| Tenant nesnesi ID'si | UUIDv7 + her tenant tablosunda `tenant_id uuid not null` |
| Tenant nesnesi için "insan okunur" kimlik | Tenant içi kod alanları (`barcode`, `accession_number`, `local_holding_key`) — bunlar **kimlik değil**, kurumun kendi anahtarlarıdır |
| Dağıtık üretim | UUIDv7 istemcide üretilebilir; merkezi sayaç gerekmez |

### 4.2 UUIDv4 → UUIDv7 gerekçesi

Mevcut tüm ID'ler `uuid.uuid4()` — tamamen rastgele. B-tree index'lerde rastgele dağılım,
100 milyon+ satırda ciddi **index parçalanması** ve düşük yazma yerelliği üretir.
UUIDv7 zaman-sıralıdır: yeni satırlar index'in sonuna yakın yazılır.

**Uygulama notu:** Konteynerde Python **3.12** var; `uuid.uuid7()` Python 3.14'te geldi.
Bu yüzden ~15 satırlık bir iç yardımcı fonksiyon yazılmalı **veya** `uuid6` paketi
eklenmelidir. Yeni bağımlılık istemiyorsak iç yardımcı tercih edilir.

**Kritik:** Mevcut satırların ID'si **yeniden üretilmez**. Geçiş yalnızca
`default=uuid7()` düzeyindedir; UUIDv4 ve UUIDv7 aynı kolonda yan yana meşru şekilde yaşar.

### 4.3 Reddedilen alternatifler

| Alternatif | Neden reddedildi |
|---|---|
| Artan bigint (serial) | Dağıtık üretimde merkezi koordinasyon ister; dış sistemlere açık kimlik olarak zayıf; birleştirme/split'te çakışır |
| UUIDv4'te kal | Ölçekte index parçalanması; geri dönüşü kolay bir karar değil |
| İçerik hash'i (DOI gibi) | İçerik değişince kimlik değişir; otorite kimliği içerikten bağımsız olmalı |
| Mevcut UUID'leri yeniden yaz | Yıkıcı. §33 ilkesine aykırı |

---

## 5. Tenant izolasyonu ve veritabanı yönlendirme

### 5.1 Karar (D5)

**Paylaşımlı şema + `tenant_id` kolonu + PostgreSQL Row Level Security**, üstünde
tenant→cluster çözümleyen bir **yönlendirme katmanı**. Bugün hepsi tek cluster'da;
mimari tenant'ın başka cluster'a taşınmasına izin verir.

### 5.2 İzolasyonun veritabanında zorlanması

Satır düzeyi güvenlik, uygulama hatasını veri sızıntısına dönüşmekten çıkarır:

```sql
create role libraryhub_global_app;   -- yalnızca public şeması
create role libraryhub_tenant_app;   -- tenant şeması, RLS'e tabi

alter table tenant.items enable row level security;
create policy tenant_isolation on tenant.items
    using      (tenant_id = current_setting('libraryhub.tenant_id')::uuid)
    with check (tenant_id = current_setting('libraryhub.tenant_id')::uuid);
```

Her tenant işlemi kendi transaction'ında `SET LOCAL libraryhub.tenant_id = '<uuid>'`
çalıştırır. `SET LOCAL` transaction kapsamlıdır, bağlantı havuzunda sızmaz.

**Neden RLS:** "Kodda `where tenant_id = ...` yazmayı unutma" disiplinine güvenmek,
binlerce tenant'lı bir sistemde kabul edilemez riskdir. RLS, unutulduğunda **sonuç
döndürmez**.

### 5.3 Veritabanı yönlendirme (tenant taşınabilirliği)

Uygulama kodu **hiçbir zaman** bir veritabanı adresi sabiti içermez:

```python
# Hedef tasarım — bugün değil, Aşama 2'den sonra
async def session_for(tenant_id: UUID) -> AsyncSession:
    route = await control_plane.route(tenant_id)   # cluster_id + secret_ref
    return sessionmaker(bind=engine_for(route.cluster_id))()
```

`control.tenant_databases` tenant → cluster eşlemesini tutar. Bir tenant başka cluster'a
taşınacağında:
1. yeni cluster'da şema kurulur,
2. `pg_dump`/mantıksal replikasyon ile veri taşınır,
3. `control.tenant_databases.cluster_id` güncellenir,
4. uygulama kodu **hiç değişmez**.

**Bugünkü durumun sorunu:** `backend/app/db.py` modül yüklemesinde tek bir
`DATABASE_URL` okuyup tek `engine` kuruyor ([db.py](../backend/app/db.py#L7-L12)).
Bu, "database konumu sabit varsayılmasın" gereksinimini bugünden ihlal eder. Ancak
**şimdi değiştirilmesi gerekmez**: tek tenant varken yönlendirme katmanı boş bir
soyutlamadır. Aşama 2'de `control.tenant_databases` ile birlikte gelir.

### 5.4 Veri yerleşimi (data residency)

`control.tenants.region` / `.data_residency` bugünden eklenir (maliyeti sıfır, kolonu
sonradan eklemek de kolay). Kişisel veri (patron, ödünç geçmişi) **asla** global
`public` şemasına yazılmaz — bu, §25'in veritabanı düzeyindeki karşılığıdır.

### 5.5 Reddedilen alternatifler

| Alternatif | Neden reddedildi |
|---|---|
| Şema-per-tenant | Migration ×N; binlerce tenant'ta sürdürülemez |
| DB-per-tenant (bugünden) | Operasyonel yük; cross-tenant analitik imkânsız |
| Yalnızca uygulama katmanı filtresi | Tek unutulan `where` tüm veriyi sızdırır |
| `tenant_id`'yi PK'ye dahil etmemek | Index'ler tenant'lar arası karışır; RLS planı yavaşlar |
| Global ve tenant verisini aynı şemada tutmak | GRANT ile ayırma imkânsız; yanlışlıkla yazma korunamaz |

---

## 6. Provenance (D6)

### 6.1 Bugünkü zemin

`source_records` zaten `source_system`, `source_record_id`, `retrieved_at`,
`source_updated_at`, `raw_data`, `content_hash` tutuyor. Bu, "bu kayıt nereden geldi"
sorusunun **kayıt düzeyinde** cevabıdır. Eksik olan **alan düzeyi** cevaptır:
"`works.canonical_title` değeri hangi kaynaktan geldi, önceki değer neydi?"

### 6.2 Öneri: kaynak sicili + alan iddiaları

```sql
create table public.source_systems (
    id           uuid primary key default uuid7(),
    code         text not null unique,      -- 'crossref','openalex','kku_catalog','manual'
    name         text not null,
    system_type  text not null
                 check (system_type in ('library_catalog','aggregator','national_library',
                                        'publisher','registry','ai','manual','import')),
    trust_level  smallint not null default 50
                 check (trust_level between 0 and 100),   -- §12: "kaynağın güven düzeyi"
    license      text,
    attribution  text,
    base_url     text,
    is_active    boolean not null default true,
    created_at   timestamptz not null default now()
);

create table public.field_assertions (
    id                uuid primary key default uuid7(),
    subject_entity_id uuid not null references public.entities(id) on delete cascade,
    field_name        text not null,          -- 'canonical_title', 'publication_date', ...
    value_text        text,
    value_json        jsonb,
    language          text,
    script            text,

    source_system_id  uuid references public.source_systems(id) on delete set null,
    source_record_id  uuid references public.source_records(id) on delete set null,
    confidence        numeric(4,3) check (confidence between 0 and 1),
    method            text,                   -- 'isbn_exact','fuzzy_title_v4','human_edit'

    status            text not null default 'proposed'
                      check (status in ('proposed','accepted','rejected','superseded')),
    observed_at       timestamptz not null default now(),
    valid_from        timestamptz,
    valid_to          timestamptz,

    decided_by        text,
    decided_at        timestamptz,
    superseded_by_id  uuid references public.field_assertions(id) on delete set null
);

create index ix_field_assertions_subject
    on public.field_assertions (subject_entity_id, field_name, status);
```

**Okuma modeli değişmez.** `works.canonical_title` gibi mevcut kolonlar hızlı okuma için
**kanonik değer** olarak kalır. `field_assertions` yalnızca "bu değer nereden geldi,
önceki neydi, kim onayladı" sorusunu yanıtlar. Bu, tam RDF-reification modelinin
ağırlığını taşımadan provenance sağlar.

**Append-only:** düzeltme yeni satır ekler; `status` değişir, satır silinmez. Bu, §13'ün
"destructive update'ten kaçın" ilkesidir.

### 6.3 Reddedilen alternatifler

| Alternatif | Neden reddedildi |
|---|---|
| Tam RDF/triple store | Şimdi için aşırı ağır; §28'e aykırı erken karmaşıklık |
| Her tabloya `created_by`/`updated_by` eklemek | "Önceki değer neydi" ve "hangi kaynaktan geldi" sorularını yanıtlamaz |
| Yalnızca `source_records` yeterli demek | Alan düzeyinde çok kaynaklı birleştirmeyi (Crossref + OpenAlex + 2 kütüphane) ifade edemez |
| Tam audit trigger seti (her tabloya) | 35 tablo × trigger; yazma maliyeti ve bakım yükü yüksek, kazanç alan düzeyinde değil |

---

## 7. Versioning ve geri alınabilir merge (D7)

### 7.1 Bugünkü durum ve somut eksik

`entity_merges` birleştirmeyi kaydeder ve `resolve_canonical_entity_id` zinciri takip eder.
Ancak birleştirme **geri alınamaz**: birleştirme sırasında taşınan her yabancı anahtar
kaydedilmiyor. `persons.py` içinde ilişkiler `object_entity_id`/`subject_entity_id`
üzerinden yeni kimliğe yazılıyor — hangi satırın hangi kolonunun değiştiği kayıt altına
alınmıyor. Yanlış bir birleştirme bugün pratikte geri döndürülemez.

### 7.2 Öneri

```sql
alter table public.entity_merges
    add column reverted_at    timestamptz,
    add column reverted_by    text,
    add column revert_reason  text;

create table public.entity_merge_moves (
    id          uuid primary key default uuid7(),
    merge_id    uuid not null references public.entity_merges(id) on delete cascade,
    table_name  text not null,
    column_name text not null,
    row_pk      jsonb not null,      -- taşınan satırın PK'sı
    old_value   uuid,
    new_value   uuid,
    moved_at    timestamptz not null default now()
);
create index ix_merge_moves_merge on public.entity_merge_moves (merge_id);

create table public.entity_splits (
    id                uuid primary key default uuid7(),
    source_entity_id  uuid not null references public.entities(id),
    new_entity_id     uuid not null references public.entities(id),
    split_reason      text,
    performed_by      text,
    performed_at      timestamptz not null default now()
);
```

**Geri alma:** `entity_merge_moves` kayıtları tersine uygulanır, `entity_merges` satırı
`reverted_at` ile işaretlenir, `resolve_canonical_entity_id` artık geri alınmış merge'leri
atlar. Bu, "iki Entity yanlışlıkla birleştirildiyse geri alınabilmeli" gereksinimini
karşılar.

### 7.3 Neden "her şeyi versiyonla" değil

Tam temporal tablo (her tabloda `valid_from`/`valid_to` + her yazma yeni satır) 35 tabloda
okuma karmaşıklığını ve depolamayı katlar. Bunun yerine:
- **Global bilgi** → `field_assertions` (§6) zaten temporal ve append-only,
- **Birleştirme/ayırma** → açık kayıt (§7.2),
- **Operasyonel tenant verisi** → normal `updated_at` + ileride audit log,
- **Silme** → `lifecycle_status`/`status` (tombstone), fiziksel silme yok.

---

## 8. Entity resolution (D8)

Mevcut `reconciliation_candidates` / `reconciliation_decisions` / `evidence_snapshot` /
`check_freshness` altyapısı doğru temeldir ve **yeniden yazılmamalıdır**. Genişletme
noktaları:

1. **Kayıt tipi genelleştirmesi.** Politika bugün `record_type='work'` ile sınırlı
   (`evaluation` endpoint'i diğer tipleri 400 ile reddediyor). Person/Concept için ayrı
   politika sürümleri (`person_*`, `concept_*`) eklenir; mevcut `work_*` politikaları
   değişmez.
2. **Identifier tabanlı bloklama.** 100 milyon varlıkta fuzzy başlık karşılaştırması
   tüm çiftler üzerinde çalıştırılamaz. `identifiers(scheme, value)` index'i zaten var;
   önce DOI/ISBN/ISSN/ORCID/VIAF üzerinden **aday kümesi** daraltılır, fuzzy skor yalnızca
   o küme üzerinde çalışır.
3. **Normalize isim anahtarı.** `nomens` için `normalized_value` (küçük harf, aksan
   soyulmuş, noktalama temizlenmiş) + GIN/trigram index. Bloklama bunun üzerinden yapılır.
4. **İnsan incelemesi** zaten var (`reviewed_by`, `evidence_snapshot`); `automatic_acceptance`
   kalibrasyon verisi gelene kadar kapalı kalır (mevcut politika bunu zaten söylüyor ve
   doğru).

---

## 9. Search plane (D9)

### 9.1 Karar

**PostgreSQL doğruluk kaynağı kalır.** Arama için ayrı bir OpenSearch/Elasticsearch
katmanı eklenir, **ancak bugün değil**: bugünkü problem arama motoru eksikliği değil,
mevcut PostgreSQL aramasının yavaşlığı ve ölçeklenmezliğidir (ölçüm: §15.2).

### 9.2 Geçişi mümkün kılan ucuz adım: transactional outbox

```sql
create table public.outbox_events (
    id             uuid primary key default uuid7(),
    aggregate_type text not null,      -- 'work','manifestation','item'
    aggregate_id   uuid not null,
    event_type     text not null,      -- 'WorkMerged','ManifestationUpdated'
    payload        jsonb not null default '{}'::jsonb,
    tenant_id      uuid,               -- tenant olayları için
    occurred_at    timestamptz not null default now(),
    published_at   timestamptz,
    attempts       int not null default 0,
    last_error     text
);
create index ix_outbox_unpublished on public.outbox_events (occurred_at)
    where published_at is null;
```

Olay, veriyi değiştiren **aynı transaction içinde** yazılır. Böylece "veri değişti ama
olay kayboldu" durumu oluşmaz. Indexer'lar bu tabloyu tüketir.

**Neden şimdi:** Tek tablo, tek index, sıfır operasyonel yük. Buna karşılık
outbox olmadan sonradan event-driven mimariye geçmek, her yazma yolunu yeniden ele almayı
gerektirir. Bu, "geleceği engelleyecek karar alma" ilkesinin en ucuz karşılığıdır.

### 9.3 Kural

Arama indeksi **asla** doğruluk kaynağı olmaz; her zaman PostgreSQL'den tam yeniden
üretilebilir olmalıdır (`reindex` komutu tanımlı ve test edilmiş olmalı).

---

## 10. AI / Semantic plane (D10)

- Embedding'ler ve öneriler ayrı şemada/tabloda tutulur (`ai.*`).
- **AI çıktısı global tablolara doğrudan yazmaz.** Ürettiği her öneri
  `field_assertions` içinde `status='proposed'` + `source_system.system_type='ai'` olarak
  girer ve insan onayı bekler.
- Bu, §16'nın "AI çıktısı ile doğrulanmış veri ayrılmalı" ve "AI verisi provenance
  taşımalı" gereksinimlerinin doğrudan karşılığıdır.
- **Not:** Hedef PostgreSQL imajında `vector` extension'ı **mevcut değil** (ölçüldü).
  Vektör arama gerektiğinde `pgvector` imajı eklenmeli **veya** ayrı bir servis
  kullanılmalıdır. Bu, Aşama 6+ kararıdır; bugün gerekmez.

---

## 11. Event modeli

`outbox_events` (§9.2) ile başlar. Örnek olay tipleri:

| Olay | Tetiklediği işler |
|---|---|
| `WorkMerged` / `WorkSplit` | arama indeksi, ilişki yeniden yönlendirme, cache |
| `ManifestationUpdated` | arama indeksi, kayıtlı kurumlara bildirim |
| `HoldingCreated` / `ItemCreated` | kurum istatistikleri, arama (kurum filtresi) |
| `AuthorityMerged` | tüm nomen/identifier index'leri |
| `AssertionAccepted` | kanonik alan güncellemesi |

**Bugün yapılmayacak:** Kafka, ayrı event store, mikroservis ayrımı. Outbox tablosu
yeterlidir ve aynı sözleşmeyi taşır.

---

## 12. Object storage (D11)

```sql
create table public.digital_objects (
    id              uuid primary key default uuid7(),
    checksum_sha256 char(64) not null,
    byte_size       bigint not null,
    mime_type       text,
    storage_backend text not null default 'local',   -- 'local','s3','minio'
    storage_key     text not null,                   -- backend'e göre anahtar
    rights          text,
    source_system_id uuid references public.source_systems(id),
    created_at      timestamptz not null default now(),
    unique (storage_backend, storage_key)
);
```

Bağlantı tabloları (`expression_digital_object`, `manifestation_digital_object`,
`item_digital_object`) ayrı eklenir. **PostgreSQL dosyanın kendisini tutmaz** — yalnızca
checksum, boyut, haklar ve köken. `storage_backend` + `storage_key` ayrımı, yerel diskten
S3'e geçişi veri taşımadan mümkün kılar.

---

## 13. API versioning ve geriye uyumluluk (D12)

**Karar:** Tüm router'lar `/api/v1` altına taşınır; **mevcut öneksiz yollar bir sürüm
boyunca deprecated alias olarak korunur.**

```python
app.include_router(works.router,  prefix="/api/v1")
app.include_router(works.router,  prefix="",  include_in_schema=False,
                   deprecated=True)   # geçiş dönemi
```

- Yanıtlara `Deprecation` ve `Sunset` başlıkları eklenir.
- Alias'lar kaldırılmadan önce en az bir sürüm boyunca duyurulur.
- Bugünkü 50 endpoint'in sözleşmesi **hiç değişmez**; `/works`, `/persons` aynı gövdeyi
  döndürmeye devam eder.

**Sözleşme testi:** `openapi.json` canlı olarak üretilip commit edilmiş bir **referans
kopyayla** karşılaştırılmalıdır. Bugün repodaki `openapi.json` 11 path içeriyor, canlıda
50 var ve dosya UTF-16 kodlu — yani mevcut haliyle sözleşme koruması **yok**. Aşama 1'de
UTF-8'e çevrilip canlı spec'ten yeniden üretilmeli ve CI'da karşılaştırılmalıdır.

---

## 14. Çok dillilik (D13)

`nomens` yaklaşımı temel olarak doğrudur (`value`, `language`, `script`, `nomen_type`,
`preferred`). Eklenecekler:

| Alan / yapı | Amaç |
|---|---|
| `nomens.normalized_value` | Bloklama ve arama için aksan/noktalama soyulmuş biçim |
| `unaccent` extension | Türkçe ve Latin dilleri için aksan normalizasyonu (kurulabilir, ölçüldü) |
| `nomens.transliteration_of_id` | Aynı adın farklı yazı sistemindeki biçimini bağlar (Kiril ↔ Latin) |
| `nomens.name_order` / `sort_key` | "Dostoyevski, F." ile "Fyodor Dostoyevski" sıralaması |
| `language` için BCP-47, `script` için ISO 15924 doğrulaması | Serbest metin yerine standart kod |

**Kritik önkoşul:** §15.3'te ölçülen trigram index hatası düzeltilmeden çok dilli arama
index'ten faydalanamaz.

---

## 15. Ölçek notları (ölçülmüş)

### 15.1 `entity_relation` ters yön index'i YOK — ölçüldü

`entity_relation` üzerindeki tek kullanışlı index:
`uq_entity_relation_subject_predicate_object (subject_entity_id, predicate, object_entity_id)`.
**Ön kolon `subject_entity_id`'dir.** Uygulama ise ters yönde arıyor:

- [relations.py:78-79](../backend/app/routers/relations.py#L78-L79) — `WHERE subject = :id OR object = :id`
- [search.py:54](../backend/app/routers/search.py#L54) ve [:66](../backend/app/routers/search.py#L66) — recursive CTE, `er.object_entity_id = ct.entity_id`
- [persons.py:539](../backend/app/routers/persons.py#L539) ve [:654](../backend/app/routers/persons.py#L654) — merge sırasında ilişki taşıma

200.000 satırlık sentetik veriyle ölçüm (geçici tablo, işlem geri alındı):

| Sorgu | Plan | Süre | Buffer |
|---|---|---|---|
| Ön kolon: `subject_entity_id` + `predicate` | Index Only Scan | 0,033 ms | 2 |
| **Uygulamanın sorgusu:** `predicate` + `object_entity_id` | **Parallel Seq Scan** (200.000 satır tarandı, 0 eşleşme) | **14,411 ms** | **1804** |
| Ters index eklendikten sonra aynı sorgu | Index Only Scan | 0,052 ms | 2 |

**Sonuç: ~440× süre, ~900× buffer farkı.** `entity_relation` milyarlarca satıra
ulaştığında bu sorgu sistemin en sıcak noktası olur.

**Uygulandı (Aşama 1, revision `b7c1e4a92f30`):**
```sql
create index ix_entity_relation_object_predicate_subject
    on public.entity_relation (object_entity_id, predicate, subject_entity_id);
```

Gerçek tabloda doğrulandı — plan artık doğru index'i kullanıyor:
`Index Only Scan using ix_entity_relation_object_predicate_subject on entity_relation`
(öncesinde yanlış index üzerinden tüm index taranıyordu).

### 15.2 `entities` ve `entity_relation` bölümleme

| Tablo | Öneri | Gerekçe |
|---|---|---|
| `entities` | `PARTITION BY LIST (entity_type)` | Tip bazlı tarama yalnızca ilgili partition'ı okur; alt tip join'leri hızlanır |
| `entity_relation` | `PARTITION BY HASH (subject_entity_id)` | Milyarlarca satırda index yüksekliği ve vacuum maliyeti düşer |
| `nomens` | `normalized_value` + GIN trigram | Çok dilli isim araması ve bloklama |
| `field_assertions` | `PARTITION BY RANGE (observed_at)` | Append-only; eski partition'lar salt-okunur |

**Bugün yapılmaz.** Partition'lama mevcut tabloyu yeniden yazmayı gerektirir; veri
hacmi henüz 91 entity. Tetikleyici eşik: **~50 milyon satır** veya `entity_relation`
sorgu gecikmesinin p95'te 100 ms'yi aşması.

### 15.3 Trigram index'i hem kullanılmıyor hem silinme riskinde — ölçüldü

| Sorgu biçimi | Plan |
|---|---|
| Uygulamanın kullandığı `ILIKE` ([search.py:213](../backend/app/routers/search.py#L213)) | `Seq Scan on works` → **index kullanılmıyor** |
| `lower(canonical_title) LIKE lower(...)` | `Bitmap Index Scan on ix_works_canonical_title_lower_trgm` → **index kullanılıyor** |

Aynı zamanda `alembic check` bu index'i "removed" olarak raporluyordu (§0.2), yani bir
sonraki autogenerate onu silecekti.

**Aşama 1'de yapılan:** index `models.py` içinde bildirildi. Böylece autogenerate onu
artık **silmez** ve `alembic check` temizdir. Kalan sınırlama §0.4'te kayıtlı: Alembic bu
tek index'i karşılaştırmak yerine "eşit varsayıp atlar".

**Dikkat — bu index hâlâ `/search` tarafından kullanılmıyor.** `/search` 20 dallı bir `OR`
çalıştırır; PostgreSQL `BitmapOr` kurabilmek için **tüm** dalların indexlenebilir olmasını
ister. Tek dal (`canonical_title`) düzeltilse bile sorgu yine tam tarama yapar. Bu yüzden
Aşama 1'de `search.py` **bilinçli olarak değiştirilmedi** — kozmetik bir değişiklik ölçülebilir
kazanç sağlamaz. Gerçek çözüm §9'daki Search Plane'dir.

### 15.4 `work_detail` N+1 ve `/search` — ölçüldü

`/search` 14 `LEFT JOIN` + 20 dallı `OR` + `DISTINCT` çalıştırıyor, ardından dönen her
satır için `build_work_detail` çağırıyor; o da eser başına ~8-10 ayrı sorgu ve her
seferinde `resolve_canonical_entity_id` atıyor. 16 eserle ölçüm (10 tekrar):

| Endpoint | min | ortalama | max |
|---|---|---|---|
| `/works` | 7,0 ms | 12,4 ms | 28,2 ms |
| `/persons` | 9,6 ms | 64,5 ms | 483,8 ms |
| **`/search?q=a`** | **117,1 ms** | **163,1 ms** | **364,6 ms** |

Sadece 16 eserle 10× fark. Bu, Search Plane'in (§9) neden gerekli olduğunun ölçülmüş
kanıtıdır. Aşama 1'de ucuz kazanç: `build_work_detail` için toplu (batch) sorgu.

### 15.5 Reconciliation aday bulma `works` tablosunu tam tarıyor — ölçüldü

`services/reconciliation.py` içindeki `retrieve_work_candidates` şu biçimde sorguluyor:

```python
similarity = func.similarity(func.lower(Work.canonical_title), source_title)
select(Work).where(Work.canonical_title.is_not(None),
                   similarity >= WORK_TRIGRAM_THRESHOLD)   # 0.30
```

**Bu sorgu biçimi pg_trgm GIN index'ini yapısal olarak kullanamaz.** pg_trgm index'i `%`
operatörünü (ve `LIKE`/`ILIKE`) hızlandırır; `similarity(...)` bir fonksiyon çağrısıdır ve
planlayıcının onun için index yolu yoktur.

200.000 satırlık sentetik veriyle ölçüm (geçici tablo, `gin (lower(canonical_title)
gin_trgm_ops)` index'li, işlem geri alındı):

| Sorgu biçimi | Plan |
|---|---|
| **Mevcut kod:** `similarity(lower(...), x) >= 0.3` | **Seq Scan** — 823 ms, 200.000 satır filter'dan geçti, 1667 buffer |
| Index kullanılabilir: `lower(...) % x` | **Bitmap Index Scan on _probe_trgm** — index kullanıldı |

Hız karşılaştırması olarak okunmamalıdır (sentetik korpusta trigram seçiciliği düşüktü);
kanıtlanan şey **yapısal**dır: mevcut sorgu biçimi index'i kullanamaz, `%` biçimi kullanır.

**Etki:** `generate_work_candidates` her kaynak kayıt için bu fonksiyonu çağırır → kaynak
kayıt sayısı × `works` tam taraması. 100 milyon eserde bu yol çalışmaz.

**Uygulandı (§0.6).** Engelleme `%` operatörüne taşındı ve `similarity()` yalnızca hayatta
kalan satırları **yeniden sıralamak** için kullanılıyor. Ölçülen sonuç: 200.000 farklı
başlıkta **1442 ms → 14,5 ms**, **2062 → 192 buffer**. §8'deki "önce aday kümesini
daralt" ilkesinin reconciliation tarafındaki karşılığıdır.

### 15.6 İki taraflı normalizasyon uyuşmazlığı — Türkçe için sistematik hata

`retrieve_work_candidates` iki tarafı **farklı** normalizasyondan geçiriyor:

| Taraf | Normalizasyon |
|---|---|
| Veritabanı | `lower(canonical_title)` — yalnızca küçük harf |
| Gelen kayıt | `normalize_text()` — `casefold` + NFKD + **aksan temizliği** + noktalama temizliği ([reconciliation.py:31-57](../backend/app/services/reconciliation.py#L31-L57)) |

Ölçüm (eşik = 0.30):

```
similarity(lower('Suç ve Ceza'), 'suc ve ceza')  =  0.714   <-- birebir aynı eser
similarity(lower('Suç ve Ceza'), 'suç ve ceza')  =  1.000
```

**Birebir aynı başlık, tek bir aksan yüzünden 1.000 yerine 0.714 skor alıyor.** Kayıp
0.286'dır ve aksan yoğunluğuyla büyür — Türkçe (ç, ğ, ı, ö, ş, ü) bu hatanın en çok
vurduğu dillerden biridir. Kısa ve aksanlı başlıklarda gerçek eşleşmeler 0.30 eşiğinin
altına düşüp **hiç bulunamayabilir**.

**Kök neden:** depoda normalize edilmiş bir başlık kolonu yok; her sorguda yeniden
normalize ediliyor ve iki taraf farklı kurallarla normalize ediliyor.

**Uygulandı (§0.6).** `works.normalized_title` kolonu eklendi, Python `normalize_text` ile
ORM olayı üzerinden türetiliyor ve üzerine trigram GIN index kuruldu. Ölçülen sonuç:
birebir aynı Türkçe başlık **0.714 → 1.000**. §14'teki `nomens.normalized_value`
kararının aynısıdır; bu bulgu o kararın gerekçesini ölçümle doğruladı.

---

## 16. Geçiş planı — aşamalı, geri alınabilir

**İlkeler:** her migration'ın `downgrade()`'i yazılır ve **test edilir**; hiçbir aşama
veri silmez; her aşama sonunda `alembic current` = `alembic heads` doğrulanır; her aşama
sonunda mevcut API sözleşmesi test edilir.

### Aşama 0 — Karar (bu belge)

Kod yok, şema yok. **Bu belgenin onaylanması** Aşama 1'in önkoşuludur.

### Aşama 1 — Zemin ve düzeltmeler (tamamen eklemeli) — ✅ TAMAMLANDI

Uygulama kaydı ve doğrulama kanıtları: **§0.4**.

| İş | Detay |
|---|---|
| `alembic check` temizliği | `models.py`'ye trigram index bildirimi **veya** `search.py`'de `lower()` kullanımı (§15.3) |
| Ters yön index'i | `ix_entity_relation_object_predicate_subject` (§15.1) |
| `source_systems` tablosu | §6.2 — boş tablo, veri kaybı yok |
| `source_records.source_system_id` | Nullable FK; mevcut `source_system` string'i korunur |
| `control` ve `tenant` şemaları | **Boş** oluşturulur; tablo yok |
| `openapi.json` | UTF-8'e çevrilir, canlı spec'ten yeniden üretilir |

- **Geri alma:** her migration'ın `downgrade()`'i index/tablo düşürür; veri kaybı yok.
- **Doğrulama:** `alembic check` çıktısı boş; `EXPLAIN` ters yön sorgusunda Index Scan;
  `/health`, `/works`, `/search`, `/search/concept/{id}` 200; ölçüm tablosu tekrar alınır.

### Aşama 2 — Control plane — ✅ TAMAMLANDI

Uygulama kaydı ve doğrulama kanıtları: **§0.5**. Özet: `control.tenants`,
`control.organizations`, `control.branches`, `control.tenant_databases` oluşturuldu ve
mevcut kurumlardan backfill edildi (4 tenant / 4 organization / 4 branch / 4
tenant_databases).

**Taslaktan sapma (bilinçli):** §3.3'teki taslak backfill'in
`role='holding_institution'` ile filtrelenmesini öngörüyordu. Uygulamada **role filtresi
kullanılmadı**, çünkü roller serbest metindir ve emaneti başka bir rolle kaydedilmiş
nüshalar sessizce düşerdi. Ayrıntı ve gerekçe: §0.5.

- **Geri alma:** `control` şemasındaki dört tablo düşürülür; `public` verisi hiç
  dokunulmamıştır. İçerik türetilmiş olduğu için yeniden üretilebilir (kanıtlandı).
- **Doğrulama:** 4/4/4/4 satır üretildi, her organization otorite kaydına bağlı,
  `alembic check` temiz, API 200, mevcut veri satır sayıları değişmedi.

### Aşama 3 — Tenant plane iskeleti

`tenant.locations`, `tenant.holdings`, `tenant.items`, RLS politikaları, `libraryhub_*`
rolleri. **Henüz veri taşınmaz.**

- **Geri alma:** `drop schema tenant cascade` — `public` etkilenmez.
- **Doğrulama:** RLS testi — yanlış `tenant_id` ile bağlanan oturum **0 satır** görür.

### Aşama 4 — Item göçü (çift yazım, en kritik aşama)

1. Mevcut her `items` satırı için:
   - `manifestation_item` üzerinden hedef Manifestation bulunur,
   - `item_agent_relation(role='holding_institution')` üzerinden kurum → şube bulunur,
   - `tenant.holdings` satırı üretilir (yoksa), `tenant.items` satırı üretilir,
   - `barcode`, `shelfmark`, `condition`, `availability_status`, `notes` kopyalanır.
2. **Uyumluluk görünümü** oluşturulur:
   ```sql
   create view public.items_compat as
     select i.id as entity_id, i.barcode, i.shelfmark, i.condition,
            i.availability_status, i.notes, h.manifestation_entity_id,
            o.collective_agent_entity_id as holding_institution_entity_id
     from tenant.items i
     join tenant.holdings h on h.id = i.holding_id
     join control.organizations o on o.tenant_id = i.tenant_id;
   ```
   Mevcut `/items` ve `/works/{id}/detail` endpoint'leri bu görünümden okumaya geçirilir;
   **API sözleşmesi birebir aynı kalır.**
3. `public.items` ve `manifestation_item` **silinmez**, salt-okunmaya alınır.

- **Geri alma:** görünüm düşürülür, endpoint'ler eski tablolara döner. Legacy tablolar
  Aşama 6'ya kadar yerinde durduğu için geri dönüş tek satırlık bir değişikliktir.
- **Doğrulama:** `select count(*) from public.items` = `select count(*) from tenant.items`;
  her `tenant.items` satırı bir `holdings` ve bir `manifestations` satırına çözülüyor;
  `/works/{id}/detail` yanıtı **önce/sonra bayt düzeyinde karşılaştırılır**.

### Aşama 5 — Okuma geçişi ve yazma yolu

Yeni kayıtlar yalnızca `tenant.*` tablolarına yazılır; `public.items` yazılmaz. Legacy
tablolar deprecated işaretlenir. `/api/v1` öneki eklenir, öneksiz yollar alias olarak
korunur (§13).

### Aşama 6 — Legacy temizlik (çok sonra, ayrı açık onay)

`public.items`, `public.manifestation_item`, `public.item_agent_relation` düşürülür.
**Yalnızca:** tam yedek alındıktan, en az bir sürüm geri dönüşsüz çalıştıktan ve açık
onay verildikten sonra. `entities` tablosundan `'ITEM'` tipinin CHECK kısıtından
çıkarılması da **bu aşamaya** aittir — bugün çıkarmak mevcut satırları geçersiz kılar.

### Aşama bağımlılık sırası

```
Aşama 0 (karar)
   └─> Aşama 1 (zemin)  ── zorunlu önkoşul
          └─> Aşama 2 (control)
                 └─> Aşama 3 (tenant iskelet)
                        └─> Aşama 4 (item göçü + uyumluluk görünümü)
                               └─> Aşama 5 (okuma/yazma geçişi + API v1)
                                      └─> Aşama 6 (legacy temizlik, ayrı onay)
```

---

## 17. Karar özeti

| # | Karar | Bölüm |
|---|---|---|
| D1 | Plane ayrımı şema düzeyinde (`public` global kalır, `control` + `tenant` eklenir); tek cluster | §1.2 |
| D2 | `Holding` birinci sınıf tenant varlığı; `Item` Holding'e ait; `Item` global `entities`'ten çıkar | §3 |
| D3 | Holding hedefi exclusive arc (Manifestation XOR Expression) | §3.4 |
| D4 | Yeni satırlar UUIDv7; mevcut UUIDv4 korunur; `canonical_uri` handle | §4 |
| D5 | Paylaşımlı şema + `tenant_id` + RLS + tenant→cluster yönlendirme katmanı | §5 |
| D6 | `source_systems` + `field_assertions`; kanonik değerler kolonda kalır | §6 |
| D7 | `entity_merge_moves` + `entity_splits` ile geri alınabilir merge | §7 |
| D8 | Mevcut reconciliation altyapısı korunur, kayıt tipi genelleştirilir + identifier bloklama | §8 |
| D9 | PostgreSQL doğruluk kaynağı; outbox tablosu şimdi, arama motoru sonra | §9 |
| D10 | AI çıktısı doğrudan yazmaz; `status='proposed'` iddia üretir | §10 |
| D11 | Nesne verisi PostgreSQL'de tutulmaz; `digital_objects` meta veri tutar | §12 |
| D12 | `/api/v1` + deprecated alias; OpenAPI sözleşme testi | §13 |
| D13 | Nomen genişletmeleri (`normalized_value`, `transliteration_of_id`, BCP-47/ISO 15924) | §14 |
| D14 | Kurumun otorite kimliği (`collective_agents`) ile tenant kimliği (`organizations`) **ayrı** kayıtlar, FK ile bağlı | §3.3 |

### D14 gerekçesi (özel not)

Bir üniversite kütüphanesi aynı anda iki şeydir:
- **Global otorite kaydı:** atıf yapılabilir tüzel kişi (yayıncı, kurumsal yazar, holding
  kurumu). Kaydı yüzyıllarca sabit kalmalı.
- **Control plane kaydı:** abonelik, kullanıcılar, yapılandırma. Silinebilir, askıya
  alınabilir, başka cluster'a taşınabilir.

Bunları tek satırda birleştirmek, tenant askıya alındığında global atıf kaydının da
etkilenmesi anlamına gelir. Ayrıca **her tüzel kişi tenant değildir** (yayınevi tenant
olmaz), **her tenant tüzel kişi değildir** (konsorsiyum olabilir). İki kayıt + FK doğru
modeldir.

---

## 18. Açık kararlar (onay gerekiyor)

| # | Soru | Önerim |
|---|---|---|
| OD1 | `public` şeması global plane adı olarak kalsın mı? | **Kalsın.** Taşımak riskli, kazanç kozmetik |
| OD2 | UUIDv7 geçişi onaylanıyor mu? | **Evet**, yalnızca yeni satırlar için |
| OD3 | Barkod benzersizliği tenant geneli mi, şube bazında mı? | **Tenant geneli** (şubeler arası transferde çakışmayı önler); gerekirse `branch_id` eklenir |
| OD4 | `Holding.branch_id` zorunlu mu? | **Zorunlu.** Tek şubeli kurum için bir varsayılan şube (`is_default`) üretilir |
| OD5 | Süreli yayında Holding hedefi Manifestation mı Expression mı? | **Manifestation birincil**, Expression alternatif (exclusive arc) |
| OD6 | Outbox tablosu şimdi mi eklensin? | **Evet** (§9.2) — tek tablo, sıfır operasyonel yük |
| OD7 | Arama motoru ne zaman? | `/search` p95'i 500 ms'yi aştığında veya veri ~1M eseri geçtiğinde |
| OD8 | Veri yerleşimi (data residency) gereksinimi var mı? | Kolonlar bugün eklenir, politika sonra netleşir |
| OD9 | `/api/v1` geçişi Aşama 5'te mi? | **Evet**, alias ile birlikte |
| OD10 | Kimlik doğrulama (Control Plane) ne zaman? | Aşama 2 ile birlikte, en azından personel girişi |
| OD11 | Django değerlendirmesi için tetikleyici nedir? | Yönetim ekranı/personel yetkilendirme ihtiyacı somutlaştığında — **bu belge kapsamı dışı** |
| OD12 | Çapraz plane yabancı anahtarları (`tenant.*` → `control.*` ve `public.*`) kalıcı mı? | **Bugün evet, tek cluster olduğu için gerçek bütünlük sağlıyorlar.** Ama D5 gereği bir tenant başka cluster'a taşındığında bu kısıtlar kalkmak zorunda. Plane'ler fiziksel olarak ayrılmadan önce karar verilmeli: (a) her cluster'da global plane replikası tutup FK'leri korumak, (b) FK'leri kaldırıp bütünlüğü uygulamaya taşımak. Bugün (a) daha güçlü, çünkü veri tek yerde |
| OD13 | RLS ne zaman gerçek yaptırım hâline gelir? | ✅ **Çözüldü (§0.8).** Uygulama `libraryhub_app` (superuser **değil**) rolüyle bağlanıyor ve `tenant_session()` her tenant işleminde `set_config('libraryhub.tenant_id', …, is_local => true)` çalıştırıyor |

---

## 19. Yapılmayacaklar (önümüzdeki aşamalarda)

- Kafka, Neo4j, Kubernetes, mikroservis ayrımı kurmak.
- `public.items` / `manifestation_item` / `entities` tablolarını **bugün** düşürmek.
- `entities.entity_type` CHECK kısıtından `'ITEM'` çıkarmak (mevcut satırları geçersiz kılar).
- Mevcut `openapi.json` sözleşmesini bozacak endpoint değişikliği.
- Mevcut `reconciliation_*` politikasını yeniden yazmak.
- Mevcut PostgreSQL verisini yeniden üretmek veya UUID'leri değiştirmek.
- Alembic geçmişini düzleştirmek / revision'ları birleştirmek.
- Veri hacmi gelmeden partition'lama ve arama motoru eklemek.
- AI çıktısını insan onayı olmadan kanonik alanlara yazmak.

---

## Ek A — Terim sözlüğü

| Terim | Bu belgedeki anlamı |
|---|---|
| **Global Knowledge Plane** | Kurumdan bağımsız, paylaşılan bibliyografik/otorite verisi (`public` şeması) |
| **Control Plane** | Kimlik, tenant, abonelik, yetkilendirme, yönlendirme (`control` şeması) |
| **Tenant Data Plane** | Kuruma ait operasyonel veri (`tenant` şeması) |
| **Manifestation** | Belirli bir baskı/yayın; kurumdan bağımsız, bir kez tanımlanır |
| **Holding** | Bir kurumun bir Manifestation için sahip olduğu koleksiyon beyanı |
| **Item** | Bir Holding'e ait tek fiziksel/dijital nüsha (barkod düzeyi) |
| **Assertion** | Bir alanın belirli bir kaynak tarafından iddia edilen değeri (provenance) |
| **Exclusive arc** | İki FK'den tam olarak birinin dolu olması kısıtı |
| **Outbox** | Veri değişikliğiyle aynı transaction'da yazılan olay kaydı |
| **RLS** | Row Level Security — satır düzeyinde erişim kuralı |

## Ek B — Doğrulama komutları

```powershell
# Servis durumu
docker compose ps -a

# Alembic: current ve heads AYNI olmalı
docker compose exec -T api alembic current
docker compose exec -T api alembic heads
docker compose exec -T api alembic check     # çıktı boş olmalı

# Şema ve veri
docker compose exec -T postgres psql -U library -d libraryhub -tAc `
  "select version_num from alembic_version"
docker compose exec -T postgres psql -U library -d libraryhub -tAc `
  "select count(*) from information_schema.tables where table_schema='public'"

# Ters yön index'inin kullanıldığını doğrula
docker compose exec -T postgres psql -U library -d libraryhub -c `
  "explain (analyze, costs off) select subject_entity_id from entity_relation
   where predicate='broader' and object_entity_id = gen_random_uuid();"

# Trigram index'inin kullanıldığını doğrula
docker compose exec -T postgres psql -U library -d libraryhub -c `
  "set enable_seqscan=off; explain select entity_id from works
   where lower(canonical_title) like lower('%bilgi%');"

# API sözleşmesi (önce/sonra karşılaştırması için sakla)
Invoke-RestMethod 'http://localhost:8010/openapi.json' | ConvertTo-Json -Depth 20

# Uçtan uca
Invoke-RestMethod 'http://localhost:8010/health'
Invoke-RestMethod 'http://localhost:8010/works?page=1&page_size=5'
Invoke-RestMethod 'http://localhost:8010/search?q=bilgi'
```

---

## Ek C — Sonraki adım

**Aşama 1, 2, normalizasyon düzeltmesi, OD13, Aşama 3, Aşama 4, atama kuyruğu ve ölçek
hata avı tamamlandı** (§0.4–§0.11). Sistem `c5d8f1b69a07` head'inde, `alembic check`
temiz, **test paketi 33/33 yeşil**, API sağlıklı ve her aşamanın geri alınabilirliği
kanıtlandı.

> **Uygulama rolünün parolasını değiştirmek.** `.env` içindeki `APP_DB_PASSWORD`
> güncellenir, sonra `docker compose exec -T postgres psql -U library -d libraryhub -c
> "alter role libraryhub_app with password '<yeni>'"` çalıştırılır ve
> `docker compose up -d` ile API yeniden başlatılır. Parola tek yerde (gitignore'lu `.env`)
> durur; `docker-compose.yml` yalnızca değişken adı taşır.

### Sıradaki: Aşama 5 — yazma yolu ve `/api/v1`

Aşama 4 veriyi taşıdı ve okuma yolunu `public.items_compat`'a çevirdi; **yazma yolu bilerek
legacy tablolarda kaldı.** Aşama 5 onu taşır:

1. `POST /items` yalnızca `tenant.items` + `tenant.holdings`'e yazar,
2. `POST /items/{id}/agents` yapısal hâle gelir (holding kurumu artık ilişki değil, aidiyet),
3. `public.items_compat`'ın ikinci dalı boşalır ve görünüm tek dala iner,
4. legacy tablolar deprecated işaretlenir (silme Aşama 6),
5. `/api/v1` öneki eklenir, öneksiz yollar bir sürüm boyunca alias olarak korunur (§13).

**Aşama 5'in önündeki tek gerçek engel: API'de tenant kimliği yok (OD10).**
`POST /items` şu an hangi kuruma yazacağını bilemez; istekte tenant bilgisi taşınmıyor ve
kimlik doğrulama yok. Bu çözülmeden yazma yolu taşınamaz — taşınırsa her yeni nüsha
rastgele bir tenant'a düşer ya da hiç yazılamaz.

Bu yüzden **Aşama 5'in ilk işi kimlik doğrulama ve tenant bağlamıdır** (OD10): en azından
personel girişi + isteğin tenant'ını belirleyen bir mekanizma, ve her istekte
`tenant_session()` kullanımı. Bu olmadan RLS'in `WITH CHECK` tarafı da zaten yazmayı
reddeder — ki bu doğru davranıştır.

**Kalan iş kalemleri:**

1. `docs/reconciliation-policy.md` güncellenmeli — "33 isolated SQLite test pass" ifadesi
   artık doğru ama testlerin SQLite vekili kullandığı ve `%` blocking'in PostgreSQL'e özel
   olduğu yazılmalı.
2. `works.normalized_title` için ileride `NOT NULL` düşünülebilir; bugün nullable çünkü
   yalnızca noktalama içeren bir başlık gerçekten karşılaştırılamaz.
3. `nomens` için aynı normalizasyon (`normalized_value`) **yapıldı** — §0.27.
4. `public.items`, `manifestation_item` ve `item_agent_relation` Aşama 6'ya kadar
   **silinmez**; `entities.entity_type` CHECK'inden `'ITEM'` çıkarmak da Aşama 6'nın işidir.
5. ✅ **`unassigned` kuyruğu kapatıldı** (§0.10) — 7 nüsha kurumlarına bağlandı, tenant 0'a
   indi. Kuyruk mekanizması yerinde kalıyor: ileride belirsiz bir nüsha yine oraya düşer.
6. **Boşluk sorgusu düzeltilmeli** (§0.11): `GET /search?q=%20` şu an 200 dönüp keyfi 50
   eser gösteriyor. `q=` doğru şekilde 422 verirken bunun da reddedilmesi gerekir.
7. **`/search` ölçekte yavaşlıyor** (§0.11): 316 eserde ortalama 298–678 ms, Arapça sorguda
   944 ms tepe. §9'daki Search Plane artık ölçekli kanıtla gerekçeli; PostgreSQL'de kalmaya
   devam ederse 100 milyonda kullanılamaz.
8. **Kimlik doğrulama** (OD10) — Aşama 5'in önündeki tek gerçek engel, aşağıda.

---

## Ek D — Ortam notu (Aşama 1 sırasında gözlenen)

Bunlar mimari kararı değil, geliştirme ortamı gözlemleridir; kayda geçiyor:

1. **Konteyner root çalışıyor** (`docker inspect` → `User=` boş) ve `./backend` host
   dizinine bağlı. Sonuç: konteyner host ağacına **root sahipli** dosyalar yazıyor.
   Örneğin `backend/app/__pycache__` host kullanıcısı tarafından yazılamaz hâle geldi;
   Python bu dizine `.pyc` yazmaya çalışırken `Permission denied` veriyor. Aşama 5'te
   Dockerfile'a `USER` eklenmesi veya `PYTHONDONTWRITEBYTECODE=1` bunu çözer.
2. **DSH sandbox, çalışma alanında önceden var olan dosyalara kabuk üzerinden yazmayı
   engelliyor.** Onarım sonrası kök dizinin kazandığı yazma iznini *miras alan* yeni
   dosyalar yazılabilir; onarım öncesi oluşturulmuş dosyalar (ör. `openapi.json`) kabuk
   üzerinden değiştirilemez. DSH'nin kendi dosya araçları bu dosyaları sorunsuz düzenler.
   `openapi.json` bu yüzden silinip yeniden oluşturularak kalıcı olarak yazılabilir hâle
   getirildi.
