# DNG Studio — konverter foto ke LinearRaw DNG sintetis

Web app berbahasa Indonesia untuk mengubah foto raster menjadi berkas **DNG tipe LinearRaw sintetis**, sambil mempertahankan ukuran raster sumber (lebar × tinggi) dan rasio aspeknya. Proses ini **tidak** dapat memulihkan data sensor RAW asli yang tidak ada pada JPEG/PNG/WebP.

## Catatan penting tentang “DNG asli”

JPEG, JPG, PNG, dan WebP berisi gambar yang sudah dirender/dikodekan. Informasi sensor kamera seperti pola CFA/Bayer asli, headroom highlight yang hilang, data pembacaan sensor, serta pipeline pemrosesan kamera tidak dapat direkonstruksi secara persis dari file tersebut. Proyek ini memakai `image2dng` untuk membuat **synthetic LinearRaw DNG** dengan provenance yang sesuai, bukan menyamar sebagai RAW asli dari kamera tertentu. Spesifikasi DNG Adobe menjelaskan DNG sebagai format untuk menyimpan data RAW, sementara proyek `image2dng` sendiri menegaskan bahwa hasilnya bukan dump sensor kamera asli.

Dimensi lebar dan tinggi tidak di-resize atau di-crop oleh aplikasi ini. Backend juga membuka kembali output TIFF/DNG dan menolak hasil jika dimensinya berbeda atau tidak dapat diverifikasi. Perhatikan bahwa representasi warna/bit depth dapat berubah saat gambar raster dinormalisasi; area transparan akan diratakan ke latar putih karena output LinearRaw RGB tidak mempertahankan transparansi. EXIF/MakerNote asli tidak dijanjikan akan dipertahankan.

## Format masukan

JPG/JPEG, PNG, WebP, BMP, TIFF, dan GIF statis. Gambar animasi ditolak agar tidak diam-diam mengambil frame pertama. HEIC/AVIF dan file RAW kamera belum diaktifkan di versi ini.

## Menjalankan di Linux/macOS

Prasyarat: Python 3.11+, Git, serta koneksi internet untuk mengambil mesin konversi DNG yang digunakan.

```bash
chmod +x setup.sh start.sh
./setup.sh
./start.sh
```

Kemudian buka `http://127.0.0.1:8000`.

`setup.sh` membuat virtual environment, memasang dependensi web, lalu mengambil proyek [`pingqLIN/Image-to-Raw`](https://github.com/pingqLIN/Image-to-Raw) ke folder `vendor/Image-to-Raw` dan menyiapkan CLI `image2dng`. Mesin konversi upstream masih merupakan prototipe; uji kompatibilitas dengan aplikasi RAW spesifik tetap disarankan.

## Menjalankan dengan Docker

```bash
docker build -t dng-studio .
docker run --rm -p 8000:8000 dng-studio
```

Buka `http://127.0.0.1:8000`.

## Konfigurasi opsional

- `IMAGE2DNG_PROJECT`: lokasi folder proyek `Image-to-Raw`.
- `MAX_UPLOAD_BYTES`: batas ukuran unggahan dalam byte (default 100 MiB).
- `MAX_PIXELS`: batas total piksel (default 100.000.000).
- `CONVERT_TIMEOUT_SECONDS`: batas waktu konversi (default 240 detik).

Default server hanya bind ke `127.0.0.1` melalui `start.sh`, agar unggahan diproses pada komputer sendiri. Jika dipasang di server publik, unggahan melewati server tempat aplikasi dipasang; tambahkan autentikasi, pembatasan laju, HTTPS, kebijakan retensi, dan pengamanan penyimpanan sebelum digunakan publik.

## Catatan implementasi

- `POST /api/inspect`: inspeksi format dan dimensi gambar tanpa mengubah berkas.
- `POST /api/convert`: menghasilkan DNG dan mengirimkan header dimensi/rasio sumber.
- `GET /api/health`: status mesin konversi.
- File kerja sementara dihapus setelah respons selesai.
