"""Local website entry point, with desktop and offline diagnostic options."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--check-offline":
        from .selftest import offline_check

        try:
            message = offline_check()
            payload, code = {"ok": True, "message": message}, 0
        except Exception as exc:
            payload, code = {"ok": False, "message": str(exc)}, 1
        if len(sys.argv) > 2:
            Path(sys.argv[2]).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if sys.stdout is not None:
            print(payload["message"])
        return code
    if len(sys.argv) > 1 and sys.argv[1] == "--desktop":
        sys.argv.pop(1)
        from .gui import main as launch_gui
        launch_gui()
        return 0
    from .web import main as launch_web
    launch_web()
    return 0
