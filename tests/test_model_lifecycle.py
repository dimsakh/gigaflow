import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from gigaflow.transcriber import TranscriptionEngine


class ModelLifecycleTests(unittest.TestCase):
    def test_model_is_stored_in_unicode_user_path_and_reused(self):
        statuses = []
        calls = []

        def load_model(name, path, **kwargs):
            calls.append((name, Path(path), kwargs))
            Path(path).mkdir(parents=True, exist_ok=True)
            return object()

        fake_module = types.SimpleNamespace(load_model=load_model)
        with tempfile.TemporaryDirectory(prefix="GigaFlow Кириллица ") as folder:
            model_dir = Path(folder) / "Пользователь с пробелом" / "models" / "test-model"
            with patch.dict(sys.modules, {"onnx_asr": fake_module}):
                first = TranscriptionEngine(
                    "test-model",
                    model_dir,
                    "int8",
                    lambda title, detail: statuses.append((title, detail)),
                )
                first._load_model()
                first.close()
                self.assertTrue((model_dir / ".ready").is_file())

                second_statuses = []
                second = TranscriptionEngine(
                    "test-model",
                    model_dir,
                    "int8",
                    lambda title, detail: second_statuses.append((title, detail)),
                )
                self.assertTrue(second.model_ready)
                second._load_model()
                second.close()

        self.assertEqual(calls[0][1], model_dir)
        self.assertEqual(calls[0][2], {"quantization": "int8"})
        self.assertIn("Загружаю модель", [title for title, _ in statuses])
        self.assertIn("Модель готова", [title for title, _ in statuses])
        self.assertIn("Проверяю модель", [title for title, _ in second_statuses])


if __name__ == "__main__":
    unittest.main()
