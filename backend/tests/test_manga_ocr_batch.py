import io
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np
import torch
from manga_ocr import MangaOcr
from PIL import Image

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def _import_image_processor():
    if "image_processor" in sys.modules:
        return sys.modules["image_processor"]
    import image_processor  # noqa: E402
    return image_processor


def _import_app():
    if "app" in sys.modules:
        return sys.modules["app"]
    with patch("os.makedirs"):
        import app  # noqa: E402
    return app


def _make_stub_manga_ocr(area_to_raw_text):
    stub = MangaOcr.__new__(MangaOcr)
    records = {
        "chunk_sizes": [],
        "chunk_areas": [],
        "inference_modes": [],
        "generate_kwargs": [],
        "grayscale_rgb": [],
    }

    def fake_processor(chunk_imgs, return_tensors="pt"):
        areas = []
        for im in chunk_imgs:
            areas.append(im.size[0] * im.size[1])
            arr = np.asarray(im)
            # .convert("L").convert("RGB") yields identical R==G==B channels
            records["grayscale_rgb"].append(
                im.mode == "RGB"
                and np.array_equal(arr[:, :, 0], arr[:, :, 1])
                and np.array_equal(arr[:, :, 1], arr[:, :, 2])
            )
        records["chunk_sizes"].append(len(chunk_imgs))
        records["chunk_areas"].append(areas)
        # Encode areas into pixel_values tensor so generate() maps back to raw text
        pv = torch.tensor([[float(a)] for a in areas], dtype=torch.float32)
        return SimpleNamespace(pixel_values=pv)

    class FakeModel:
        device = torch.device("cpu")

        def generate(self, pixel_values, **kwargs):
            records["inference_modes"].append(torch.is_inference_mode_enabled())
            records["generate_kwargs"].append(dict(kwargs))
            return pixel_values.to(torch.long)

    class FakeTokenizer:
        def batch_decode(self, generated_ids, skip_special_tokens=True):
            return [area_to_raw_text[int(row[0].item())] for row in generated_ids]

    stub.processor = fake_processor
    stub.model = FakeModel()
    stub.tokenizer = FakeTokenizer()
    return stub, records


class TestMangaOcrBatching(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ip = _import_image_processor()
        cls.flask_app_mod = _import_app()

    def test_batch_manga_ocr_sorts_chunks_and_restores_order(self):
        # Distinct crop sizes & areas: 1600, 100, 900, 400, 2500
        dims = [(40, 40), (10, 10), (30, 30), (20, 20), (50, 50)]
        # Non-gray colors verify .convert("L").convert("RGB") runs before processor
        crops = [Image.new("RGB", wh, (200, 50, 10)) for wh in dims]
        area_to_raw = {
            100: "テ ス ト…",
            400: "は い",
            900: "な に !?",
            1600: "わ か っ た",
            2500: "よ し",
        }
        stub, records = _make_stub_manga_ocr(area_to_raw)

        out = self.ip.batch_manga_ocr(stub, crops, batch_size=2)

        self.assertEqual(records["chunk_sizes"], [2, 2, 1])
        self.assertEqual(records["chunk_areas"], [[100, 400], [900, 1600], [2500]])
        self.assertEqual(records["inference_modes"], [True, True, True])
        self.assertTrue(all(records["grayscale_rgb"]))
        for kw in records["generate_kwargs"]:
            self.assertEqual(kw.get("max_length"), 300)
            self.assertNotIn("num_beams", kw)

        # Returned texts must match original crop order + manga_ocr post_process (half->fullwidth)
        self.assertEqual(out, ["わかった", "テスト．．．", "なに！？", "はい", "よし"])

    def test_batch_manga_ocr_handles_empty_and_non_manga_ocr_callable(self):
        stub, records = _make_stub_manga_ocr({})
        self.assertEqual(self.ip.batch_manga_ocr(stub, []), [])
        self.assertEqual(records["chunk_sizes"], [])

        calls = []

        def fake_callable_ocr(crop):
            calls.append(crop.size)
            return "text" if crop.size == (10, 10) else ""

        crops = [Image.new("RGB", (10, 10)), Image.new("RGB", (20, 20))]
        self.assertEqual(self.ip.batch_manga_ocr(fake_callable_ocr, crops), ["text", ""])
        self.assertEqual(calls, [(10, 10), (20, 20)])

    def test_detect_bubbles_clamps_skips_degenerate_and_records_timings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = os.path.join(tmpdir, "page.png")
            cv2.imwrite(img_path, np.zeros((80, 100, 3), dtype=np.uint8))

            inference_flags = []

            def fake_yolo(img_rgb):
                inference_flags.append(torch.is_inference_mode_enabled())
                tensor = torch.tensor(
                    [
                        [-5.0, 5.0, 25.0, 35.0, 0.9, 0.0],   # clamped to (0, 5, 25, 35)
                        [110.0, 10.0, 120.0, 30.0, 0.85, 0.0],  # clamped to zero width -> skipped from pending_crops
                    ],
                    dtype=torch.float32,
                )
                return SimpleNamespace(xyxy=[tensor])

            timings = {}
            with (
                patch.object(self.ip, "get_yolo_model", return_value=fake_yolo),
                patch.object(
                    self.ip.ImageDraw,
                    "Draw",
                    side_effect=AssertionError("ImageDraw.Draw should not run in detect_bubbles"),
                ),
            ):
                img_pil, bubbles, pending_crops = self.ip.detect_bubbles(
                    img_path, image_id=1, timings=timings
                )

        self.assertEqual(inference_flags, [True])
        self.assertEqual(img_pil.size, (100, 80))
        self.assertEqual(len(bubbles), 2)
        self.assertEqual((bubbles[0]["x1"], bubbles[0]["y1"], bubbles[0]["x2"], bubbles[0]["y2"]), (0, 5, 25, 35))
        self.assertEqual(bubbles[1]["orig_box_width"], 0)
        self.assertEqual(len(pending_crops), 1)
        self.assertIs(pending_crops[0][0], bubbles[0])
        self.assertEqual(pending_crops[0][1].size, (25, 30))
        self.assertIn("read", timings)
        self.assertIn("yolo", timings)

    def test_process_image_jp_batches_manga_ocr_across_multiple_pages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            uploads_dir = os.path.join(tmpdir, "uploads")
            os.makedirs(uploads_dir)
            history_file = os.path.join(tmpdir, "history.json")
            font_path = os.path.join(BACKEND_DIR, "static", "fonts", "Winky_Rough", "WinkyRough-Regular.ttf")

            def make_png_bytes(w, h):
                buf = io.BytesIO()
                Image.new("RGB", (w, h), (20, 20, 20)).save(buf, format="PNG")
                buf.seek(0)
                return buf

            # Page 1 (width 200) -> 2 bubbles; Page 2 (width 220) -> 3 bubbles (total 5)
            def fake_yolo(img_rgb):
                if img_rgb.shape[1] == 200:
                    boxes = [
                        [10.0, 10.0, 30.0, 30.0, 0.9, 0.0],   # area 400
                        [40.0, 10.0, 90.0, 60.0, 0.9, 0.0],   # area 2500
                    ]
                else:
                    boxes = [
                        [10.0, 10.0, 20.0, 20.0, 0.9, 0.0],   # area 100
                        [30.0, 10.0, 60.0, 40.0, 0.9, 0.0],   # area 900
                        [70.0, 10.0, 110.0, 50.0, 0.9, 0.0],  # area 1600
                    ]
                return SimpleNamespace(xyxy=[torch.tensor(boxes, dtype=torch.float32)])

            area_to_raw = {
                400: "ページ1バブル1",
                2500: "ページ1バブル2",
                100: "ページ2バブル1",
                900: "ページ2バブル2",
                1600: "ページ2バブル3",
            }
            stub_ocr, records = _make_stub_manga_ocr(area_to_raw)

            seen_bubbles = []

            def fake_google_translate(bubbles, src, tgt, existing=None):
                seen_bubbles.extend((b["id"], b["cleaned_text"]) for b in bubbles)
                return {b["id"]: f"T:{b['cleaned_text']}" for b in bubbles}

            orig_render = self.ip.render_bubbles

            def render_with_abs_font(img_pil, bubbles, translations, target_lang):
                return orig_render(img_pil, bubbles, translations, target_lang, font_path=font_path)

            client = self.flask_app_mod.app.test_client()
            with (
                patch.object(self.flask_app_mod, "UPLOAD_FOLDER", uploads_dir),
                patch.object(self.flask_app_mod, "HISTORY_FILE", history_file),
                patch.object(self.flask_app_mod, "selectOCR", return_value=(stub_ocr, 0, "ja")),
                patch.object(self.ip, "get_yolo_model", return_value=fake_yolo),
                patch.object(self.flask_app_mod, "batch_google_translate", side_effect=fake_google_translate),
                patch.object(self.flask_app_mod, "render_bubbles", side_effect=render_with_abs_font),
            ):
                resp = client.post(
                    "/process-image",
                    data={
                        "source": "jp",
                        "target": "id",
                        "engine": "googletrans",
                        "image[]": [
                            (make_png_bytes(200, 120), "page1.png"),
                            (make_png_bytes(220, 120), "page2.png"),
                        ],
                    },
                    content_type="multipart/form-data",
                )

            self.assertEqual(resp.status_code, 200)
            payload = resp.get_json()
            self.assertEqual(len(payload["results"]), 2)
            # Single cross-page batch of 5 bubbles, sorted by area
            self.assertEqual(records["chunk_sizes"], [5])
            self.assertEqual(records["chunk_areas"], [[100, 400, 900, 1600, 2500]])
            # Mapped back in exact page/bubble order (post_process converts ASCII digits to full-width)
            self.assertEqual(
                seen_bubbles,
                [
                    ("0_0", "ページ１バブル１"),
                    ("0_1", "ページ１バブル２"),
                    ("1_0", "ページ２バブル１"),
                    ("1_1", "ページ２バブル２"),
                    ("1_2", "ページ２バブル３"),
                ],
            )
            output_files = [f for f in os.listdir(uploads_dir) if f.startswith("output_")]
            self.assertEqual(len(output_files), 2)


if __name__ == "__main__":
    unittest.main()
