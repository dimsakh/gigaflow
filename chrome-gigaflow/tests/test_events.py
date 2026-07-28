import threading
import time
import unittest

from gigaflow_chrome.host import EventBus


class EventBusTests(unittest.TestCase):
    def test_waits_for_next_event(self):
        bus = EventBus()

        def publish():
            time.sleep(0.02)
            bus.publish("result", text="Готово")

        threading.Thread(target=publish).start()
        events = bus.wait_after(0, timeout=1)
        self.assertEqual(events[0]["type"], "result")
        self.assertEqual(events[0]["text"], "Готово")


if __name__ == "__main__":
    unittest.main()
