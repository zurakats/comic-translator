from flask import Flask, request, jsonify
from flask_cors import CORS
from image_processor import extract_bubbles, render_bubbles, batch_gemini_translate, selectOCR, translator
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

        ocr, index, translate_code = selectOCR(sourceLang)

        image_contexts = []
        all_bubbles = []

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Fase 1: YOLO + OCR untuk SEMUA gambar dulu, belum translate
        for img_idx, file in enumerate(files):
            raw_filename = secure_filename(file.filename)
            name, ext = os.path.splitext(raw_filename)
            filename = f"{name}_{timestamp}_{img_idx+1}{ext}"
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)

            img_pil, draw, bubbles = extract_bubbles(filepath, ocr, index, translate_code, image_id=img_idx)
            image_contexts.append({
                'img_pil': img_pil, 'draw': draw, 'bubbles': bubbles, 'filename': filename
            })
            all_bubbles.extend(bubbles)

        # Fase 2: SATU (atau sedikit, kalau > batch_size) request Gemini untuk semua bubble
        translations = {}
        if engine == 'gemini' and api_key:
            translations = batch_gemini_translate(all_bubbles, translate_code, targetLang, api_key)

        # Fallback googletrans untuk bubble yang belum dapat translation (gemini gagal / engine googletrans)
        for b in all_bubbles:
            if not translations.get(b['id']):
                if b['cleaned_text'].strip():
                    translations[b['id']] = translator.translate(
                        b['cleaned_text'], src=translate_code, dest=targetLang
                    ).text
                else:
                    translations[b['id']] = "[Teks tidak terbaca]"

        # Fase 3: gambar ulang tiap gambar pakai hasil translate
        results = []
        for ctx in image_contexts:
            render_bubbles(ctx['img_pil'], ctx['draw'], ctx['bubbles'], translations, targetLang)

            output_path = os.path.join(UPLOAD_FOLDER, f"output_{ctx['filename']}")
            ctx['img_pil'].save(output_path)

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
    app.run(host="0.0.0.0", port=5000, debug=True)