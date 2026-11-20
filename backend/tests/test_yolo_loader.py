import ast
import importlib
import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def _import_image_processor():
    if "image_processor" in sys.modules:
        return sys.modules["image_processor"]
    import image_processor  # noqa: E402
    return image_processor


class TestYoloLoader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ip = _import_image_processor()

    def setUp(self):
        self._prev_model = self.ip._yolo_model
        self.ip._yolo_model = None

    def tearDown(self):
        self.ip._yolo_model = self._prev_model

    def test_import_does_not_load_yolo_eagerly(self):
        prev = sys.modules.pop("image_processor", None)
        try:
            with patch("torch.hub.load") as mock_load:
                imported = importlib.import_module("image_processor")
            mock_load.assert_not_called()
            self.assertIsNone(imported._yolo_model)
        finally:
            if prev is not None:
                sys.modules["image_processor"] = prev

    def test_uses_local_hub_cache_when_available(self):
        with tempfile.TemporaryDirectory() as tmp_hub:
            cached_repo = os.path.join(tmp_hub, "ultralytics_yolov5_master")
            os.makedirs(cached_repo)
            with open(os.path.join(cached_repo, "hubconf.py"), "w", encoding="utf-8") as f:
                f.write("# stub hubconf\n")

            fake_model = MagicMock(name="LocalYoloModel")
            with (
                patch.object(self.ip.torch.hub, "get_dir", return_value=tmp_hub),
                patch.object(self.ip.torch.hub, "load", return_value=fake_model) as mock_load,
            ):
                m1 = self.ip.get_yolo_model()
                m2 = self.ip.get_yolo_model()

            mock_load.assert_called_once_with(
                cached_repo,
                "custom",
                path=self.ip.model_path,
                source="local",
            )
            self.assertIs(m1, fake_model)
            self.assertIs(m1, m2)
            self.assertEqual(m1.conf, 0.75)

    def test_falls_back_to_github_without_force_reload_when_cache_missing(self):
        with tempfile.TemporaryDirectory() as empty_hub:
            fake_model = MagicMock(name="GithubYoloModel")
            with (
                patch.object(self.ip.torch.hub, "get_dir", return_value=empty_hub),
                patch.object(self.ip.torch.hub, "load", return_value=fake_model) as mock_load,
            ):
                loaded = self.ip.get_yolo_model()

            mock_load.assert_called_once_with(
                "ultralytics/yolov5",
                "custom",
                path=self.ip.model_path,
                source="github",
                force_reload=False,
            )
            self.assertIs(loaded, fake_model)
            self.assertEqual(loaded.conf, 0.75)

    def test_concurrent_calls_load_yolo_once(self):
        barrier = threading.Barrier(4)
        results = []
        errors = []

        def worker():
            try:
                barrier.wait(timeout=5)
                results.append(self.ip.get_yolo_model())
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        with tempfile.TemporaryDirectory() as empty_hub:
            fake_model = MagicMock(name="SharedYoloModel")
            with (
                patch.object(self.ip.torch.hub, "get_dir", return_value=empty_hub),
                patch.object(self.ip.torch.hub, "load", return_value=fake_model) as mock_load,
            ):
                threads = [threading.Thread(target=worker) for _ in range(4)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join(timeout=5)

        self.assertEqual(errors, [])
        self.assertEqual(mock_load.call_count, 1)
        self.assertEqual(len(results), 4)
        for model_ref in results:
            self.assertIs(model_ref, fake_model)

    def test_failed_load_does_not_cache_none_or_broken_state(self):
        fake_model = MagicMock(name="RecoveredYoloModel")
        with tempfile.TemporaryDirectory() as empty_hub:
            with (
                patch.object(self.ip.torch.hub, "get_dir", return_value=empty_hub),
                patch.object(
                    self.ip.torch.hub,
                    "load",
                    side_effect=[RuntimeError("network error"), fake_model],
                ) as mock_load,
            ):
                with self.assertRaises(RuntimeError):
                    self.ip.get_yolo_model()
                self.assertIsNone(self.ip._yolo_model)

                loaded = self.ip.get_yolo_model()

        self.assertEqual(mock_load.call_count, 2)
        self.assertIs(loaded, fake_model)

    def test_app_disables_werkzeug_reloader(self):
        app_path = os.path.join(BACKEND_DIR, "app.py")
        with open(app_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=app_path)

        app_run_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "app"
        ]
        self.assertEqual(len(app_run_calls), 1)
        kw = {k.arg: ast.literal_eval(k.value) for k in app_run_calls[0].keywords if k.arg}
        self.assertIs(kw.get("use_reloader"), False)

    def test_app_warms_up_yolo_in_main_block_before_run(self):
        app_path = os.path.join(BACKEND_DIR, "app.py")
        with open(app_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=app_path)

        main_blocks = [
            node
            for node in tree.body
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
        ]
        self.assertEqual(len(main_blocks), 1)

        call_names = []
        for stmt in main_blocks[0].body:
            for node in ast.walk(stmt):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        call_names.append(node.func.id)
                    elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                        call_names.append(f"{node.func.value.id}.{node.func.attr}")

        self.assertIn("get_yolo_model", call_names)
        self.assertIn("app.run", call_names)
        self.assertLess(call_names.index("get_yolo_model"), call_names.index("app.run"))


if __name__ == "__main__":
    unittest.main()
