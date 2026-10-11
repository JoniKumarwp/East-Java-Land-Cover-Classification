# Business Understanding

**Nama:** Joni Kumar Meghwar  
**NIM:** 240411100234

## Fokus dan tujuan

Menyediakan alat peninjauan awal tutupan lahan untuk mendukung pemantauan kawasan pesisir dan penggunaan lahan Jawa Timur. Fokus utamanya adalah membedakan mangrove dari hutan darat, pertanian, air dan bangunan melalui data spektral Sentinel-2 serta menyediakan pemeriksaan visual pada peta satelit.

Pengguna dapat menampilkan hanya kelas tertentu untuk meninjau sampel mangrove, sawah atau kawasan terbangun. Peta evaluasi memungkinkan pemeriksaan lokasi kesalahan prediksi sebelum informasi dipakai dalam kajian lanjutan.

## Kriteria keberhasilan

1. Lima kelas tersedia dengan label dan geometri yang dapat ditelusuri.
2. Fitur band dan indeks berasal dari citra Sentinel-2 aktual, termasuk B8A, B11 dan B04.
3. Evaluasi dilakukan pada poligon yang tidak dipakai melatih model; laporkan accuracy, precision, recall, F1 dan Cohen Kappa.
4. Kesalahan antar kelas dibahas berdasarkan hasil aktual, terutama mangrove vs hutan darat.
5. Overlay satelit memiliki checkbox untuk setiap kelas dan aplikasi dapat dijalankan di Streamlit.

Jumlah sampel awal tidak memastikan model sudah baik. Tambahkan atau perbaiki digitasi berdasarkan kualitas data dan evaluasi yang jujur. Untuk menguji generalisasi geografis, gunakan blok wilayah terpisah pada pengembangan lanjutan.

## Batasan informasi

Klasifikasi dilakukan pada fitur rata-rata poligon sampel, sesuai alur referensi. Tidak ada klaim luas total atau pemetaan semua piksel Jawa Timur. Hasil ini mendukung eksplorasi akademik, bukan keputusan tata ruang final tanpa validasi tambahan.
