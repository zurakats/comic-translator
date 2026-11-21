import asyncio
from collections import OrderedDict
from functools import lru_cache
import os
import threading
import cv2
import torch
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from manga_ocr import MangaOcr
import easyocr
from googletrans import Translator
import pathlib
import re
import pyphen
import urllib.request
import json
import time

dic_id = pyphen.Pyphen(lang='id_ID')
dic_en = pyphen.Pyphen(lang='en_US')

pathlib.PosixPath = pathlib.WindowsPath

model_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "yolo-model",
    "bubble-detector-new",
    "weights",
    "best.pt",
)
_yolo_model = None
_yolo_lock = threading.Lock()


def _get_cached_yolov5_dir():
    hub_dir = torch.hub.get_dir()
    for repo_dir_name in ("ultralytics_yolov5_master", "ultralytics_yolov5_main"):
        candidate = os.path.join(hub_dir, repo_dir_name)
        if os.path.isfile(os.path.join(candidate, "hubconf.py")):
            return candidate
    return None


def get_yolo_model():
    """Lazily load and cache the YOLOv5 speech-bubble detector."""
    global _yolo_model
    if _yolo_model is not None:
        return _yolo_model

    with _yolo_lock:
        if _yolo_model is not None:
            return _yolo_model

        cached_dir = _get_cached_yolov5_dir()
        if cached_dir is not None:
            loaded = torch.hub.load(cached_dir, 'custom', path=model_path, source='local')
        else:
            loaded = torch.hub.load(
                'ultralytics/yolov5',
                'custom',
                path=model_path,
                source='github',
                force_reload=False,
            )
        loaded.conf = 0.75
        _yolo_model = loaded
        return _yolo_model

def process_language(sourceLang):
    try:        
        if sourceLang == "jp":
            return "ja"
        elif sourceLang == "ko":
            return "ko"
        elif sourceLang == "ch_sim":
            return "zh_cn"
        elif sourceLang == "en":
            return "en"
            
    except Exception as e:
        print(f"⚠️ Error saat memproses OCR: {e}")
        raise
    
def get_language_codes(sourceLang):
    mapping = {
        "jp": ("jp", "ja"),
        "ko": ("ko", "ko"),
        "ch_sim": ("ch_sim", "zh-cn"),
        "ch_tra": ("ch_tra", "zh-tw"),
        "en": ("en", "en")
    }

    if sourceLang not in mapping:
        raise ValueError(f"Unsupported language code: {sourceLang}")

    return mapping[sourceLang] 

MAX_OCR_CACHE = 2
_ocr_cache = OrderedDict()
_ocr_lock = threading.Lock()

def selectOCR(sourceLang):
    """Return a cached OCR reader instance, engine index, and translation code."""
    easyocr_code, translate_code = get_language_codes(sourceLang)
    index = 0 if easyocr_code == "jp" else 1

    with _ocr_lock:
        if easyocr_code in _ocr_cache:
            _ocr_cache.move_to_end(easyocr_code)
            return _ocr_cache[easyocr_code], index, translate_code

        ocr_instance = MangaOcr() if index == 0 else easyocr.Reader([easyocr_code])
        _ocr_cache[easyocr_code] = ocr_instance
        if len(_ocr_cache) > MAX_OCR_CACHE:
            _ocr_cache.popitem(last=False)
        return ocr_instance, index, translate_code

def clean_ocr_text(ocr_text):
    if not ocr_text:
        return ""
    cleaned_text = re.sub(r'\bLai\b', '!', ocr_text)
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
    return cleaned_text

def _parse_json_array(raw_text):
    # extract a JSON array from Gemini's response text.
    text = raw_text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find('[')
        end = text.rfind(']')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    print("⚠️ Gagal parse JSON dari Gemini, batch ini fallback ke googletrans")
    return []

def batch_gemini_translate(bubbles, source_lang, target_lang, api_key, batch_size=40, max_retries=1):
    api_key = api_key.strip().replace('"', '').replace("'", "")
    translations = {}

    items = [{"id": b["id"], "text": b["cleaned_text"]} for b in bubbles if b["cleaned_text"].strip()]
    if not items:
        return translations

    # url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent"

    for i in range(0, len(items), batch_size):
        chunk = items[i:i + batch_size]
        print(f"[Gemini] Batch translating {len(chunk)} teks (item {i+1}-{i+len(chunk)} dari {len(items)})")

        prompt = (
            f"You will translate comic/manga dialogue lines from {source_lang} to {target_lang}. "
            f"Below is a JSON array of objects, each with an \"id\" and \"text\" field. "
            f"Translate the \"text\" of each object naturally, keeping tone and context appropriate for a comic. "
            f"Respond with ONLY a valid JSON array (no markdown fences, no commentary), where each object has "
            f"the SAME \"id\" and a new \"translated\" field containing the translation. "
            f"Do not skip any id, and keep the array in the same order.\n\n"
            f"Input:\n{json.dumps(chunk, ensure_ascii=False)}"
        )
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3}
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'x-goog-api-key': api_key}
        )

        for attempt in range(max_retries + 1):
            try:
                with urllib.request.urlopen(req) as response:
                    result = json.loads(response.read().decode('utf-8'))
                    raw_text = result['candidates'][0]['content']['parts'][0]['text'].strip()
                    parsed = _parse_json_array(raw_text)
                    for obj in parsed:
                        if "id" in obj and "translated" in obj:
                            translations[obj["id"]] = obj["translated"]
                    break
            except urllib.error.HTTPError as e:
                error_body = e.read().decode('utf-8', errors='replace')
                if e.code in (429, 503) and attempt < max_retries:
                    if e.code == 429 and 'PerDay' in error_body:
                        print("Gemini daily quota habis, skip retry & fallback ke googletrans untuk batch ini")
                        break
                    wait = 4 * (attempt + 1)
                    if e.code == 429:
                        try:
                            err_json = json.loads(error_body)
                            for d in err_json.get("error", {}).get("details", []):
                                if d.get("@type", "").endswith("RetryInfo"):
                                    wait = float(d["retryDelay"].rstrip("s")) + 0.5
                        except Exception:
                            pass
                    print(f"Gemini batch {e.code}, retry in {wait:.1f}s (attempt {attempt+1}/{max_retries})")
                    time.sleep(wait)
                    continue
                print(f"Gemini batch API Error {e.code}: {error_body}")
                break
            except Exception as e:
                print(f"Gemini batch API Error: {e}")
                break

    return translations

async def _async_google_translate(items, source_lang, target_lang):
    """Translate bubble items asynchronously using googletrans v4.0.2."""
    async with Translator() as translator:
        texts = [item["text"] for item in items]
        results = await translator.translate(texts, src=source_lang, dest=target_lang)
        if not isinstance(results, list):
            results = [results]
        return {item["id"]: res.text for item, res in zip(items, results)}

def batch_google_translate(bubbles, source_lang, target_lang, existing_translations=None):
    """Translate any remaining untranslated bubbles via googletrans v4.0.2."""
    translations = dict(existing_translations) if existing_translations else {}
    pending = []

    for b in bubbles:
        if translations.get(b["id"]):
            continue
        if b["cleaned_text"].strip():
            pending.append({"id": b["id"], "text": b["cleaned_text"]})
        else:
            translations[b["id"]] = "[Teks tidak terbaca]"

    if pending:
        translations.update(asyncio.run(_async_google_translate(pending, source_lang, target_lang)))

    return translations

@lru_cache(maxsize=256)
def get_font(font_path, font_size):
    """Load and cache TrueType font objects across bubbles and pages."""
    return ImageFont.truetype(font_path, font_size)

@lru_cache(maxsize=2048)
def _split_syllables(word, target_lang):
    """Split a word into hyphenation syllables and cache the result."""
    if target_lang == 'id':
        dic = dic_id
    elif target_lang == 'en':
        dic = dic_en
    else:
        dic = None

    if dic:
        syllables = dic.inserted(word).split('-')
    else:
        syllables = list(word)

    if len(syllables) <= 1 and len(word) > 3:
        syllables = list(word)
    return tuple(syllables)

def break_word(word, draw, font, max_width, target_lang, remaining_lines=None, fail_on_overflow=False):
    if len(word) <= 5:
        return [word]

    syllables = _split_syllables(word, target_lang)

    lines = []
    current_part = ""
    for i, syl in enumerate(syllables):
        is_last_syl = (i == len(syllables) - 1)
        test_part = current_part + syl + ("" if is_last_syl else "-")
        bbox = draw.textbbox((0, 0), test_part, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current_part += syl
        else:
            if not current_part:
                if fail_on_overflow:
                    return None
                lines.append(syl + ("" if is_last_syl else "-"))
                current_part = ""
            else:
                lines.append(current_part + "-")
                current_part = syl
            if remaining_lines is not None:
                min_needed = len(lines) + (1 if (current_part or not is_last_syl) else 0)
                if min_needed > remaining_lines:
                    return None
    if current_part:
        lines.append(current_part)
    if remaining_lines is not None and len(lines) > remaining_lines:
        return None
    return lines

def wrap_text(text, draw, font, max_width, target_lang, max_lines=None):
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        if current_line:
            test_line = current_line + " " + word
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if (bbox[2] - bbox[0]) <= max_width:
                current_line = test_line
                continue
            lines.append(current_line)
            current_line = ""
            if max_lines is not None and len(lines) >= max_lines:
                return None
            bbox_word = draw.textbbox((0, 0), word, font=font)
            if (bbox_word[2] - bbox_word[0]) <= max_width:
                current_line = word
                continue
        else:
            bbox_word = draw.textbbox((0, 0), word, font=font)
            if (bbox_word[2] - bbox_word[0]) <= max_width:
                current_line = word
                continue

        if max_lines is not None and len(word) <= 5:
            return None

        rem = None if max_lines is None else (max_lines - len(lines))
        broken_lines = break_word(
            word,
            draw,
            font,
            max_width,
            target_lang,
            remaining_lines=rem,
            fail_on_overflow=(max_lines is not None),
        )
        if broken_lines is None:
            return None
        if broken_lines:
            lines.extend(broken_lines[:-1])
            current_line = broken_lines[-1]
        else:
            current_line = ""
        if max_lines is not None and len(lines) + (1 if current_line else 0) > max_lines:
            return None
    if current_line:
        lines.append(current_line)
    if max_lines is not None and len(lines) > max_lines:
        return None
    return lines

def extract_bubbles(image_path, ocr, index, translate_code, image_id, timings=None):
    # YOLO + OCR
    t_read0 = time.perf_counter()
    img_cv = cv2.imread(image_path)
    if img_cv is None:
        raise ValueError(f"Failed to read image: {image_path}")
    img_rgb = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB, dst=img_cv)
    height, width = img_rgb.shape[:2]
    t_read = time.perf_counter() - t_read0

    t_yolo0 = time.perf_counter()
    with torch.inference_mode():
        results = get_yolo_model()(img_rgb)
    detections = results.xyxy[0][:, :4].tolist()
    t_yolo = time.perf_counter() - t_yolo0

    img_pil = Image.fromarray(img_rgb) if index == 0 else None
    bubbles = []
    t_ocr0 = time.perf_counter()
    for bubble_idx, box in enumerate(detections):
        x1, y1, x2, y2 = (int(round(v)) for v in box)
        x1 = max(0, min(width, x1))
        y1 = max(0, min(height, y1))
        x2 = max(0, min(width, x2))
        y2 = max(0, min(height, y2))
        orig_box_width = x2 - x1
        orig_box_height = y2 - y1

        if orig_box_width <= 0 or orig_box_height <= 0:
            text = ""
        elif index == 0:
            cropped = img_pil.crop((x1, y1, x2, y2))
            text = ocr(cropped) or ""
        else:
            cropped_np = img_rgb[y1:y2, x1:x2]
            result = ocr.readtext(cropped_np, detail=0)
            text = " ".join(result) or ""

        cleaned_text = clean_ocr_text(text) or ""

        bubbles.append({
            "id": f"{image_id}_{bubble_idx}",
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "orig_box_width": orig_box_width,
            "orig_box_height": orig_box_height,
            "ocr_text": text,
            "cleaned_text": cleaned_text,
        })
    t_ocr = time.perf_counter() - t_ocr0

    if img_pil is None:
        img_pil = Image.fromarray(img_rgb)

    if timings is not None:
        timings["read"] = timings.get("read", 0.0) + t_read
        timings["yolo"] = timings.get("yolo", 0.0) + t_yolo
        timings["ocr"] = timings.get("ocr", 0.0) + t_ocr

    return img_pil, bubbles

def _measure_lines(translated, draw, font, avail_width, target_lang, line_height):
    """Wrap translated text and compute per-line widths and total block dimensions."""
    lines = wrap_text(translated, draw, font, avail_width, target_lang)
    total_height = line_height * len(lines)
    line_widths = []
    max_line_width = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        line_widths.append(w)
        if w > max_line_width:
            max_line_width = w
    return lines, line_widths, total_height, max_line_width

def _try_fit_layout(
    translated,
    draw,
    font,
    avail_width,
    avail_height,
    target_lang,
    line_spacing_factor,
    unbreakable_words,
    has_words,
):
    """Return layout tuple if text fits inside (avail_width, avail_height), else None."""
    ascent, descent = font.getmetrics()
    line_height = int((ascent + descent) * line_spacing_factor)
    if has_words and line_height > avail_height:
        return None

    for uw in unbreakable_words:
        bbox = draw.textbbox((0, 0), uw, font=font)
        if (bbox[2] - bbox[0]) > avail_width:
            return None

    max_lines = (avail_height // line_height) if (has_words and line_height > 0) else None
    lines = wrap_text(translated, draw, font, avail_width, target_lang, max_lines=max_lines)
    if lines is None:
        return None

    total_height = line_height * len(lines)
    if total_height > avail_height:
        return None

    line_widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        if w > avail_width:
            return None
        line_widths.append(w)

    return font, lines, line_widths, line_height, total_height

def render_bubbles(img_pil, bubbles, translations, targetLang,
                    font_path="static/fonts/Winky_Rough/WinkyRough-Regular.ttf",
                    draw=None):
    if not bubbles:
        return
    if draw is None:
        draw = ImageDraw.Draw(img_pil)
    line_spacing_factor = 1.05
    for b in bubbles:
        cleaned_text = b["cleaned_text"]
        if cleaned_text.strip():
            translated = translations.get(b["id"]) or "[Teks tidak terbaca]"
            translated = re.sub(r'\bLai\b', '!', translated)
            translated = translated.replace('．', '.').replace('…', '...').replace('。', '.')
            translated = re.sub(r'([.?!])([a-zA-Z])', r'\1 \2', translated)
        else:
            translated = "[Teks tidak terbaca]"

        print("OCR Result:", b["ocr_text"])
        print("Cleaned Text:", cleaned_text)
        print("Translated:", translated)

        x1, y1, x2, y2 = b["x1"], b["y1"], b["x2"], b["y2"]
        box_width = b["orig_box_width"]
        box_height = b["orig_box_height"]

        # Text is allowed to expand 22% to the left and 22% to the right (1.44x total box_width)
        text_box_width = int(box_width * 1.22)
        avail_width = max(10, text_box_width)
        avail_height = max(10, box_height - 4)

        words = translated.split()
        has_words = bool(words)
        unbreakable_words = tuple(sorted({w for w in words if len(w) <= 5}, key=len, reverse=True)[:3])

        fitted = None
        lo, hi = 12, 110
        while lo <= hi:
            mid = (lo + hi) // 2
            font = get_font(font_path, mid)
            res = _try_fit_layout(
                translated,
                draw,
                font,
                avail_width,
                avail_height,
                targetLang,
                line_spacing_factor,
                unbreakable_words,
                has_words,
            )
            if res is not None:
                fitted = res
                lo = mid + 1
            else:
                hi = mid - 1

        if fitted is None:
            font = get_font(font_path, 12)
            ascent, descent = font.getmetrics()
            line_height = int((ascent + descent) * line_spacing_factor)
            lines, line_widths, total_height, _ = _measure_lines(
                translated, draw, font, avail_width, targetLang, line_height
            )
        else:
            font, lines, line_widths, line_height, total_height = fitted

        # Inset by ~1.5% (min 1px) so the background fits 100% snugly inside the YOLOv5 detection box
        inset_x = max(1, int(box_width * 0.015))
        inset_y = max(1, int(box_height * 0.015))

        rect_x1 = x1 + inset_x
        rect_y1 = y1 + inset_y
        rect_x2 = max(rect_x1, x2 - inset_x - 1)
        rect_y2 = max(rect_y1, y2 - inset_y - 1)

        draw.rectangle([rect_x1, rect_y1, rect_x2, rect_y2], fill="white")

        current_y = y1 + (box_height - total_height) // 2
        for line, line_width in zip(lines, line_widths):
            text_x = x1 + (box_width - line_width) // 2
            draw.text(
                (text_x, current_y), 
                line, 
                font=font, 
                fill="black", 
                stroke_width=2, 
                stroke_fill="white"
            )
            current_y += line_height