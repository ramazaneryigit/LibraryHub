# Makale ↔ Akademisyen — İhtiyacın Gerçek Boyutu

**Söylenen:** dergi **yönetimi** değil, dergi **bilgisi** ✓ — ve sebebi
**akademisyen ↔ makale ilişkisi** ✓.

**Sonuç:** ihtiyaç beklediğimden **belirgin biçimde küçük** ✓. Süreli yayın
"deseni" (dergi → sayı → makale zinciri ✓) gerekmiyor ✗ — çünkü o, **yayın
sürecini** modellemektir ✓, **yayın bilgisini** değil ✗.

---

## 1. Zaten var olan yarı

| Gereken | Bugün |
|---|---|
| **Akademisyen ↔ makale** bağı | ✅ **`work_agent_relation`** — `role='author'` ✓ |
| Makale = bir **eser** | ✅ `works` + `work_type` ✓ |
| Dergi = bir **eser** | ✅ `works` + `work_type` ✓ |
| Eser ↔ eser bağı | ✅ **`entity_relation`** (`subject, predicate, object`) ✓ |
| Atıf | ✅ aynı tablo, `predicate='cites'` ✓ |
| Künye alanları (başlık, yıl, dil ✓) | ✅ |

**Yani "akademisyen hangi makaleyi yazdı" sorusu, bugünkü modelle
cevaplanabilir** ✓ — tek eksik, **makalelerin var olmaması** ✗.

---

## 2. Eksik olan tek şey: **makale hangi sayıda çıktı**

Bir akademisyenin yayın listesi şöyle görünür ✓:

```
Kaya, B. (2024). "Veri Madenciliğinde Yeni Yaklaşımlar".
  Bilgi Dünyası, Cilt 25, Sayı 3, s. 412-431.
```

Burada **iki ayrı bilgi** var ✓:

| Bilgi | Nerede durur |
|---|---|
| **Hangi dergide** | `entity_relation` → `is_part_of` ✓ (tablo var ✓) |
| **Hangi cilt/sayı/sayfa/yıl** | ❌ **numaralandırma verisi** — yeri yok ✗ |

**Numaralandırma bir *varlık* değil, bir *nitelemedir*** ✓ — `Cilt 25, Sayı 3`
bağımsız bir şey değil ✗, **ilişkinin özelliğidir** ✓.

---

## 3. Bu yüzden gereken, üç tablo değil — **bir tablo ve iki değer**

| # | İş | Boyut |
|---|---|---|
| **1** | `entity_relation` için `is_part_of` yüklemi | **değer** ✓ — şema değişmez ✗ |
| **2** | `work_type` için `article`, `serial` değerleri | **değer** ✓ |
| **3** | İlişki nitelemesi: cilt, sayı, sayfa, yıl | **küçük bir tablo** ✓ ya da `entity_relation`'a dört kolon |

**Üçüncüsü tek gerçek ekleme** ✓ ve o da **ilişkiye aittir** ✓, ayrı bir varlığa
değil ✗.

**Karşılaştırma:** dergi **yönetimi** modeli (dergi → cilt → sayı → makale ✓ +
hakemlik ✓ + akış ✓) **onlarca tablo** olurdu ✗. İhtiyaç, onun **onda biri** ✓.

---

## 4. Ve akademisyen profili için gereken bu kadar

```
Akademisyen (person)
   │  work_agent_relation  ✓ VAR
   ▼
Makale (work_type='article')
   │  entity_relation 'is_part_of'  +  cilt/sayı/sayfa  ← EKSİK
   ▼
Dergi (work_type='serial')
```

**Profilin göstereceği şey budur** ✓ — ve ANKOS'a, ORCID'e, YÖK'e karşı
savunulacak liste de budur ✓ (`docs/rda-uygulanabilirligi.md` ✓).

**Ve DergiPark entegrasyonu bunu besler** ✓: OAI-PMH künyesi, makale + dergi +
cilt/sayı bilgisini **zaten taşır** ✓ — yani hasat edilen veri, bu üç parçayı
doldurur ✓.

---

## 5. Dürüst not

**Tam makale modellemesi (cilt/sayı varlık olarak ✓) ertelenebilir** ✓ — çünkü
ihtiyaç **bibliyografik** ✓, **idari** değil ✗. Bir gün dergi bazlı raporlama
gerekirse (bir derginin tüm sayıları ✓), o zaman sayı **varlık** olur ✓; bugün
**niteleme** olması yeter ✓.

**Ve bu, "değer genişlemesi + küçük bir katman" demek** ✓ — "yeni desen" değil ✗.
Yani sıralamadaki 1 numara, **beklediğimden küçük** ✓.
