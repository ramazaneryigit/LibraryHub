# OJS / DergiPark ve Bu Platform — İki Farklı İş

**Kısa cevap:** **OJS'e girmiyoruz** ✗ — ve **dergi yönetimini dahil etmek yanlış
olur** ✗. Doğru cevap **entegrasyon** ✓, ve DergiPark bunu **zaten mümkün kılıyor** ✓.

---

## 1. İki sistem iki farklı iş yapar

| | OJS / DergiPark | Bu platform |
|---|---|---|
| **Ne yapar** | **Üretim**: gönderim, hakemlik, editoryal akış, dizgi, yayın | **Keşif**: kimde var, hangi baskı, hangi kütüphane |
| **Kime hizmet eder** | Editör, hakem, yazar | Okuyucu, kütüphane, araştırmacı |
| **Birincil veri** | Makale **tam metni** + yayın süreci | **Künye** + holding + nüsha |
| **OAI-PMH** | **Yayınlar** ✓ | **Hasat eder** ✓ |
| **Sahibi** | Derginin editör kurulu | Kütüphaneler |

**Kesişim noktası künyedir** ✓ — ve **sadece** künyedir ✓. Geri kalan her şey
ayrıdır ✓.

---

## 2. Dergi yönetimini dahil etmek neden yanlış olur

**Dört sebep, ve dördü de bağımsız olarak yeterli:**

**1. Farklı bir iş.** Hakem atamak, yayın kararı vermek, dizgi takip etmek ✓ —
bunlar bir **kütüphane kataloğunun işi değil** ✗. Bir kütüphaneci hakem atamaz ✗.

**2. Farklı bir sahip.** Dergi yönetimi **derginin** işidir ✓, platformun değil ✗.
Editör kurulu kendi dergisinin kararını verir ✓; platform o kararın **sahibi
olamaz** ✗.

**3. Zaten çözülmüş.** **DergiPark** Türkiye'de ~2000 akademik dergiyi barındırıyor
✓ ve TÜBİTAK ULAKBİM tarafından işletiliyor ✓. Onu yeniden yapmak **var olanı
kopyalamaktır** ✗ — TO-KAT için verilen cevabın aynısı ✓.

**4. Ölçek ve sorumluluk.** 2000 derginin hakemlik akışını taşımak, bambaşka bir
ürün olurdu ✗ — ve o ürünün **muhatabı kütüphaneler değil** ✗.

---

## 3. Doğru yapı: hasat et, üretme

```
   DergiPark / OJS              bu platform
   ───────────────              ───────────
   gönderi, hakemlik            OAI-PMH HASAT EDİCİ
   editoryal karar       ──►         │
   dizgi, yayın                      ▼
   OAI-PMH YAYINLAR ✓          public: Work → Expression →
   DOI kaydı                     Manifestation (makale, sayı)
                                     │
                                     ▼
                            + süreli yayın deseni
                            + kütüphane holding'leri
                            + kitap ↔ makale bağı
```

**Biz künyeyi alırız** ✓; **onlar süreci yürütür** ✓. İki sistem **aynı kaydı iki kez
yazmaz** ✗ — biri üretir ✓, diğeri keşfettirir ✓.

---

## 4. Ve bizim eklediğimiz şey, onların yapamadığı şey

DergiPark açık erişim makaleyi **verir** ✓. Veremediği üç şey var ✓ — ve üçü de bu
platformun varlık sebebi ✓:

| DergiPark verir | Bu platform ekler |
|---|---|
| Makale künyesi ✓ | **Hangi kütüphanede basılı nüshası var** ✓ |
| Tam metin ✓ | **Kitap ↔ makale bağı** ✓ (atıf grafiği) |
| — | **Tek aramada basılı + elektronik** ✓✓ |

**Üçüncüsü asıl değerdir** ✓: bir okuyucu, aynı aramada **kütüphanesindeki basılı
kitabı** ✓ ve **açık erişim makaleyi** ✓ birlikte bulur ✓. Bugün bunu yapan bir
sistem yok ✗ — çünkü kütüphane katalogları makale bilmez ✗, DergiPark holding
bilmez ✗.

**Ve bu, SOBİAD'ın da üstünde durduğu yerdir** ✓: `cites` yüklemi ile **makale →
kitap atfı** taşınabilir ✓ — yani "bu kitaba atıf yapan makaleler" sorusu
cevaplanabilir ✓.

---

## 5. Bunun için gereken üç iş — ve sırası

| # | İş | Neden |
|---|---|---|
| **1** | **Süreli yayın deseni** (dergi → sayı → makale) | Makale **ancak** sayıya bağlanabilirse var olur ✓ |
| **2** | **Hak / erişim katmanı** | Açık erişim de bir **haktır** ✓ (bedeli sıfır olsa da ✓) |
| **3** | **Değer genişlemesi** (`work_type='article'`, `carrier_type='online'`) | Yeni tablo gerekmez ✓ |
| **4** | **`cites` yüklemi** | Atıf grafiği ✓, SOBİAD verisi ✓ |
| **5** | **OAI-PMH hasat edici** + DergiPark hedefi | **Makalelerin giriş yolu** ✓ |

**5 numara, DergiPark entegrasyonunun kendisidir** ✓ — ve 1 numara olmadan
çalışmaz ✗, çünkü hasat edilen makalenin **duracağı yer yoktur** ✗.

---

## 6. Dürüst iki not

**1. DergiPark'ın OAI-PMH uç noktasını doğrulamadım.** Türkiye'deki açık erişim
platformlarının çoğu OAI-PMH yayınlar ✓ ve DergiPark'ın da yayınladığını
**bekliyorum** ✗ — ama **ölçmedim** ✗. Doğrulanmadan plana yazılmamalı ✓; ilk iş
`/oai` uç noktasını denemektir ✓.

**2. Tam metni almıyoruz.** Platform **künye** havuzudur ✓, **tam metin arşivi
değildir** ✗. Makalenin kendisi DergiPark'ta kalır ✓ ve biz **erişim linkini**
taşırız ✓ (`access_url` ✓ — hak katmanı bunun için var ✓). Tam metni kopyalamak
hem gereksiz ✗ hem telif açısından yanlış olurdu ✗.

---

## 7. Tek cümle

**DergiPark'ı yenmiyoruz, ona bağlanıyoruz** ✓ — ve bağlandığımızda **sahip
olmadığımız** bir şeyi (dergi yönetimini) almış olmayız ✗, **sahip olduğumuz** bir
şeyi (holding ve keşif) ona ekleriz ✓.
