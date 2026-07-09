# DonatıPlan

Akıllı Donatı Kesim, Artık ve Hurda Analizi  
by BBO

Geliştiren: Berke Boran Özdemir

> Bu sürüm erken aşama pilot MVP’dir. Nihai ticari ürün değildir; gerçek şantiye kullanımından önce mühendis kontrolü ve saha doğrulaması gerekir.

## Kısa kullanım

1. `RebarFlow-Baslat.cmd` dosyasını çalıştırın.
2. Tarayıcıda `http://127.0.0.1:5173` adresi açılır.
3. Kullanıcı hesabınızla giriş yapın.
4. Proje oluşturun veya mevcut projeyi seçin.
5. BBS/donatı listesini CSV ya da XLSX olarak yükleyin.
6. Minimum kullanılabilir artık, standart çubuk boyu ve kesim kaybı ayarlarını kontrol edin.
7. Planı optimize edin.
8. Toplam artık, gerçek hurda ve kullanılabilir artık listesini kontrol edin.
9. Excel/PDF raporlarını indirin.

> DonatıPlan mühendis onayının yerine geçmez; onaylı donatı açılım listesini kesim ve stok yönetimi açısından planlar.

## BBS dosya formatı

CSV/XLSX dosyasında poz, çap, boy ve adet bilgileri olmalıdır. Şu başlıklar desteklenir:

- Çap: `Çap`, `Çap (mm)`, `Ø`, `Fi`, `Donatı Çapı`
- Boy: `Boy`, `Boy (mm)`, `Uzunluk`, `Kesim Boyu`, `Kesim Boyu (mm)`
- Adet: `Adet`, `Miktar`, `Quantity`

Örnek dosyalar: `examples/field-pilot/`

## Sonuç metrikleri

- Toplam artık uzunluk: Kesimlerden sonra kalan tüm parçalar.
- İşlem toplam artık oranı: Tüm kalan artık / kullanılan toplam kaynak.
- Yeni stok artık oranı: Sadece yeni stoktan kalan artık / satın alınan yeni stok. Yeni stok kullanılmadıysa “Yeni stok kullanılmadı” yazılır.
- Gerçek hurda: Minimum kullanılabilir artık sınırının altında kalan kısa parçalar.
- Kullanılabilir artık: Bu projede kullanılmamış, stokta tekrar kullanılabilecek parça.

## Temiz paylaşım / ZIP hazırlama

Paylaşım paketine `.venv`, `node_modules`, `backend/data/rebarflow.db`, `__pycache__`, `.pytest_cache`, `dist`, `build`, `.git`, `.env`, `.env.*`, `*.db`, `*.sqlite`, `*.sqlite3` ve `*.tsbuildinfo` dosyalarını koymayın.

Temiz pakette kaynak kod, `scripts`, `README.md`, `KULLANIM.md` ve örnek dosyalar yeterlidir. Böylece hem paket küçülür hem de gerçek kullanıcı/veritabanı bilgileri yanlışlıkla paylaşılmaz.
