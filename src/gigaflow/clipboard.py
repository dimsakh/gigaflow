from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes


def _copy_with_windows(text: str) -> bool:
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
        if not user32.SetClipboardData(13, handle):  # CF_UNICODETEXT
            return False
        transferred = True
        return True
    finally:
        user32.CloseClipboard()
        if handle and not transferred:
            kernel32.GlobalFree(handle)


def copy_text(text: str) -> bool:
    """Copy text and verify it through Qt, with a Win32 fallback."""
    from PySide6.QtGui import QGuiApplication

    clipboard = QGuiApplication.clipboard()
    clipboard.setText(text)
    if clipboard.text() == text:
        return True
    if _copy_with_windows(text):
        return clipboard.text() == text
    return False


def foreground_external_window() -> int | None:
    """Return the active window unless it belongs to GigaFlow itself."""
    if os.name != "nt":
        return None

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    window = user32.GetForegroundWindow()
    if not window:
        return None

    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(window, ctypes.byref(process_id))
    if process_id.value == os.getpid():
        return None
    return int(window)


def paste_from_clipboard(target_window: int | None) -> bool:
    """Focus a previously active window and simulate Ctrl+V."""
    if os.name != "nt" or not target_window:
        return False

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL

    window = wintypes.HWND(target_window)
    if not user32.IsWindow(window):
        return False

    if int(user32.GetForegroundWindow() or 0) != target_window:
        user32.SetForegroundWindow(window)
        for _ in range(10):
            if int(user32.GetForegroundWindow() or 0) == target_window:
                break
            time.sleep(0.02)
        else:
            return False

    class KeyboardInput(ctypes.Structure):
        _fields_ = [
            ("virtual_key", wintypes.WORD),
            ("scan_code", wintypes.WORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("extra_info", ctypes.c_size_t),
        ]

    class MouseInput(ctypes.Structure):
        _fields_ = [
            ("x", wintypes.LONG),
            ("y", wintypes.LONG),
            ("mouse_data", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("extra_info", ctypes.c_size_t),
        ]

    class HardwareInput(ctypes.Structure):
        _fields_ = [
            ("message", wintypes.DWORD),
            ("parameter_low", wintypes.WORD),
            ("parameter_high", wintypes.WORD),
        ]

    class InputValue(ctypes.Union):
        _fields_ = [
            ("mouse", MouseInput),
            ("keyboard", KeyboardInput),
            ("hardware", HardwareInput),
        ]

    class Input(ctypes.Structure):
        _anonymous_ = ("value",)
        _fields_ = [
            ("input_type", wintypes.DWORD),
            ("value", InputValue),
        ]

    user32.SendInput.argtypes = [
        wintypes.UINT,
        ctypes.POINTER(Input),
        ctypes.c_int,
    ]
    user32.SendInput.restype = wintypes.UINT

    key_up = 0x0002
    control = 0x11
    letter_v = 0x56
    events = (Input * 4)(
        Input(input_type=1, keyboard=KeyboardInput(virtual_key=control)),
        Input(input_type=1, keyboard=KeyboardInput(virtual_key=letter_v)),
        Input(
            input_type=1,
            keyboard=KeyboardInput(virtual_key=letter_v, flags=key_up),
        ),
        Input(
            input_type=1,
            keyboard=KeyboardInput(virtual_key=control, flags=key_up),
        ),
    )
    return user32.SendInput(4, events, ctypes.sizeof(Input)) == 4
