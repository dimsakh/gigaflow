import unittest

from gigaflow_chrome.text import remove_filler_words


class TextFilterTests(unittest.TestCase):
    def test_soft(self):
        self.assertEqual(
            remove_filler_words("Э-э, ну, я я подготовил документ.", "soft"),
            "Я подготовил документ.",
        )

    def test_full(self):
        self.assertEqual(
            remove_filler_words(
                "Значит, я, соответственно, выбрал, как бы, второй вариант.",
                "full",
            ),
            "Я выбрал второй вариант.",
        )

    def test_meaning_is_preserved(self):
        self.assertEqual(
            remove_filler_words("Это значит, что нужен объект типа B.", "full"),
            "Это значит, что нужен объект типа B.",
        )


if __name__ == "__main__":
    unittest.main()
