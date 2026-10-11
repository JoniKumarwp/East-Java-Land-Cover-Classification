# Data Understanding dan Data Preparation

## Sumber digitasi

`EastJawa_Data.geojson` berisi 250 fitur Polygon. Air memakai properti `Type`, sedangkan empat kelas lainnya memakai `Class`. Label disamakan menjadi Air, Pemukiman, Sawah, Hutan Non-Mangrove dan Hutan Mangrove.

Setelah pemeriksaan, 247 poligon dapat dipakai: Air 50, Pemukiman 48, Sawah 49, Mangrove 50 dan Hutan 50. Sembilan poligon diperbaiki; fitur sumber 70, 71 dan 148 harus didigitasi ulang karena tidak mempunyai luas yang dapat dipulihkan. File asli dipertahankan. Laporan rinci tersedia dalam `uts/deploy/geometry_issues.csv`. Lima belas pasangan poligon beririsan; piksel bersama dibuang saat ekstraksi.

## Data satelit

Produk Sentinel-2 Level-2A diambil melalui openEO Copernicus Data Space. Band: B02, B03, B04, B08, B8A dan B11. Periode awal 2026-09-01 sampai 2026-10-01 (akhir eksklusif). Seleksi scene dengan cloud cover maksimum 30%, lalu mask SCL sebelum median waktu.

Indeks:

| Indeks | Rumus |
|---|---|
| NDVI | (B08 − B04) / (B08 + B04) |
| NDWI | (B03 − B08) / (B03 + B08) |
| MNDWI | (B03 − B11) / (B03 + B11) |
| NDBI | (B11 − B08) / (B11 + B08) |
| NDMI_8A | (B8A − B11) / (B8A + B11) |

B8A berbeda dari B08. Band 20 m diselaraskan ke grid 10 m; resolusi efektif asli tidak meningkat. Poligon sangat kecil dapat memakai piksel yang tersentuh batas, sehingga perlu verifikasi visual.

## Persiapan dan pemodelan

Piksel valid disimpan beserta ID poligon sumber. Maksimum 2.000 piksel per poligon per tile diambil secara reproducible. Semua fitur dirata-ratakan per poligon, kemudian dilakukan stratified split 70% training dan 30% testing dengan seed 42. Jumlah akhir bergantung pada poligon yang benar-benar mempunyai piksel valid.

StandardScaler dilatih hanya pada training. Model k-NN menggunakan k=5, bobot distance dan jarak Euclidean. Kurva k=1 sampai 15 dihitung melalui stratified cross-validation pada training, bukan dengan memilih berdasarkan test set.

## Status hasil

Citra belum diambil dengan akun pengguna. Tidak ada skor accuracy atau confusion matrix aktual yang dapat dilaporkan. Notebook dan dashboard akan menghasilkan tabel tersebut setelah ekstraksi dan training selesai.
