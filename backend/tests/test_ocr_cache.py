import os
import sys
import threading
import unittest
from unittest.mock import MagicMock, patch

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def _import_image_processor():
    if "image_processor" in sys.modules:
        return sys.modules["image_processor"]
    with patch("torch.hub.load", return_value=MagicMock()):
        import image_processor  # noqa: E402
    return image_processor


class TestSelectOCRCache(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ip = _import_image_processor()

    def setUp(self):
        self.ip._ocr_cache.clear()

    def tearDown(self):
        self.ip._ocr_cache.clear()

    def test_caches_manga_ocr_across_requests(self):
        created = []

        def fake_manga_ocr():
            obj = MagicMock(name=f"MangaOcr-{len(created)}")
            created.append(obj)
            return obj

        with patch.object(self.ip, "MangaOcr", side_effect=fake_manga_ocr) as mock_cls:
            ocr1, idx1, lang1 = self.ip.selectOCR("jp")
            ocr2, idx2, lang2 = self.ip.selectOCR("jp")

        self.assertEqual(mock_cls.call_count, 1)
        self.assertIs(ocr1, ocr2)
        self.assertEqual((idx1, lang1), (0, "ja"))
        self.assertEqual((idx2, lang2), (0, "ja"))

    def test_caches_easyocr_per_language(self):
        def fake_reader(langs):
            return MagicMock(name=f"EasyOCR-{langs[0]}")

        with patch.object(self.ip.easyocr, "Reader", side_effect=fake_reader) as mock_reader:
            ko1, idx_ko1, t_ko1 = self.ip.selectOCR("ko")
            ko2, idx_ko2, t_ko2 = self.ip.selectOCR("ko")
            en1, idx_en1, t_en1 = self.ip.selectOCR("en")

        self.assertEqual(mock_reader.call_count, 2)
        mock_reader.assert_any_call(["ko"])
        mock_reader.assert_any_call(["en"])
        self.assertIs(ko1, ko2)
        self.assertIsNot(ko1, en1)
        self.assertEqual((idx_ko1, t_ko1), (1, "ko"))
        self.assertEqual((idx_ko2, t_ko2), (1, "ko"))
        self.assertEqual((idx_en1, t_en1), (1, "en"))

    def test_lru_eviction_respects_max_cache_size(self):
        with (
            patch.object(self.ip, "MangaOcr", side_effect=lambda: MagicMock(name="MangaOcr")) as mock_manga,
            patch.object(self.ip.easyocr, "Reader", side_effect=lambda langs: MagicMock(name=f"Reader-{langs[0]}")) as mock_reader,
        ):
            self.ip.selectOCR("jp")
            self.ip.selectOCR("ko")
            # Hit on jp promotes jp to most-recently-used; ko becomes oldest.
            self.ip.selectOCR("jp")
            # Adding en evicts ko when MAX_OCR_CACHE == 2.
            self.ip.selectOCR("en")

            self.assertEqual(list(self.ip._ocr_cache.keys()), ["jp", "en"])

            # jp is still cached; ko must be re-instantiated.
            self.ip.selectOCR("jp")
            self.ip.selectOCR("ko")

        self.assertEqual(mock_manga.call_count, 1)
        self.assertEqual(mock_reader.call_count, 3)  # ko, en, ko

    def test_invalid_language_raises_without_modifying_cache(self):
        with self.assertRaises(ValueError):
            self.ip.selectOCR("fr")
        self.assertEqual(len(self.ip._ocr_cache), 0)

    def test_concurrent_calls_instantiate_once(self):
        barrier = threading.Barrier(4)
        results = []
        errors = []

        def fake_manga_ocr():
            return MagicMock(name="SharedMangaOcr")

        def worker():
            try:
                barrier.wait(timeout=5)
                results.append(self.ip.selectOCR("jp"))
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        with patch.object(self.ip, "MangaOcr", side_effect=fake_manga_ocr) as mock_manga:
            threads = [threading.Thread(target=worker) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

        self.assertEqual(errors, [])
        self.assertEqual(mock_manga.call_count, 1)
        self.assertEqual(len(results), 4)
        first_ocr = results[0][0]
        for ocr, idx, lang in results:
            self.assertIs(ocr, first_ocr)
            self.assertEqual((idx, lang), (0, "ja"))

    def test_failed_init_does_not_poison_cache(self):
        sentinel = MagicMock(name="RecoveredMangaOcr")
        with patch.object(
            self.ip,
            "MangaOcr",
            side_effect=[RuntimeError("load failed"), sentinel],
        ) as mock_manga:
            with self.assertRaises(RuntimeError):
                self.ip.selectOCR("jp")
            self.assertEqual(len(self.ip._ocr_cache), 0)

            ocr, idx, lang = self.ip.selectOCR("jp")

        self.assertEqual(mock_manga.call_count, 2)
        self.assertIs(ocr, sentinel)
        self.assertEqual((idx, lang), (0, "ja"))


if __name__ == "__main__":
    unittest.main()
