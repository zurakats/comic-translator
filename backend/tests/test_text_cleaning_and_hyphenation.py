import os
import sys
import unittest
from PIL import Image, ImageDraw

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def _import_image_processor():
    if "image_processor" in sys.modules:
        return sys.modules["image_processor"]
    import image_processor  # noqa: E402
    return image_processor


class TestTextCleaningAndHyphenation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ip = _import_image_processor()
        cls.font_path = os.path.join(
            BACKEND_DIR, "static", "fonts", "Winky_Rough", "WinkyRough-Regular.ttf"
        )

    def test_dots_and_punctuation_break_without_hyphens(self):
        img = Image.new("RGB", (200, 200), "black")
        draw = ImageDraw.Draw(img)
        font = self.ip.get_font(self.font_path, 24)

        for token in ("......", "............", "......?!"):
            lines = self.ip.break_word(token, draw, font, max_width=24, target_lang="id")
            self.assertGreater(len(lines), 1, f"Expected multiple lines for {token!r}")
            self.assertTrue(
                all("-" not in line for line in lines),
                f"Unexpected hyphen in broken punctuation lines: {lines!r}",
            )
            self.assertEqual("".join(lines), token)

        mixed_lines = self.ip.break_word("Aku......", draw, font, max_width=55, target_lang="id")
        self.assertGreater(len(mixed_lines), 1)
        self.assertTrue(all("-" not in line for line in mixed_lines), f"Got {mixed_lines!r}")
        self.assertEqual("".join(mixed_lines), "Aku......")

    def test_alphanumeric_words_still_hyphenate_when_broken(self):
        img = Image.new("RGB", (200, 200), "black")
        draw = ImageDraw.Draw(img)
        font = self.ip.get_font(self.font_path, 24)

        for lang, word in (("id", "pertanggungjawaban"), ("en", "extraordinary")):
            lines = self.ip.break_word(word, draw, font, max_width=70, target_lang=lang)
            self.assertGreater(len(lines), 1)
            for line in lines[:-1]:
                self.assertTrue(line.endswith("-"), f"Expected trailing '-' on {line!r}")
            self.assertFalse(lines[-1].endswith("-"))

    def test_render_bubbles_draws_dots_without_hyphen(self):
        img = Image.new("RGB", (120, 120), "black")
        real_draw = ImageDraw.Draw(img)
        drawn_lines = []

        class DrawSpy:
            def textbbox(self, *args, **kwargs):
                return real_draw.textbbox(*args, **kwargs)

            def rectangle(self, *args, **kwargs):
                return real_draw.rectangle(*args, **kwargs)

            def text(self, xy, text, *args, **kwargs):
                drawn_lines.append(text)
                return real_draw.text(xy, text, *args, **kwargs)

        # Narrow box (width=18, avail_width=21) forces 6 dots ("……" -> "......") to wrap across lines
        bubbles = [{
            "id": "0_0",
            "x1": 10, "y1": 10, "x2": 28, "y2": 80,
            "orig_box_width": 18,
            "orig_box_height": 70,
            "ocr_text": "……",
            "cleaned_text": "……",
        }]
        self.ip.render_bubbles(
            img,
            bubbles,
            {"0_0": "……"},
            "id",
            font_path=self.font_path,
            draw=DrawSpy(),
        )

        self.assertGreaterEqual(len(drawn_lines), 2)
        self.assertTrue(all("-" not in line for line in drawn_lines), f"Got {drawn_lines!r}")
        self.assertEqual("".join(drawn_lines), "......")

    def test_clean_ocr_text_strips_japanese_dashes_and_tildes_preserving_katakana_choonpu(self):
        cases = [
            # Leading Japanese dashes
            ("――だけど僕にはわからない。", "だけど僕にはわからない。"),
            ("ーーだけど僕にはわからない。", "だけど僕にはわからない。"),
            ("ーはい", "はい"),
            # Middle & trailing dashes/tildes
            ("だけど――わからない", "だけどわからない"),
            ("あそこにいるよおそこ～～", "あそこにいるよおそこ"),
            ("うわーーーっ！", "うわっ！"),
            ("そうー", "そう"),
            ("─テスト─", "テスト"),
            ("テスト~", "テスト"),
            ("テスト～", "テスト"),
            ("テスト〜", "テスト"),
            ("―—–─━‒−", ""),
            # Valid single Katakana prolonged vowel marks preserved
            ("ヒーローのゲーム", "ヒーローのゲーム"),
            ("ページ１バブル１", "ページ１バブル１"),
            ("ラーメン", "ラーメン"),
            # ASCII dashes vs single hyphen
            ("Wait—don't go!", "Wait don't go!"),
            ("Wait--what?!", "Wait what?!"),
            ("self-control", "self-control"),
            ("tiba-tiba", "tiba-tiba"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(self.ip.clean_ocr_text(raw), expected)

    def test_render_bubbles_post_translation_strips_dashes_and_tildes(self):
        img = Image.new("RGB", (400, 240), "black")
        real_draw = ImageDraw.Draw(img)
        drawn_lines = []

        class DrawSpy:
            def textbbox(self, *args, **kwargs):
                return real_draw.textbbox(*args, **kwargs)

            def rectangle(self, *args, **kwargs):
                return real_draw.rectangle(*args, **kwargs)

            def text(self, xy, text, *args, **kwargs):
                drawn_lines.append(text)
                return real_draw.text(xy, text, *args, **kwargs)

        bubbles = [
            {
                "id": "0_0",
                "x1": 10, "y1": 10, "x2": 390, "y2": 100,
                "orig_box_width": 380,
                "orig_box_height": 90,
                "ocr_text": "――だけど僕にはわからない。",
                "cleaned_text": "だけど僕にはわからない。",
            },
            {
                "id": "0_1",
                "x1": 10, "y1": 120, "x2": 390, "y2": 210,
                "orig_box_width": 380,
                "orig_box_height": 90,
                "ocr_text": "tiba",
                "cleaned_text": "tiba",
            },
        ]
        translations = {
            "0_0": "—Tapi aku tidak mengerti.",
            "0_1": "Tiba-tiba—dia pergi~",
        }
        self.ip.render_bubbles(
            img,
            bubbles,
            translations,
            "id",
            font_path=self.font_path,
            draw=DrawSpy(),
        )

        self.assertEqual(drawn_lines, ["Tapi aku tidak mengerti.", "Tiba-tiba dia pergi"])


if __name__ == "__main__":
    unittest.main()
