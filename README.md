# Comic & Manga Translator v2

A local web application for translating text inside comic and manga image pages. You upload one or more pages through the browser, select the source and target languages, and the local Python backend detects speech bubbles with YOLOv5, extracts text using cross-page batched Manga-OCR or zero-copy EasyOCR, translates the dialogue using Google Translate or the Google Gemini API, and renders the translated text back onto the images with automatic font fitting and syllable hyphenation. Results can be viewed side by side in the browser, reviewed later from the history page, or exported as a single PDF file.

---

## Supported Languages & Translation Engines

- **Source languages**: Japanese (`jp`), Korean (`ko`), Simplified Chinese (`ch_sim`), English (`en`) *(plus Traditional Chinese `ch_tra` in the backend API)*
- **Target languages**: Indonesian (`id`), English (`en`)
- **Translation engines**:
  - **Google Translate** (default, requires no API key, powered by asynchronous `googletrans==4.0.2`)
  - **Google Gemini API** (requires an API key from [Google AI Studio](https://aistudio.google.com/))

---

## Prerequisites

- **Python 3.9+** and `pip`
- **Node.js 18+** and `npm`
- **Git** (used by `torch.hub.load` on initial setup if the `ultralytics/yolov5` repository is not yet cached locally)
- **Internet connection** (required when calling translation services, and on the first run if YOLOv5 or OCR model weights have not yet been cached locally)
- *(Optional)* An NVIDIA GPU with CUDA support for PyTorch and OCR execution (falls back to CPU when unavailable)

---

## Setup & Installation

The application consists of two processes that run locally: a **Python Flask backend** and a **React (Vite) frontend**.

### 1. Backend Setup

1. Open a terminal and change into the `backend` directory:
   ```bash
   cd backend
   ```
   > **Note**: Keep `backend/` as your working directory when running the server, as `app.py` and `render_bubbles()` resolve `static/uploads`, `static/history.json`, and default font paths relative to this folder.

2. Create and activate a Python virtual environment:
   - **Windows (PowerShell)**:
     ```powershell
     python -m venv .venv
     .venv\Scripts\Activate.ps1
     ```
   - **macOS / Linux**:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. Install the Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Verify that the YOLOv5 weights file exists at:
   ```text
   backend/yolo-model/bubble-detector-new/weights/best.pt
   ```

5. Start the Flask backend server:
   ```bash
   python app.py
   ```
   On startup, the backend pre-warms YOLOv5 (loading directly from the local PyTorch Hub cache when available) and listens on `http://127.0.0.1:5000` with Werkzeug's duplicate reloader disabled (`use_reloader=False`). On the first translation request for a given source language, Manga-OCR or EasyOCR loads its weights and caches the reader in memory (`MAX_OCR_CACHE = 2`) for subsequent requests.

---

### 2. Frontend Setup

1. Open a second terminal and change into the `frontend` directory:
   ```bash
   cd frontend
   ```

2. Install the Node.js dependencies:
   ```bash
   npm install
   ```

3. Start the Vite development server:
   ```bash
   npm run dev
   ```

4. Open the local URL shown in the terminal (by default `http://localhost:5173`) in your web browser.

---

## How to Use

> **Note**: Navigation links are labeled in English (`Home`, `History`, `Settings`), while buttons and form labels inside the pages are displayed in Indonesian.

1. **Choose a translation engine (optional)**:
   - Open **Settings** from the top navigation bar.
   - Select either **Google Translate (Gratis & Default)** or **Google Gemini AI (Lebih Natural & Pintar)**.
   - If you select Google Gemini AI, paste your API key from [Google AI Studio](https://aistudio.google.com/) and click **SIMPAN PENGATURAN**. Your selection and key are stored in your browser's `localStorage`.
2. **Upload comic pages**:
   - On the **Home** page, click **UPLOAD GAMBAR** and select one or more image files.
3. **Select languages**:
   - Choose the source language from the left dropdown (`Bahasa Jepang`, `Bahasa Korea`, `Bahasa Mandarin`, or `Bahasa Inggris`).
   - Choose the target language from the right dropdown (`Bahasa Indonesia` or `Bahasa Inggris`).
4. **Run translation**:
   - Click **Terjemahkan**. The status box displays elapsed processing time until the backend responds, while the backend terminal logs per-image and per-phase timing breakdowns (`[Timing] ...`).
   - Once complete, each page is shown side by side under **Asli** (original) and **Terjemahan** (translated).
5. **Export to PDF**:
   - After results appear, click **DOWNLOAD PDF** to combine the translated images into a single `hasil_gambar.pdf` file.
6. **View or clear history**:
   - Open **History** to browse past translation sessions saved on the backend.
   - Toggle between grid and list layouts, click any entry to open a side-by-side modal view, or click **Hapus Semua** to clear the saved history and delete uploaded/output image files from `backend/static/uploads/`.

---

## Running Backend Tests

The `backend/tests/` directory contains 36 unit and integration tests covering OCR LRU caching, offline-first YOLOv5 loading, bubble extraction, cross-page batched Manga-OCR, binary-search text rendering with pixel-equivalence checks, and OCR text cleaning / hyphenation rules:

```powershell
backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

---

## Troubleshooting

- **`NotImplementedError: cannot instantiate 'WindowsPath' on your system` (Linux / macOS)**:
  Line 24 of `backend/image_processor.py` sets `pathlib.PosixPath = pathlib.WindowsPath` so YOLOv5 weights trained on Linux can load on Windows. On Linux or macOS, remove or comment out that line (or guard it with `if os.name == 'nt':`).
- **Frontend cannot reach the backend**:
  The frontend sends requests directly to `http://127.0.0.1:5000`. Make sure `python app.py` is running from the `backend/` directory before starting a translation.
- **Google Gemini rate limits (`HTTP 429`)**:
  Free-tier Gemini API keys have per-minute and per-day request limits. The backend waits and retries once on temporary `429`/`503` responses, and falls back to Google Translate for bubbles that were not returned by Gemini (including when the daily quota is exceeded).

---

## Technical Documentation

- For the system architecture, 3-phase processing pipeline, typesetting & binary-search fitting logic, REST API reference, and known codebase limitations, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- For the performance audit, benchmark progression, implemented optimizations, and remaining optimization roadmap, see [PERFORMANCE_AUDIT.md](PERFORMANCE_AUDIT.md).
