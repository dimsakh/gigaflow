from __future__ import annotations

import ctypes
import sys
from importlib.resources import files

from PySide6.QtGui import QIcon


def icon_path():
    assets = files("gigaflow").joinpath("assets")
    ico = assets.joinpath("gigaflow.ico")
    if ico.is_file():
        return ico
    return assets.joinpath("gigaflow.svg")


def application_icon() -> QIcon:
    return QIcon(str(icon_path()))


def set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "GigaFlow.LocalVoiceInput"
        )
    except (AttributeError, OSError):
        pass
