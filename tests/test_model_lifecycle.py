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

        def load_model(name, **kwargs):
            calls.append((name, kwargs))
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

        self.assertEqual(calls[0][0], "test-model")
        self.assertEqual(calls[0][1], {"quantization": "int8"})
        self.assertIn("Загружаю модель", [title for title, _ in statuses])
        self.assertIn("Модель готова", [title for title, _ in statuses])
        self.assertIn("Проверяю модель", [title for title, _ in second_statuses])

    def test_incomplete_model_directory_is_removed_before_retry(self):
        statuses = []

        def load_model(name, **kwargs):
            self.assertFalse((model_dir / "partial.download").exists())
            return object()

        fake_module = types.SimpleNamespace(load_model=load_model)
        with tempfile.TemporaryDirectory() as folder:
            model_dir = Path(folder) / "models" / "test-model"
            model_dir.mkdir(parents=True)
            (model_dir / "partial.download").write_text("broken")
            with patch.dict(sys.modules, {"onnx_asr": fake_module}):
                engine = TranscriptionEngine(
                    "test-model",
                    model_dir,
                    "int8",
                    lambda title, detail: statuses.append((title, detail)),
                )
                engine._load_model()
                engine.close()
                self.assertTrue((model_dir / ".ready").is_file())

        self.assertIn("Повторяю загрузку модели", [title for title, _ in statuses])


    def test_transient_download_failure_is_retried_automatically(self):
        statuses = []
        attempts = 0

        def load_model(name, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ConnectionError("temporary network failure")
            return object()

        fake_module = types.SimpleNamespace(load_model=load_model)
        with tempfile.TemporaryDirectory() as folder:
            model_dir = Path(folder) / "models" / "test-model"
            with (
                patch.dict(sys.modules, {"onnx_asr": fake_module}),
                patch("gigaflow.transcriber.time.sleep"),
            ):
                engine = TranscriptionEngine(
                    "test-model",
                    model_dir,
                    "int8",
                    lambda title, detail: statuses.append((title, detail)),
                )
                engine._preload_safely()
                engine.close()

                self.assertEqual(attempts, 3)
                self.assertTrue((model_dir / ".ready").is_file())
                titles = [title for title, _ in statuses]
                self.assertEqual(titles.count("Продолжаю загрузку модели"), 2)
                self.assertIn("Модель готова", titles)
                self.assertNotIn("Не удалось загрузить модель", titles)


if __name__ == "__main__":
    unittest.main()
