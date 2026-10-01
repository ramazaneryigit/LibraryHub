# Pilot ve Gösterim Planı — ANKOS, TO-KAT, Bakanlık

**Sorulan soru:** "TO-KAT için yol anlaşma; bu yapıyı anlatmak için çalışan bir
yapı inşa etmem gerekiyor. Nasıl anlayacaklar?"

**Kısa cevap:** Şemayı anlatmayı bırakın. Kurumlar şema dinlemez ✗. **Kendi
kataloglarının bugün cevaplayamadığı bir soruyu, onların kendi verisiyle**
cevapladığınızı görürlerse anlarlar ✓.

---

## 1. Anlamanın tek yolu: cevaplayamadıkları bir soru

TO-KAT ve her kütüphane şu soruyu **zaten** cevaplıyor:

> "Bu kitap hangi kütüphanelerde var?"

O yüzden bu soruyu sormak bir şey kanıtlamaz ✗.

Cevaplayamadıkları sorular şunlar ve **her biri bir gösterim sahnesidir**:

| # | Soru | Neden cevaplayamıyorlar |
|---|---|---|
| **1** | "Bu eserin **2020 baskısı** hangi kütüphanelerde, ve **şu an rafta mı**?" | TO-KAT **holding** düzeyinde ✓; nüsha ve durum onda yok ✗ |
| **2** | "Bu kitap **henüz basılmadı**, hangi kütüphaneler sipariş planına aldı?" | ISBN ajansı akışı yok ✗ |
| **3** | "Bu yayınevinin kitapları **hangi kütüphanelerde**?" | Yayınevi tarafı yok ✗ |
| **4** | "**Ayşe** yazdığımda **Ayşe**'yi buluyor mu?" | Normalizasyon çoğu sistemde yok ✗ |
| **5** | "Bu alanı **kim** değiştirdi, **hangi kaynak** öyle dedi?" | Provenance yok ✗ |

**Gösterim bu beş sorudan ibarettir.** Slayt yok, şema yok — soru sorulur, cevap
ekranda görünür ✓.

---

## 2. Çalışan yapı ne demek — asgari

Anlaşma için gereken **en küçük çalışan şey**:

| # | Gereken | Durum |
|---|---|---|
| 1 | **Bir gerçek kütüphanenin gerçek koleksiyonu** (bir `.mrc` dosyası) | ✗ yok |
| 2 | **MARC ayrıştırıcı** (ISO 2709) | ✗ yazılmadı |
| 3 | **Yükleme ekranı** — kütüphaneci dosyayı bırakır | ✗ |
| 4 | **Dürüst uyum raporu** — kaç kayıt, kaç eşleşmedi, **hangi alan** | ✗ |
| 5 | **Nüsha düzeyi cevap** — "2020 baskısı, rafta" | ⚠️ veri var, uç kırık ✗ |
| 6 | **MARC dışa aktarma** | ✗ |

Ve **üç engel** (hepsi kod, hiçbiri veri değil):

- `create_user.py` kiracısız paydaş hesabı açamıyor ✗
- Hesap kalkanı paydaş hesabını `admin` olarak reddediyor ✗
- **`POST /tenant/holdings` 500 veriyor** ✗ ← bu düzelmeden 5. satır çalışmaz

---

## 3. İnandırıcılığı kuran şey: **dışa aktarma**

Bir kurumun imza atmadan önce sorduğu gerçek soru şudur:

> **"Verimizi verirsek geri alabilir miyiz?"**

Bu yüzden **MARC dışa aktarma**, içe almadan **daha önemlidir** ✓. Ve ucuzdur ✓ —
aynı kodek ters yönde ✓.

**Anlaşmanın cümlesi şu olmalı:**

> Veriniz sizde kalır. İstediğiniz gün **aynı MARC dosyasını** geri alırsınız.
> Katılma geri alınabilir; çıkma veri kaybı değildir.

Bu cümle söylenemezse anlaşma olmaz ✗.

---

## 4. Dürüstlük en güçlü argüman

Kolay olan, "42.318 kayıt başarıyla yüklendi" demektir ✗. **İnandırıcı olan:**

```
Alınan kayıt       : 42.318
Eşleşen            : 41.902
Eşleşmeyen         :   416
  ├─ 245 alanı boş :   118
  ├─ 020 ISBN yok  :   201
  └─ 852 şube yok  :    97
```

Bunu gösteren bir sistem, **kendi eksiğini söyleyen** bir sistemdir ✓ ve kurumlar
tam olarak buna güvenir ✓. Ayrıca aynı rapor kütüphaneciye **ne düzelteceğini**
söyler ✓ — yani işe yarar ✓.

---

## 5. Sıra — ANKOS'a değil, **bir kütüphaneye** gidin

| Adım | Kiminle | Ne istenir |
|---|---|---|
| **1** | **Bir üniversite kütüphanesi** (pilot) | Tek bir `.mrc` dışa aktarımı (~100 kayıt yeter) |
| **2** | Aynı kütüphane | Gerçek koleksiyonla deneme; hatalarını gösterin |
| **3** | Aynı kütüphane | **Referans** olur: "bizde çalışıyor" |
| **4** | **ANKOS** | Çalışan bir referansla gidin, şemayla değil |
| **5** | **TO-KAT / Bakanlık** | Artık protokol konuşulabilir |
| **6** | **ISBN Ajansı** | 2. sahne (basılmamış yayın) onların ilgi alanı |

**ANKOS'a ilk gidişte şema götürmek, reddedilmenin en hızlı yoludur** ✗. Çalışan
bir pilot kütüphane götürmek, kabulün en hızlı yoludur ✓.

---

## 6. Pilot kütüphaneye söylenecekler — üç cümle

1. **Ne istiyoruz:** koleksiyonunuzun bir MARC dışa aktarımı. Başka hiçbir şey.
2. **Ne veriyoruz:** eserlerinizin hangi kütüphanelerde olduğunu **nüsha ve raf
   düzeyinde** gösteren bir katalog, ve **dilediğiniz an MARC olarak geri alma**.
3. **Ne yapmıyoruz:** okuyucu verisi istemiyoruz, ödünç kaydı istemiyoruz,
   sisteminize **yazmıyoruz** ✓. Sizden çıkan veri sizin kalır.

Üçüncü cümle pazarlık edilemez ✓. Bir kütüphanenin en hassas verisi
**okuyucusudur** ve ona dokunmadığımızı baştan söylemek, geri kalan her şeyi
mümkün kılar ✓.

---

## 7. Tek cümlelik özet

> **Beş soru, tek gerçek kütüphane, dürüst bir rapor, ve MARC geri alma sözü.**
> Bunlar varsa anlaşma konuşulur; bunlar yoksa şema anlatmak ikna etmez.

---

## 8. Bunu inşa etmek için sıra

| # | İş | Neden bu sırada |
|---|---|---|
| **A** | Üç engeli kapat (hesap, kalkan, holding 500) | Bunlar olmadan hiçbir sahne çalışmaz |
| **B** | MARC **içe** ayrıştırıcı + yükleme ekranı | Pilot kütüphanenin koleksiyonu |
| **C** | Uyum raporu (alan alan) | İnandırıcılık |
| **D** | **MARC dışa** aktarma | Anlaşmanın önkoşulu |
| **E** | Beş sahnenin ekranları | Gösterim |
| **F** | Pilot kütüphane + gerçek koleksiyon | Referans |

**A ve D olmadan gösterime çıkılmaz** ✗ — biri sahneyi çalıştırır, diğeri
anlaşmayı mümkün kılar.
