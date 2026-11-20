from flask import Flask, request, jsonify
from flask_cors import CORS
from image_processor import (
    extract_bubbles,
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
from datetime import datetime

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = os.path.join("static", "uploads")
HISTORY_FILE = os.path.join("static", "history.json")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_history(history_data):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Gagal menyimpan history: {e}")

@app.route('/process-image', methods=['POST'])
def process_image_endpoint():
    try:
        if 'image[]' not in request.files:
            return jsonify({'error': 'No image provided'}), 400

        sourceLang = request.form['source']
        targetLang = request.form['target']
        engine = request.form.get('engine', 'googletrans')
        api_key = request.form.get('apiKey', '')
        files = request.files.getlist('image[]')

        t_total_start = time.perf_counter()

        t0 = time.perf_counter()
        ocr, index, translate_code = selectOCR(sourceLang)
        t_ocr_load = time.perf_counter() - t0

        image_contexts = []
        all_bubbles = []

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Fase 1: YOLO + OCR untuk SEMUA gambar dulu, belum translate
        t_read = 0.0
        t_yolo = 0.0
        t_ocr_infer = 0.0
        for img_idx, file in enumerate(files):
            raw_filename = secure_filename(file.filename)
            name, ext = os.path.splitext(raw_filename)
            filename = f"{name}_{timestamp}_{img_idx+1}{ext}"
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)

            img_timings = {}
            img_pil, bubbles = extract_bubbles(
                filepath, ocr, index, translate_code, image_id=img_idx, timings=img_timings
            )
            t_read += img_timings.get("read", 0.0)
            t_yolo += img_timings.get("yolo", 0.0)
            t_ocr_infer += img_timings.get("ocr", 0.0)
            print(
                f"[Timing] img {img_idx+1}/{len(files)} ({filename}): "
                f"yolo={img_timings.get('yolo', 0.0):.2f}s "
                f"ocr={img_timings.get('ocr', 0.0):.2f}s ({len(bubbles)} bubbles)"
            )
            image_contexts.append({
                'img_pil': img_pil, 'bubbles': bubbles, 'filename': filename
            })
            all_bubbles.extend(bubbles)

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
                'original': f"http://127.0.0.1:5000/static/uploads/{ctx['filename']}",
                'translated': f"http://127.0.0.1:5000/static/uploads/output_{ctx['filename']}"
            })

        # Simpan hasil ke history JSON di backend
        history_entry = {
            'id': int(time.time() * 1000),
            'date': datetime.now().strftime("%d/%m/%Y, %H.%M.%S"),
            'sourceLang': sourceLang,
            'targetLang': targetLang,
            'engine': engine,
            'images': results
        }
        history = load_history()
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

@app.route('/history', methods=['GET'])
def get_history_endpoint():
    return jsonify(load_history())

@app.route('/clear-history', methods=['POST'])
def clear_history_endpoint():
    save_history([])
    
    # Hapus semua file gambar di dalam folder static/uploads
    try:
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