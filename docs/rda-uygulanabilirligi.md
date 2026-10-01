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
