import io
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import torch
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


def _write_test_image(path, width=100, height=80, box=(10, 20, 50, 60), box_rgb=(12, 200, 34)):
    img = np.zeros((height, width, 3), dtype=np.uint8)
    x1, y1, x2, y2 = box
    img[y1:y2, x1:x2] = box_rgb
    # OpenCV expects BGR when writing to disk
    cv2.imwrite(path, cv2.cvtColor(img, cv2.COLOR_RGB2BGR))


class TestBubbleExtractionAndRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ip = _import_image_processor()
        cls.flask_app_mod = _import_app()

    def _make_fake_yolo(self, tensor_rows):
        inference_states = []

        def fake_model(img_rgb):
            inference_states.append(torch.is_inference_mode_enabled())
            tensor = torch.tensor(tensor_rows, dtype=torch.float32) if tensor_rows else torch.zeros((0, 6), dtype=torch.float32)

            def fail_pandas():
                raise AssertionError("results.pandas() should not be called")

            return SimpleNamespace(xyxy=[tensor], pandas=fail_pandas)

        return fake_model, inference_states

    def test_easyocr_uses_numpy_view_without_pil_crop_or_pandas_or_draw(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = os.path.join(tmpdir, "page.png")
            _write_test_image(img_path, width=100, height=80, box=(10, 21, 50, 60), box_rgb=(12, 200, 34))

            fake_model, inference_states = self._make_fake_yolo([[10.4, 20.6, 50.2, 60.1, 0.95, 0.0]])
            captured = {}

            class FakeEasyOCR:
                def readtext(self, arr, detail=0):
                    captured["arr"] = arr
                    captured["detail"] = detail
                    return ["HELLO", "WORLD"]

            with (
                patch.object(self.ip, "get_yolo_model", return_value=fake_model),
                patch.object(Image.Image, "crop", side_effect=AssertionError("PIL crop should not run for EasyOCR")),
                patch.object(self.ip.ImageDraw, "Draw", side_effect=AssertionError("ImageDraw.Draw should not run in extract_bubbles")),
            ):
                img_pil, bubbles = self.ip.extract_bubbles(img_path, FakeEasyOCR(), 1, "en", image_id=0)

        self.assertEqual(inference_states, [True])
        self.assertIsInstance(img_pil, Image.Image)
        self.assertEqual(img_pil.size, (100, 80))
        self.assertEqual(captured["detail"], 0)
        self.assertIsInstance(captured["arr"], np.ndarray)
        self.assertIsNotNone(captured["arr"].base)
        self.assertEqual(captured["arr"].shape, (39, 40, 3))
        self.assertEqual(tuple(captured["arr"][0, 0]), (12, 200, 34))

        self.assertEqual(len(bubbles), 1)
        self.assertEqual(bubbles[0]["id"], "0_0")
        self.assertEqual((bubbles[0]["x1"], bubbles[0]["y1"], bubbles[0]["x2"], bubbles[0]["y2"]), (10, 21, 50, 60))
        self.assertEqual(bubbles[0]["orig_box_width"], 40)
        self.assertEqual(bubbles[0]["orig_box_height"], 39)
        self.assertEqual(bubbles[0]["cleaned_text"], "HELLO WORLD")

    def test_manga_ocr_receives_rgb_pil_crop_without_draw(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = os.path.join(tmpdir, "manga.png")
            _write_test_image(img_path, width=100, height=80, box=(10, 20, 50, 60), box_rgb=(200, 40, 90))

            fake_model, inference_states = self._make_fake_yolo([[10.0, 20.0, 50.0, 60.0, 0.9, 0.0]])
            captured = {}

            def fake_manga_ocr(crop_img):
                captured["crop"] = crop_img
                return "テスト　"

            with (
                patch.object(self.ip, "get_yolo_model", return_value=fake_model),
                patch.object(self.ip.ImageDraw, "Draw", side_effect=AssertionError("ImageDraw.Draw should not run in extract_bubbles")),
            ):
                img_pil, bubbles = self.ip.extract_bubbles(img_path, fake_manga_ocr, 0, "ja", image_id=2)

        self.assertEqual(inference_states, [True])
        self.assertIsInstance(img_pil, Image.Image)
        self.assertIsInstance(captured["crop"], Image.Image)
        self.assertEqual(captured["crop"].mode, "RGB")
        self.assertEqual(captured["crop"].size, (40, 40))
        self.assertEqual(captured["crop"].getpixel((0, 0)), (200, 40, 90))
        self.assertEqual(bubbles[0]["id"], "2_0")
        self.assertEqual(bubbles[0]["cleaned_text"], "テスト")

    def test_handles_empty_detections_and_degenerate_boxes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = os.path.join(tmpdir, "empty.png")
            _write_test_image(img_path, width=100, height=80)

            empty_model, _ = self._make_fake_yolo([])
            with patch.object(self.ip, "get_yolo_model", return_value=empty_model):
                img_pil, bubbles = self.ip.extract_bubbles(img_path, MagicMock(), 1, "en", image_id=0)
            self.assertEqual(img_pil.size, (100, 80))
            self.assertEqual(bubbles, [])

            # Box clamped outside bounds -> zero width -> OCR must not be called
            degen_model, _ = self._make_fake_yolo([[105.0, 10.0, 120.0, 40.0, 0.85, 0.0]])
            ocr_mock = MagicMock()
            with patch.object(self.ip, "get_yolo_model", return_value=degen_model):
                _, degen_bubbles = self.ip.extract_bubbles(img_path, ocr_mock, 1, "en", image_id=0)
            ocr_mock.readtext.assert_not_called()
            self.assertEqual(len(degen_bubbles), 1)
            self.assertEqual(degen_bubbles[0]["orig_box_width"], 0)
            self.assertEqual(degen_bubbles[0]["cleaned_text"], "")

    def test_invalid_image_path_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.ip.extract_bubbles("non_existent_file_12345.png", MagicMock(), 1, "en", image_id=0)

    def test_extract_bubbles_records_timings_when_dict_provided(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = os.path.join(tmpdir, "timed.png")
            _write_test_image(img_path, width=100, height=80, box=(10, 20, 50, 60))

            fake_model, _ = self._make_fake_yolo([[10.0, 20.0, 50.0, 60.0, 0.9, 0.0]])
            fake_ocr = MagicMock()
            fake_ocr.readtext.return_value = ["Hi"]
            timings = {}

            with patch.object(self.ip, "get_yolo_model", return_value=fake_model):
                _, bubbles = self.ip.extract_bubbles(
                    img_path, fake_ocr, 1, "en", image_id=0, timings=timings
                )

        self.assertEqual(len(bubbles), 1)
        for key in ("read", "yolo", "ocr"):
            self.assertIn(key, timings)
            self.assertIsInstance(timings[key], float)
            self.assertGreaterEqual(timings[key], 0.0)

    def test_render_bubbles_creates_draw_in_phase3_and_skips_empty(self):
        img_empty = Image.new("RGB", (100, 80), "black")
        with patch.object(self.ip.ImageDraw, "Draw", side_effect=AssertionError("Should skip Draw on empty bubbles")):
            self.ip.render_bubbles(img_empty, [], {}, "id")

        img = Image.new("RGB", (200, 120), "black")
        bubbles = [{
            "id": "0_0",
            "x1": 20, "y1": 20, "x2": 180, "y2": 100,
            "orig_box_width": 160,
            "orig_box_height": 80,
            "ocr_text": "hello",
            "cleaned_text": "hello",
        }]
        font_path = os.path.join(BACKEND_DIR, "static", "fonts", "Winky_Rough", "WinkyRough-Regular.ttf")
        self.ip.render_bubbles(img, bubbles, {"0_0": "Halo"}, "id", font_path=font_path)
        # Center region inside bubble should be drawn (white background / stroked text, no longer pure black)
        self.assertEqual(img.getpixel((25, 25)), (255, 255, 255))

    def test_process_image_endpoint_integration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            uploads_dir = os.path.join(tmpdir, "uploads")
            os.makedirs(uploads_dir)
            history_file = os.path.join(tmpdir, "history.json")
            font_path = os.path.join(BACKEND_DIR, "static", "fonts", "Winky_Rough", "WinkyRough-Regular.ttf")

            buf = io.BytesIO()
            Image.new("RGB", (160, 100), (10, 10, 10)).save(buf, format="PNG")
            buf.seek(0)

            fake_model, _ = self._make_fake_yolo([[10.0, 10.0, 150.0, 90.0, 0.9, 0.0]])
            fake_ocr = MagicMock()
            fake_ocr.readtext.return_value = ["Hello"]

            orig_render = self.ip.render_bubbles

            def render_with_abs_font(img_pil, bubbles, translations, target_lang):
                return orig_render(img_pil, bubbles, translations, target_lang, font_path=font_path)

            client = self.flask_app_mod.app.test_client()
            with (
                patch.object(self.flask_app_mod, "UPLOAD_FOLDER", uploads_dir),
                patch.object(self.flask_app_mod, "HISTORY_FILE", history_file),
                patch.object(self.flask_app_mod, "selectOCR", return_value=(fake_ocr, 1, "en")),
                patch.object(self.ip, "get_yolo_model", return_value=fake_model),
                patch.object(self.flask_app_mod, "batch_google_translate", return_value={"0_0": "Halo"}),
                patch.object(self.flask_app_mod, "render_bubbles", side_effect=render_with_abs_font),
            ):
                resp = client.post(
                    "/process-image",
                    data={
                        "source": "en",
                        "target": "id",
                        "engine": "googletrans",
                        "image[]": (buf, "page1.png"),
                    },
                    content_type="multipart/form-data",
                )

            self.assertEqual(resp.status_code, 200)
            payload = resp.get_json()
            self.assertEqual(len(payload["results"]), 1)
            files_in_dir = os.listdir(uploads_dir)
            self.assertTrue(any(f.startswith("output_") and f.endswith(".png") for f in files_in_dir))


if __name__ == "__main__":
    unittest.main()
