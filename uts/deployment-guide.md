# Deployment Streamlit dan GitHub Pages

**Joni Kumar Meghwar · 240411100234**

## 1. Jalankan dan verifikasi proyek

Dari folder utama proyek:

```bash
python -m pip install -r requirements.txt
python uts/code/crawling.py --plan
python uts/code/crawling.py
python uts/code/pipeline.py train
python -m streamlit run uts/deploy/app.py
```

Buat akun pada [Copernicus Data Space](https://dataspace.copernicus.eu/). Script menggunakan `authenticate_oidc()` dan meminta login di browser. Password tidak perlu disimpan di Python atau GitHub. Periksa kuota akun sebelum menjalankan batch job. Akun Copernicus diperlukan untuk mengambil/memproses data satelit; dashboard yang membaca hasil lokal tidak memerlukan login Copernicus.

Jika ingin menjalankan dari Google Colab, buka `uts/code/Run_in_Colab.ipynb`, jalankan cell berurutan, upload ZIP proyek, login melalui tautan device login yang dicetak, lalu unduh ZIP hasil. Colab dapat terputus untuk pekerjaan lama; gunakan komputer lokal untuk proses yang lebih stabil. Catatan hasil training perlu disimpan/diunggah sebelum sesi berakhir.

## 2. Upload ke GitHub

Buat repository milik Anda. Upload isi `Joni_PSD_UTS` sehingga `uts` berada langsung di root repository. Jangan upload folder job GeoTIFF atau kredensial. Setelah model dilatih, sertakan hasil di `uts/deploy`, tabel poligon di `uts/data/csv/poligon`, dan model di `uts/models`.

Jika memakai Git, sesudah repository remote Anda ditambahkan:

```bash
git add .
git commit -m "Add Joni East Java LULC UTS project"
git push -u origin main
```

## 3. Streamlit Community Cloud

Masuk di [Streamlit Community Cloud](https://share.streamlit.io/) menggunakan GitHub. Buat app dari repository Anda, branch `main`, main file path **`uts/deploy/app.py`**. Gunakan Python 3.12 pada pengaturan deployment jika tersedia. Dependencies untuk dashboard berada di `uts/deploy/requirements.txt`.

Dashboard dapat di-deploy sebelum training, tetapi akan jelas menampilkan status model belum dilatih. Untuk submission hasil klasifikasi, selesaikan ekstraksi/training dan push hasilnya terlebih dahulu.

Setelah berhasil, salin URL Streamlit asli ke README dan bagian di bawah. Link ini belum tersedia karena belum ada deployment pada akun Anda.

**URL Streamlit:** pending deployment.  
**URL repository:** isi setelah repository dibuat.

## 4. Dokumentasi GitHub Pages seperti referensi

Workflow `.github/workflows/deploy-book.yml` membangun Jupyter Book dari dokumen CRISP-DM dan notebooks tanpa mengeksekusi remote jobs. Di Settings → Actions → General, izinkan workflow memakai read/write repository permissions jika diperlukan. Setelah workflow sukses dan branch `gh-pages` muncul, di Settings → Pages pilih deploy from branch `gh-pages`, folder root.

Panduan ini akan berada pada `https://USERNAME.github.io/REPOSITORY/uts/deployment-guide.html`. Ganti USERNAME/REPOSITORY sesuai akun Anda; ini format URL, bukan link deployment yang sudah aktif.

## 5. Checklist submission

- Data digitasi milik sendiri, laporan validasi dan lima kelas.
- Business understanding dengan tujuan yang jelas.
- Ekstraksi citra aktual, data preparation, model dan evaluation.
- Layer yang bisa dicentang di atas citra satelit.
- Notebook, CSV evaluasi dan model hasil data Anda.
- Link GitHub Pages dan Streamlit yang benar-benar dapat dibuka.
 
 
- [Streamlit deployment documentation](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app)
