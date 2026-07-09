# Katkıda bulunma

## Değişiklik ilkeleri

- Mühendislik hesaplarında birim açık olmalıdır.
- Uzunluklar çekirdekte tam sayı milimetre tutulmalıdır.
- Yeni algoritma hızlı referans çözümden daha kötü sonucu sessizce kabul etmemelidir.
- Veritabanı şema değişiklikleri `PRAGMA user_version` göçü içermelidir.
- API değişikliği backend testi ve TypeScript tip güncellemesiyle birlikte gelmelidir.
- Mevcut kullanıcı verisi silinmemelidir.

## Doğrulama

Pull request öncesinde:

```powershell
cd backend
.venv\Scripts\python -m unittest discover -s tests -v

cd ..\frontend
pnpm run build
```

Arayüz değişikliklerinde proje oluşturma, XLSX yükleme, optimizasyon, rapor indirme,
stoğa işleme ve yedek geri yükleme akışlarını elle kontrol edin.
