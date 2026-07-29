from __future__ import annotations

import os
import sys


# A windowed PyInstaller executable has no console, so sys.stdout and
# sys.stderr are None. Hugging Face/tqdm may still try to write download
# progress there and crash with "NoneType has no attribute write".
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from gigaflow.app import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
