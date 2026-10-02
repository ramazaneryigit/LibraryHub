# Gordon'un Yol Haritası — Değerlendirme

**Özet:** İyi iş ✓, ve kod tabanını **doğru okumuş** ✓ — ama bir **özellik**
haritası ✓, bir **risk** haritası değil ✗. Ve bu projenin sıradaki riski eksik
özellik değil ✗, **kanıtlanmamış özellik** ✓.

---

## 1. Doğru olanlar — ve bunlar küçük değil

| Tespit | Neden doğru |
|---|---|
| Plane ayrımı, RLS, provenance, FRBR, worker | **Doğru okunmuş** ✓ — mevcut güçlü yanlar listesi hatasız |
| **"Kurumdan bağımsız vs kuruma özgü" tablosu** | **Belgedeki en iyi şey** ✓ — veri sahipliğini bu netlikte kimse yazmamıştı |
| **"Shared Tenant (Consortium)" seviyesi** | **Yeni bir kavram** ✓ — adı konmamış bir gerçeği adlandırıyor |
| Ödünç modülü tasarımı (patron/loan/reservation ✓) | Sağlam ✓, ve outbox → worker bağlantısı doğru ✓ |
| **Webhook tasarımı** (HMAC ✓, delivery log ✓) | Ders kitabı ✓ |
| RBAC tabloları | Makul ✓ |
| **Üretime hazırlık kontrol listesi** | **Çok değerli** ✓ — yedek **prova edilmiş** ✓, SLA ✓, DR ✓, audit ✓ |
| `analytics.daily_stats` snapshot | Doğru ilke ✓ — *"çalışma zamanı sorgulamıyor"* ✓, türetilmiş ✓ |

**Bunların hepsi alınmalı** ✓.

---

## 2. Yanlış olanlar

### 2.1 OpenSearch — kendi tetikleyicimizle çelişiyor ✗✗

Yol haritası diyor: *"Bugün: Trigram + ILIKE, ölçeksiz."* ✗

**Bu artık doğru değil** ✓. Trigram/ILIKE sorgusu **kaldırıldı** ✓ ve yerine
**türetilmiş indeks** (`search_documents` ✓) geldi ✓. **Ölçüldü: 18–130 ms** ✓.

Ve eşik **belgede yazılı** ✓: `/search` p95 > **500 ms** ✓ (OD7 ✓). Yani
**altı kat uzaktayız** ✓.

**Şimdi OpenSearch eklemek** ✗: bir container daha ✓, bir **ikinci doğruluk
kaynağı riski** ✓, ve **ölçülmüş olmayan** bir sorun için ✓.

**Ama işaret ettiği gerçek boşluk var** ✓: **faseting** ✓. Ve **faseting
OpenSearch gerektirmez** ✓✓ — kendi indeksimiz `GROUP BY` ile yapabilir ✓
(`docs/cekirdek-eksikleri.md` §5 ✓).

**Sonuç: faseting'i al, container'ı bırak** ✓.

### 2.2 Takvim, gerçek engeli beşinci aya koyuyor ✗✗

| Ay | İş |
|---|---|
| 1–2 | Zemin ✅ (bitti) |
| 2–3 | Ödünç |
| 3–4 | OpenSearch |
| 4–5 | Webhook |
| **5–6** | **MARC import/export** |

**Ama import zaten bitti** ✓ (D1–D4 ✓) ve **export, anlaşmanın önkoşulu** ✓.

> **Bir kurumun ilk sorusu: "verimi geri alabilir miyim?"** ✓
> Bu soruya beşinci aya kadar **cevap verilemez** ✗ — ve o zamana kadar
> **hiçbir kütüphane imza atmaz** ✗.

**Bu, haritanın en büyük sıralama hatası** ✓✓ — ve kod tarafında **iş yarım gün** ✓
(yazıcı hazır ✓, uç yok ✗).

### 2.3 `pymarc` — ikinci bir uygulama ✗

Import örneği `pymarc` kullanıyor ✓. Ama **bizde zaten var** ✓: saf ISO 2709
ayrıştırıcı ✓ + eşleme ✓ + **yazıcı** ✓ + yükleme hattı ✓, **50+ testle** ✓.

`pymarc` iyi bir kütüphanedir ✓ — ama eklemek **bir kararın ikinci uygulaması**
olur ✗, ki bu projenin kaçındığı tek şey ✓.

### 2.4 `api/v2` — tüketicisi olmayan sürüm ✗

`prefix="/api/v2"` ✗ — v1'in **henüz tüketicisi yokken** v2 açmak ✓ spekülatif ✓.

### 2.5 AI'nın yeri yanlış ✗

**Doğru olan** ✓: AI önerir ✓, `field_assertions`'a `status='proposed'` yazar ✓,
**insan karar verir** ✓✓ — bu tam bizim provenance modelimiz ✓.

**Yanlış olan** ✗: **başlık tamamlama** düşük değerli bir kullanım ✓. Bir toplu
katalogda AI'nın **yüksek değerli** kullanımı **otorite kontrolüdür** ✓✓ —
*"bu kırk yazımdan hangileri aynı kişi"* ✓ — ki **yol haritası tam da onu
atlıyor** ✗.

Ve **`ollama` container'ı** bir **GPU/RAM taahhüdü** ✓, değeri kanıtlanmamış ✓.

---

## 3. Tamamen eksik olanlar

**En çok burada fark var** ✗:

| Eksik | Neden önemli |
|---|---|
| **Otorite kontrolü bağlama + kuyruk ekranı** | Çekirdek #2 ✓ — 40 yazım 40 kişi olur ✗. Eşleştirme **bitti** ✓, ekran yok ✗ |
| **MARC dışa aktarma ucu** | **Anlaşmanın önkoşulu** ✓ |
| **OAI-PMH** | **Hiç yok** ✓✗ — 1000 kütüphanenin senkron yolu ✓ ve **makalelerin giriş yolu** ✓ |
| **Dublin Core / `oai_dc`** | OAI-PMH'nin **zorunlu** biçimi ✓ |
| **Makale / süreli yayın nitelemesi** | Akademisyen profilinin önkoşulu ✓ |
| **Hak / erişim katmanı** | Kullanıcının kendi gereği: **"sahiplik"** ✓ |
| **Tombstone / silme semantiği** | Hasat edilen tarafta **sessiz tutarsızlık** ✗ |
| **Hız sınırlama** | Kamuya açık katalog **kazınır** ✓ |

### Ve en büyük eksik: **Türkiye bağlamı** ✗✗

Yol haritasında **hiçbiri yok** ✗:

- **DergiPark** ✓ (~2000 açık erişim dergisi ✓, TÜBİTAK ULAKBİM ✓)
- **TO-KAT** ✓ (Türkiye'nin toplu katalogu, Kültür ve Turizm Bakanlığı ✓)
- **ANKOS** ✓ (üniversite kütüphaneleri konsorsiyumu ✓)
- **YÖK Akademik / ORCID** ✓
- **ISBN Ajansı** ✓

**Bu, genel bir bulut ILS planı** ✗ — **bu ülkenin ekosistemi için bir plan
değil** ✗. Ve bu projenin bütün ayırt edici değeri **orada** ✓.

---

## 4. Adlandırmam gereken desen

> **Yol haritası "ne ekleyebiliriz" diye soruyor** ✓.
> **Sormadığı soru: "ne kanıtlanmadı"** ✗.

Projenin gerçek durumu: **yetenekler var, ama gerçek veriyle kanıtlanmadı** ✓
(tek bir gerçek MARC kaydı geçirdim ✓ — 1000 kayıt hâlâ gelmedi ✗).

Ve haritanın cevabı **daha çok yetenek** ✗. Bu, kanıtlanmamış yüzeyi
**büyütür** ✗, küçültmez ✓.

---

## 5. Benim sıralamam — düzeltilmiş

| # | İş | Süre | Neden burada |
|---|---|---|---|
| **1** | **MARC dışa aktarma ucu** | ~yarım gün | Kod hazır ✓, **anlaşmayı bloke ediyor** ✓ |
| **2** | **Otorite kuyruğu ekranı** + gürültü | ~1 gün | Veri gelince kuyruk okunabilmeli |
| **3** | **Makale nitelemesi** (`is_part_of` + cilt/sayı) | ~1 gün | Akademisyen profilinin önkoşulu |
| **4** | **Hak / erişim katmanı** | ~2 gün | "Sahiplik" ✓, sağlayıcı paydaşının önkoşulu |
| **5** | **Ödünç modülü** (patron/loan/reservation ✓) | ~1 hafta | Gordon'un tasarımı **alınır** ✓ |
| **6** | **OAI-PMH hasat edici** → DergiPark | ~3 gün | Makalelerin girişi |
| **7** | **OAI-PMH sunucu + `oai_dc`** | ~2 gün | Hasat edilebilirlik |
| **8** | **Facet + sayfalama** (kendi indeksimizde ✓) | ~1 gün | OpenSearch **değil** ✗ |
| **9** | **Analytics snapshot + dashboard** | ~3 gün | Gordon'un tasarımı **alınır** ✓ |
| **10** | **Webhook** | ~3 gün | Gordon'un tasarımı **alınır** ✓ |
| **11** | **Operasyon**: yedek provası, DR, monitoring, hız sınırı, tombstone | ~1 hafta | **Gerçek yükten önce** ✓ |
| **12** | OpenSearch | — | **Yalnızca p95 > 500 ms olduğunda** ✓ |

**6 ay değil, ~2 ay** ✓ — çünkü **yapılmış olanları takvimden çıkardım** ✓.

---

## 6. Tek cümlelik hüküm

**Gordon'un tasarımları iyi** ✓ — ödünç ✓, webhook ✓, RBAC ✓, analytics ✓,
sahiplik tablosu ✓. **Uygulama sırası ve iki teknik karar yanlış** ✗ (OpenSearch
zamanlaması ✓, `pymarc` ✓), ve **Türkiye ekosistemi tamamen eksik** ✗.

**Alınacaklar:** §1'in tamamı + §5'teki 5, 9, 10 ✓.
**Bırakılacaklar:** OpenSearch (şimdilik ✓), `pymarc` ✗, `api/v2` ✗, ollama ✗.
**Eklenecekler:** §3'ün tamamı ✗ — özellikle **OAI-PMH** ✓ ve **hak katmanı** ✓.
