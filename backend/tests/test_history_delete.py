import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import app as backend_app


class DeleteHistoryBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.upload_dir = os.path.join(self.temp_dir.name, 'uploads')
        os.makedirs(self.upload_dir, exist_ok=True)
        self.history_file = os.path.join(self.temp_dir.name, 'history.json')

        # Create dummy image files for two batches
        self.files = {
            'b1_orig': os.path.join(self.upload_dir, 'page1_20261121_1.png'),
            'b1_trans': os.path.join(self.upload_dir, 'output_page1_20261121_1.png'),
            'b2_orig': os.path.join(self.upload_dir, 'page2_20261121_1.png'),
            'b2_trans': os.path.join(self.upload_dir, 'output_page2_20261121_1.png'),
        }
        for path in self.files.values():
            with open(path, 'wb') as f:
                f.write(b'img')

        self.initial_history = [
            {
                'id': 1001,
                'date': '21/11/2026, 09.00.00',
                'sourceLang': 'jp',
                'targetLang': 'en',
                'engine': 'googletrans',
                'images': [
                    {
                        'original': 'http://127.0.0.1:5000/static/uploads/page1_20261121_1.png',
                        'translated': 'http://127.0.0.1:5000/static/uploads/output_page1_20261121_1.png',
                    }
                ],
            },
            {
                'id': 1002,
                'date': '21/11/2026, 09.05.00',
                'sourceLang': 'ko',
                'targetLang': 'id',
                'engine': 'gemini',
                'images': [
                    {
                        'original': 'http://127.0.0.1:5000/static/uploads/page2_20261121_1.png',
                        'translated': 'http://127.0.0.1:5000/static/uploads/output_page2_20261121_1.png',
                    }
                ],
            },
        ]
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(self.initial_history, f)

        self.client = backend_app.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_delete_existing_batch_removes_entry_and_files(self):
        with patch.object(backend_app, 'HISTORY_FILE', self.history_file), \
             patch.object(backend_app, 'UPLOAD_FOLDER', self.upload_dir):
            res = self.client.delete('/history/1001')

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), {'status': 'success', 'id': 1001})

        with open(self.history_file, 'r', encoding='utf-8') as f:
            remaining = json.load(f)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]['id'], 1002)

        self.assertFalse(os.path.exists(self.files['b1_orig']))
        self.assertFalse(os.path.exists(self.files['b1_trans']))
        self.assertTrue(os.path.exists(self.files['b2_orig']))
        self.assertTrue(os.path.exists(self.files['b2_trans']))

    def test_delete_missing_batch_returns_404(self):
        with patch.object(backend_app, 'HISTORY_FILE', self.history_file), \
             patch.object(backend_app, 'UPLOAD_FOLDER', self.upload_dir):
            res = self.client.delete('/history/9999')

        self.assertEqual(res.status_code, 404)
        with open(self.history_file, 'r', encoding='utf-8') as f:
            remaining = json.load(f)
        self.assertEqual(len(remaining), 2)


if __name__ == '__main__':
    unittest.main()
