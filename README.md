# DonatıPlan

Akıllı Donatı Kesim, Artık ve Hurda Analizi  
by BBO

DonatıPlan, betonarme projelerinde donatı kesimini optimize eden; artık parçaları,
stok hareketlerini ve saha çıktılarını tek yerde yöneten yerel-öncelikli bir karar
destek sistemidir.

> DonatıPlan statik proje hazırlamaz ve mühendis onayının yerine geçmez. Onaylı
> donatı açılım listesini kesim ve stok yönetimi açısından planlar.
> Bu repo erken aşama pilot MVP seviyesindedir; nihai ticari ürün olarak
> değerlendirilmeden önce gerçek şantiye verileriyle saha doğrulaması yapılmalıdır.

Geliştiren: Berke Boran Özdemir

## Öne çıkan özellikler

- CSV ve XLSX donatı açılım listesi içe aktarma
- Proje bazında kalıcı BBS talep taslakları
- İndirilebilir, doğrulamalı BBS Excel şablonu
- Küçük işler için kesin branch-and-bound çözümü
- Büyük işler için OR-Tools CP-SAT optimizasyonu
- Hızlı referans planla otomatik senaryo karşılaştırması
- Kesim ağzı kaybı, standart çubuk ve minimum artık ayarları
- Kalıcı proje, stok, optimizasyon geçmişi ve denetim izi
- Kesim planını atomik stok hareketine dönüştürme
- QR kodlu artık parça etiketleri
- Formüllü Excel ve yazdırılabilir PDF raporları
- Maliyet, ağırlık ve karbon tasarrufu göstergeleri
- Proje yedekleme ve geri yükleme
- Yönetici, mühendis, depo ve görüntüleyici rolleri
- Kurulabilir PWA kabuğu ve çevrimdışı arayüz önbelleği

## Hızlı başlangıç — Windows

İlk kez kullanırken `RebarFlow-Kur.cmd`, sonraki açılışlarda
`RebarFlow-Baslat.cmd` dosyasına çift
tıklayın. API ve arayüz başlatılır; tarayıcı otomatik olarak
`http://127.0.0.1:5173` adresini açar.

İlk açılışta en az 10 karakterli parola ile yönetici hesabı oluşturulur.

## Geliştirici kurulumu

Backend:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[test]"
.venv\Scripts\python -m uvicorn rebarflow.api:app --app-dir src --reload
```

Frontend — ikinci terminal:

```powershell
cd frontend
pnpm install
pnpm dev
```

Adresler:

- Web arayüzü: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8000`
- API dokümantasyonu: `http://127.0.0.1:8000/docs`

## Test ve derleme

```powershell
cd backend
.venv\Scripts\python -m unittest discover -s tests -v

cd ..\frontend
pnpm run build
```

## BBS dosyası yükleme

Uygulama CSV ve XLSX formatında donatı açılım/BBS dosyası alır. Dosyada en az şu bilgiler bulunmalıdır:

- Poz veya parça adı
- Çap bilgisi (`Çap`, `Çap (mm)`, `Ø`, `Fi`, `Donatı Çapı`)
- Boy bilgisi (`Boy`, `Boy (mm)`, `Uzunluk`, `Kesim Boyu`, `Kesim Boyu (mm)`)
- Adet bilgisi (`Adet`, `Miktar`, `Quantity`)

Örnek saha pilot dosyaları `examples/field-pilot/` klasöründedir.

## Metriklerin anlamı

- Toplam artık uzunluk: Kesimlerden sonra kalan tüm parçaların toplamıdır.
- İşlem toplam artık oranı: Tüm kalan artık / kullanılan toplam kaynak.
- Yeni stok artık oranı: Sadece satın alınan yeni stoktan kalan artık / satın alınan yeni stok. Yeni stok kullanılmadıysa raporda “Yeni stok kullanılmadı” gösterilir.
- Gerçek hurda: Minimum kullanılabilir artık sınırının altında kalan kısa parçalar.
- Kullanılabilir artık: Bu projede kullanılmayan, stokta tekrar kullanılabilecek yeterli uzunluktaki parçalardır.

## Temiz paylaşım / ZIP hazırlama

Projeyi başka bilgisayara aktarırken veya ZIP olarak paylaşırken sadece kaynak kodu ve kullanıcı dokümanlarını ekleyin.

ZIP’e koymayın:

- `.venv`
- `node_modules`
- `backend/data/rebarflow.db`
- `__pycache__`
- `.pytest_cache`
- `dist`
- `build`
- `.git`
- `.env`
- `.env.*`
- `*.db`, `*.sqlite`, `*.sqlite3`
- `*.tsbuildinfo`

Temiz paylaşım klasöründe sadece kaynak kod, `scripts`, `README.md`, `KULLANIM.md` ve örnek dosyalar bulunmalıdır. Gerçek saha verisi, kullanıcı hesabı/veritabanı ve derleme çıktıları paylaşım paketine girmemelidir.

## Klasör yapısı

```text
backend/
  src/rebarflow/  API, optimizasyon, veri, rapor ve güvenlik katmanları
  tests/          Birim ve API entegrasyon testleri
  assets/         BBS Excel şablonu
  data/           Yerel SQLite veritabanı (Git dışında)
frontend/
  src/            React + TypeScript arayüzü
  public/         PWA manifesti, servis çalışanı ve ikon
docs/             Mimari, yol haritası ve ürün belgeleri
examples/         Örnek BBS verileri
```

## Ortam değişkenleri

`backend/.env.example` dosyasına bakın. Başlıca ayarlar:

- `REBARFLOW_ALLOWED_ORIGINS`: Virgülle ayrılmış izinli web kökenleri
- `REBARFLOW_SECURE_COOKIE=1`: HTTPS üretim ortamında güvenli çerez
- `REBARFLOW_DATABASE_PATH`: SQLite veri dosyasının konumu

## Roller

| Rol | Okuma | Optimizasyon/proje | Stok işlemleri | Kullanıcı/yedek geri yükleme |
|---|---:|---:|---:|---:|
| Yönetici | ✓ | ✓ | ✓ | ✓ |
| Mühendis | ✓ | ✓ | ✓ | — |
| Depo | ✓ | — | ✓ | — |
| Görüntüleyici | ✓ | — | — | — |

## Veri ve yedekleme

Yerel veri varsayılan olarak `backend/data/rebarflow.db` dosyasında tutulur.
Her proje arayüzden JSON paketi olarak dışa aktarılabilir ve yeni bir proje
olarak geri yüklenebilir. Veritabanı ve yedek dosyaları kaynak kontrolüne
eklenmemelidir.

## Belgeler

- `docs/ARCHITECTURE.md` — bileşenler ve veri akışı
- `docs/ROADMAP.md` — geliştirme ve saha doğrulama planı
- `SECURITY.md` — güvenlik modeli ve bildirim yöntemi
- `CONTRIBUTING.md` — geliştirme kuralları
