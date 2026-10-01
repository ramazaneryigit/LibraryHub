# Dublin Core Bu Yapıya Nasıl Entegre Edilir

**Kısa cevap:** **Model olarak asla** ✗ — **dışa aktarma biçimi olarak zorunlu** ✓.

Ve bu bir çelişki değil ✗: Dublin Core (DC) bir **veri modeli değil**, bir
**çapraz haritalama hedefidir** ✓. Tasarlanış amacı **ortak payda** olmaktır ✓,
zenginlik değil ✗.

---

## 1. Neden **içeride** DC olamaz

DC on beş **istemli olarak düz** öğedir ✓. Bu düzlük onu görünür kılar,
kullanışlı kılar — ve **bu projenin cevapladığı her soruyu öldürür** ✗:

| Bu projenin sorusu | DC'de karşılığı |
|---|---|
| "Bu eserin **2020 baskısı** kimde?" | ❌ `dc:date` bir **dizedir**; baskı kavramı yok ✗ |
| "Hangi **kütüphanede**?" | ❌ Holding kavramı yok ✗ |
| "Şu an **rafta mı**?" | ❌ Nüsha kavramı yok ✗ |
| "**Ayşe** yazınca **Ayşe**'yi bulur mu?" | ⚠️ `dc:creator` serbest metindir ✗ |
| "Bu alanı **kim** değiştirdi?" | ❌ Provenance yok ✗ |
| "Eser → ifade → baskı" zinciri | ❌ `dc:relation` bunu taşıyamaz ✗ |

**DC kayıptır** ✗ ve **kayıplı olduğu bilerek tasarlanmıştır** ✓ — on beş öğe
FRBR'ı ifade edemez ✓.

**Somut sonuç:** DC'yi içeride model yapmak, **altı aşamada kurduğumuz
Manifestation/Holding/Item ayrımını geri almaktır** ✗ — ve o ayrım bu ürünün
kendisidir ✓.

---

## 2. Neden **dışarıda** zorunlu

### 2.1 OAI-PMH, `oai_dc`'yi **şart koşar**

OAI-PMH'nin **zorunlu** üst veri biçimi `oai_dc`'dir ✓. Başka biçimler
(`marcxml`, `mods` ✓) **isteğe bağlıdır** ✓, ama `oai_dc` olmadan **uyumlu
sayılmazsınız** ✗.

Ve çekirdek eksikleri listemde **4. madde** şuydu ✓:

> *Kendi OAI-PMH ucumuzu yayınlamak — 1000 kütüphane verisini elle dosya yükleyerek
> güncellemez. Hasat edilebilir olmak entegrasyonun tek ölçeklenebilir yoludur ✓.*

**Yani `oai_dc` üretmek, o maddenin önkoşuludur** ✓✓. İsteğe bağlı değil ✓.

### 2.2 DC, kütüphane olmayan sistemlerin gördüğü dildir

MARC'ı **kütüphaneler** okur ✓. DC'yi **herkes** okur ✓:
- Kurumsal arşivler (DSpace, EPrints ✓)
- Açık erişim platformları (OpenAIRE ✓)
- Kültürel miras agregatörleri (Europeana ✓)
- Ulusal tez/yayın sistemleri

**Bir üniversitenin kurumsal arşivi bizden hasat edebilmeli** ✓ — ve o hasat
`oai_dc` ile olur ✓.

---

## 3. Nasıl entegre edilir — ve neden sorun olmaz

**Çünkü DC de türetilmiş bir görünümdür** ✓ — tıpkı arama indeksi ✓ ve
`holdings_compat` ✓ gibi.

```
        KANONİK KAYIT (FRBR/LRM, provenance'lı)
                      │
        ┌─────────────┼─────────────┬──────────────┐
        ▼             ▼             ▼              ▼
   MARC21/.mrc    MARCXML       oai_dc        arama indeksi
   (kütüphaneler) (kütüphaneler) (herkes)      (kendi aramamız)
```

**Hiçbiri kaynak değildir** ✓ — hepsi kanonik kayıttan **yeniden üretilebilir** ✓.
DC'yi eklemek, mevcut hiçbir şeyi değiştirmez ✗✓; **bir görünüm daha** ekler ✓.

**Sorun olmamasının sebebi tam olarak bu** ✓: kayıplı bir biçim, kayıplı olduğu
sürece zararsızdır ✓. Tehlikeli olan, kayıplı biçimi **saklamak** olurdu ✗.

---

## 4. Eşleme — FRBR'dan DC'ye

| DC öğesi | Bizden |
|---|---|
| `dc:title` | `works.canonical_title` |
| `dc:creator` | ana yazar (`100`) |
| `dc:contributor` | diğer yazarlar (`700`) |
| `dc:publisher` | yayıncı ajanı |
| `dc:date` | `manifestations.publication_date` |
| `dc:language` | `expressions.language` |
| `dc:identifier` | ISBN / ISSN / URI |
| `dc:subject` | `concepts` |
| `dc:type` | `works.work_type` |
| `dc:format` | `manifestations.carrier_type` |
| `dc:description` | eser/ifade açıklaması |
| `dc:source` | kütüphane + holding |
| `dc:relation` | eser → ifade → baskı bağlantıları |
| `dc:rights` | `source_systems.license` |
| `dc:coverage` | yer + tarih |

**Bir dikkat:** `oai_dc` **niteliksiz** on beş öğedir ✓. **Nitelikli DC** (DCMI
Terms, şema ve sözlüklerle ✓) daha zengindir ✓ ama OAI-PMH'nin `oai_dc`'si onu
kabul etmez ✗. Yani iki şey ayrıdır ✓:
- **`oai_dc`** → OAI-PMH için, on beş öğe ✓
- **Nitelikli DC / JSON-LD** → kendi API'miz için, daha zengin ✓

---

## 5. Uyarılar — dürüst olmam gereken yerler

**1. DC'den geri dönüş yok.** Bir DC kaydı **RDA kaydına çevrilemez** ✗ — bilgi
orada değil ✓. Yani DC **yalnızca çıkış** olmalı ✓. İçe alınacaksa **düşük
sadakatli** kabul edilmeli ✓ ve kanonik kaydı **ezmemeli** ✗.

**2. `dc:creator` bir dizedir.** Ondan otorite kaydı üretmek, "Dostoyevski" ile
"Достоевский"i iki kişi yapar ✗ — otorite kontrolü eksikliğinin (çekirdek
eksikleri #2 ✓) DC tarafında **daha da görünür** hâli ✓.

**3. DC zenginliği ölçmez, erişilebilirliği ölçer.** "DC veriyoruz" demek "iyi
veri veriyoruz" demek değildir ✗ — **en düşük ortak paydayı** veriyoruz demektir ✓.

**4. `oai_dc`'nin tarih biçimi kısıtlıdır.** `dc:date` için önerilen biçim
`YYYY-MM-DD` ✓; bizim `publication_date` **serbest metindir** ✓ (`"2026"`,
`"2026-03"`, `"3. baskı"` değil ama `"2026."` ✓). **Dönüştürücü** bunu normalize
etmeli ✓ ve edemiyorsa **olduğu gibi bırakmalı** ✓, uydurmamalı ✗.

---

## 6. Sonuç

| Soru | Cevap |
|---|---|
| İçeride model olarak? | **Hayır** ✗ — FRBR'ı öldürür |
| Dışarıda biçim olarak? | **Evet, hem de zorunlu** ✓ — `oai_dc` OAI-PMH'nin şartı |
| Sorun olur mu? | **Olmaz** ✓ — türetilmiş görünüm, kanonik kaydı etkilemez |
| Ne zaman? | OAI-PMH sunucusuyla **aynı işte** ✓ (çekirdek eksikleri #4) |
| Risk ne? | DC'yi **içe** almaya kalkmak ✗ — orada kayıp geri dönüşsüzdür |

**Tek cümle:** DC, katalogumuzun **dili değil**, dışarıya konuştuğumuz **ortak
dildir** ✓ — ve kayıplı olduğunu bilerek, yalnızca dışarı konuşmak için
kullanılmalıdır ✓.
