from __future__ import annotations

import ctypes
import json
import logging
import os
import threading
import time
import uuid
from collections import deque
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .audio import AudioRecorder, SAMPLE_RATE
from .text import remove_filler_words
from .transcriber import TranscriptionEngine

HOST = "127.0.0.1"
PORT = 38473
AUTO_FINISH_SECONDS = 2.2
PARTIAL_INTERVAL_SECONDS = 0.9


def app_dir() -> Path:
    override = os.environ.get("GIGAFLOW_CHROME_HOME")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "GigaFlowChrome" if base else Path.home() / ".gigaflow-chrome"


def model_dir() -> Path:
    override = os.environ.get("GIGAFLOW_CHROME_MODEL_DIR")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA")
    if base:
        shared = Path(base) / "GigaFlow" / "models" / "gigaam-v3-e2e-rnnt"
        if shared.exists():
            return shared
    return app_dir() / "models" / "gigaam-v3-e2e-rnnt"


class EventBus:
    def __init__(self):
        self._condition = threading.Condition()
        self._events: deque[dict] = deque(maxlen=500)
        self._sequence = 0

    def publish(self, event_type: str, **data) -> None:
        with self._condition:
            self._sequence += 1
            self._events.append(
                {"sequence": self._sequence, "type": event_type, **data}
            )
            self._condition.notify_all()

    def wait_after(self, sequence: int, timeout: float = 20.0) -> list[dict]:
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._sequence <= sequence:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return []
                self._condition.wait(remaining)
            return [event for event in self._events if event["sequence"] > sequence]


class ChromeGigaFlow:
    def __init__(self):
        self.root = app_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        self.config_path = self.root / "config.json"
        self.filter_mode = self._load_filter_mode()
        self.instance_id = uuid.uuid4().hex
        self.events = EventBus()
        self.recorder = AudioRecorder(self._on_level)
        self.engine = TranscriptionEngine(model_dir())
        self.processing = False
        self.started_at = 0.0
        self.session_client = ""
        self.last_partial_at = 0.0
        self.last_level_at = 0.0
        self.shutdown_requested = threading.Event()
        self._state_lock = threading.Lock()
        self.engine.preload()

    def _load_filter_mode(self) -> str:
        try:
            value = json.loads(self.config_path.read_text(encoding="utf-8")).get(
                "filler_filter", "soft"
            )
            return value if value in {"off", "soft", "full"} else "soft"
        except (OSError, ValueError, TypeError):
            return "soft"

    def set_filter_mode(self, mode: str) -> None:
        if mode not in {"off", "soft", "full"}:
            raise ValueError("Неизвестный режим очистки")
        self.filter_mode = mode
        temporary = self.config_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"filler_filter": mode}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.config_path)
        self.events.publish("settings", filler_filter=mode)

    def state(self) -> dict:
        return {
            "recording": self.recorder.recording,
            "processing": self.processing,
            "filler_filter": self.filter_mode,
        }

    def toggle(self, client_id: str) -> None:
        with self._state_lock:
            if self.recorder.recording:
                self._finish_recording()
            elif self.processing:
                self.events.publish(
                    "error",
                    client_id=client_id,
                    message="Предыдущая запись ещё распознаётся",
                )
            else:
                self._start_recording(client_id)

    def _start_recording(self, client_id: str) -> None:
        try:
            self.recorder.start()
        except Exception as exc:
            self.events.publish(
                "error",
                client_id=client_id,
                message=f"Не удалось открыть микрофон: {exc}",
            )
            return
        self.session_client = client_id
        self.started_at = time.monotonic()
        self.last_partial_at = self.started_at
        self.events.publish("recording", client_id=client_id)

    def _finish_recording(self) -> None:
        audio = self.recorder.stop()
        client_id = self.session_client
        if audio.size < SAMPLE_RATE // 2:
            self.events.publish(
                "error",
                client_id=client_id,
                message="Слишком короткая запись",
            )
            return
        self.processing = True
        self.events.publish("processing", client_id=client_id)
        accepted = self.engine.submit(
            audio,
            final=True,
            callback=self._on_transcription,
            error_callback=self._on_error,
        )
        if not accepted:
            self.processing = False
            self.events.publish(
                "error",
                client_id=client_id,
                message="Слишком короткая запись",
            )

    def _request_partial(self) -> None:
        audio = self.recorder.snapshot()
        self.engine.submit(
            audio,
            final=False,
            callback=self._on_transcription,
            error_callback=self._on_error,
        )

    def _on_transcription(self, text: str, final: bool) -> None:
        if not final:
            if text and self.recorder.recording:
                self.events.publish(
                    "partial",
                    client_id=self.session_client,
                    text=text,
                )
            return
        cleaned = remove_filler_words(text, self.filter_mode)
        self.processing = False
        if not cleaned:
            self.events.publish(
                "error",
                client_id=self.session_client,
                message="Речь не распознана",
            )
            return
        copied = copy_windows(cleaned)
        self.events.publish(
            "result",
            client_id=self.session_client,
            text=cleaned,
            copied=copied,
        )

    def _on_error(self, message: str) -> None:
        logging.error(message)
        self.processing = False
        self.events.publish(
            "error",
            client_id=self.session_client,
            message=message,
        )

    def _on_level(self, level: float) -> None:
        now = time.monotonic()
        if now - self.last_level_at >= 0.08:
            self.last_level_at = now
            self.events.publish(
                "level",
                client_id=self.session_client,
                level=round(level, 3),
            )

    def tick(self) -> None:
        if not self.recorder.recording:
            return
        now = time.monotonic()
        if now - self.last_partial_at >= PARTIAL_INTERVAL_SECONDS:
            self.last_partial_at = now
            self._request_partial()
        if (
            self.recorder.heard_voice
            and now - self.started_at >= 1.0
            and self.recorder.silence_seconds >= AUTO_FINISH_SECONDS
        ):
            with self._state_lock:
                if self.recorder.recording:
                    self._finish_recording()

    def close(self) -> None:
        if self.recorder.recording:
            self.recorder.cancel()
        self.engine.close()


def copy_windows(text: str) -> bool:
    if os.name != "nt":
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL
    encoded = (text + "\0").encode("utf-16-le")
    for _ in range(10):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return False
    handle = None
    transferred = False
    try:
        if not user32.EmptyClipboard():
            return False
        handle = kernel32.GlobalAlloc(0x0002, len(encoded))
        if not handle:
            return False
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return False
        try:
            ctypes.memmove(pointer, encoded, len(encoded))
        finally:
            kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(13, handle):
            return False
        transferred = True
        return True
    finally:
        user32.CloseClipboard()
        if handle and not transferred:
            kernel32.GlobalFree(handle)


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "GigaFlowChrome/0.1"

    @property
    def controller(self) -> ChromeGigaFlow:
        return self.server.controller  # type: ignore[attr-defined]

    def _origin(self) -> str | None:
        origin = self.headers.get("Origin", "")
        return origin if origin.startswith("chrome-extension://") else None

    def _send_json(self, status: int, data: object) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        origin = self._origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 64_000:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_OPTIONS(self) -> None:
        origin = self._origin()
        self.send_response(204 if origin else 403)
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        if not self._origin():
            self._send_json(403, {"error": "Extension origin required"})
            return
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(200, {"ok": True, **self.controller.state()})
            return
        if parsed.path == "/events":
            query = parse_qs(parsed.query)
            after = int(query.get("after", ["0"])[0])
            instance_id = getattr(self.controller, "instance_id", "test")
            if query.get("instance", [""])[0] != instance_id:
                after = 0
            events = self.controller.events.wait_after(after)
            self._send_json(
                200,
                {"events": events, "instance_id": instance_id},
            )
            return
        self._send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        if not self._origin():
            self._send_json(403, {"error": "Extension origin required"})
            return
        try:
            data = self._read_json()
            if self.path == "/toggle":
                self.controller.toggle(str(data.get("client_id", "")))
                self._send_json(200, {"ok": True})
            elif self.path == "/settings":
                self.controller.set_filter_mode(str(data.get("filler_filter", "")))
                self._send_json(200, {"ok": True, **self.controller.state()})
            elif self.path == "/shutdown":
                self.controller.shutdown_requested.set()
                self._send_json(200, {"ok": True})
            else:
                self._send_json(404, {"error": "Not found"})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._send_json(400, {"error": str(exc)})

    def log_message(self, format_string: str, *args) -> None:
        logging.info("%s - %s", self.address_string(), format_string % args)


def main() -> int:
    root = app_dir()
    (root / "logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=root / "logs" / "host.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    controller = ChromeGigaFlow()
    try:
        server = ThreadingHTTPServer((HOST, PORT), ApiHandler)
    except OSError:
        return 0
    server.controller = controller  # type: ignore[attr-defined]
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        while not controller.shutdown_requested.wait(0.1):
            controller.tick()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        controller.close()
    return 0
