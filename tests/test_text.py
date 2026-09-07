import unittest

import numpy as np

from gigaflow.text import (
    clean_transcript,
    common_prefix_length,
    merge_transcripts,
    remove_filler_words,
    split_audio,
)


class TextTests(unittest.TestCase):
    def test_clean_transcript(self):
        self.assertEqual(clean_transcript("  Привет  ,   мир!  "), "Привет, мир!")

    def test_merge_with_overlap(self):
        self.assertEqual(
            merge_transcripts(["Один два три четыре", "три четыре пять шесть"]),
            "Один два три четыре пять шесть",
        )

    def test_merge_removes_long_chunk_overlap(self):
        repeated = " ".join(f"слово{index}" for index in range(1, 33))
        self.assertEqual(
            merge_transcripts(
                [
                    f"Начало диктовки {repeated}",
                    f"{repeated} завершение диктовки",
                ]
            ),
            f"Начало диктовки {repeated} завершение диктовки",
        )

    def test_split_audio_with_overlap(self):
        audio = np.zeros(45 * 16_000, dtype=np.float32)
        chunks = split_audio(audio)
        self.assertEqual(len(chunks), 3)
        self.assertLessEqual(max(map(len, chunks)), 20 * 16_000)

    def test_soft_filler_filter(self):
        self.assertEqual(
            remove_filler_words("Э-э, ну, я я подготовил документ.", "soft"),
            "Я подготовил документ.",
        )

    def test_full_filler_filter(self):
        self.assertEqual(
            remove_filler_words(
                "Значит, я, соответственно, выбрал, как бы, второй вариант.",
                "full",
            ),
            "Я выбрал второй вариант.",
        )

    def test_full_filter_keeps_meaningful_words(self):
        self.assertEqual(
            remove_filler_words("Это значит, что нужен объект типа B.", "full"),
            "Это значит, что нужен объект типа B.",
        )


    def test_common_prefix_length(self):
        self.assertEqual(common_prefix_length("привет мир", "привет мир!"), len("привет мир"))
        self.assertEqual(common_prefix_length("привет мир", "привет всем"), len("привет "))
        self.assertEqual(common_prefix_length("", "текст"), 0)
        self.assertEqual(common_prefix_length("текст", "текст"), len("текст"))


if __name__ == "__main__":
    unittest.main()
