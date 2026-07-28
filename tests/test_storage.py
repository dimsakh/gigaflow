import tempfile
import unittest
from pathlib import Path

from gigaflow.storage import HistoryStore


class StorageTests(unittest.TestCase):
    def test_add_read_delete(self):
        with tempfile.TemporaryDirectory() as folder:
            store = HistoryStore(Path(folder) / "history.sqlite3")
            item_id = store.add("Проверка", 1.25)
            items = store.recent()
            self.assertEqual(items[0].id, item_id)
            self.assertEqual(items[0].text, "Проверка")
            store.delete(item_id)
            self.assertEqual(store.recent(), [])
            store.close()


if __name__ == "__main__":
    unittest.main()

