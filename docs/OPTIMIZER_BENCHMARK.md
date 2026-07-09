# DonatıPlan Optimizasyon Benchmark Notu

Bu not, hızlı kesim algoritmasının eski tek geçişli best-fit-decreasing yaklaşımına göre nasıl iyileştirildiğini özetler.

## Skor sırası

Her aday kesim planı şu sırayla karşılaştırılır:

1. Kullanılan yeni stok çubuk sayısı
2. Gerçek hurda uzunluğu
3. Toplam artık uzunluğu
4. Kullanılabilir artık parça sayısı
5. En büyük kullanılabilir artık uzunluğu

Bu nedenle aynı çubuk sayısı ve aynı toplam artıkta daha az gerçek hurda bırakan plan seçilir. Yine eşitlik varsa daha az ve daha uzun kullanılabilir artık bırakan plan tercih edilir.

## Karşılaştırma

| Senaryo | Algoritma | Yeni stok çubuk | Toplam artık | Gerçek hurda | Gerçek hurda oranı | Kullanılabilir artık listesi |
|---|---:|---:|---:|---:|---:|---|
| 4 x 1000 mm + 1 x 8500 mm, Ø16 | Eski tek geçişli greedy | 2 | 11500 mm | 500 mm | %2,08 | 11000 mm |
| 4 x 1000 mm + 1 x 8500 mm, Ø16 | Yeni multi-start greedy | 2 | 11500 mm | 0 mm | %0,00 | 8000 mm, 3500 mm |
| 6000 + 6000 + 3000 + 3000 mm, Ø16 | Eski tek geçişli greedy | 2 | 6000 mm | 0 mm | %0,00 | 6000 mm |
| 6000 + 6000 + 3000 + 3000 mm, Ø16 | Yeni multi-start greedy | 2 | 6000 mm | 0 mm | %0,00 | 6000 mm |
| 20, 20, 20, 25, 45, 60 birim, kapasite 100 | Eski tek geçişli greedy | 3 | 110 | 0 | %0,00 | 80, 15, 15 |
| 20, 20, 20, 25, 45, 60 birim, kapasite 100 | Yeni multi-start greedy | 2 | 10 | 0 | %0,00 | 10 |

## Yorum

- İlk senaryoda satın alınan çubuk sayısı ve toplam artık değişmedi; fakat gerçek hurda 500 mm'den 0 mm'ye düştü.
- İkinci senaryoda sonuç matematiksel olarak zaten iyiydi; yeni algoritma 6000 mm tek kullanılabilir artığı korudu.
- Üçüncü senaryoda eski greedy 3 çubuk kullanırken yeni multi-start denemeler 2 çubukluk yerleşimi buldu.
- Çap grupları ayrı çözüldüğü için farklı çapların artıkları hiçbir aşamada birleştirilmez.
