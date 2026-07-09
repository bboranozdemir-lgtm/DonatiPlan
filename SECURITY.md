# Güvenlik

## Desteklenen kullanım

DonatıPlan varsayılan olarak yerel bilgisayarda çalışır. İnternete açık üretim
kurulumunda HTTPS, güvenli çerez ve ters vekil kullanılması zorunludur.

## Güvenlik özellikleri

- PBKDF2-HMAC-SHA256 parola karmalama
- HttpOnly, SameSite oturum çerezi
- Sunucuda yalnızca oturum belirteci özeti
- Rol tabanlı yazma yetkileri
- CORS izin listesi
- XLSX boyut ve ZIP içerik limitleri
- Pydantic istek doğrulaması
- Atomik stok taahhütleri
- Temel güvenlik yanıt başlıkları

## Üretim kontrol listesi

1. `REBARFLOW_SECURE_COOKIE=1` ayarlayın.
2. `REBARFLOW_ALLOWED_ORIGINS` değerini yalnız gerçek HTTPS alan adına indirin.
3. API'yi doğrudan internete açmayın; HTTPS ters vekil arkasına alın.
4. Veritabanını ve proje yedeklerini düzenli yedekleyin.
5. Varsayılan yönetici parolasını paylaşmayın.
6. BBS ve rapor dosyalarını kişisel/veri sınıflandırma politikasına göre saklayın.

Güvenlik açığını herkese açık issue yerine depo sahibine özel kanaldan bildirin.
