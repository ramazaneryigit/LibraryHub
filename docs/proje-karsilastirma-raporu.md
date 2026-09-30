# LibraryHub — İlk Proje Dosyası ile Bugünkü Hâl Arasındaki Fark

**Karşılaştırılan sürümler**

| | Commit | Tarih |
|---|---|---|
| Başlangıç | `1906e50` — *Initial LibraryHub WEMI and concept search implementation* | 2026-09-18 |
| Bugün | `4ee6c94` | 2026-09-30 |

Aradaki mesafe: **100 commit**, 12 gün. Ölçümler iki ayrı çalışma ağacı üzerinde
alındı; sayılar tahmin değil.

---

## 1. Tek bakışta

| Ölçüm | Başlangıç | Bugün | Kat |
|---|---|---|---|
| Commit | 1 | **100** | — |
| Python dosyası | 13 | **141** | 10,8× |
| Python satırı | 2.640 | **25.643** | 9,7× |
| API uç noktası | 16 | **77** | 4,8× |
| Model sınıfı | 19 | **47** | 2,5× |
| Migration | 8 | **49** | 6,1× |
| **Test** | **0** | **6 dosya / 2.269 satır** | ∞ |
| Operasyon script'i | 0 | **11 / 3.791 satır** | ∞ |
| Arayüz | **0** | **6 dosya / 3.961 satır** | ∞ |
| Belge | **0** | **2 dosya / ~3.600 satır** | ∞ |
| Veritabanı tablosu | 19 | **48** | 2,5× |
| Görünüm (view) | 0 | **3** | ∞ |
| Tetikleyici | 7 | **42** | 6× |
| RLS politikası | **0** | **6** | ∞ |
| Kısıt | — | **280** | — |
| Index | — | **125** | — |

---

## 2. Başlangıç noktası — ne vardı

```
backend/app/
    __init__.py        0 satır
    db.py             15 satır
    main.py        1.163 satır   ← 16 uç noktanın tamamı burada
    models.py        403 satır
backend/alembic/versions/        8 migration
db/backup_before_lrm.sql        87 satır
docker-compose.yml
```

**Karakteristiği:**

- **Tek dosyada 1.163 satır.** Uç noktalar, Pydantic modelleri, iş mantığı ve SQL
  aynı dosyada; `main.py` içinde ne olduğunu anlamak için tamamını okumak gerekiyordu.
- **Tek düzlem.** Her şey `public` şemasında; `control.` veya `tenant.` diye bir şey
  yok (ölçüm: şema niteleyicisi kullanımı **0**).
- **İzolasyon yok.** `ENABLE ROW LEVEL SECURITY` **0**, `CREATE POLICY` **0**.
  Yani bugünkü anlamda bir kiracı ayrımı yoktu.
- **Test yok.** `tests/` klasörü bile yok.
- **Script yok.** Seed/göç/denetim araçları yok.
- **Arayüz yok.** `static/` yok; API çıplak.
- **Belge yok.** `docs/` yok.

7 tetikleyici vardı ve hepsi **alt tür bütünlüğü** içindi (bir `works` satırının
`entities` satırı doğru türde olmalı) — bugün de duruyorlar, ama artık ertelenebilir
kısıt tetikleyicisi olarak.

---

## 3. Bugünkü hâl — ne var

```
backend/app/
    api/          21 dosya   → api/v1/__init__.py, api/deps.py, api/v1/routes/ (17)
    services/     12 dosya / 3.768 satır
    schemas/      16 dosya /   586 satır   ← API sözleşmesi, handler'lardan ayrı
    core/          5 dosya /   337 satır   ← config, ids, security, text (yapraklar)
    db/           17 dosya /   226 + modeller
        models/   14 dosya / 3.383 satır   ← 47 model, alan alan bölünmüş
    static/        6 dosya / 3.961 satır   ← arama arayüzü + yönetim paneli
    main.py                     (montaj)
backend/alembic/versions/     49 migration / 5.272 satır
backend/tests/                 6 dosya / 2.269 satır
backend/scripts/              11 dosya / 3.791 satır
docs/                          2 dosya / ~3.600 satır
```

**Katmanlar ve kuralları:**

| Katman | Ne yapar | Kuralı |
|---|---|---|
| `core/` | config, uuid7, parola/oturum, metin normalizasyonu | **Hiçbir şeye bağlı değil** — model modüllerinden bile import edilebilir |
| `db/` | motor, oturum, kiracı kapsamı | İki motor: uygulama rolü ve **sahip** rolü |
| `db/models/` | 47 model, alan başına bir modül | `identity` önce gelir; bağımlılık `relationship()` ile **açık** |
| `schemas/` | istek gövdeleri | Handler'lar buradan import eder |
| `services/` | iş mantığı ve SQL | Hem API hem script aynı fonksiyonu çağırır |
| `api/v1/routes/` | HTTP | İnce; SQL ve kural serviste |
| `static/` | arayüz | Çerçevesiz, `escapeHtml`, hash yönlendirme |

---

## 4. Veri modeli: 1 düzlemden 3 düzleme

**Başlangıç:** her şey `public`. 19 tablo.

**Bugün:** üç şema, 48 tablo.

| Şema | Tablo | Ne tutar |
|---|---|---|
| `public` | **35** | Paylaşılan bibliyografik kayıt (FRBR/LRM) + `entities` kayıt defteri |
| `control` | **8** | Kiracılar, kurumlar, şubeler, kullanıcılar, oturumlar, e-posta doğrulama |
| `tenant` | **5** | Nüshalar, holding'ler, öneriler, yerleşkeler, nüsha tanımlayıcıları |

**3 görünüm** düzlemler arası okuma için: `items_compat`, `holdings_compat`,
`item_identifiers`.

### Asıl mimari karar: `Manifestation → Holding → Item`

Bu ayrım başlangıçta yoktu. Bugün:

```
Work ──► Expression ──► Manifestation (baskı) ──► Holding (kütüphane) ──► Item (nüsha)
                            ▲                          ▲                       ▲
                        paylaşılan                 kiracının              kiracının
                         kayıt                      kaydı                  nüshası
```

**Kütüphane Holding'in özelliğidir**, nüshanın değil:
`holdings.branch_id → branches.organization_id → organizations.collective_agent_entity_id`.

Bunun neden önemli olduğu ölçülmüş bir hatayla kanıtlandı: kurum **nüshadan**
türetildiğinde, holding'i kataloglayıp nüshalarını henüz girmemiş bir kütüphane
toplu katalogda **hiç görünmüyordu**. Bu veritabanında 16 holding'in **6'sı**
nüshasızdı — kütüphanelerin üçte biri. 1.000 kütüphaneli hedefte bu, katalogun
kendisini kaybetmek demek.

---

## 5. Güvenlik modeli: yoktan veritabanı düzeyine

| | Başlangıç | Bugün |
|---|---|---|
| RLS | **0** | 6 politika, `FORCE` ile, fail-closed |
| Uygulama rolü | — | `libraryhub_app` (süper kullanıcı **değil**) |
| Kiracı rolü | — | `libraryhub_tenant_app` — `SET LOCAL ROLE` ile **geçiş** |
| Global yazma rolü | — | `libraryhub_global_app` |
| Hesap kalkanı | — | `guard_application_account_writes` |
| Şube sahipliği | — | `assert_branch_belongs_to_tenant()` |
| Alt tür bütünlüğü | 7 tetikleyici | 9 (ertelenebilir kısıt tetikleyicisi) |

**Temel ilke değişti:** başlangıçta koruma *yoktu*; bugün koruma **grant ve
politikadır**, uygulama kodunda bir `WHERE` değil. Bir kiracı işlemi fiziksel
olarak `public.works`'a yazamaz — uygulama istese bile.

Bu, yol boyunca iki gerçek açık kapatılarak kuruldu:

1. **Kalkan yalnızca INSERT'i koruyordu.** Bir `UPDATE` bir kütüphaneciyi yönetici
   yapabilir ya da bir yöneticinin parolasını değiştirebilirdi. Kapatıldı.
2. **`pg_has_role` bir süper kullanıcı için her rolde `true` döner** — yani hesap
   kalkanının "owner muaf" dalı hiç çalışmamıştı ve `create_user.py` kalkan
   eklendiğinden beri hiç hesap açamıyordu.

---

## 6. Test ve doğrulama: sıfırdan güvenlik ağına

| | Başlangıç | Bugün |
|---|---|---|
| Birim testi | **0** | **123** |
| Senaryo kontrolü | **0** | **39** |
| Test satırı | 0 | 2.269 |

**İki katman, iki farklı iş:**

- **123 birim testi** (SQLite, hızlı): parola/oturum akışı, kiracı izolasyonu,
  öneri kuralları, yönetici yetkisi, personel yönetimi.
- **39 senaryo kontrolü** (gerçek PostgreSQL): RLS'in gerçekten kapalı olduğu,
  rollerin gerçekten yasakladığı, tetikleyicilerin gerçekten reddettiği, indeksin
  gerçekten yeniden üretilebilir olduğu.

**Ayrım keyfi değil.** SQLite'ın göremediği şeyler var ve bunlar tam da en tehlikeli
olanlar: RLS, roller, PG'ye özel kısıtlar, `uuid[]`, `jsonb`, `unaccent`. Birkaç kez
"testler geçiyor ama kod çalışamaz" durumu yaşandı ve her biri bu yüzden.

**Bugünkü yeşil durum:** 123/123 test, 39/39 kontrol, `alembic check` temiz.

---

## 7. Yol boyunca bulunan gerçek hatalar

Bunlar raporun en kullanışlı kısmı: her biri **sessizdi** ve her biri bir kontrol
veya bir ekran görüntüsü tarafından yakalandı.

| Hata | Nasıl görünüyordu | Kök neden |
|---|---|---|
| Ölçek fixture'ları gerçek kayıtlara bağlanıyordu | Arama çalışıyor, cevabı kurgu | Üreteç "ilk 12 manifestation"ı seçiyordu — onlar gerçek kayıtlardı |
| Kütüphane bağı nüshadan kuruluyordu | Kütüphanelerin üçte biri görünmüyor | Kurum, holding'in değil nüshanın özelliği sanılmıştı |
| Bir migration yeniden oynatılamıyordu | Hiçbir şey — bu veritabanı o adımı geçmişti | Yeniden adlandırılmış bir modülü import ediyordu; sıfırdan kurulum orada dururdu |
| Alt tür yazma sırası bozuldu | Her global kayıt oluşturma çöküyor | SQLAlchemy, ilişkisiz mapper'ları **isim sırasına** göre flush ediyor; sıra şans eseriydi |
| `hidden` form açılışta görünüyordu | Form gizlenmiyor | `[hidden]` özniteliğini `display: flex` eziyor |
| Arama kartı kütüphane göstermiyordu | "Kimde var?" cevapsız | Kart o veriyi hiç okumuyordu (detay okuyordu) |
| `/static/*` önbellek başlıksız | Düzeltme yayınlanıyor, kullanıcı eskisini görüyor | `Cache-Control` yok → tarayıcı sormadan yeniden kullanıyor |

**Ortak desen:** hata *veri* veya *yapı* doğruydu, **bağ** yanlıştı. Ve hiçbiri
testlerle görülmedi; ya bir PostgreSQL kontrolü ya da gerçek tarayıcı ekran
görüntüsü buldu.

---

## 8. Geliştirme için pratik rehber

### Bir şey eklerken nereye

| Ekleyeceğiniz | Yeri |
|---|---|
| Yeni bir uç nokta | `api/v1/routes/<kaynak>.py` + `schemas/<kaynak>.py` |
| İş kuralı veya sorgu | `services/<konu>.py` — **route'a SQL yazmayın** |
| Yeni tablo | `db/models/<alan>.py` + bir migration |
| Ayar | `core/config.py` — başka yerde `os.environ` **okumayın** |
| Doğrulama kuralı | Tercihen **veritabanına** (kısıt/tetikleyici), uygulamaya değil |

### Bozmamanız gereken değişmezler

1. **Kiracı izolasyonu veritabanında.** `tenant.*`'a uygulama kodunda `WHERE
   tenant_id = ...` eklemeyin; politika zaten orada ve ikinci bir filtre
   "uygulama koruyor" yanılsaması üretir.
2. **`core/` yapraktır.** `app.db`'den veya `app.api`'den import etmez.
3. **Kurum holding'den türer**, nüshadan değil.
4. **Türetilmiş hiçbir şey doğruluk kaynağı değil.** Arama indeksi atılıp
   `reindex` ile geri kurulabilmeli.
5. **Kontrol yazmadan kural eklemeyin.** Bu projede 39 kontrol var ve ikisi kendi
   eklediğim tabloyu ilk koşuda yakaladı.

### Çalıştırma

```bash
docker compose up -d
docker compose exec -T api alembic upgrade head
docker compose exec -T api sh -c "cd /app && /tmp/tv/bin/python -m unittest discover -s tests"
docker compose exec -T api sh -c "cd /app/scripts && python run_scale_checks.py"
docker compose exec -T api sh -c "cd /app/scripts && python reindex.py --rebuild"
```

Arayüz `http://localhost:8010/`, panel `http://localhost:8010/admin`.

### Bilinen sınırlar

- `/search` henüz **indeksi kullanmıyor**; kendi SQL'i ile çalışıyor (ölçüm: 944 ms
  tepe). İndeks hazır ve doğrulanmış; geçiş ayrı bir adım.
- **`control.tenants` uygulama üzerinden açılamaz** — yalnızca
  `register_domain.py`, sahip kimlik bilgisiyle.
- **Yönetici hesabı panelden açılamaz** — kalkan reddeder, `create_user.py` gerekir.
- **Raporlama (ödünç/gecikme) yok**: önce bir dolaşım modeli gerekiyor.
- **`nomens.normalized_value` ORM olayıyla doldurulur** — ham SQL yazan biri
  kolonu boş bırakırsa kontrol yakalar.

---

## 9. Özet

**Başlangıç:** 1.163 satırlık tek bir `main.py`, tek şema, sıfır test, sıfır
izolasyon, sıfır arayüz, sıfır belge.

**Bugün:** üç düzlemli bir veri modeli, veritabanı düzeyinde kiracı izolasyonu,
77 uç noktası, 123 test ve 39 senaryo kontrolü, bir arama arayüzü ve bir yönetim
paneli, ~3.600 satır mimari belge, ve 1.000 kütüphaneli bir toplu katalog için
ölçülmüş temeller.

**Asıl fark satır sayısı değil, şu üç şey:**

1. **Sınırlar veritabanında.** Bir kiracı paylaşılan kaydı yazamaz; bu bir kural
   değil, bir grant.
2. **Türetilmiş her şey yeniden üretilebilir.** Arama indeksi atılıp geri
   kurulur ve kontroller ikisinin aynı olduğunu doğrular.
3. **Doğrulanmamış iddia yok.** "Çalışıyor" demek yerine 39 kontrol ve gerçek
   tarayıcı ekran görüntüleri var — ve bu turda bulunan yedi hatanın **hiçbiri**
   testlerle görülmedi.
