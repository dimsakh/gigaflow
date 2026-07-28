import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

from gigaflow_chrome.host import ApiHandler, EventBus


class FakeController:
    def __init__(self):
        self.events = EventBus()
        self.filter_mode = "soft"
        self.shutdown_requested = threading.Event()
        self.toggled_by = None

    def state(self):
        return {
            "recording": False,
            "processing": False,
            "filler_filter": self.filter_mode,
        }

    def toggle(self, client_id):
        self.toggled_by = client_id

    def set_filter_mode(self, mode):
        self.filter_mode = mode


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.controller = FakeController()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ApiHandler)
        self.server.controller = self.controller
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path, data=None):
        body = None if data is None else json.dumps(data).encode()
        request = Request(
            self.base + path,
            data=body,
            method="GET" if data is None else "POST",
            headers={
                "Origin": "chrome-extension://gigaflow-test",
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=2) as response:
            return json.load(response)

    def test_health(self):
        self.assertEqual(self.request("/health")["filler_filter"], "soft")

    def test_toggle(self):
        self.request("/toggle", {"client_id": "tab-1"})
        self.assertEqual(self.controller.toggled_by, "tab-1")


if __name__ == "__main__":
    unittest.main()
