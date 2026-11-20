import os
import re
import sys
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw, ImageFont

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def _import_image_processor():
    if "image_processor" in sys.modules:
        return sys.modules["image_processor"]
    import image_processor  # noqa: E402
    return image_processor


def _legacy_render_bubbles(ip, img_pil, bubbles, translations, target_lang, font_path):
    """Exact copy of the original unoptimized linear render_bubbles algorithm."""
    draw = ImageDraw.Draw(img_pil)
    for b in bubbles:
        cleaned_text = b["cleaned_text"]
        if cleaned_text.strip():
            translated = translations.get(b["id"]) or "[Teks tidak terbaca]"
            translated = re.sub(r'\bLai\b', '!', translated)
            translated = translated.replace('．', '.').replace('…', '...').replace('。', '.')
            translated = re.sub(r'([.?!])([a-zA-Z])', r'\1 \2', translated)
        else:
            translated = "[Teks tidak terbaca]"

        x1, y1, x2, y2 = b["x1"], b["y1"], b["x2"], b["y2"]
        box_width = b["orig_box_width"]
        box_height = b["orig_box_height"]

        text_box_width = int(box_width * 1.22)
        avail_width = max(10, text_box_width)
        avail_height = max(10, box_height - 4)

        font_size = 110
        while font_size > 12:
            font = ImageFont.truetype(font_path, font_size)
            lines = ip.wrap_text(translated, draw, font, avail_width, target_lang)
            line_spacing_factor = 1.05

            ascent, descent = font.getmetrics()
            line_height = int((ascent + descent) * line_spacing_factor)
            total_height = line_height * len(lines)

            max_line_width = 0
            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                w = bbox[2] - bbox[0]
                if w > max_line_width:
                    max_line_width = w

            if total_height <= avail_height and max_line_width <= avail_width:
                break
            font_size -= 1

        font_size = int(font_size * 1.0)

        font = ImageFont.truetype(font_path, font_size)
        lines = ip.wrap_text(translated, draw, font, avail_width, target_lang)
        ascent, descent = font.getmetrics()
        line_height = int((ascent + descent) * 1.05)
        total_height = line_height * len(lines)

        inset_x = max(1, int(box_width * 0.015))
        inset_y = max(1, int(box_height * 0.015))

        rect_x1 = x1 + inset_x
        rect_y1 = y1 + inset_y
        rect_x2 = max(rect_x1, x2 - inset_x - 1)
        rect_y2 = max(rect_y1, y2 - inset_y - 1)

        draw.rectangle([rect_x1, rect_y1, rect_x2, rect_y2], fill="white")

        current_y = y1 + (box_height - total_height) // 2
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_width = bbox[2] - bbox[0]
            text_x = x1 + (box_width - line_width) // 2
            draw.text(
                (text_x, current_y),
                line,
                font=font,
                fill="black",
                stroke_width=2,
                stroke_fill="white",
            )
            current_y += line_height


def _make_bubble(bid, x1, y1, x2, y2, cleaned="dummy"):
    return {
        "id": bid,
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "orig_box_width": x2 - x1,
        "orig_box_height": y2 - y1,
        "ocr_text": cleaned,
        "cleaned_text": cleaned,
    }


class TestRenderBubblesOptimization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ip = _import_image_processor()
        cls.font_path = os.path.join(
            BACKEND_DIR, "static", "fonts", "Winky_Rough", "WinkyRough-Regular.ttf"
        )

    def setUp(self):
        self.ip.get_font.cache_clear()
        self.ip._split_syllables.cache_clear()

    def tearDown(self):
        self.ip.get_font.cache_clear()
        self.ip._split_syllables.cache_clear()

    def test_pixel_exact_equivalence_across_diverse_bubbles(self):
        cases = [
            (
                "id",
                (420, 620),
                [
                    # Tiny box forcing fallback to font_size == 12
                    _make_bubble("tiny", 10, 10, 45, 32, "text"),
                    # Medium dialogue box
                    _make_bubble("med", 60, 20, 260, 120, "text"),
                    # Tall narrow box forcing break_word + pyphen id_ID
                    _make_bubble("narrow_id", 280, 20, 355, 290, "text"),
                    # Large box with short exclamation near max font size
                    _make_bubble("large", 20, 160, 240, 360, "text"),
                    # Empty cleaned_text -> [Teks tidak terbaca]
                    _make_bubble("empty", 20, 390, 200, 470, ""),
                    # Whitespace-only translation
                    _make_bubble("ws", 220, 390, 390, 470, "text"),
                ],
                {
                    "tiny": "Kalimat panjang sekali di kotak sangat kecil!",
                    "med": "Kau pikir aku akan menyerah begitu saja?!",
                    "narrow_id": "Pertanggungjawaban ketidakberdayaan mereka.",
                    "large": "Oi!",
                    "ws": "   ",
                },
            ),
            (
                "en",
                (320, 320),
                [
                    _make_bubble("narrow_en", 30, 20, 115, 260, "text"),
                    _make_bubble("normal_en", 130, 20, 300, 160, "text"),
                ],
                {
                    "narrow_en": "Unbelievably extraordinary!",
                    "normal_en": "Wait...What?!",
                },
            ),
            (
                "fr",
                (240, 240),
                [
                    _make_bubble("narrow_other", 20, 20, 95, 200, "text"),
                ],
                {
                    "narrow_other": "Extraordinaire!",
                },
            ),
        ]

        for target_lang, size, bubbles, translations in cases:
            with self.subTest(target_lang=target_lang):
                img_expected = Image.new("RGB", size, (40, 80, 120))
                img_actual = img_expected.copy()

                _legacy_render_bubbles(
                    self.ip, img_expected, bubbles, translations, target_lang, self.font_path
                )
                self.ip.render_bubbles(
                    img_actual, bubbles, translations, target_lang, font_path=self.font_path
                )

                self.assertTrue(
                    np.array_equal(np.array(img_expected), np.array(img_actual)),
                    f"Rendered pixels diverged for target_lang={target_lang}",
                )

    def test_font_lru_cache_hits_across_bubbles_and_renders(self):
        bubbles = [
            _make_bubble("b1", 20, 20, 180, 100, "hi"),
            _make_bubble("b2", 20, 120, 180, 200, "hello"),
        ]
        translations = {"b1": "Halo kawan!", "b2": "Apa kabar hari ini?"}

        orig_truetype = ImageFont.truetype
        with patch.object(self.ip.ImageFont, "truetype", wraps=orig_truetype) as spy_truetype:
            img1 = Image.new("RGB", (220, 240), "black")
            self.ip.render_bubbles(img1, bubbles, translations, "id", font_path=self.font_path)
            first_calls = spy_truetype.call_count
            unique_args = {call.args for call in spy_truetype.call_args_list}

            self.assertEqual(first_calls, len(unique_args))
            self.assertGreater(first_calls, 0)

            img2 = Image.new("RGB", (220, 240), "black")
            self.ip.render_bubbles(img2, bubbles, translations, "id", font_path=self.font_path)
            self.assertEqual(spy_truetype.call_count, first_calls)

    def test_no_redundant_post_loop_wrap_and_skips_oversized_line_height(self):
        # Case 1: Wide short box fits on the first size where line_height <= avail_height -> only 1 wrap_text call
        img_wide = Image.new("RGB", (300, 150), "black")
        wide_bubbles = [_make_bubble("mid", 20, 20, 260, 80, "text")]
        called_wide = []
        orig_wrap = self.ip.wrap_text

        def spy_wrap_wide(text, draw, font, max_width, target_lang):
            called_wide.append(font.size)
            return orig_wrap(text, draw, font, max_width, target_lang)

        with patch.object(self.ip, "wrap_text", side_effect=spy_wrap_wide):
            self.ip.render_bubbles(img_wide, wide_bubbles, {"mid": "Halo dunia!"}, "id", font_path=self.font_path)

        self.assertEqual(len(called_wide), 1)
        self.assertNotEqual(called_wide[0], 110)

        # Case 2: Narrower box steps down multiple sizes after line_height <= avail_height, without post-loop duplicate
        img_narrow = Image.new("RGB", (200, 150), "black")
        narrow_bubbles = [_make_bubble("narrow", 20, 20, 120, 80, "text")]
        called_narrow = []

        def spy_wrap_narrow(text, draw, font, max_width, target_lang):
            called_narrow.append(font.size)
            return orig_wrap(text, draw, font, max_width, target_lang)

        with patch.object(self.ip, "wrap_text", side_effect=spy_wrap_narrow):
            self.ip.render_bubbles(
                img_narrow,
                narrow_bubbles,
                {"narrow": "Halo dunia yang sangat indah sekali!"},
                "id",
                font_path=self.font_path,
            )

        self.assertGreaterEqual(len(called_narrow), 2)
        self.assertNotIn(110, called_narrow)
        self.assertNotEqual(called_narrow[-1], called_narrow[-2])

    def test_no_textbbox_calls_during_final_drawing(self):
        img = Image.new("RGB", (240, 140), "black")
        real_draw = ImageDraw.Draw(img)
        events = []

        class DrawSpy:
            def textbbox(self, *args, **kwargs):
                events.append("textbbox")
                return real_draw.textbbox(*args, **kwargs)

            def rectangle(self, *args, **kwargs):
                events.append("rectangle")
                return real_draw.rectangle(*args, **kwargs)

            def text(self, *args, **kwargs):
                events.append("text")
                return real_draw.text(*args, **kwargs)

        bubbles = [_make_bubble("b1", 20, 20, 220, 120, "text")]
        translations = {"b1": "Selamat pagi semuanya!"}

        self.ip.render_bubbles(
            img, bubbles, translations, "id", font_path=self.font_path, draw=DrawSpy()
        )

        self.assertIn("rectangle", events)
        rect_idx = events.index("rectangle")
        after_rect = events[rect_idx + 1 :]
        self.assertGreater(len(after_rect), 0)
        self.assertTrue(all(ev == "text" for ev in after_rect))


if __name__ == "__main__":
    unittest.main()
