import io
import json
import os
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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


class TestWifiClientServerMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ip = _import_image_processor()
        cls.app_mod = _import_app()

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.upload_dir = os.path.join(self.temp_dir.name, "uploads")
        os.makedirs(self.upload_dir, exist_ok=True)
        self.history_file = os.path.join(self.temp_dir.name, "history.json")
        self.settings_file = os.path.join(self.temp_dir.name, "settings.json")
        self.client = self.app_mod.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _patched_paths(self):
        return (
            patch.object(self.app_mod, "UPLOAD_FOLDER", self.upload_dir),
            patch.object(self.app_mod, "HISTORY_FILE", self.history_file),
            patch.object(self.app_mod, "SETTINGS_FILE", self.settings_file),
        )

    def _make_image_bytes(self, w=160, h=100):
        buf = io.BytesIO()
        Image.new("RGB", (w, h), (10, 10, 10)).save(buf, format="PNG")
        buf.seek(0)
        return buf

    def _make_fake_yolo(self):
        def fake_model(_img_rgb):
            tensor = torch.tensor([[10.0, 10.0, 150.0, 90.0, 0.9, 0.0]], dtype=torch.float32)
            return SimpleNamespace(xyxy=[tensor])

        return fake_model

    def test_get_settings_returns_defaults_when_file_missing(self):
        with (
            patch.object(self.app_mod, "SETTINGS_FILE", self.settings_file),
        ):
            res = self.client.get("/settings")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), {"engine": "googletrans", "apiKey": ""})

    def test_post_settings_persists_trims_supports_partial_update_and_validates(self):
        with patch.object(self.app_mod, "SETTINGS_FILE", self.settings_file):
            # Save gemini + whitespace-padded API key
            res = self.client.post(
                "/settings",
                json={"engine": "gemini", "apiKey": "  my-secret-key  "},
            )
            self.assertEqual(res.status_code, 200)
            self.assertEqual(
                res.get_json(),
                {"status": "success", "engine": "gemini", "apiKey": "my-secret-key"},
            )

            # Partial update: change engine only, keep existing apiKey
            res_partial = self.client.post("/settings", json={"engine": "googletrans"})
            self.assertEqual(res_partial.status_code, 200)
            self.assertEqual(
                res_partial.get_json(),
                {"status": "success", "engine": "googletrans", "apiKey": "my-secret-key"},
            )

            # Confirm persisted via GET
            res_get = self.client.get("/settings")
            self.assertEqual(res_get.status_code, 200)
            self.assertEqual(
                res_get.get_json(),
                {"engine": "googletrans", "apiKey": "my-secret-key"},
            )

            # Validation: non-JSON / non-dict / invalid engine / non-string apiKey
            bad_body = self.client.post("/settings", data="not-json", content_type="text/plain")
            self.assertEqual(bad_body.status_code, 400)

            bad_engine = self.client.post("/settings", json={"engine": "deepl"})
            self.assertEqual(bad_engine.status_code, 400)

            bad_key = self.client.post("/settings", json={"apiKey": 12345})
            self.assertEqual(bad_key.status_code, 400)

    def test_process_image_returns_relative_paths_and_falls_back_to_saved_settings(self):
        with open(self.settings_file, "w", encoding="utf-8") as f:
            json.dump({"engine": "gemini", "apiKey": "server-key-xyz"}, f)

        fake_ocr = MagicMock()
        fake_ocr.readtext.return_value = ["Hello"]
        font_path = os.path.join(BACKEND_DIR, "static", "fonts", "Winky_Rough", "WinkyRough-Regular.ttf")
        orig_render = self.ip.render_bubbles

        def render_with_abs_font(img_pil, bubbles, translations, target_lang):
            return orig_render(img_pil, bubbles, translations, target_lang, font_path=font_path)

        with (
            patch.object(self.app_mod, "UPLOAD_FOLDER", self.upload_dir),
            patch.object(self.app_mod, "HISTORY_FILE", self.history_file),
            patch.object(self.app_mod, "SETTINGS_FILE", self.settings_file),
            patch.object(self.app_mod, "selectOCR", return_value=(fake_ocr, 1, "en")),
            patch.object(self.ip, "get_yolo_model", return_value=self._make_fake_yolo()),
            patch.object(self.app_mod, "batch_gemini_translate", return_value={"0_0": "Halo"}) as mock_gemini,
            patch.object(self.app_mod, "batch_google_translate", side_effect=lambda b, s, t, tr: tr),
            patch.object(self.app_mod, "render_bubbles", side_effect=render_with_abs_font),
        ):
            # Omit engine and apiKey from form data -> uses saved server settings
            resp = self.client.post(
                "/process-image",
                data={
                    "source": "en",
                    "target": "id",
                    "image[]": (self._make_image_bytes(), "page1.png"),
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(resp.status_code, 200)
        mock_gemini.assert_called_once()
        self.assertEqual(mock_gemini.call_args[0][3], "server-key-xyz")

        payload = resp.get_json()
        self.assertEqual(len(payload["results"]), 1)
        result = payload["results"][0]
        self.assertTrue(result["original"].startswith("/static/uploads/"))
        self.assertTrue(result["translated"].startswith("/static/uploads/output_"))
        self.assertNotIn("127.0.0.1", result["original"])
        self.assertNotIn("127.0.0.1", result["translated"])

        with open(self.history_file, "r", encoding="utf-8") as f:
            saved_history = json.load(f)
        self.assertEqual(len(saved_history), 1)
        self.assertEqual(saved_history[0]["name"], "")
        self.assertEqual(saved_history[0]["engine"], "gemini")
        self.assertEqual(saved_history[0]["images"], payload["results"])

    def test_process_image_handles_non_ascii_mobile_filenames(self):
        fake_ocr = MagicMock()
        fake_ocr.readtext.return_value = ["Hello"]
        font_path = os.path.join(BACKEND_DIR, "static", "fonts", "Winky_Rough", "WinkyRough-Regular.ttf")
        orig_render = self.ip.render_bubbles

        def render_with_abs_font(img_pil, bubbles, translations, target_lang):
            return orig_render(img_pil, bubbles, translations, target_lang, font_path=font_path)

        with (
            patch.object(self.app_mod, "UPLOAD_FOLDER", self.upload_dir),
            patch.object(self.app_mod, "HISTORY_FILE", self.history_file),
            patch.object(self.app_mod, "SETTINGS_FILE", self.settings_file),
            patch.object(self.app_mod, "selectOCR", return_value=(fake_ocr, 1, "en")),
            patch.object(self.ip, "get_yolo_model", return_value=self._make_fake_yolo()),
            patch.object(self.app_mod, "batch_google_translate", return_value={"0_0": "Halo"}),
            patch.object(self.app_mod, "render_bubbles", side_effect=render_with_abs_font),
        ):
            resp = self.client.post(
                "/process-image",
                data={
                    "source": "en",
                    "target": "id",
                    "engine": "googletrans",
                    "image[]": [
                        (self._make_image_bytes(), "ページ1.jpg"),
                        (self._make_image_bytes(), "ページ.png"),
                    ],
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(resp.status_code, 200)
        results = resp.get_json()["results"]
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["original"].endswith(".jpg"))
        self.assertTrue(results[0]["translated"].endswith(".jpg"))
        self.assertTrue(results[1]["original"].endswith(".png"))
        self.assertTrue(results[1]["translated"].endswith(".png"))
        for item in results:
            orig_fname = os.path.basename(item["original"])
            trans_fname = os.path.basename(item["translated"])
            self.assertTrue(os.path.isfile(os.path.join(self.upload_dir, orig_fname)))
            self.assertTrue(os.path.isfile(os.path.join(self.upload_dir, trans_fname)))

    def test_get_history_normalizes_legacy_localhost_urls_and_default_name(self):
        legacy_history = [
            {
                "id": 2001,
                "date": "21/11/2026, 10.00.00",
                "sourceLang": "jp",
                "targetLang": "id",
                "engine": "gemini",
                "images": [
                    {
                        "original": "http://127.0.0.1:5000/static/uploads/legacy_1.jpg",
                        "translated": "http://127.0.0.1:5000/static/uploads/output_legacy_1.jpg",
                    }
                ],
            }
        ]
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(legacy_history, f)

        with patch.object(self.app_mod, "HISTORY_FILE", self.history_file):
            res = self.client.get("/history")

        self.assertEqual(res.status_code, 200)
        items = res.get_json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "")
        self.assertEqual(
            items[0]["images"][0],
            {
                "original": "/static/uploads/legacy_1.jpg",
                "translated": "/static/uploads/output_legacy_1.jpg",
            },
        )

    def test_patch_history_batch_renames_trims_clamps_and_validates(self):
        history = [
            {
                "id": 3001,
                "name": "",
                "date": "21/11/2026, 10.00.00",
                "sourceLang": "jp",
                "targetLang": "id",
                "engine": "googletrans",
                "images": [],
            }
        ]
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(history, f)

        with patch.object(self.app_mod, "HISTORY_FILE", self.history_file):
            long_name = "  " + ("A" * 95) + "  "
            res = self.client.patch("/history/3001", json={"name": long_name})
            self.assertEqual(res.status_code, 200)
            self.assertEqual(
                res.get_json(),
                {"status": "success", "id": 3001, "name": "A" * 80},
            )

            with open(self.history_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(saved[0]["name"], "A" * 80)

            res_missing = self.client.patch("/history/9999", json={"name": "Chapter 1"})
            self.assertEqual(res_missing.status_code, 404)

            res_invalid = self.client.patch("/history/3001", json={"name": 123})
            self.assertEqual(res_invalid.status_code, 400)

    def test_delete_history_batch_removes_files_with_relative_urls(self):
        orig_path = os.path.join(self.upload_dir, "rel_page_1.png")
        trans_path = os.path.join(self.upload_dir, "output_rel_page_1.png")
        for p in (orig_path, trans_path):
            with open(p, "wb") as f:
                f.write(b"png")

        history = [
            {
                "id": 4001,
                "name": "Chapter 4",
                "date": "21/11/2026, 10.00.00",
                "sourceLang": "jp",
                "targetLang": "id",
                "engine": "googletrans",
                "images": [
                    {
                        "original": "/static/uploads/rel_page_1.png",
                        "translated": "/static/uploads/output_rel_page_1.png",
                    }
                ],
            }
        ]
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(history, f)

        with (
            patch.object(self.app_mod, "HISTORY_FILE", self.history_file),
            patch.object(self.app_mod, "UPLOAD_FOLDER", self.upload_dir),
        ):
            res = self.client.delete("/history/4001")

        self.assertEqual(res.status_code, 200)
        self.assertFalse(os.path.exists(orig_path))
        self.assertFalse(os.path.exists(trans_path))

    def test_concurrent_settings_and_history_updates_preserve_valid_json(self):
        history = [
            {
                "id": 5000 + i,
                "name": "",
                "date": "21/11/2026, 10.00.00",
                "sourceLang": "jp",
                "targetLang": "id",
                "engine": "googletrans",
                "images": [],
            }
            for i in range(6)
        ]
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(history, f)

        errors = []
        barrier = threading.Barrier(12)

        def rename_worker(idx):
            client = self.app_mod.app.test_client()
            try:
                barrier.wait(timeout=5)
                resp = client.patch(f"/history/{5000 + idx}", json={"name": f"Batch {idx}"})
                if resp.status_code != 200:
                    errors.append(f"rename {idx}: {resp.status_code}")
            except Exception as exc:
                errors.append(str(exc))

        def settings_worker(idx):
            client = self.app_mod.app.test_client()
            try:
                barrier.wait(timeout=5)
                engine = "gemini" if idx % 2 == 0 else "googletrans"
                resp = client.post("/settings", json={"engine": engine, "apiKey": f"key-{idx}"})
                if resp.status_code != 200:
                    errors.append(f"settings {idx}: {resp.status_code}")
            except Exception as exc:
                errors.append(str(exc))

        with (
            patch.object(self.app_mod, "HISTORY_FILE", self.history_file),
            patch.object(self.app_mod, "SETTINGS_FILE", self.settings_file),
        ):
            threads = (
                [threading.Thread(target=rename_worker, args=(i,)) for i in range(6)]
                + [threading.Thread(target=settings_worker, args=(i,)) for i in range(6)]
            )
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

        self.assertEqual(errors, [])
        with open(self.history_file, "r", encoding="utf-8") as f:
            final_history = json.load(f)
        self.assertEqual([entry["name"] for entry in final_history], [f"Batch {i}" for i in range(6)])

        with open(self.settings_file, "r", encoding="utf-8") as f:
            final_settings = json.load(f)
        self.assertIn(final_settings["engine"], {"gemini", "googletrans"})
        self.assertTrue(final_settings["apiKey"].startswith("key-"))


if __name__ == "__main__":
    unittest.main()
