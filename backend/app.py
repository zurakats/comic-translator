from flask import Flask, request, jsonify
from flask_cors import CORS
from image_processor import (
    extract_bubbles,
    detect_bubbles,
    batch_manga_ocr,
    clean_ocr_text,
    MANGA_OCR_BATCH_SIZE,
    render_bubbles,
    batch_gemini_translate,
    batch_google_translate,
    selectOCR,
    get_yolo_model,
)
from werkzeug.utils import secure_filename
import os
import json
import time
import threading
import uuid
from datetime import datetime
from urllib.parse import urlparse

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = os.path.join("static", "uploads")
HISTORY_FILE = os.path.join("static", "history.json")
SETTINGS_FILE = os.path.join("static", "settings.json")
VALID_ENGINES = {"googletrans", "gemini"}
DEFAULT_SETTINGS = {"engine": "googletrans", "apiKey": ""}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

_history_lock = threading.RLock()
_settings_lock = threading.RLock()

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def _write_json_atomic(filepath, data):
    parent_dir = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(parent_dir, exist_ok=True)
    tmp_path = f"{filepath}.{uuid.uuid4().hex}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, filepath)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


def _normalize_upload_url(url):
    if not url or not isinstance(url, str):
        return url
    parsed_path = urlparse(url).path
    if parsed_path.startswith("/static/uploads/"):
        return parsed_path
    if parsed_path.startswith("static/uploads/"):
        return f"/{parsed_path}"
    return url


def _normalize_history_entry(entry):
    if not isinstance(entry, dict):
        return entry
    normalized = dict(entry)
    raw_name = entry.get("name")
    normalized["name"] = raw_name.strip() if isinstance(raw_name, str) else ""
    normalized_images = []
    for img in entry.get("images", []):
        if isinstance(img, dict):
            img_copy = dict(img)
            if "original" in img_copy:
                img_copy["original"] = _normalize_upload_url(img_copy["original"])
            if "translated" in img_copy:
                img_copy["translated"] = _normalize_upload_url(img_copy["translated"])
            normalized_images.append(img_copy)
    normalized["images"] = normalized_images
    return normalized


def _build_safe_upload_filename(orig_filename, timestamp, req_uid, img_idx):
    orig_stem, orig_ext = os.path.splitext(orig_filename or "")
    ext = orig_ext.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        ext = ".png"
    safe_name = secure_filename(orig_stem) or "image"
    return f"{safe_name}_{timestamp}_{req_uid}_{img_idx + 1}{ext}"


def load_history():
    with _history_lock:
        if not os.path.exists(HISTORY_FILE):
            return []
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []


def save_history(history_data):
    with _history_lock:
        try:
            _write_json_atomic(HISTORY_FILE, history_data)
        except Exception as e:
            print(f"⚠️ Gagal menyimpan history: {e}")


def _sanitize_settings(data):
    if not isinstance(data, dict):
        return dict(DEFAULT_SETTINGS)
    engine = data.get("engine")
    if not isinstance(engine, str) or engine not in VALID_ENGINES:
        engine = DEFAULT_SETTINGS["engine"]
    api_key = data.get("apiKey")
    if not isinstance(api_key, str):
        api_key = DEFAULT_SETTINGS["apiKey"]
    else:
        api_key = api_key.strip()
    return {"engine": engine, "apiKey": api_key}


def load_settings():
    with _settings_lock:
        if not os.path.exists(SETTINGS_FILE):
            return dict(DEFAULT_SETTINGS)
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return _sanitize_settings(data)
        except Exception:
            return dict(DEFAULT_SETTINGS)


def save_settings(settings_data):
    with _settings_lock:
        sanitized = _sanitize_settings(settings_data)
        _write_json_atomic(SETTINGS_FILE, sanitized)
        return sanitized


@app.route('/settings', methods=['GET'])
def get_settings_endpoint():
    return jsonify(load_settings())


@app.route('/settings', methods=['POST', 'PUT'])
def update_settings_endpoint():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': 'Invalid JSON body'}), 400

    if 'engine' in payload:
        if not isinstance(payload['engine'], str) or payload['engine'] not in VALID_ENGINES:
            return jsonify({'error': 'Invalid translation engine'}), 400

    if 'apiKey' in payload and not isinstance(payload['apiKey'], str):
        return jsonify({'error': 'Invalid API key format'}), 400

    with _settings_lock:
        current = load_settings()
        if 'engine' in payload:
            current['engine'] = payload['engine']
        if 'apiKey' in payload:
            current['apiKey'] = payload['apiKey'].strip()
        saved = save_settings(current)

    return jsonify({'status': 'success', **saved})


@app.route('/process-image', methods=['POST'])
def process_image_endpoint():
    try:
        if 'image[]' not in request.files:
            return jsonify({'error': 'No image provided'}), 400

        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        sourceLang = request.form['source']
        targetLang = request.form['target']
        saved_settings = load_settings()
        form_engine = (request.form.get('engine') or '').strip()
        engine = form_engine if form_engine in VALID_ENGINES else saved_settings['engine']
        form_api_key = (request.form.get('apiKey') or '').strip()
        api_key = form_api_key or (saved_settings['apiKey'] if engine == 'gemini' else '')
        files = request.files.getlist('image[]')

        t_total_start = time.perf_counter()

        t0 = time.perf_counter()
        ocr, index, translate_code = selectOCR(sourceLang)
        t_ocr_load = time.perf_counter() - t0

        image_contexts = []
        all_bubbles = []

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        req_uid = uuid.uuid4().hex[:6]

        # Fase 1: YOLO + OCR untuk SEMUA gambar dulu, belum translate
        t_read = 0.0
        t_yolo = 0.0
        t_ocr_infer = 0.0
        all_pending_crops = []
        for img_idx, file in enumerate(files):
            filename = _build_safe_upload_filename(file.filename, timestamp, req_uid, img_idx)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)

            img_timings = {}
            if index == 0:
                img_pil, bubbles, pending_crops = detect_bubbles(
                    filepath, image_id=img_idx, timings=img_timings
                )
                all_pending_crops.extend(pending_crops)
                print(
                    f"[Timing] img {img_idx+1}/{len(files)} ({filename}): "
                    f"yolo={img_timings.get('yolo', 0.0):.2f}s ({len(bubbles)} bubbles)"
                )
            else:
                img_pil, bubbles = extract_bubbles(
                    filepath, ocr, index, translate_code, image_id=img_idx, timings=img_timings
                )
                t_ocr_infer += img_timings.get("ocr", 0.0)
                print(
                    f"[Timing] img {img_idx+1}/{len(files)} ({filename}): "
                    f"yolo={img_timings.get('yolo', 0.0):.2f}s "
                    f"ocr={img_timings.get('ocr', 0.0):.2f}s ({len(bubbles)} bubbles)"
                )

            t_read += img_timings.get("read", 0.0)
            t_yolo += img_timings.get("yolo", 0.0)
            image_contexts.append({
                'img_pil': img_pil, 'bubbles': bubbles, 'filename': filename
            })
            all_bubbles.extend(bubbles)

        if index == 0 and all_pending_crops:
            t0 = time.perf_counter()
            texts = batch_manga_ocr(ocr, [crop for _, crop in all_pending_crops])
            for (bubble, _), text in zip(all_pending_crops, texts):
                bubble["ocr_text"] = text
                bubble["cleaned_text"] = clean_ocr_text(text) or ""
            t_ocr_infer = time.perf_counter() - t0
            all_pending_crops.clear()
            print(
                f"[Timing] manga_ocr_batch: {t_ocr_infer:.2f}s "
                f"({len(texts)} bubbles, batch_size={MANGA_OCR_BATCH_SIZE})"
            )

        # Fase 2: SATU (atau sedikit, kalau > batch_size) request Gemini untuk semua bubble
        translations = {}
        t_gemini = 0.0
        if engine == 'gemini' and api_key:
            t0 = time.perf_counter()
            translations = batch_gemini_translate(all_bubbles, translate_code, targetLang, api_key)
            t_gemini = time.perf_counter() - t0

        # Fallback googletrans untuk bubble yang belum dapat translation (gemini gagal / engine googletrans)
        t0 = time.perf_counter()
        translations = batch_google_translate(all_bubbles, translate_code, targetLang, translations)
        t_gtrans = time.perf_counter() - t0

        # Fase 3: gambar ulang tiap gambar pakai hasil translate
        results = []
        t_render = 0.0
        t_save = 0.0
        for ctx in image_contexts:
            t0 = time.perf_counter()
            render_bubbles(ctx['img_pil'], ctx['bubbles'], translations, targetLang)
            t_render += time.perf_counter() - t0

            t0 = time.perf_counter()
            output_path = os.path.join(UPLOAD_FOLDER, f"output_{ctx['filename']}")
            ctx['img_pil'].save(output_path)
            t_save += time.perf_counter() - t0

            results.append({
                'original': f"/static/uploads/{ctx['filename']}",
                'translated': f"/static/uploads/output_{ctx['filename']}"
            })

        # Simpan hasil ke history JSON di backend
        with _history_lock:
            history = load_history()
            existing_ids = {entry.get('id') for entry in history if isinstance(entry, dict)}
            batch_id = int(time.time() * 1000)
            while batch_id in existing_ids:
                batch_id += 1

            history_entry = {
                'id': batch_id,
                'name': '',
                'date': datetime.now().strftime("%d/%m/%Y, %H.%M.%S"),
                'sourceLang': sourceLang,
                'targetLang': targetLang,
                'engine': engine,
                'images': results
            }
            history.insert(0, history_entry)
            save_history(history)

        t_total = time.perf_counter() - t_total_start
        print(
            f"[Timing] total={t_total:.2f}s | ocr_load={t_ocr_load:.2f}s | "
            f"read={t_read:.2f}s | yolo={t_yolo:.2f}s | ocr_infer={t_ocr_infer:.2f}s | "
            f"gemini={t_gemini:.2f}s | gtrans={t_gtrans:.2f}s | "
            f"render={t_render:.2f}s | save={t_save:.2f}s | "
            f"({len(files)} img, {len(all_bubbles)} bubbles)"
        )

        return jsonify({'results': results})

    except Exception as e:
        print(f"⚠️ Error saat memproses gambar: {e}")
        return jsonify({'error': str(e)}), 500

def _extract_upload_filename(url):
    if not url or not isinstance(url, str):
        return None
    parsed_path = urlparse(url).path
    filename = os.path.basename(parsed_path)
    return filename or None


def _delete_unreferenced_batch_files(deleted_entry, remaining_history):
    referenced_filenames = set()
    for entry in remaining_history:
        for img in entry.get('images', []):
            for key in ('original', 'translated'):
                fname = _extract_upload_filename(img.get(key))
                if fname:
                    referenced_filenames.add(fname)

    upload_root = os.path.abspath(UPLOAD_FOLDER)
    for img in deleted_entry.get('images', []):
        for key in ('original', 'translated'):
            fname = _extract_upload_filename(img.get(key))
            if not fname or fname in referenced_filenames:
                continue
            target_path = os.path.abspath(os.path.join(upload_root, fname))
            if os.path.dirname(target_path) != upload_root:
                continue
            try:
                if os.path.isfile(target_path):
                    os.remove(target_path)
            except Exception as e:
                print(f"⚠️ Gagal menghapus file {fname}: {e}")


@app.route('/history', methods=['GET'])
def get_history_endpoint():
    with _history_lock:
        history = load_history()
    return jsonify([_normalize_history_entry(entry) for entry in history])


@app.route('/history/<int:batch_id>', methods=['PATCH', 'PUT'])
def update_history_batch_endpoint(batch_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get('name'), str):
        return jsonify({'error': 'Invalid batch name'}), 400

    new_name = payload['name'].strip()[:80]

    with _history_lock:
        history = load_history()
        target_entry = None
        for entry in history:
            if entry.get('id') == batch_id:
                target_entry = entry
                break

        if target_entry is None:
            return jsonify({'error': 'History batch not found'}), 404

        target_entry['name'] = new_name
        save_history(history)

    return jsonify({'status': 'success', 'id': batch_id, 'name': new_name})


@app.route('/history/<int:batch_id>', methods=['DELETE'])
def delete_history_batch_endpoint(batch_id):
    with _history_lock:
        history = load_history()
        deleted_entry = None
        remaining_history = []

        for entry in history:
            if entry.get('id') == batch_id and deleted_entry is None:
                deleted_entry = entry
            else:
                remaining_history.append(entry)

        if deleted_entry is None:
            return jsonify({'error': 'History batch not found'}), 404

        save_history(remaining_history)
        _delete_unreferenced_batch_files(deleted_entry, remaining_history)
    return jsonify({'status': 'success', 'id': batch_id})

@app.route('/clear-history', methods=['POST'])
def clear_history_endpoint():
    with _history_lock:
        save_history([])
        
        # Hapus semua file gambar di dalam folder static/uploads
        try:
            if os.path.isdir(UPLOAD_FOLDER):
                for filename in os.listdir(UPLOAD_FOLDER):
                    file_path = os.path.join(UPLOAD_FOLDER, filename)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
        except Exception as e:
            print(f"⚠️ Gagal membersihkan folder uploads: {e}")
        
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    t0 = time.perf_counter()
    get_yolo_model()
    print(f"[Startup] YOLOv5 ready in {time.perf_counter() - t0:.2f}s")
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)