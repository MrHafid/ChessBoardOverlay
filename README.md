# Chess Board Overlay

Overlay transparen yang diletakkan di atas papan catur di layar, misalnya di Chess.com, Lichess, atau GUI NautilusChess. Program membaca langkah dari gambar di dalam kotak overlay, mengikuti jalannya game, lalu menampilkan saran langkah dari engine:

- sebagai **panah** di atas papan, dan
- sebagai **teks** di panel kanan: langkah terbaik, evaluasi, 3 variasi teratas, dan riwayat game.

Program tidak pernah mengklik atau menjalankan bidak. Semua langkah tetap kamu yang menjalankan.

## Fitur

- **Kotak overlay transparen** yang bisa digeser dan diubah ukurannya, dengan grid 8×8 untuk menyelaraskan dengan papan.
- **Tembus klik.** Saat terkunci, semua klik dan drag diteruskan ke papan di bawahnya.
- **Tidak ikut ter-capture.** Panah overlay tidak terbaca sebagai bagian dari papan.
- **Pengenalan bidak.** Rupa ke-12 jenis bidak direkam dari papan yang sedang dipakai, jadi tetap jalan dengan tema papan dan set bidak apa pun.
- **Rekam otomatis.** Bidak direkam dan arah papan (Putih atau Hitam di bawah) diatur otomatis begitu posisi awal terlihat.
- **Membaca langkah kedua pihak**, termasuk langkah bot, rokade, en passant, dan promosi ke bidak apa pun. Highlight, titik langkah, dan bidak yang sedang dipilih tidak mengganggu.
- **Baca posisi di tengah game** dengan satu tombol.
- **Sinkron ulang otomatis.** Kalau ada langkah yang terlewat, posisi dibaca ulang dari layar. Game baru di papan juga langsung terdeteksi.
- **Engine Stockfish.** Kalau Stockfish tidak ada, program memakai Komodo dari NautilusChess.

## Kebutuhan

| Kebutuhan | Keterangan |
|---|---|
| macOS | Overlay memakai AppKit (lihat [Dukungan platform](#dukungan-platform)) |
| Python 3.15 | Dari [python.org](https://www.python.org/downloads/macos/). Tkinter sudah termasuk |
| Stockfish | `brew install stockfish` |
| Izin Screen Recording | System Settings › Privacy & Security › Screen Recording, untuk aplikasi yang menjalankan program (misalnya Terminal) |
| NautilusChess (opsional) | Di folder sebelah (`../NautilusChess`), untuk profil warna situs dan engine Komodo cadangan |

Dependensi Python ada di `requirements.txt`: `chess`, `Pillow`, dan `pyobjc-framework-Cocoa`.

## Instalasi

```bash
cd ChessBoardOverlay
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
brew install stockfish
```

## Menjalankan

```bash
cd ChessBoardOverlay
source venv/bin/activate
python main.py
```

## Cara pakai

1. **Buka papan catur** dan pastikan papannya terlihat penuh, tidak tertutup jendela lain.
2. **Atur kotak.** Di **Mode atur kotak**, geser kotak biru dengan klik-tahan di dalamnya. Ubah ukurannya dengan menarik kotak kecil di pojok kanan bawah, atau pakai tombol **Perbesar/Perkecil**. Garis 8×8 harus pas dengan petak papan.
3. Pastikan **Cara baca** = **Semua papan (perubahan petak)**, lalu tekan **Mulai**. Kotak otomatis terkunci dan tembus klik.
4. **Mulai game dari posisi awal.** Begitu posisi awal terlihat, status menampilkan *"bidak direkam otomatis"*. Setelah itu semua langkah ikut terbaca.
5. **Ikuti saran.** Panah **oranye** adalah saran untuk giliranmu. Panah **abu-abu** adalah perkiraan balasan lawan.

Untuk game yang sudah berjalan, kalau bidak sudah pernah terekam, tekan **Baca posisi → Putih jalan** atau **Hitam jalan** sesuai giliran.

### Tombol di panel

| Tombol | Fungsi |
|---|---|
| **Mulai / Jeda** | Mulai atau berhenti membaca papan |
| **Game baru** | Reset ke posisi awal, sekaligus merekam ulang bidak kalau papan sedang di posisi awal |
| **Mundur** | Batalkan 1 langkah yang salah terbaca |
| **Baca posisi: Putih jalan / Hitam jalan** | Baca posisi di layar saat ini. Kalau giliran salah dipilih, giliran dikoreksi otomatis di langkah berikutnya |
| **Mode atur kotak / Terkunci** | Pindah antara mengatur kotak dan mode tembus klik |
| **Perkecil / Perbesar** | Ubah ukuran kotak per 20 px |
| **Cara baca** | Pilih cara membaca papan (lihat di bawah) |
| **Bawah papan: Putih / Hitam** | Warna yang ada di bawah layar. Biasanya terisi otomatis |
| **Waktu pikir** | Lama engine berpikir per posisi (0,3–5 detik) |

Kotak putus-putus magenta di papan menunjukkan petak yang sedang terbaca berubah. Ini berguna untuk mengecek apakah kotak sudah pas.

### Cara baca

- **Semua papan (perubahan petak)**, dianjurkan: membandingkan isi petak antar screenshot dan mengenali bidak. Jalan di papan, tema, dan situs apa pun.
- **chess.com, lichess, chess24, chessfriends**: cara asli NautilusChess, yaitu mencari warna highlight langkah terakhir dari `../NautilusChess/images/<situs>/pixel.txt`. Hanya jalan di tema bawaan situs tersebut.

## Cara kerja

```
screenshot area kotak (±3×/detik, overlay dikecualikan)
        │
        ▼
deteksi perubahan petak ──► tunggu papan diam 2 frame
        │
        ▼
kenali bidak di tiap petak
  • terisi atau kosong : warna seragam vs ada bidak
  • warna bidak        : kecerahan bidak
  • jenis bidak        : bentuk garis tepi (edge map)
        │
        ▼
cari 1–2 langkah legal yang menghasilkan posisi di layar
  • cocok             → catat langkah
  • posisi awal       → reset game
  • tidak cocok terus → sinkron ulang dari layar
        │
        ▼
Stockfish menganalisis ──► panah + panel saran
```

Rekaman bidak dibuat dari posisi awal, karena di posisi itu letak setiap bidak sudah pasti. Rekaman disimpan di `piece_templates.json`.

## Struktur proyek

| File | Isi |
|---|---|
| `main.py` | Titik masuk program |
| `overlay_app.py` | Panel Tkinter dan penghubung semua bagian |
| `native_board_overlay.py` | Kotak overlay macOS (AppKit): transparan, tembus klik, tidak ikut ter-capture |
| `advisor_worker.py` | Thread latar: capture, baca langkah, sinkron, dan analisis engine |
| `board_reader.py` | Capture layar, pemetaan petak, dan deteksi highlight (cara Nautilus) |
| `square_change_detector.py` | Deteksi perubahan petak dan petak terisi |
| `piece_recognizer.py` | Rekam dan kenali bidak |
| `game_tracker.py` | Posisi game dan pencarian langkah legal yang cocok |
| `engine_advisor.py` | Menjalankan Stockfish atau Komodo dan memformat saran |
| `site_profiles.py` | Membaca profil warna situs dari NautilusChess |
| `settings_store.py` | Menyimpan pengaturan ke `settings.json` |
| `project_paths.py` | Lokasi folder proyek dan NautilusChess |
| `LICENSE` | Lisensi MIT |

`settings.json` dan `piece_templates.json` dibuat otomatis dan tidak ikut di-commit.

## Pengaturan

`settings.json` tersimpan otomatis setiap ada perubahan:

| Kunci | Arti |
|---|---|
| `x`, `y`, `board_size` | Posisi dan ukuran kotak (point layar, kiri atas) |
| `site_name` | Cara baca yang dipilih |
| `white_at_bottom` | `true` kalau Putih di bawah |
| `think_seconds` | Waktu pikir engine |
| `color_tolerance` | Toleransi warna untuk cara baca highlight per situs |

Untuk merekam ulang bidak dari awal, hapus `piece_templates.json`, lalu buka papan di posisi awal.

## Mengatasi masalah

| Gejala | Penyebab dan solusi |
|---|---|
| Tidak ada langkah yang terbaca sama sekali | Izin Screen Recording belum diberikan, atau **Cara baca** masih per situs. Ganti ke **Semua papan** |
| Status *"belum ada highlight langkah"* | Kamu sedang memakai cara baca per situs. Ganti ke **Semua papan** |
| Status *"Langkah tidak cocok … Bidak belum terekam"* | Mulai game baru di papan supaya bidak terekam otomatis |
| Langkah salah atau tidak terbaca | Ada jendela lain yang menutupi papan, atau grid 8×8 tidak pas dengan petak |
| Overlay tertutup jendela lain | Jalankan ulang program. Overlay berada di level jendela status macOS |
| Panah tidak terlihat di screenshot | Normal. Overlay sengaja dikecualikan dari capture layar |
| Ganti tema papan atau set bidak | Mulai game baru supaya bidak direkam ulang, atau tekan **Game baru** di posisi awal |

## Batasan

- Hak rokade dan en passant tidak terlihat di gambar. Saat posisi dibaca dari layar, hak rokade ditebak dari letak raja dan benteng.
- Program hanya membaca apa yang terlihat. Papan yang tertutup sebagian, sedang dianimasikan, atau di-zoom tidak rata bisa salah terbaca.
- Tanpa rekaman bidak, program hanya bisa mengikuti game yang dimulai dari posisi awal.

## Dukungan platform

| Platform | Status |
|---|---|
| macOS | Didukung dan sudah diuji |
| Windows | Belum. Rencana: overlay Tk `-transparentcolor`, tembus klik lewat `WS_EX_TRANSPARENT`, dikecualikan dari capture dengan `WDA_EXCLUDEFROMCAPTURE` |
| Linux (X11) | Belum. Rencana: dukungan terbatas, butuh compositor untuk transparansi |
| Linux (Wayland) | Belum ada rencana. Capture layar dan overlay dibatasi oleh sistem |

Rencana build: PyInstaller per OS, dijalankan lewat GitHub Actions (matrix macOS, Windows, dan Linux), dengan Stockfish disertakan per platform.

## Penggunaan yang adil

Pakai untuk melawan komputer, di papan analisis, atau untuk belajar. Memakainya di game melawan manusia di Chess.com atau Lichess melanggar aturan fair play, dan akun bisa diblokir.

## Penulis

**Mr Hafid**: [mrhafid.com](https://mrhafid.com)

## Lisensi

Dirilis dengan [lisensi MIT](LICENSE). Copyright (c) 2026 Mr Hafid.

Stockfish dan Komodo adalah engine terpisah dengan lisensinya masing-masing dan tidak termasuk dalam proyek ini. Stockfish berlisensi GPLv3.
