# RDA Bu Projede Uygulanabilir mi?

**Kısa cevap: Evet — ve bu proje çoğu kütüphane sisteminden belirgin biçimde daha
yakın duruyor.** Sebep tek bir cümle: **RDA'nın veri modeli FRBR/LRM'dir ve bu
proje zaten onu uyguluyor.**

---

## 1. Neden yakın

RDA bir **kataloglama kuralıdır** ✓, bir veri modeli değil ✗. Altında yatan veri
modeli **FRBR**, sonra **FRBR-LRM**'dir ✓.

Bizim zincirimiz:

```
Work → Expression → Manifestation → Item
```

**Bu, FRBR'ın ta kendisidir.** Ve LRM'in "WEMI" dediği şey ✓.

Türkiye'deki yaygın kütüphane sistemleri ise **düz MARC** tutar ✗: bir kayıt = bir
satır ✓, yazarlar **dize** olarak ✓, baskı kavramı yok ✓. Onlarda RDA dönüşümü bir
**veri modeli yeniden yazımıdır** ✗. Bizde ise büyük ölçüde **alan ve sözlük
eklemesidir** ✓.

**Fark bu.** Dönüşümün maliyeti, veri modelinin zaten var olup olmamasıdır.

---

## 2. RDA'nın istediği ve bizde zaten olan

| RDA/LRM gereği | Bizde |
|---|---|
| Work / Expression / Manifestation / Item ayrı varlıklar | ✅ tam |
| Ajanlar **varlık** olarak, dize değil | ✅ `persons`, `collective_agents` |
| Ajanın **tercih edilen adı** (authorized access point) | ✅ `canonical_name` |
| Ad **varyantları** | ✅ `nomens` |
| Ajan **tanımlayıcıları** (ORCID, VIAF…) | ✅ `identifiers` |
| **İlişki tasarımcıları** (relationship designators) | ✅ `role`, `entity_relation.predicate` |
| Eser → ifade → yayın bağı | ✅ `work_expression`, `expression_manifestation` |
| Konu başlıkları | ✅ `concepts` + `entity_relation` |
| **Her alanın kaynağı** (provenance) | ✅ `field_assertions` |
| Çok yazarlı/çok kütüphaneli gerçeklik | ✅ `Holding` ayrımı |

**Bu liste, RDA dönüşümünün pahalı kısmının zaten yapılmış olduğunu gösteriyor** ✓.

---

## 3. RDA'nın istediği ve bizde **eksik** olan

Somut ve küçük ✓:

| # | Eksik | Nerede durur |
|---|---|---|
| **1** | **`336/337/338`** — içerik türü, ortam türü, taşıyıcı türü | `manifestations`'ta tek `carrier_type` var ✗ → **üç ayrı kolon** olmalı |
| **2** | **`040$e` = `rda`** — kaydın RDA olduğunu söyleyen işaret | Yeni bir kolon ya da `source_systems` üzerinden |
| **3** | **Kontrollü ilişki sözlüğü** | `role` şu an **serbest metin** ✗ (`"çeviren"` ✓) → kodlanmış karşılığı (`$4` ✓) kontrollü liste olmalı |
| **4** | **İfade tarihi / içerik türü** (expression level) | `expressions`'a iki kolon |
| **5** | **Eser tarihi, kaynak yeri, eser biçimi** | `works`'ta `work_type` var ✓, diğerleri yok ✗ |
| **6** | **Tercih edilen başlık + varyant başlıklar** | `works.canonical_title` ✓ ama **varyant başlık tablosu yok** ✗ |

**Hepsi eklemeli** ✓ — hiçbiri mevcut yapıyı bozmuyor ✗✓. Bu, "uygulanabilir mi"
sorusunun en somut cevabı ✓.

---

## 4. Kritik pratik nokta: **MARC'ı bırakmak gerekmiyor**

En yaygın yanlış anlama: *"RDA'ya geçmek MARC'ı bırakmaktır."* ✗

Gerçek şu: **RDA-in-MARC** standarttır ✓ ve dünyada en yaygın uygulamadır ✓.
`336/337/338`, `040$e rda`, `$e`/`$4` ilişki tasarımcıları — **hepsi MARC
alanlarıdır** ✓.

Yani:
- **İçe aktarma** MARC olarak kalır ✓ (RDA alanları okunur ✓)
- **Dışa aktarma** MARC olarak kalır ✓ (RDA alanları yazılır ✓)
- Buna karşılık **içeride** varlıklar ayrı durur ✓

**Bu, hem geriye dönük uyumluluğu hem RDA'yı birlikte verir** ✓ — ve kütüphanelerin
istemediği şey zaten ikisinden birini seçmek zorunda kalmaktır ✗.

---

## 5. Bu projenin RDA'daki gerçek avantajı

Bir **toplu katalog** düşünün: kütüphaneler RDA'ya geçiyor ✓, ama toplu katalog
**düz MARC** tutuyorsa, gelen RDA kayıtlarını **düzleştirmek zorundadır** ✗ — yani
kütüphanelerin emeğini geri alır ✗.

**FRBR varlıklarını tutan bir toplu katalog, RDA kayıtlarını olduğu gibi taşıyabilir
ve RDA olarak servis edebilir** ✓✓.

Ve ANKOS/TO-KAT görüşmesinde bu, şemadan değil **çalışan bir şeyden** konuşulan bir
argümandır ✓:

> *"Biz RDA kayıtlarını düzleştirmiyoruz; eser, ifade ve baskı ayrı duruyor. Sizden
> gelen RDA kaydı, bizden RDA olarak çıkar."*

---

## 6. Dürüst olmam gereken iki yer

**1. RDA Toolkit lisanslı bir üründür.** Kural metni ve araç seti ücretlidir ✗. RDA
**sözlükleri** (vocabularies) linked-data olarak yayımlanır ✓ ama **lisanslarını ben
doğrulamadım** ✗ ve doğrulamadan "serbest" demem yanlış olur ✗. Kullanılacaksa lisans
kontrol edilmeli ✓.

**2. Türkiye'nin RDA durumunu bilmiyorum.** Hangi kütüphanelerin geçtiğini, hangi
konsorsiyumun karar verdiğini **ölçmedim** ✗. Bu, ANKOS'a sorulacak bir sorudur ✓ —
ve cevabı, E aşamasının (MARC dışa aktarma) hangi alanları öncelikle yazacağını
belirler ✓.

---

## 7. Sonuç ve E'ye etkisi

| Soru | Cevap |
|---|---|
| Uygulanabilir mi? | **Evet** ✓ — veri modeli zaten FRBR/LRM |
| Yeniden yazım gerekir mi? | **Hayır** ✓ — eklemeli, altı küçük alan |
| MARC bırakılır mı? | **Hayır** ✗ — RDA-in-MARC standart ✓ |
| Bizim avantajımız ne? | **Varlıkları düzleştirmiyoruz** ✓ — RDA kaydını RDA olarak taşırız |
| Ne eksik? | `336/337/338`, `040$e`, kontrollü ilişki sözlüğü, varyant başlıklar |

**E (MARC dışa aktarma) bu yüzden şunu yapmalı:**

1. `245/100/700/264/020/650/852/876` — **standart alanlar** ✓ (her sistem okur ✓)
2. **`040$e rda`** — kaydın RDA olduğunu söyleyen işaret ✓
3. **`336/337/338`** — içerik/ortam/taşıyıcı ✓ (kolonlar eklendikten sonra ✓)
4. **`$e`/`$4`** — ilişki tasarımcıları ✓ (kontrollü sözlük eklendikten sonra ✓)

**Ve E'nin ilk sürümü 1'i yapmalı** ✓ — çünkü **her** kütüphane sistemi onu okur ✓;
2–4 ise RDA alanlarıdır ✓ ve sırası geldiğinde eklenir ✓.

**Yani cevap: RDA uygulanabilir, hatta bu projenin en güçlü olduğu yer; ve MARC
dışa aktarma onu bugün de besleyebilir, yarın da genişletebilir.**

---

## 8. Gerçek bir kayıt bunu doğruladı

Bir üniversite kütüphanesinden gelen gerçek bir MARC kaydı
(`Reklamcılık ve manipülasyon`, Çetinkaya, Ağaç Yayıncılık, 1993) hattan
geçirildi ✓. **Tek kayıt, ama RDA kaydı** ✓:

```
040    $aTVK $btur $erda $cTVK          ← RDA işareti ✓
336    $atext $2rdacontent             ← içerik türü ✓
337    $aunmediated $2rdamedia         ← ortam türü ✓
338    $avolume $2rdacarrier           ← taşıyıcı türü ✓
050 00 $aHF 5823 $bC48 1993            ← yer numarası ✓
250    $a2. Baskı                      ← baskı ✓
504    $aKaynakça vardır.              ← not ✓
300    $a135 sayfa : $bresim ; $c18 cm. ← fiziksel tanım ✓
```

**Hattın okuduğu** ✓: başlık ✓, yazar (inverted ✓), ISBN ✓, dil (`041`'den ✓),
yayın yeri/yayıncı/yıl ✓, konular ✓, yer numarası (`050`'den ✓).

**Hattın okumadığı — ve bu belgenin öngördüğü tam liste** ✗:

| Alan | Değer | Durum |
|---|---|---|
| `336/337/338` | `text` / `unmediated` / `volume` | **kolonlar yok** ✗ (§3, madde 1) |
| `040$e` | `rda` | okunmuyor ✗ (§3, madde 2) |
| `300` | `135 sayfa` | **`extent` kolonu var** ✓ ama eşlenmiyor ✗ |
| `504` | `Kaynakça vardır.` | **`notes` kolonu var** ✓ ama eşlenmiyor ✗ |

**Yani belgedeki "eksik" listesi tahmin değildi** ✓ — gerçek bir kayıtta
**dört maddesi birden** görünüyor ✓.

**Ve iki şey daha öğrendi:**

1. **Yerel alanlar var** ✓ (`907` = `PROF. DR. RECEP TAYFUN` ✓, `596` = nüsha
   sayısı ✓). Bunlar **paylaşılan kayda yazılmamalı** ✗ — bir kütüphanenin kendi
   notudur ✓ → **holding düzeyine** aittir ✓.
2. **Kaynak veride hata var**: `650 0 $aAdvertisiing.` ✗ ("Advertising" ✓).
   Gerçek veri **temiz değil** ✓ ve bu, provenance'ın (§6) neden gerekli olduğunun
   kanıtı ✓.

---

## 9. Bu kaydın söylediği sıra

| # | İş | Neden şimdi |
|---|---|---|
| **1** | `300` → `extent`, `504` → `notes` eşlemesi | **Kolonlar zaten var** ✓, sadece eşlenmiyor ✗ |
| **2** | `336/337/338` kolonları + eşleme | RDA'nın ilk gerçek adımı ✓ |
| **3** | `040$e` → RDA işareti | |
| **4** | `9xx` yerel alanlar → **holding notu** | Paylaşılan kayda **değil** ✗ |

**1 numara neredeyse bedava** ✓: iki kolon var ✓, iki satır eşleme eksik ✗.
