# YouTube Downloader

Aplikasi desktop Windows untuk mengunduh video dengan suara, banyak link, dan playlist. Default kualitas **tertinggi hingga 1080p**. Hasil **MP4 H.264/AAC** jika tersedia pada resolusi terpilih; jika codec lain diperlukan, hasil **MKV dengan codec asli**. Aplikasi tidak menaikkan resolusi dan tidak melakukan encoding ulang.

## Langsung pakai

Python, Tkinter, yt-dlp, FFmpeg, FFprobe, dan Deno sudah disiapkan pada komputer ini. Klik dua kali **Autorun.bat** dari folder proyek untuk membuka aplikasi. Peluncur **Buka YouTube Downloader.bat** juga tetap bisa digunakan. Biarkan terminal peluncur tetap terbuka selama aplikasi digunakan.

1. Paste satu atau beberapa link, **satu link per baris**. Link video dan playlist boleh dicampur.
2. Pilih **Kualitas hingga** dan folder penyimpanan.
3. Klik **Tambahkan ke antrean**. Resolusi setiap video baru diperiksa saat akan diunduh sehingga penambahan batch tidak menunggu pemeriksaan semuanya.
4. Semua entri awalnya dipilih. Klik tanda pada kolom **Pilih**, atau fokuskan baris dan tekan Space untuk mengubah pilihan. Pilih semua/kosongkan pilihan berlaku ke seluruh antrean, bukan hanya halaman saat ini.
5. Klik **Mulai**. Aplikasi mengerjakan satu video pada satu waktu agar laptop tetap ringan.

**Cek satu video** bersifat opsional: menampilkan resolusi sumber dan menambahkan video ke antrean. Metadata disimpan dalam cache sehingga klik Mulai tidak perlu mengambil informasi yang sama lagi selama cache masih berlaku.

Link `watch?v=...&list=...` secara default hanya menambahkan satu video. Aktifkan **Seluruh playlist pada link video** untuk mengambil playlist-nya. Link `/playlist?list=...` otomatis dianggap playlist. Entri playlist muncul bertahap; antrean boleh dimulai sebelum seluruh daftar selesai dimuat. Video duplikat berdasarkan ID dilewati. Baris input tidak valid ditandai merah.

## Kontrol antrean

| Kontrol | Perilaku |
| --- | --- |
| Mulai | Memproses pekerjaan terpilih yang masih menunggu. |
| Jeda setelah video ini | Menyelesaikan video aktif, lalu berhenti mengambil pekerjaan berikutnya. |
| Batalkan video aktif | Membatalkan video aktif; antrean tetap berjalan jika belum dijeda. File parsial dipertahankan. |
| Coba lagi yang gagal | Mengembalikan pekerjaan gagal/dibatalkan yang terpilih ke status menunggu. Klik Mulai jika antrean sedang berhenti. |
| Hapus terpilih | Menghapus entri yang bukan pekerjaan aktif. File hasil dan bahan parsial tidak dihapus. |
| Hentikan pemeriksaan | Menghentikan pemuatan link/playlist; entri yang sudah masuk tetap tersedia. |
| Detail & log | Mengganti area tabel dengan detail baris yang difokuskan dan maksimum 500 baris log. Klik Kembali ke antrean untuk kembali. |
| Buka folder | Membuka folder hasil baris yang difokuskan, atau folder penyimpanan saat ini. |

Klik dua kali baris yang selesai untuk membuka file hasil dengan pemutar bawaan. MKV dapat memerlukan pemutar yang mendukung codec sumber, misalnya VLC.

Kegagalan satu video tidak menghentikan video berikutnya. Video privat/dihapus akan ditandai gagal saat diketahui; video yang membutuhkan login, DRM, live, atau belum tayang tidak didukung.

Mengubah kualitas/folder berlaku untuk pekerjaan **menunggu dan terpilih**, bukan pekerjaan yang sudah aktif atau selesai. Resolusi aktual yang lebih rendah ditandai panah turun. Contoh: batas 1080p dan sumber maksimal 720p menghasilkan video 720p dengan suara.

## Performa dan pemulihan

- Satu download aktif; maksimal dua fragmen paralel untuk format DASH/HLS yang mendukung. Percobaan ulang menggunakan satu fragmen. Pengaturan ini tidak berarti semua stream HTTPS diunduh melalui dua koneksi.
- Cache metadata maksimum 10 video, berlaku lima menit, hanya di memori. Jika URL media ditolak/kedaluwarsa (403/410), metadata diperbarui sekali. Tidak ada trik mengganti client atau melewati tantangan YouTube.
- Stream dipilih berdasarkan resolusi dahulu, lalu kompatibilitas codec. Penggabungan memakai satu proses FFmpeg dengan `-c copy`; tidak ada tahap encoding H.264/AAC tambahan.
- File akhir diperiksa sekali dengan FFprobe untuk memastikan video, audio, dan resolusinya. File dipublikasikan dalam filesystem yang sama tanpa menyalin seluruh isinya atau menimpa hasil lama; nama yang sama diberi nomor tambahan.
- Progres diperbarui maksimal lima kali per detik di UI dan tidak ditumpuk sebagai ribuan event. Tabel menampilkan maksimal 100 baris per halaman. Tidak ada unduhan thumbnail otomatis atau animasi progres saat idle.
- Kecepatan dan ETA adalah milik stream aktif, bukan estimasi seluruh playlist. Saat metadata, penggabungan, atau verifikasi berjalan, lihat status teks; persentase transfer tidak menjamin seluruh proses selesai.
- Pengaturan dan antrean disimpan otomatis di `data/state.json`. Setelah aplikasi ditutup, pekerjaan aktif kembali menunggu; download tidak otomatis berjalan saat dibuka lagi. Klik Mulai untuk melanjutkan. URL stream bertanda tangan dan metadata lengkap tidak disimpan ke disk.
- File parsial berada di `<folder hasil>/.youtube-work/<ID pekerjaan>/`. Retry memakai folder dan format yang sama untuk melanjutkan jika sumber mendukungnya. Jika format berubah, bahan lama dipindahkan ke subfolder `previous-...` agar byte dari format berbeda tidak dicampur.
- File sementara dihapus setelah sukses. Saat gagal, detail menampilkan lokasinya; kegagalan penggabungan dapat diperiksa di `ffmpeg.log`. Menghapus entri antrean tidak menghapus folder parsial tersebut. Boleh dibersihkan manual setelah proses berhenti dan bahannya tidak diperlukan lagi.
- Penutupan aplikasi membatalkan pekerjaan aktif secara terkontrol dan menyimpan antrean. Permintaan metadata/jaringan yang sedang berjalan dapat menunggu timeout/retry; pembatalan tidak selalu seketika. FFmpeg dihentikan saat penggabungan dibatalkan.

Siapkan ruang untuk stream sumber dan file gabungan. Resume tidak dijamin bila server tidak mendukung byte range, file berubah, atau URL sumber sudah tidak tersedia.

## Hasil pengukuran

Pengukuran pada lingkungan pengembangan ini, 22 Oktober 2026. Angka jaringan memakai link `LRy-MMx2pvI`, tiga pengulangan; angka pemrosesan memakai video sintetis 1080p berdurasi satu detik.

| Bagian | Referensi pekerjaan lama | Jalur baru |
| --- | --- | --- |
| Persiapan metadata, median | Ekstraksi ulang: 2,491 detik | Pembacaan cache: 0,0066 detik |
| Pemrosesan file sintetis, median | Konversi H.264/AAC: 0,242 detik | Mux codec asli: 0,042 detik |
| CPU proses FFmpeg sintetis, median | 0,594 detik CPU | 0,031 detik CPU |

Uji UI dengan 1.000 entri menampilkan 100 baris, dengan waktu render sekitar 2,2 ms. Ini bukan jaminan kecepatan download internet atau benchmark seluruh aplikasi lama melawan aplikasi baru. Cek pertama tetap membutuhkan akses YouTube. CPU FFmpeg di atas adalah waktu CPU proses, bukan persentase CPU seluruh laptop; contoh video sintetis bukan representasi semua video.

Skrip benchmark menyimpan hasil di `.tools/benchmark.json`, dan uji UI di `.tools/ui-performance.json`. Keduanya dapat dijalankan ulang; angka dapat berubah menurut komputer, koneksi, dan keadaan YouTube.

## Instalasi ulang / komputer lain

Tidak perlu melakukan langkah ini lagi pada komputer yang sudah disiapkan.

1. Pasang Python 3.13 lengkap dari [python.org](https://www.python.org/downloads/windows/), termasuk **pip** dan **Tcl/Tk**. Aktifkan Add Python to PATH.
2. Sediakan `ffmpeg.exe` dan `ffprobe.exe` dari build Windows yang ditautkan [FFmpeg](https://ffmpeg.org/download.html) atau [yt-dlp FFmpeg Builds](https://github.com/yt-dlp/FFmpeg-Builds).
3. Sediakan `deno.exe` dari [Deno](https://docs.deno.com/runtime/getting_started/installation/). Deno diperlukan untuk tantangan JavaScript YouTube; lihat [panduan EJS yt-dlp](https://github.com/yt-dlp/yt-dlp/wiki/EJS).
4. Letakkan tiga executable tersebut di `.tools/bin/` di dalam proyek, atau pasang ke PATH. Aplikasi mengutamakan executable lokal.
5. Dari folder proyek:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Kemudian buka peluncur `.bat`. Folder `.venv`, `.tools`, dan `data` tidak dimasukkan ke Git.

Jika `python` membuka shortcut Microsoft Store, tutup seluruh VS Code dan buka kembali sesudah instalasi. Alternatif untuk instalasi per pengguna di lokasi default:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Python embeddable di `.tools/python` hanya dipakai untuk tes logika dan tidak memiliki Tkinter. Aplikasi memakai Python lengkap di `.venv`.

Perbarui dependensi jika mekanisme YouTube berubah:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade -r requirements.txt
```

## Pengujian dan struktur

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tests\gui_smoke.py
.\.venv\Scripts\python.exe tests\benchmark.py
# Opsional: pemeriksaan metadata jaringan dan satu entri playlist publik
.\.venv\Scripts\python.exe tests\benchmark.py --network
```

Tes otomatis mencakup TTL/LRU cache, pemilihan kualitas/container, retry/refresh metadata, file parsial, pembatalan, publikasi tanpa overwrite, antrean/pemulihan, dan 1.000 entri. Tes integrasi memakai yt-dlp serta FFmpeg dengan fixture lokal MP4/MKV; tidak mengunduh video YouTube. Tanpa dependensi media, tes integrasi dilewati. Uji GUI membuka jendela sintetis dan menutupnya otomatis.

`downloader.py` menangani metadata, playlist, stream, dan mux. `queue_model.py` menangani scheduler satu pekerja, event yang dibatasi, dan penyimpanan. `app.py` hanya memperbarui Tkinter pada thread UI. `DownloadEngine.inspect()` dan `DownloadEngine.download()` pada instance yang sama berbagi cache; fungsi kompatibilitas `inspect_video()` / `download_video()` memakai engine default.

Tampilan mengikuti susunan downloader dari [Free Download Manager](https://www.freedownloadmanager.org/) serta pola toolbar dan daftar Windows. UI memakai Tkinter/ttk dengan font sistem; tidak menambahkan framework web.
