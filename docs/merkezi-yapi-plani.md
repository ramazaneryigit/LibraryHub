# LibraryHub — Merkezî Yapı Planı

**Amaç.** Platform, bibliyografik kaydın **merkezî alanı** olur: her katılımcı
yalnızca **kendi otorite olduğu şeyi** beyan eder ve **kendisini ilgilendireni**
okur. Kütüphaneler, akademisyenler, yayınevleri, ISBN ajansı ve veritabanı
şirketleri aynı kayda farklı yerlerden katkı verir.

Bu belge bir **plandır**, uygulama kaydı değil. Bugüne kadar yapılanlar
`architecture-v2.md` §0.x'te; burası sıradaki beş paydaşın nasıl ekleneceğini ve
hangi kararların sizin onayınızı beklediğini anlatır.

---

## 1. Ölçülen başlangıç — model ne kadarını zaten taşıyor

Ölçüm `f3b8d1e64c72` head'inde alındı.

| İhtiyaç | Bugünkü durum | Sonuç |
|---|---|---|
| Yayınevi kimliği | `collective_agents.agent_type` içinde **`publisher`** var | ✅ hazır |
| Kurumsal hesap | `control.users.account_kind` = `institutional, corporate` | ✅ hazır |
| Elektronik yayın | `holdings.holding_type='electronic'` + `access_url` + `license_note` | ✅ hazır, **kullanılmıyor** |
| Akademisyen verisi | `persons` (ad, soyad, biyografi) + `identifiers` (ORCID) + `work_agent_relation` | ✅ hazır |
| ISBN | `identifiers.scheme` serbest metin | ✅ hazır |
| Toplu veri alımı | `source_systems`, `source_records`, `ingestion_batches` | ✅ hazır |
| **Provenance / beyan** | — | ❌ **tablo yok** |
| **Yayın yaşam döngüsü** | `manifestations`'ta durum kolonu yok | ❌ eksik |
| **Kişiye bağlı hesap** | hesaplar kiracıya bağlı ya da kiracısız platform yöneticisi | ❌ eksik |
| **Kapsamlı yazma hakkı** | her yazma `admin` gerektiriyor | ❌ eksik |

**Yorum:** veri modeli bu genişlemeyi **önceden düşünmüş**. Eksik olan model
değil, **kimin neyi beyan edebileceği** — yani provenance ve kapsam.

---

## 2. Omurga — Aşama E: Provenance ve beyan

Her paydaşın ortak ihtiyacı aynı: **"bunu ben söylüyorum."** Bu yüzden dört
çalışma alanından önce tek bir altyapı gelir.

### E.1 `public.field_assertions`

```sql
create table public.field_assertions (
    id               uuid primary key,
    entity_id        uuid not null,          -- hangi kayıt
    field            text not null,          -- hangi alan
    value            jsonb,                  -- iddia edilen değer
    source_system_id uuid not null,          -- kim söylüyor
    asserted_at      timestamptz not null default now(),
    status           text not null default 'proposed',
                     -- proposed | accepted | rejected | superseded
    confidence       real,
    reviewed_by      uuid,
    reviewed_at      timestamptz
);
```

`source_systems` **zaten var** (§6.2, Aşama 1'de boş tablo olarak eklendi) ve
`source_records` onu kullanıyor. Bu tablo onu **alan düzeyine** indirir.

### E.2 Neden bu, ve neden şimdi

Bugün bir öneri `tenant.change_proposals` içinde yaşıyor ve **yalnızca kiracılar**
öneri açabiliyor. Yayınevi, ajans, sağlayıcı ve akademisyen kiracı değil; her biri
için ayrı bir öneri tablosu açmak, aynı işi dört kez yazmak olurdu.

`field_assertions` bunu tek yerde toplar ve **§6'nın provenance kararını**
(her alanın kaynağı bilinir) uygular. Mevcut `change_proposals` **kaldırılmaz**;
kiracı önerisi bir **iş akışıdır** (gerekçe, kanıt, geri çekme), assertion ise
**veri**. Öneri kabul edildiğinde bir assertion doğar.

### E.3 Karar gerekiyor

> **Platform otorite mi, beyan merkezi mi?**
>
> **Önerim: beyan merkezi, küratörlü.** Hiçbir kaynak tek başına doğru değildir;
> ISBN ajansı ISBN'yi, yayınevi kendi künyesini, kütüphane elindekini bilir. Alan
> düzeyinde çakışma normaldir ve **çözülmesi gerekir** — bugünkü öneri akışının
> yaptığı tam olarak bu.

---

## 3. Omurga — Aşama F: Paydaş tipleri ve kapsamlı yetki

### F.1 Bugünkü hâl

`control.users` bir kiracıya bağlıdır (`tenant_id`) ya da kiracısızdır ve o zaman
`role='admin'` olmak zorundadır (`ck_users_tenant_required`). Rol üç değerli:
`admin | librarian | viewer`.

Bu, **beş** paydaş tipini ifade edemez.

### F.2 Öneri

`control.users` üzerine bir **asıl (principal) tipi**:

| `principal_kind` | Kim | Ne yapabilir |
|---|---|---|
| `platform` | platform yöneticisi | her şey (bugünkü `admin`) |
| `tenant_staff` | kütüphane personeli | kendi kiracı düzlemi + öneri |
| `academician` | akademisyen | **kendi** eserlerini sahiplenme ve tamamlama |
| `publisher` | yayınevi | **kendi yayınladığı** kayıtları açma ve güncelleme |
| `isbn_agency` | ISBN ajansı | **basılmamış** yayın kaydı açma |
| `vendor` | veritabanı şirketi | elektronik üst veri + erişim linki |

### F.3 Kapsam veritabanında olmalı

Bu projenin kuralı: **sınır grant ve politikadır, uygulama `if`'i değil.** Yani
"yayınevi yalnızca kendi kitabını düzenler" bir kontrol değil bir **kapsam**
olmalı. İki katman:

1. **Satır düzeyi**: `field_assertions`'a `source_system_id` ile yazılır; bir
   yayınevinin oturumu yalnızca kendi `source_system_id`'siyle yazabilir (RLS).
2. **Kabul düzeyi**: bir assertion'ın kanonik alana **dönüşmesi** yalnızca
   küratörden (platform yöneticisi) geçer. Yani bir yayınevi kendi künyesini
   beyan eder; kaydı **tek başına değiştiremez**.

### F.4 Karar gerekiyor

> **Bir yayınevi kendi kitabının künyesini doğrudan yazabilmeli mi, yoksa
> küratörden mi geçmeli?**
>
> **Önerim: küratörden geçsin.** Sebep, mimarinin baştan beri söylediği şey:
> paylaşılan kayıt **tek ve ortaktır**; onu değiştiren yol denetlenebilir olmalı.
> Aksi hâlde 1000 kütüphaneli bir katalogda her yayınevi kendi künyesini yazar ve
> katalog ticari broşüre döner.

---

## 4. Aşama G — Yayın yaşam döngüsü

ISBN ajansının işi **basılmamış** yayını platforma sokmak. Bunun için kaydın bir
**durumu** olmalı:

```sql
alter table public.manifestations
  add column publication_status text not null default 'published';
  -- announced | in_press | published | out_of_print | cancelled
```

**Neden değerli:** kütüphane, daha basılmadan bir eseri **görür** ve sipariş
planına alır. Bir toplu katalog için bu, ISBN ajansı işbirliğinin bütün sebebi.

**Karar gerekiyor:**
> Basılmamış (`announced`) kayıtlar kamuya açık aramada görünsün mü?
>
> **Önerim: görünsün, ama işaretli.** "Henüz basılmadı" etiketiyle görünmesi bir
> kütüphanenin işine yarar; gizlenmesi işbirliğini anlamsız kılar.

---

## 5. Dört çalışma alanı

Dördü de **E ve F'ye bağlı**. Sıra, toplu katalog hedefine katkıya göre.

### 5.1 Aşama H — ISBN ajansı (`/isbn`) — **önerilen ilk**

| | |
|---|---|
| **Ne** | Basılmamış yayın kayıtlarını toplu yükler; ISBN atama kayıtlarını tutar |
| **Var** | `identifiers` (ISBN) ✓, `source_records` toplu alım ✓, outbox ✓, arama indeksi ✓ |
| **Yok** | yayın durumu (G), kapsamlı yazma (F) |
| **Değer** | Katalogda **henüz basılmamış** eserler görünür — toplu katalog için en yüksek katkı |

### 5.2 Aşama I — Yayınevi (`/yayinevi`)

| | |
|---|---|
| **Ne** | Kendi kitaplarının **hangi kütüphanede** olduğunu görür, yeni yayın ekler, istatistik alır |
| **Var** | `agent_type='publisher'` ✓, holding zinciri tam ✓ (**rapor tamamen hazır**) |
| **Yok** | kapsamlı yazma (F), çalışma alanı |
| **Değer** | Ticari olarak en görünür paydaş; "kitabım 40 kütüphanede" bilgisi |
| **Not** | Rapor için **tek satır yeni veri gerekmiyor** — zincir zaten kurulu |

### 5.3 Aşama J — Akademisyen profili (`/akademisyen`)

| | |
|---|---|
| **Ne** | Kendi çalışmalarını görür; katalogdan gelenler + kendi ekledikleri |
| **Var** | `persons`, `identifiers` (ORCID), `work_agent_relation` ✓ |
| **Yok** | kişiye bağlı hesap (F), profil görünümü, sahiplenme akışı |
| **Yön** | **İki yönlü ve birbirini besler:** profil katalogdan oluşur, akademisyen eksikleri tamamlar, tamamladıkları kataloğa döner |

**Karar gerekiyor — ve burada dürüst olmam gerekiyor:**

> **YÖK Akademik'in genel bir API'si yok.** Ekran kazımak (scraping) hem kırılgan
> hem hukuken tartışmalı. **Önerim: ORCID.** Açık API'si var, akademisyen kendi
> kaydını kendisi güncel tutar, ve uluslararası standart. YÖK ile ilişki
> kurulacaksa bu bir **protokol** işidir, tersine mühendislik değil.

### 5.4 Aşama K — Veritabanı şirketleri (`/saglayici`)

| | |
|---|---|
| **Ne** | Elektronik yayınların üst verisini toplu yükler; abonelik/satın alma erişim linklerini paylaşır |
| **Var** | `holding_type='electronic'` ✓, `holdings.access_url` ✓, `license_note` ✓, `source_records` ✓ |
| **Yok** | kapsamlı yazma (F), çalışma alanı |
| **Karar** | Platform erişimi **aracılık etmez**, yalnızca **linkler**. Satın alma platformun işi değil; üst veri ve keşfedilebilirlik onun işi |

---

## 6. Amaç: merkezî yapı — ve bunun mimari karşılığı

İstenen şey "merkezî bir yapı". Bunun teknik karşılığı şudur ve bugüne kadar
kurulanların tam üstüne oturur:

```
        ISBN ajansı ──┐
         yayınevi  ───┤
     akademisyen  ────┼──►  BEYAN (field_assertions)  ──►  KÜRATÖR  ──►  KANONİK KAYIT
    veritabanı ş. ────┤                                          │
      kütüphaneler ───┘                                          ▼
                                                       ARAMA İNDEKSİ (türetilmiş)
                                                                 │
                                                                 ▼
                                            kamuya açık arama · /kutuphane · raporlar
```

**Merkezî olan, herkesin kendi verisini yazması değil; herkesin katkısının tek bir
kanonik kayda yakınsamasıdır.** Bu yüzden provenance omurgadır, ilk iştir.

---

## 7. Sıra ve bağımlılıklar

| Aşama | Ne | Bağlı olduğu | Durum |
|---|---|---|---|
| **A** | Kiracı çalışma alanı (`/kutuphane`) | — | ✅ **bitti** |
| **B** | Kendi kendine katılım | — | sırada |
| **E** | **Provenance / beyan** | — | **omurga** |
| **F** | **Paydaş tipleri + kapsamlı yetki** | E | **omurga** |
| **G** | Yayın yaşam döngüsü | — | küçük, bağımsız |
| **C** | Okuyucular + dolaşım | — | ayrı hat |
| **H** | ISBN ajansı | E, F, G | |
| **I** | Yayınevi | E, F | |
| **J** | Akademisyen | E, F | |
| **K** | Veritabanı şirketi | E, F | |
| **D** | Raporlama | C, I | |

**Kritik yol:** **E ve F.** Dört çalışma alanının hiçbiri bunlar olmadan
yazılamaz — yazılırsa dört ayrı yetki modeli doğar ve proje tam da kaçındığı şeye
döner: aynı kararın birden çok uygulaması.

---

## 8. Kararlar — onayınızı bekleyen

| # | Soru | Önerim | Neden önemli |
|---|---|---|---|
| **P1** | Platform otorite mi, beyan merkezi mi? | **Beyan merkezi, küratörlü** | Bütün plan bunun üstüne kurulu |
| **P2** | Yayınevi kendi künyesini doğrudan yazabilir mi? | **Hayır, küratörden geçsin** | Aksi hâlde katalog ticari broşüre döner |
| **P3** | Basılmamış kayıtlar kamuya açık mı? | **Evet, işaretli** | ISBN işbirliğinin bütün değeri burada |
| **P4** | Akademisyen verisi nereden? | **ORCID** (YÖK'ün API'si yok) | Ekran kazımak kırılgan ve tartışmalı |
| **P5** | Platform elektronik erişime aracılık eder mi? | **Hayır, yalnızca link** | Satın alma platformun işi değil |
| **P6** | Kapsam nerede uygulanır? | **Veritabanında (RLS + küratör)** | Projenin baştan beri kuralı |

---

## 9. Bu planın yapmadıkları

- **Koha ile entegrasyon yok.** Kurumun kendi otomasyonu platformun içinde
  büyüyor (`/kutuphane`); dış bir ILS ile senkronizasyon ayrı bir karar ve şu an
  gündemde değil.
- **Satın alma / abonelik yönetimi yok.** Sağlayıcı link paylaşır, platform
  keşfettirir.
- **Ödeme, faturalama, kimlik doğrulama federasyonu yok.**
- **YÖK Akademik kazıma yok** (P4).
- **AI** — §10 hâlâ ertelenmiş durumda; bu plan onu öne almıyor.
