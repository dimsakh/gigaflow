from __future__ import annotations

from collections.abc import Callable

import keyboard


class GlobalHotkey:
    def __init__(self, hotkey: str, callback: Callable[[], None]):
        self.hotkey = hotkey
        self.callback = callback
        self._handle = None

    def register(self) -> None:
        self.unregister()
        self._handle = keyboard.add_hotkey(
            self.hotkey,
            self.callback,
            suppress=False,
            trigger_on_release=False,
        )

    def unregister(self) -> None:
        if self._handle is not None:
            keyboard.remove_hotkey(self._handle)
            self._handle = None

