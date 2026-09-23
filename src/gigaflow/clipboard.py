from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes


class _KeyboardInput(ctypes.Structure):
    _fields_ = [
        ("virtual_key", wintypes.WORD),
        ("scan_code", wintypes.WORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra_info", ctypes.c_size_t),
    ]


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
        ("mouse_data", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra_info", ctypes.c_size_t),
    ]


class _HardwareInput(ctypes.Structure):
    _fields_ = [
        ("message", wintypes.DWORD),
        ("parameter_low", wintypes.WORD),
        ("parameter_high", wintypes.WORD),
    ]


class _InputValue(ctypes.Union):
    _fields_ = [
        ("mouse", _MouseInput),
        ("keyboard", _KeyboardInput),
        ("hardware", _HardwareInput),
    ]


class _Input(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = [
        ("input_type", wintypes.DWORD),
        ("value", _InputValue),
    ]


_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_UNICODE = 0x0004
_VK_CONTROL = 0x11
_VK_V = 0x56
_VK_BACK = 0x08


def _user32() -> ctypes.WinDLL:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_Input), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    return user32


def _send_input(events: tuple[_Input, ...]) -> bool:
    array = (_Input * len(events))(*events)
    return _user32().SendInput(len(events), array, ctypes.sizeof(_Input)) == len(events)


def _focus_window(target_window: int) -> bool:
    """Bring a previously active window to the foreground and wait for it."""
    user32 = _user32()
    window = wintypes.HWND(target_window)
    if not user32.IsWindow(window):
        return False
    if int(user32.GetForegroundWindow() or 0) == target_window:
        return True
    user32.SetForegroundWindow(window)
    for _ in range(10):
        if int(user32.GetForegroundWindow() or 0) == target_window:
            return True
        time.sleep(0.02)
    return False


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
    if not _focus_window(target_window):
        return False

    events = (
        _Input(input_type=_INPUT_KEYBOARD, keyboard=_KeyboardInput(virtual_key=_VK_CONTROL)),
        _Input(input_type=_INPUT_KEYBOARD, keyboard=_KeyboardInput(virtual_key=_VK_V)),
        _Input(
            input_type=_INPUT_KEYBOARD,
            keyboard=_KeyboardInput(virtual_key=_VK_V, flags=_KEYEVENTF_KEYUP),
        ),
        _Input(
            input_type=_INPUT_KEYBOARD,
            keyboard=_KeyboardInput(virtual_key=_VK_CONTROL, flags=_KEYEVENTF_KEYUP),
        ),
    )
    return _send_input(events)


def _utf16_units(text: str):
    for char in text:
        code = ord(char)
        if code > 0xFFFF:
            code -= 0x10000
            yield 0xD800 + (code >> 10)
            yield 0xDC00 + (code & 0x3FF)
        else:
            yield code


def type_text(target_window: int | None, text: str) -> bool:
    """Focus a previously active window and type text directly (no clipboard).

    Used to insert recognized speech as it becomes available, instead of
    waiting for the whole dictation to finish before pasting one block.
    """
    if os.name != "nt" or not target_window or not text:
        return False
    if not _focus_window(target_window):
        return False

    events: list[_Input] = []
    for unit in _utf16_units(text):
        events.append(
            _Input(
                input_type=_INPUT_KEYBOARD,
                keyboard=_KeyboardInput(scan_code=unit, flags=_KEYEVENTF_UNICODE),
            )
        )
        events.append(
            _Input(
                input_type=_INPUT_KEYBOARD,
                keyboard=_KeyboardInput(
                    scan_code=unit, flags=_KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP
                ),
            )
        )
    return _send_input(tuple(events))


def send_backspaces(target_window: int | None, count: int) -> bool:
    """Focus a previously active window and delete `count` characters before the caret."""
    if os.name != "nt" or not target_window or count <= 0:
        return False
    if not _focus_window(target_window):
        return False

    events: list[_Input] = []
    for _ in range(count):
        events.append(
            _Input(input_type=_INPUT_KEYBOARD, keyboard=_KeyboardInput(virtual_key=_VK_BACK))
        )
        events.append(
            _Input(
                input_type=_INPUT_KEYBOARD,
                keyboard=_KeyboardInput(virtual_key=_VK_BACK, flags=_KEYEVENTF_KEYUP),
            )
        )
    return _send_input(tuple(events))
