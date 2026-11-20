# Audit Performa & Identifikasi Masalah Proses Penerjemahan

Dokumen ini merangkum seluruh temuan masalah performa, efisiensi, redundansi, dan reliabilitas pada aplikasi **Comic & Manga Translator v2** berdasarkan verifikasi langsung terhadap *source code* aktual (sebagai sumber kebenaran), serta perbandingannya dengan [README.md](README.md) dan [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

> **Status Dokumen**: Fase identifikasi masalah & perancangan (belum masuk tahap implementasi/coding).

---

## Prinsip & Kriteria Prioritas

1. **Prioritas Tertinggi (P1 — Kritis / Redundansi Tanpa Dampak Positif)**  
   Implementasi yang keliru, berulang, atau boros komputasi/memori **tanpa memberikan nilai tambah apa pun** terhadap akurasi OCR, kualitas terjemahan, maupun hasil visual.
2. **Prioritas Menengah (P2 — Efisiensi API, Memori, & Reliabilitas)**  
   Proses di fase translasi dan manajemen data/memori yang memperbesar latensi jaringan, pemakaian token/kuota API, atau berisiko menggagalkan seluruh request yang sudah melewati proses OCR.
3. **Prioritas Terendah / *Least Priority* (P3 — Komputasi Visual & *Typesetting*)**  
   Proses di fase rendering (`render_bubbles`) yang berhubungan langsung dengan tampilan visual hasil terjemahan komik. Sub-bagian **P3-A** berisi optimasi komputasi murni dengan hasil visual **100% identik**, sedangkan **P3-B** berisi algoritma visual yang **dipertahankan** agar kualitas tata letak komik tetap bagus.

---

## Ringkasan Matriks Temuan

| ID | Prioritas | Lokasi Utama | Ringkasan Masalah | Dampak Utama | Efek ke Visual |
| :--- | :---: | :--- | :--- | :--- | :---: |
| **P1.1** | 🔴 Tertinggi | `backend/app.py`, `backend/image_processor.py` | Instansiasi ulang model OCR (`MangaOcr` / `EasyOCR`) pada **setiap request** | Tambahan waktu ~3–15+ detik/request & lonjakan RAM/VRAM | Tidak ada |
| **P1.2** | 🔴 Tertinggi | `backend/image_processor.py`, `backend/app.py` | YOLOv5 `force_reload=True` dari GitHub + *double-load* akibat `debug=True` reloader | Startup lambat, butuh akses GitHub tiap start, **2x RAM/VRAM** model YOLO | Tidak ada |
| **P1.3** | 🔴 Tertinggi | `backend/image_processor.py` | Konversi berantai OpenCV BGR $\rightarrow$ RGB $\rightarrow$ PIL $\rightarrow$ Crop PIL $\rightarrow$ NumPy (untuk EasyOCR) & pembuatan `ImageDraw` terlalu dini | Alokasi & penyalinan piksel berulang pada setiap gambar & bubble | Tidak ada |
| **P1.4** | 🔴 Tertinggi | `backend/image_processor.py` | Output YOLOv5 dikonversi ke `pandas.DataFrame` + `iterrows()`, tanpa `torch.inference_mode()` | Overhead CPU & konversi objek Python per gambar | Tidak ada |
| **P2.1** | 🟡 Menengah | `backend/image_processor.py` | Teks bubble duplikat & teks tanda baca murni tetap dikirim ke Gemini / Google Translate | Boros token, latensi API lebih lama, kuota cepat habis, batch membengkak | Tidak ada |
| **P2.2** | 🟡 Menengah | `backend/image_processor.py` | `break` pada error fatal (`429 PerDay`, `401/403`, dll.) hanya keluar dari loop retry, bukan loop chunk Gemini | Mengulangi request gagal ke Gemini pada chunk-chunk berikutnya | Tidak ada |
| **P2.3** | 🟡 Menengah | `backend/image_processor.py` | Request Gemini tanpa `timeout` & `batch_google_translate` tanpa `try/except` | Risiko server *hang* atau *crash* `HTTP 500` di akhir pipeline | Tidak ada |
| **P2.4** | 🟡 Menengah | `backend/app.py`, `backend/image_processor.py` | Menahan seluruh `img_pil` (uncompressed) & `draw` di RAM sepanjang Fase 1 & 2 | Konsumsi RAM membengkak saat unggah banyak halaman resolusi tinggi | Tidak ada |
| **P2.5** | 🟡 Menengah | `backend/app.py`, `backend/image_processor.py` | Inferensi YOLOv5 & OCR diproses satu per satu secara sekuensial tanpa batching | Throughput multi-halaman dan multi-bubble belum optimal | Tidak ada |
| **P3-A.1** | 🟢 Rendah | `backend/image_processor.py` | `ImageFont.truetype()` dibaca dari disk pada setiap iterasi `font_size` (hingga ~99x/bubble) | Disk I/O & parsing font berulang ribuan kali per sesi | Tidak ada |
| **P3-A.2** | 🟢 Rendah | `backend/image_processor.py` | Kalkulasi ulang identik setelah `while` loop (`font_size * 1.0`, `truetype`, `wrap_text`) | Membuang 1 iterasi penuh *wrapping* + *load font* per bubble | Tidak ada |
| **P3-A.3** | 🟢 Rendah | `backend/image_processor.py` | Pencarian linear `font_size` (`110` turun 1 per 1 ke `12`) + pengukuran `textbbox` berulang | Hingga 99 iterasi `wrap_text` per bubble | Sangat rendah *(lihat catatan P3-A.3)* |
| **P3-B** | 🟢 Terendah | `backend/image_processor.py` | Algoritma *typesetting* (`wrap_text`, `break_word`, `pyphen`, ekspansi `1.22x`, *inset* `1.5%`, *stroke*) | Menjaga keterbacaan & estetika teks dalam bubble | **Berpengaruh langsung (Dipertahankan)** |

---

## 🔴 Prioritas 1 (Tertinggi): Implementasi Salah / Redundan Tanpa Dampak Positif

### P1.1. Model OCR Di-load Ulang dari Disk di Setiap Request
- **Lokasi**:
  - [backend/app.py](backend/app.py#L45) — `ocr, index, translate_code = selectOCR(sourceLang)`
  - [backend/image_processor.py](backend/image_processor.py#L54-L60) — fungsi `selectOCR(sourceLang)`
- **Akar Masalah**:  
  Setiap kali endpoint `POST /process-image` dipanggil, `selectOCR()` selalu membuat objek baru `MangaOcr()` (untuk `jp`) atau `easyocr.Reader([easyocr_code])` (untuk `ko`, `ch_sim`, `ch_tra`, `en`). Tidak ada mekanisme *caching* lintas request.
- **Dampak**:  
  - Bobot model (*weights* PyTorch/Transformers/CRAFT) dimuat ulang dari disk ke RAM/VRAM pada **setiap klik tombol "Terjemahkan"**, meskipun bahasa sumbernya sama.
  - Menambah waktu proses sekitar **3–15+ detik per request** dan memicu *garbage collection* objek model berukuran ratusan MB secara berulang.
- **Arah Rancangan Perbaikan**:  
  Terapkan *in-memory cache* (pola *Lazy Singleton* per bahasa, misalnya dictionary `_OCR_CACHE[sourceLang]`) di `image_processor.py` agar model hanya diinisialisasi pada pemakaian pertama untuk bahasa tersebut dan langsung dipakai ulang pada request berikutnya.

### P1.2. YOLOv5 `force_reload=True` dari GitHub & *Double-Loading* oleh Flask Reloader
- **Lokasi**:
  - [backend/image_processor.py](backend/image_processor.py#L21-L23) — `torch.hub.load('ultralytics/yolov5', 'custom', path=model_path, source='github', force_reload=True)`
  - [backend/app.py](backend/app.py#L3) & [backend/app.py](backend/app.py#L126) — `import ...` di top-level dan `app.run(host="0.0.0.0", port=5000, debug=True)`
- **Akar Masalah**:  
  1. `force_reload=True` memaksa PyTorch Hub mengunduh ulang repositori `ultralytics/yolov5` dari GitHub setiap kali modul `image_processor` diimpor, mengabaikan cache lokal yang sudah ada.
  2. `debug=True` mengaktifkan Werkzeug *auto-reloader*, yang menjalankan proses *parent* (pemantau file) dan proses *child* (worker Flask). Karena model YOLOv5 dimuat di level modul (`top-level`), kedua proses tersebut masing-masing mengeksekusi `torch.hub.load(...)`.
- **Dampak**:  
  - Waktu startup server menjadi jauh lebih lambat dan gagal berjalan jika koneksi ke GitHub bermasalah saat startup.
  - Penggunaan RAM/VRAM untuk model YOLOv5 menjadi **2 kali lipat**, di mana satu salinan model menganggur di *parent process*.
- **Arah Rancangan Perbaikan**:  
  - Gunakan `force_reload=False` (atau manfaatkan cache lokal PyTorch Hub jika sudah ada).
  - Ubah pemuatan model YOLOv5 menjadi *lazy initialization* melalui fungsi `get_yolo_model()` agar proses pemantau reloader tidak ikut memuat model ke memori, atau jalankan server tanpa reloader (`use_reloader=False`).

### P1.3. Konversi & Penyalinan Memori Gambar Berulang di `extract_bubbles`
- **Lokasi**: [backend/image_processor.py](backend/image_processor.py#L250-L274) — fungsi `extract_bubbles()`
- **Akar Masalah**:  
  1. Gambar dibaca dari disk dengan `cv2.imread(image_path)` (format BGR), dikonversi ke RGB dengan `cv2.cvtColor(..., cv2.COLOR_BGR2RGB)` (salinan array baru), lalu dikonversi lagi ke objek `PIL.Image` dengan `Image.fromarray(img_rgb)` (salinan memori baru), dan langsung dibuatkan `draw = ImageDraw.Draw(img_pil)` padahal Fase 1 tidak menggambar apa pun.
  2. Di dalam *loop* setiap bubble (`baris 265–272`), kode selalu memanggil `cropped = img_pil.crop((x1, y1, x2, y2))`. Lalu ketika menggunakan EasyOCR (`index != 0`), `cropped` (objek PIL) dikonversi **kembali** menjadi array NumPy via `cropped_np = np.array(cropped)`, padahal array NumPy `img_rgb` sudah tersedia di baris 253.
- **Dampak**:  
  Terjadi alokasi memori dan penyalinan piksel berulang kali pada setiap halaman dan setiap *speech bubble*.
- **Arah Rancangan Perbaikan**:  
  - Untuk EasyOCR (`index != 0`), lakukan *array slicing* langsung pada `img_rgb`: `cropped_np = img_rgb[y1:y2, x1:x2]` (*zero-copy NumPy view*, tanpa lewat `img_pil.crop()` dan `np.array()`).
  - Pembuatan `img_pil.crop(...)` hanya dilakukan jika `index == 0` (`MangaOcr`).
  - Pindahkan pembuatan `ImageDraw.Draw(img_pil)` ke Fase 3 (`render_bubbles`).

### P1.4. Penggunaan `results.pandas().xyxy[0]` & `.iterrows()` serta Ketiadaan `torch.inference_mode()`
- **Lokasi**: [backend/image_processor.py](backend/image_processor.py#L257-L262)
- **Akar Masalah**:  
  Setelah `results = model(img_rgb)`, kode memanggil `results.pandas().xyxy[0]` untuk membungkus tensor koordinat menjadi `pandas.DataFrame`, lalu mengiterasinya menggunakan `detections.iterrows()` (yang membuat objek `pandas.Series` di setiap baris bubble). Selain itu, pemanggilan inferensi tidak dibungkus `with torch.inference_mode():`.
- **Dampak**:  
  Menambah *overhead* konversi objek Python/Pandas pada setiap gambar yang diproses.
- **Arah Rancangan Perbaikan**:  
  Gunakan `with torch.inference_mode():` saat inferensi dan ambil koordinat langsung dari tensor `results.xyxy[0].tolist()` (atau array NumPy `.cpu().numpy()`).

---

## 🟡 Prioritas 2 (Menengah): Efisiensi Proses Translasi, Memori, & Reliabilitas

### P2.1. Tidak Ada Deduplikasi Teks & Bubble Tanda Baca Murni Tetap Dikirim ke API Translasi
- **Lokasi**:
  - [backend/image_processor.py](backend/image_processor.py#L91) (`batch_gemini_translate`)
  - [backend/image_processor.py](backend/image_processor.py#L171-L178) (`batch_google_translate`)
- **Akar Masalah**:  
  1. Seluruh bubble dengan `cleaned_text.strip()` yang tidak kosong langsung dimasukkan ke antrean API dengan masing-masing `id`. Teks dialog atau seruan pendek yang muncul berulang lintas halaman (misal `"え？"`, `"はい"`, `"..."`, `"!!"`) dikirim berulang kali.
  2. Teks hasil OCR yang hanya berisi tanda baca atau simbol murni (misal `"..."`, `"!?"`, `"！？"`, `"──"`) lolos filter `.strip()` dan tetap dikirim ke Gemini API / Google Translate.
- **Dampak**:  
  - Memperbesar payload dan jumlah token *output* JSON yang harus dihasilkan Gemini (waktu respons LLM sangat bergantung pada panjang token output).
  - Mempercepat habisnya *rate limit* free-tier Gemini (5 RPM) dan berpotensi memecah jumlah chunk (`batch_size=40`) lebih banyak dari yang seharusnya.
- **Arah Rancangan Perbaikan**:  
  - Tambahkan filter karakter alfanumerik/huruf/CJK: jika bubble hanya berisi tanda baca/simbol, langsung salin `cleaned_text` sebagai hasil terjemahan tanpa mengirimnya ke API.
  - Lakukan deduplikasi berdasarkan `cleaned_text` unik sebelum mengirim batch ke Gemini atau Google Translate, lalu petakan kembali hasil terjemahan ke seluruh `bubble_id` yang memiliki teks sumber identik.

### P2.2. Bug Kontrol Loop Error pada `batch_gemini_translate` (Mengulang Chunk Setelah Error Fatal)
- **Lokasi**: [backend/image_processor.py](backend/image_processor.py#L98-L153)
- **Akar Masalah**:  
  Di dalam outer loop `for i in range(0, len(items), batch_size):`, terdapat inner loop `for attempt in range(max_retries + 1):`. Ketika terjadi error fatal yang berlaku global untuk seluruh sesi—seperti `429` dengan `'PerDay'` (kuota harian habis), `400`/`401`/`403` (API Key tidak valid), atau kegagalan retry setelah menunggu—pernyataan `break` hanya keluar dari **inner loop** (`attempt`), **bukan** keluar dari **outer loop** (`chunk`).
- **Dampak**:  
  Jika pengguna memproses komik dengan > 40 bubble (misal 120 bubble = 3 chunk), saat chunk ke-1 gagal karena API key invalid atau kuota harian habis, sistem tetap membuang waktu mengirim chunk ke-2 dan ke-3 ke Gemini yang sudah pasti gagal, sebelum akhirnya dilempar ke fallback `googletrans`.
- **Arah Rancangan Perbaikan**:  
  Untuk error bersifat global/fatal (`PerDay`, `400`, `401`, `403`, atau kegagalan koneksi permanen), hentikan seluruh loop chunk (`return translations`) agar bubble tersisa langsung ditangani oleh fallback Google Translate.

### P2.3. Ketiadaan `timeout` pada Request Gemini & Tidak Ada Penanganan Error di `batch_google_translate`
- **Lokasi**:
  - [backend/image_processor.py](backend/image_processor.py#L123) — `urllib.request.urlopen(req)` tanpa `timeout`
  - [backend/image_processor.py](backend/image_processor.py#L180) — `asyncio.run(_async_google_translate(...))` tanpa `try/except`
- **Akar Masalah**:  
  1. `urlopen(req)` dipanggil tanpa batas waktu (`timeout`), sehingga request bisa menggantung tanpa batas jika jaringan atau server upstream bermasalah.
  2. `batch_google_translate` memanggil `asyncio.run(...)` untuk seluruh item `pending` sekaligus tanpa membungkusnya dengan `try/except` (dan tanpa batas ukuran chunk/batch).
- **Dampak**:  
  Jika terjadi gangguan koneksi atau rate-limit dari endpoint Google Translate pada salah satu batch, seluruh proses `/process-image` langsung *crash* dengan `HTTP 500`, sehingga seluruh hasil komputasi berat Fase 1 (YOLO + OCR) dan Fase 2 (Gemini) terbuang percuma.
- **Arah Rancangan Perbaikan**:  
  - Tambahkan `timeout` yang wajar (misal `30–60` detik) pada `urllib.request.urlopen(req, timeout=...)`.
  - Pecah `pending` Google Translate ke ukuran chunk yang aman dan bungkus `try/except` agar kegagalan pada satu item/batch tidak menggugurkan seluruh halaman yang sudah diproses (bisa fallback ke teks asli atau penanda gagal lokal).

### P2.4. Penahanan Seluruh Objek Gambar (`img_pil` & `draw`) di RAM Selama Fase 1 & 2
- **Lokasi**: [backend/app.py](backend/app.py#L47-L80) & [backend/image_processor.py](backend/image_processor.py#L254-L255)
- **Akar Masalah**:  
  `app.py` menyimpan seluruh objek `img_pil` (*uncompressed* RGB bitmap di memori) dan `draw` untuk semua halaman dalam list `image_contexts` mulai dari awal Fase 1, bertahan selama Fase 1 (OCR semua halaman) dan Fase 2 (request jaringan + potensi `time.sleep` retry Gemini), baru digunakan di Fase 3.
- **Dampak**:  
  Jika pengguna mengunggah banyak halaman beresolusi tinggi sekaligus (misalnya 1 chapter berisi 30–50 halaman), penggunaan RAM melonjak sebanding dengan total piksel seluruh gambar yang disimpan bersamaan.
- **Arah Rancangan Perbaikan**:  
  Evaluasi penyimpanan `filepath` di `image_contexts` dan membuka ulang gambar saat Fase 3 (khususnya jika jumlah halaman melebihi ambang tertentu), sebagai *trade-off* kecil antara biaya decode ulang (~beberapa milidetik/gambar) vs penghematan RAM signifikan untuk batch besar.

### P2.5. Inferensi YOLOv5 & OCR Berjalan Sekuensial Satu per Satu
- **Lokasi**: [backend/app.py](backend/app.py#L53-L64) & [backend/image_processor.py](backend/image_processor.py#L257-L272)
- **Akar Masalah**:  
  - Setiap gambar yang diunggah menjalankan `model(img_rgb)` satu per satu dalam loop `for img_idx, file in enumerate(files)`.
  - Setiap *cropped bubble* menjalankan OCR (`MangaOcr` atau `EasyOCR`) satu per satu secara sekuensial.
- **Dampak**:  
  Pada sesi multi-halaman dengan puluhan bubble, total waktu Fase 1 adalah akumulasi linear penuh dari seluruh inferensi deteksi + OCR.
- **Arah Rancangan Perbaikan**:  
  Sebagai optimasi tahap lanjut setelah P1 & P2: pertimbangkan pemisahan/batching inferensi (atau *batched OCR* bila didukung) dengan tetap memperhatikan kompatibilitas ukuran gambar/aspek rasio pada YOLOv5 dan batas memori GPU/CPU.

---

## 🟢 Prioritas 3 (*Least Priority*): Proses Kalkulasi Visual & *Typesetting* (`render_bubbles`)

Sesuai prioritas proyek, aspek yang bersentuhan dengan rendering visual komik ditempatkan di prioritas paling akhir. Bagian ini dipisahkan menjadi **P3-A** (redundansi murni tanpa mengubah tampilan visual) dan **P3-B** (logika visual yang harus dijaga).

### P3-A. Redundansi Komputasi di Dalam `render_bubbles()` (Tanpa Mengubah Visual)

1. **Pemuatan File Font `.ttf` Berulang dari Disk di Dalam Loop (`image_processor.py:314`)**:
   - Di dalam loop `while font_size > 12:`, fungsi `ImageFont.truetype(font_path, font_size)` dipanggil pada **setiap penurunan 1 pt ukuran font** (hingga 99 kali per bubble), lalu dipanggil sekali lagi di baris 336.
   - *Rancangan*: Cache objek `ImageFont` di memori berdasarkan `(font_path, font_size)` menggunakan `@functools.lru_cache`. Hasil visual **100% identik**.
2. **Kalkulasi Ulang Identik Pasca-Loop (`image_processor.py:333-340`)**:
   - Setelah loop `while` selesai/berhenti (`break`), baris 334 menulis `font_size = int(font_size * 1.0)` (operasi identitas), kemudian baris 336–340 memanggil ulang `ImageFont.truetype(...)`, `wrap_text(...)`, `font.getmetrics()`, dan menghitung ulang `line_height` serta `total_height` dengan nilai yang sama persis seperti iterasi terakhir di dalam loop.
   - *Rancangan*: Simpan dan gunakan langsung `font`, `lines`, `line_height`, dan `total_height` dari iterasi loop yang lolos (atau nilai fallback `font_size = 12`). Hasil visual **100% identik**.
3. **Pencarian Linear `font_size` (`110` $\rightarrow$ `12`) & Pengukuran `textbbox` Berulang (`image_processor.py:312-331, 355`)**:
   - Pencarian ukuran font turun 1 demi 1 hingga maksimal **99 iterasi** `wrap_text` per bubble, dan saat menggambar di baris 355 `draw.textbbox` dipanggil lagi untuk setiap baris teks.
   - *Rancangan*: Ganti pencarian linear menjadi *Binary Search* pada rentang `[12, 110]` (maksimal $\lceil \log_2(99) \rceil = 7$ iterasi) serta simpan lebar tiap baris hasil wrapping agar tidak diukur ulang saat `draw.text`.
   - *Catatan Risiko Visual*: Karena `wrap_text` + `break_word` memiliki ambang batas pemenggalan kata/suku kata diskret, pada kasus tepi yang sangat jarang fungsi tinggi total bisa tidak sepenuhnya monotonik pada dua ukuran font berdekatan. Oleh karena itu, perubahan ke *Binary Search* ditempatkan di prioritas paling bawah dan perlu diuji perbandingan visualnya.

### P3-B. Logika Visual & *Typesetting* yang Dipertahankan
- `wrap_text()` & `break_word()` menggunakan kamus suku kata `pyphen` (`id_ID`, `en_US`) serta guard `len(word) <= 5` ([image_processor.py](backend/image_processor.py#L184-L248)).
- Ekspansi area lebar teks `int(box_width * 1.22)`, `line_spacing_factor = 1.05`, batas *inset* kotak putih `1.5%` (`inset_x`, `inset_y`), perataan tengah horizontal/vertikal, serta `stroke_width=2, stroke_fill="white"` ([image_processor.py](backend/image_processor.py#L307-L366)).
- Proses-proses ini secara langsung menghasilkan tampilan terjemahan komik yang rapi dan mudah dibaca, sehingga **tidak direkomendasikan untuk diubah**.

---

## Temuan Pendukung: *Dead Code*, Portabilitas, Frontend, & Sinkronisasi Dokumentasi

Temuan berikut bukan *bottleneck* utama proses translasi, namun ditemukan saat memverifikasi *source code* terhadap dokumentasi:

1. **Ketidaksinkronan Dokumentasi ([docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)) vs *Source Code* Aktual**:
   - Dokumentasi menyebut backend memakai `googletrans==4.0.0rc1` dan melakukan fallback per-bubble secara sinkron di dalam `app.py` (baris 71–79). Pada kode aktual ([backend/requirements.txt](backend/requirements.txt#L6), [backend/app.py](backend/app.py#L72), [backend/image_processor.py](backend/image_processor.py#L157-L182)), proyek sudah memakai `googletrans==4.0.2` dengan `batch_google_translate()` berbasis `asyncio`.
   - Dokumentasi menyebut `google-genai` ada di `backend/requirements.txt`, padahal pada [backend/requirements.txt](backend/requirements.txt) aktual library tersebut sudah tidak tercantum (hanya `python-dotenv` yang tersisa sebagai dependensi tidak terpakai).
2. ***Dead Code* & Parameter Tidak Terpakai di `backend/image_processor.py`**:
   - Fungsi `process_language()` ([baris 25–38](backend/image_processor.py#L25-L38)) tidak pernah dipanggil di mana pun.
   - Parameter `translate_code` pada `extract_bubbles()` ([baris 250](backend/image_processor.py#L250)) diterima namun tidak digunakan di dalam fungsi.
   - `re.sub(r'\bLai\b', '!', translated)` pada `render_bubbles()` ([baris 293](backend/image_processor.py#L293)) menerapkan perbaikan artifak OCR kepada teks yang **sudah diterjemahkan** (padahal `clean_ocr_text` di baris 65 sudah melakukannya sebelum translasi).
   - `print(...)` debug per bubble di `render_bubbles()` ([baris 299–301](backend/image_processor.py#L299-L301)) tetap aktif di setiap pemrosesan.
3. **Portabilitas OS (`backend/image_processor.py:19`)**:
   - `pathlib.PosixPath = pathlib.WindowsPath` dieksekusi tanpa guard `if os.name == 'nt':`, sehingga akan gagal di Linux/macOS.
4. **Catatan Minor Frontend (`frontend/src/pages/Home.jsx`)**:
   - `useEffect` diimpor pada [baris 1](frontend/src/pages/Home.jsx#L1) tetapi tidak digunakan; `setInterval` pada `timerRef` ([baris 20](frontend/src/pages/Home.jsx#L20)) tidak memiliki cleanup saat komponen unmount.
   - `downloadPDF()` ([baris 143](frontend/src/pages/Home.jsx#L143)) selalu meneruskan format `'JPEG'` ke `pdf.addImage(img, 'JPEG', ...)` tanpa menyesuaikan format gambar hasil sebenarnya (misal `.png` atau `.webp`).
   - Hardcoded base URL `http://127.0.0.1:5000` di frontend (`Home.jsx`, `History.jsx`) dan data yang tersimpan ke `history.json` oleh `app.py`.

---

## Rekomendasi Urutan Eksekusi (Untuk Tahap Implementasi Berikutnya)

1. **Tahap 1 — Quick Wins (Prioritas P1)**:
   - Cache model OCR (`_OCR_CACHE`) di `selectOCR()`.
   - Matikan `force_reload=True` dan terapkan *lazy loading* model YOLOv5 (atau `use_reloader=False`).
   - Ganti crop PIL $\rightarrow$ NumPy pada EasyOCR dengan *zero-copy NumPy slicing* `img_rgb[y1:y2, x1:x2]` dan pindahkan `ImageDraw.Draw` ke Fase 3.
   - Gunakan `torch.inference_mode()` dan akses koordinat tensor YOLOv5 langsung tanpa `pandas().xyxy[0]` + `.iterrows()`.
2. **Tahap 2 — Efisiensi & Reliabilitas Translasi (Prioritas P2)**:
   - Tambahkan filter bubble tanda baca murni & deduplikasi teks unik sebelum memanggil Gemini / Google Translate.
   - Perbaiki *break* pada error global/fatal di `batch_gemini_translate`, tambahkan `timeout` HTTP, serta amankan `batch_google_translate` dengan chunking dan `try/except`.
   - Evaluasi manajemen memori `image_contexts` untuk batch halaman besar.
3. **Tahap 3 — Optimasi Komputasi Render yang Aman Secara Visual (Prioritas P3-A)**:
   - Cache `ImageFont.truetype()` dengan `@functools.lru_cache` dan hapus kalkulasi ulang identik setelah loop `while`.
   - Pertahankan logika *typesetting* & estetika pada **P3-B** secara utuh.
