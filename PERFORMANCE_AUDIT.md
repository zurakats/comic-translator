# Rekap Audit Performa, Implementasi Optimasi, & Roadmap Tersisa

Dokumen ini merangkum seluruh **temuan masalah**, **perbaikan yang telah diimplementasikan**, **data hasil benchmark nyata**, **eksperimen yang diuji**, serta **opsi perbaikan yang tersisa** pada aplikasi **Comic & Manga Translator v2** berdasarkan kondisi *source code* terbaru ([backend/app.py](backend/app.py), [backend/image_processor.py](backend/image_processor.py), dan [backend/tests/](backend/tests)).

---

## 1. Ringkasan Eksekutif & Rekap Hasil Pengujian Nyata

### 1.1. Progres Waktu Eksekusi pada 3 Sampel Komik (`jp -> id`)

| Tahap / Versi | Kimetsu no Yaiba (4 gbr, 34 bubble) | Tsuiho Yuusha (5 gbr) | Yani Neko (6 gbr) | Total 3 Komik (*Warm*) | Penghematan vs `main` |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **1. Baseline (`main`)** | `34s` *(cold)* | `36s` | `53s` | **`123s`** | — |
| **2. `P1.1 + P1.2` *(lazy YOLO)*** | `43s` *(cold)* / `30s` *(warm)* | `22s` | `47s` | **`99s`** | `-24s (-20%)` |
| **3. `+ P1.3 + P1.4`** | `36s` *(cold)* / `33s` *(warm)* | `24s` | `51s` | **`108s`** | `-15s (-12%)` |
| **4. `+ Startup Warmup & Timing Log`** | `33s` *(cold)* / `30s` *(warm)* | `23s` | `48s` | **`101s`** | `-22s (-18%)` |
| **5. `+ P3-A.1 & P3-A.2` *(Cache Font & Suku Kata)*** | `31s` *(cold)* / `28s` *(warm)* | `22s` | `44s` | **`94s`** | `-29s (-24%)` |
| **6. `+ Opsi 1a` *(Fast-Reject & Early-Exit Render)*** | `23s` *(cold)* / **`21s`** (`21.33s` *warm*) | **`16s`** | **`34s`** | **`71s`** | **`-52s (-42%)`** |
| **7. `+ Opsi 1b` *(Binary Search Render)* + `Opsi OCR-A` *(Cross-Page Batched Manga-OCR)*** | *(`render` ~`0.7s`, `ocr_infer` ~`10.1s` $\rightarrow$ estimasi total *warm* **~15–16s**)* | *(estimasi **~11–12s**)* | *(estimasi **~24–26s**)* | *(estimasi **~50–54s**)* | **`~ -69s s/d -73s (~56–59% lebih cepat)`** |

---

### 1.2. Evolusi Breakdown Waktu per Komponen (Sampel Kimetsu no Yaiba — 4 Gambar, 34 Bubble, *Warm*)

| Komponen Pipeline | Tahap #4 (Sebelum Optimasi Render & Batch OCR) | Tahap #5 (+ P3-A.1/A.2) | Tahap #6 (+ Opsi 1a) | Tahap #7 (+ Opsi 1b & Opsi OCR-A) | Perubahan |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **`ocr_load`** (`selectOCR`) | `0.00s` *(cold: 2.65s)* | `0.00s` | `0.00s` | **`0.00s`** | Turun dari ~3–15s/req menjadi **0s** saat *warm* (P1.1) |
| **`read` + `yolo` + `save`** | `0.45s` | `0.42s` | `0.43s` | **`~0.41s`** | Sangat ringan (~1–2% total waktu) |
| **`render`** (`render_bubbles`) | `10.92s` | `9.35s` | `1.93s` | **`~0.71s`** | **~15x lebih cepat** (`10.92s` $\rightarrow$ `~0.71s`, hemat ~10.2s) |
| **`ocr_infer`** (`MangaOcr`) | `15.37s` | `14.62s` | `15.03s` | **`10.09s`** | **~1.5x lebih cepat** (`~15.0s` $\rightarrow$ `10.09s`, hemat ~5.0s, akurasi `34/34` identik) |
| **`gemini`** (Batch 34 teks) | `4.21s` | `4.35s` | `3.90s` | **`~3.90s`** | Menunggu tahap **P2.1–P2.3** |

---

## 2. Matriks Status Seluruh Temuan & Perbaikan

| ID | Kategori | Ringkasan Masalah / Perbaikan | Status | Lokasi Kode & Test |
| :--- | :---: | :--- | :---: | :--- |
| **P1.1** | 🔴 Prioritas 1 | Cache model OCR (`MangaOcr` & `EasyOCR`) lintas request dengan *thread-safe LRU* (`MAX_OCR_CACHE = 2`) | ✅ **Selesai** | `image_processor.py:100-118`, `test_ocr_cache.py` |
| **P1.2** | 🔴 Prioritas 1 | Matikan `force_reload=True`, gunakan cache PyTorch Hub lokal (`source='local'`), *lazy loader* `get_yolo_model()`, *warmup* saat startup, & `use_reloader=False` | ✅ **Selesai** | `image_processor.py:26-69`, `app.py:199-203`, `test_yolo_loader.py` |
| **P1.3** | 🔴 Prioritas 1 | Konversi BGR $\rightarrow$ RGB *in-place*, *zero-copy NumPy slicing* untuk EasyOCR, & tunda pembuatan `ImageDraw.Draw` ke Fase 3 | ✅ **Selesai** | `image_processor.py:453-519, 576-583`, `test_bubble_extraction.py` |
| **P1.4** | 🔴 Prioritas 1 | Inferensi YOLOv5 di dalam `torch.inference_mode()` & akses tensor `results.xyxy[0][:, :4].tolist()` tanpa `pandas.DataFrame.iterrows()` | ✅ **Selesai** | `image_processor.py:417-419, 477-479`, `test_bubble_extraction.py` |
| **Obs** | 🔵 Observabilitas | Instrumentasi `[Timing]` per gambar dan per fase (`ocr_load`, `read`, `yolo`, `ocr_infer`, `gemini`, `gtrans`, `render`, `save`, `total`) | ✅ **Selesai** | `app.py:56-173`, `image_processor.py:406-519` |
| **P3-A.1** | 🟢 Render (0% Ubah Visual) | Cache `ImageFont.truetype` (`get_font`, `@lru_cache(256)`) dan pemenggalan suku kata `pyphen` (`_split_syllables`, `@lru_cache(2048)`) | ✅ **Selesai** | `image_processor.py:251-273`, `test_render_bubbles.py` |
| **P3-A.2** | 🟢 Render (0% Ubah Visual) | Hapus kalkulasi ulang pasca-loop (`font_size * 1.0`) & gunakan kembali `line_widths` saat `draw.text` tanpa `textbbox` ulang | ✅ **Selesai** | `image_processor.py:521-533, 637-669`, `test_render_bubbles.py` |
| **Opsi 1a** | 🟢 Render (0% Ubah Visual) | *Fast-reject* kata tak-terpenggal (`len <= 5`) terhadap `avail_width`, cek `line_height > avail_height`, & *early-exit* `max_lines` di `wrap_text` / `break_word` | ✅ **Selesai** | `image_processor.py:275-374, 535-574`, `test_render_bubbles.py` |
| **Opsi 1b (P3-A.3)** | 🟢 Render (*Binary Search*) | Ganti pencarian linear `110 -> 12` dengan *binary search* `lo=12, hi=110` ($\le 7$ iterasi per bubble) | ✅ **Selesai** | `image_processor.py:615-636`, `test_render_bubbles.py` |
| **Opsi OCR-A (P2.5)** | 🔴 Bottleneck #1 (`ocr_infer`) | Pisahkan deteksi YOLOv5 lintas halaman (`detect_bubbles`) & jalankan *cross-page area-sorted batched* `MangaOcr` (`batch_size=16`, `num_beams=4` FP32) | ✅ **Selesai** | `image_processor.py:376-466`, `app.py:71-118`, `test_manga_ocr_batch.py` |
| **Text-1** | 🟣 Kualitas Visual/Teks | Cegah penambahan tanda hubung `"-"` saat memecah deretan titik-titik / tanda baca non-alfanumerik di `break_word` (`"......"` $\rightarrow$ `"..."` / `"..."`) | ✅ **Selesai** | `image_processor.py:275-321`, `test_text_cleaning_and_hyphenation.py` |
| **Text-2** | 🟣 Kualitas Translasi/Teks | Hapus simbol strip/tilde (`―`, `—`, `–`, `─`, `━`, `‒`, `−`, `~`, `～`, `〜`, `--`, `ーー`, dan `ー` non-Katakana) di `clean_ocr_text` & `render_bubbles` sambil menjaga `ー` Katakana & `-` kata ulang | ✅ **Selesai** | `image_processor.py:120-134, 586-595`, `test_text_cleaning_and_hyphenation.py` |
| **P2.1** | 🟡 Prioritas 2 | Deduplikasi teks bubble identik lintas halaman & *skip* bubble berisi tanda baca murni sebelum panggil API translasi | ⏳ **Tersisa (Ditunda)** | `image_processor.py:158, 238-245` |
| **P2.2** | 🟡 Prioritas 2 | Hentikan seluruh loop chunk Gemini pada error fatal (`429 PerDay`, `401/403` API key invalid) & gunakan *structured output* (`responseSchema`) | ⏳ **Tersisa (Ditunda)** | `image_processor.py:165-221` |
| **P2.3** | 🟡 Prioritas 2 | Tambahkan `timeout` HTTP pada `urlopen` Gemini serta *error isolation* (`try/except` & batas konkurensi) pada `batch_google_translate` | ⏳ **Tersisa (Ditunda)** | `image_processor.py:190, 224-249` |
| **P2.4** | 🟡 Prioritas 2 | Optimasi pemakaian RAM `image_contexts` untuk batch puluhan halaman resolusi tinggi | ⏳ **Tersisa (Opsional)** | `app.py:62-151` |

---

## 3. Rincian Perbaikan yang Telah Diimplementasikan

### 3.1. Fase Startup & Model Lifecycle (`P1.1` & `P1.2`)
1. **Thread-Safe LRU Cache untuk Model OCR (`selectOCR`)**:
   - Menyimpan maksimal `MAX_OCR_CACHE = 2` pembaca OCR di memori (`_ocr_cache = OrderedDict()`, dikunci dengan `_ocr_lock = threading.Lock()`).
   - Menghilangkan penalti ~3–15 detik pemuatan ulang bobot `MangaOcr` / `EasyOCR` dari disk pada setiap request.
2. **Offline-First Lazy YOLOv5 Loader & Startup Warmup (`get_yolo_model`)**:
   - Memeriksa direktori cache lokal PyTorch Hub (`ultralytics_yolov5_master` / `ultralytics_yolov5_main`). Bila `hubconf.py` tersedia, model dimuat secara lokal (`source='local'`) tanpa koneksi jaringan ke GitHub; bila belum ada, menggunakan `source='github', force_reload=False`.
   - `app.py` memanggil `get_yolo_model()` saat startup di dalam blok `if __name__ == '__main__':` dan menonaktifkan Werkzeug auto-reloader (`use_reloader=False`), sehingga tidak terjadi *double-loading* model di RAM/VRAM dan request pertama tidak mengalami penalti *cold load* YOLOv5 (~8 detik).

### 3.2. Optimasi Fase 1: Ekstraksi Bubble & Cross-Page Batched `MangaOcr` (`P1.3`, `P1.4`, `Opsi OCR-A`)
1. **In-Place Color Conversion & Direct Tensor Unpacking**:
   - Menggunakan `cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB, dst=img_cv)` tanpa alokasi buffer gambar penuh kedua.
   - Menjalankan YOLOv5 di dalam `with torch.inference_mode():` dan membaca koordinat langsung dari tensor `results.xyxy[0][:, :4].tolist()` tanpa membuat `pandas.DataFrame` maupun `iterrows()`.
   - Untuk EasyOCR (`index != 0`), memotong area bubble langsung dengan *zero-copy NumPy view* `img_rgb[y1:y2, x1:x2]`.
2. **Investigasi & Optimasi Bottleneck #1 (`ocr_infer` — `Opsi OCR-A`)**:
   - Dari profiling `MangaOcr` pada 34 bubble Kimetsu no Yaiba di CPU (6 *physical cores* / 12 *logical threads*, `torch 2.14.1+cpu`), ditemukan bahwa ViT Encoder memakan ~39.5% waktu dan BERT Decoder memakan ~60.2% waktu (karena `generation_config` bawaan memakai `num_beams=4`).
   - Fase 1 untuk bahasa Jepang (`index == 0`) kini dipisahkan menjadi:
     - **Fase 1A (`detect_bubbles`)**: Menjalankan deteksi YOLOv5 di seluruh halaman (~0.35s untuk 4 halaman) dan mengumpulkan seluruh PIL crop bubble yang valid.
     - **Fase 1B (`batch_manga_ocr`)**: Mengurutkan seluruh crop lintas halaman berdasarkan luas piksel (`w * h`) agar bubble pendek dikelompokkan bersama bubble pendek, lalu menjalankan inferensi batch (`MANGA_OCR_BATCH_SIZE = 16`, `num_beams=4`, FP32) di dalam `torch.inference_mode()`.
   - **Hasil**: Waktu `ocr_infer` pada 34 bubble Kimetsu no Yaiba turun dari **`~15.0–16.1s` $\rightarrow$ `10.09s`** (~1.5x lebih cepat, hemat ~5 detik) dengan **akurasi karakter 100% identik (`34/34`)**.

> **Catatan Eksperimen `MangaOcr` yang Diuji namun Ditolak**:
> - **Kuantisasi Dinamis `INT8` (`torch.ao.quantization.quantize_dynamic`)**: Hanya menghemat ~1 detik dibanding FP32 batch, namun menyebabkan kesalahan baca pada Kanji kompleks (contoh nyata pada Kimetsu no Yaiba: `禰豆子` / *Nezuko* terbaca salah menjadi `禍豆子`) serta menggunakan API PyTorch yang sudah *deprecated*.
> - **`BF16` Autocast di CPU**: Memperlambat eksekusi hingga 3x lipat (`48.06s`) karena CPU tidak memiliki akselerator hardware BF16 sehingga diemulasikan secara software.
> - **Multi-threading (`ThreadPoolExecutor`) / `torch.set_num_threads(12)`**: Lebih lambat (`16.4s–22.8s`) akibat kontensi thread OpenMP pada 6 *physical cores*.

### 3.3. Optimasi Fase 3: Binary-Search Typesetting & Rendering (`P3-A.1`, `P3-A.2`, `Opsi 1a`, `Opsi 1b`)
Profiling dengan `cProfile` mengungkap bahwa `render_bubbles` awalnya memakan **`10.92s` (35.3% total waktu)** hanya untuk 34 bubble karena ribuan pembacaan file `.ttf` dari disk dan **47.000+ panggilan `Font.getsize()`** pada bubble vertikal manga. Perbaikan yang diterapkan:
1. **LRU Cache Font & Suku Kata (`P3-A.1`)**: `get_font(font_path, font_size)` (`@lru_cache(256)`) dan `_split_syllables(word, target_lang)` (`@lru_cache(2048)`).
2. **Penghapusan Kalkulasi Ulang Pasca-Loop (`P3-A.2`)**: Menyimpan tuple `(font, lines, line_widths, line_height, total_height)` yang sudah cocok dan menggunakan ulang `line_widths` saat menggambar teks tanpa memanggil `draw.textbbox` lagi.
3. **Fast-Reject & Early-Exit Wrapping (`Opsi 1a`)**:
   - Menolak ukuran font secara instan sebelum memanggil `wrap_text` apabila `line_height > avail_height` atau salah satu dari 3 kata tak-terpenggal terpanjang (`len(word) <= 5`) sudah melebihi `avail_width`.
   - Menghentikan `wrap_text` dan `break_word` lebih awal (`return None`) begitu jumlah baris melampaui kapasitas vertikal `avail_height // line_height` atau satu suku kata tunggal melebihi `avail_width`.
4. **Binary Search Ukuran Font `[12..110]` (`Opsi 1b / P3-A.3`)**:
   - Mengganti pencarian linear `110 -> 12` (~85 iterasi per bubble vertikal) menjadi *binary search* `lo, hi = 12, 110` (maksimal **7 iterasi** per bubble), memangkas waktu `render` dari **`10.92s` $\rightarrow$ `1.93s` (Opsi 1a) $\rightarrow$ `~0.71s` (Opsi 1b)** (~15x lebih cepat) dengan `0/100` perbedaan piksel pada uji simulasi 100 bubble manga.

### 3.4. Perbaikan Kualitas Teks & Typesetting (`Text-1` & `Text-2`)
1. **Penghapusan Hyphen pada Titik-Titik (`break_word`)**:
   - Tanda hubung `"-"` kini hanya ditambahkan saat memecah kata apabila karakter tepat sebelum **dan** sesudah titik potong sama-sama alfanumerik (`isalnum()`).
   - Deretan titik-titik panjang seperti `"......"` atau `"......?!"` yang terpecah ke baris berikutnya kini dirender rapi sebagai `"..."` / `"..."` (tanpa `"...-"`), sementara pemenggalan kata biasa (`"pertanggungjawaban"`, `"extraordinary"`) tetap memakai `"-"`.
2. **Pembersihan Simbol Strip & Tilde Sebelum dan Sesudah Translasi (`clean_ocr_text` & `render_bubbles`)**:
   - Menghapus simbol strip dekoratif dan tilde (`―`, `—`, `–`, `─`, `━`, `‒`, `−`, `~`, `～`, `〜`, `--`, `ーー`, serta `ー` yang tidak didahului karakter Katakana `\u30A1-\u30F6`) pada `clean_ocr_text()` sebelum teks dikirim ke Gemini atau Google Translate (contoh: `"――だけど僕にはわからない。"` $\rightarrow$ `"だけど僕にはわからない。"`).
   - Tetap mempertahankan tanda vokal panjang Katakana tunggal yang valid (`"ヒーロー"`, `"ゲーム"`, `"ページ"`) serta tanda hubung ASCII tunggal `-` pada kata ulang bahasa Indonesia/Inggris (`"tiba-tiba"`, `"self-control"`).
   - Menambahkan pembersihan serupa pada normalisasi pasca-terjemahan di `render_bubbles()` jika mesin penerjemah masih menyisipkan `—` atau `~`.

---

## 4. Cakupan Pengujian Otomatis (`backend/tests/`)

Seluruh perbaikan di atas dilengkapi dengan **36 unit & integration test** di dalam 6 modul test (semuanya lolos dalam ~5.6 detik):
- [backend/tests/test_ocr_cache.py](backend/tests/test_ocr_cache.py) (6 test)
- [backend/tests/test_yolo_loader.py](backend/tests/test_yolo_loader.py) (6 test)
- [backend/tests/test_bubble_extraction.py](backend/tests/test_bubble_extraction.py) (7 test)
- [backend/tests/test_manga_ocr_batch.py](backend/tests/test_manga_ocr_batch.py) (4 test)
- [backend/tests/test_render_bubbles.py](backend/tests/test_render_bubbles.py) (7 test)
- [backend/tests/test_text_cleaning_and_hyphenation.py](backend/tests/test_text_cleaning_and_hyphenation.py) (5 test)

---

## 5. Opsi Perbaikan yang Tersisa (Roadmap Tahap Berikutnya)

### 5.1. Prioritas 2: Efisiensi & Reliabilitas Translasi Fase 2 (`P2.1 – P2.3`)
1. **P2.1 — Deduplikasi Teks & Filter Bubble Tanda Baca Murni**:
   - Bubble yang hanya berisi tanda baca/simbol murni (misal `"..."`, `"!?"`, `"！？"`) sebaiknya langsung disalin ke hasil terjemahan tanpa dikirim ke API Gemini maupun Google Translate.
   - Deduplikasi teks sumber yang identik lintas halaman sebelum dikirim ke API translasi, lalu petakan kembali hasil terjemahannya ke semua `bubble_id` terkait untuk menghemat token, waktu tunggu LLM, dan kuota *rate-limit*.
2. **P2.2 — Penghentian Loop Chunk pada Error Fatal Gemini & *Structured Output***:
   - Pada `batch_gemini_translate()` ([backend/image_processor.py](backend/image_processor.py#L188-L220)), saat terjadi error fatal global seperti `429 PerDay` (kuota harian habis) atau `401`/`403`/`API_KEY_INVALID`, hentikan seluruh loop chunk (`break` dari outer loop) agar chunk berikutnya langsung dialihkan ke fallback Google Translate tanpa mengulang request yang pasti gagal.
   - Tambahkan `responseMimeType: "application/json"` dan `responseSchema` pada `generationConfig` Gemini agar format keluaran JSON selalu terjamin valid.
3. **P2.3 — Timeout HTTP Gemini & Isolasi Error `batch_google_translate`**:
   - Tambahkan parameter `timeout=60` pada `urllib.request.urlopen(req, timeout=60)` di `batch_gemini_translate()` agar thread server tidak menggantung tanpa batas saat jaringan bermasalah.
   - Bungkus `asyncio.run(_async_google_translate(...))` di `batch_google_translate()` dengan `try/except` serta isolasi error per item (`asyncio.gather(..., return_exceptions=True)` dengan batas konkurensi `Semaphore`) agar kegagalan jaringan pada satu bubble di Google Translate tidak menggagalkan seluruh request dengan `HTTP 500`.

### 5.2. Opsi Lanjutan `ocr_infer` & Manajemen Memori (`P2.4` & Eksplorasi OCR)
1. **Opsi OCR-B (`num_beams=2`) pada `batch_manga_ocr` *(Opsional)***:
   - Jika suatu saat diperlukan percepatan OCR tambahan di CPU tanpa menambah dependensi, menurunkan `num_beams` dari `4` ke `2` memangkas `ocr_infer` dari `~10.5s` ke **`~7.9–8.5s`** (~2x lebih cepat dari baseline awal) dengan Kanji tetap akurat dan hanya selisih sangat kecil pada hiragana teriakan.
2. **Akselerasi Hardware / Runtime (`ONNX Runtime` atau `CUDA`) *(Opsional Jangka Panjang)***:
   - Mengekspor model encoder-decoder `MangaOcr` ke `onnxruntime` (CPU) atau menjalankan PyTorch dengan GPU NVIDIA (`CUDA`) dapat memangkas `ocr_infer` hingga `< 2–4 detik` tanpa kompromi akurasi FP32.
3. **P2.4 — Penghematan RAM pada Batch Halaman Besar**:
   - Jika pengguna mengunggah puluhan halaman beresolusi tinggi sekaligus (1 chapter penuh), `img_pil` di `image_contexts` dapat dibuka ulang dari `filepath` saat Fase 3 alih-alih ditahan seluruhnya di RAM sepanjang Fase 1 dan Fase 2.

### 5.3. Pembersihan Kode Minor & Portabilitas
- Menambahkan guard `if os.name == 'nt':` sebelum `pathlib.PosixPath = pathlib.WindowsPath` di [backend/image_processor.py](backend/image_processor.py#L24) agar langsung kompatibel di Linux/macOS.
- Menghapus fungsi warisan yang tidak lagi dipanggil (`process_language()` di [backend/image_processor.py](backend/image_processor.py#L71-L85), parameter `translate_code` pada `extract_bubbles()`, serta dependensi `python-dotenv` dan `pandas` di [backend/requirements.txt](backend/requirements.txt)).
- Menambahkan cleanup `useEffect` untuk `timerRef` (`clearInterval`) saat komponen unmount di [frontend/src/pages/Home.jsx](frontend/src/pages/Home.jsx#L14-L32).
