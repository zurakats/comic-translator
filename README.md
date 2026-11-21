# Comic & Manga Translator v2

A local client-server web application for translating text inside comic and manga image pages over localhost or a local Wi-Fi network. Run the Python backend and Vite server on your desktop PC, then open the web UI from the desktop or from any smartphone/tablet on the same Wi-Fi network. You upload one or more pages through the browser, select the source and target languages, and the desktop backend detects speech bubbles with YOLOv5, extracts text using cross-page batched Manga-OCR or zero-copy EasyOCR, translates the dialogue using Google Translate or the Google Gemini API, and renders the translated text back onto the images with automatic font fitting and syllable hyphenation. Results, shared history (with batch renaming and deletion), and server-wide translation settings are stored centrally on the desktop and can be accessed from any connected device, or exported as a single PDF file.

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
   > **Note**: Keep `backend/` as your working directory when running the server, as `app.py` and `render_bubbles()` resolve `static/uploads`, `static/history.json`, `static/settings.json`, and default font paths relative to this folder.

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
   Vite is configured with `host: true` on port `5173` and proxies `/api/*` and `/static/*` requests to the local Flask backend (`http://127.0.0.1:5000`, configurable via `VITE_BACKEND_URL`).

4. Open the application:
   - **On the desktop**: open `http://localhost:5173` in your web browser.
   - **From a smartphone or tablet on the same Wi-Fi network**: copy the `Network: http://<DESKTOP_LAN_IP>:5173` URL printed in the Vite terminal and open it in your mobile browser. All devices share the same settings, uploaded pages, and translation history stored on the desktop server.

---

## How to Use

> **Note**: Navigation links are labeled in English (`Home`, `History`, `Settings`), while interface controls are displayed in English.

1. **Choose a translation engine (optional)**:
   - Open **Settings** from the top navigation bar (on the desktop or any connected device).
   - Select either **Google Translate (Free & Default)** or **Google Gemini AI (More Natural & Context-Aware)**.
   - If you select Google Gemini AI, paste your API key from [Google AI Studio](https://aistudio.google.com/) and click **SAVE SETTINGS**. Your selection and API key are saved centrally on the desktop server (`backend/static/settings.json`), so other devices on the same Wi-Fi can immediately translate with Gemini without re-entering the key.
2. **Upload comic pages**:
   - On the **Home** page (grouped in a compact mobile control card on smaller screens), click **UPLOAD IMAGES** and select one or more image files from your desktop or mobile gallery.
3. **Select languages**:
   - Choose the source language from the left dropdown (`Japanese`, `Korean`, `Chinese (Simplified)`, or `English`).
   - Choose the target language from the right dropdown (`Indonesian` or `English`).
4. **Run translation**:
   - Click **Translate**. The status box displays elapsed processing time until the backend responds, while the backend terminal logs per-image and per-phase timing breakdowns (`[Timing] ...`).
   - Once complete, each page is shown side by side on desktop (or switchable **Original** / **Translated** reader tabs on mobile/tablet).
5. **Export to PDF**:
   - After results appear, click **Download PDF** (`jsPDF` is loaded on demand) to combine the translated images into a single `translated_comic.pdf` file.
6. **View, rename, or delete history**:
   - Open **History** from any connected device to browse past translation sessions saved on the desktop backend (`backend/static/history.json`).
   - Toggle between grid and list layouts, rename batches (persisted on the server and synced across devices), click any entry to open the reader modal, delete individual batches, or click **Clear All** to clear all saved history and delete files from `backend/static/uploads/`.

---

## Running Backend Tests

The `backend/tests/` directory contains 47 unit and integration tests across 8 modules covering OCR LRU caching, offline-first YOLOv5 loading, bubble extraction, cross-page batched Manga-OCR, binary-search text rendering with pixel-equivalence checks, OCR text cleaning / hyphenation rules, single-batch history deletion, static upload immutable caching, and Wi-Fi client-server settings/history/proxy contracts:

```powershell
backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

---

## Troubleshooting

- **`NotImplementedError: cannot instantiate 'WindowsPath' on your system` (Linux / macOS)**:
  Line 24 of `backend/image_processor.py` sets `pathlib.PosixPath = pathlib.WindowsPath` so YOLOv5 weights trained on Linux can load on Windows. On Linux or macOS, remove or comment out that line (or guard it with `if os.name == 'nt':`).
- **Frontend cannot reach the backend**:
  Vite proxies `/api/*` and `/static/*` requests directly to `http://127.0.0.1:5000` (or `VITE_BACKEND_URL`). Make sure `python app.py` is running from the `backend/` directory before using the web app.
- **Smartphone/tablet on the same Wi-Fi cannot open `http://<DESKTOP_LAN_IP>:5173`**:
  On Windows, verify that your Wi-Fi network profile is set to **Private** (not Public) and allow Node.js (`5173`) through **Windows Defender Firewall** when prompted. Make sure both the desktop and mobile device are on the same Wi-Fi subnet without AP/client isolation enabled on the router.
- **Google Gemini rate limits (`HTTP 429`)**:
  Free-tier Gemini API keys have per-minute and per-day request limits. The backend waits and retries once on temporary `429`/`503` responses, and falls back to Google Translate for bubbles that were not returned by Gemini (including when the daily quota is exceeded).

---

## Technical Documentation

- For the system architecture, 3-phase processing pipeline, typesetting & binary-search fitting logic, REST API reference, and known codebase limitations, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- For the performance audit, benchmark progression, implemented optimizations, and remaining optimization roadmap, see [PERFORMANCE_AUDIT.md](PERFORMANCE_AUDIT.md).
