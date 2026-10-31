"""Build on Windows; PyInstaller does not cross-compile Windows executables."""
from __future__ import annotations

import os
import json
import subprocess
import sys
from pathlib import Path


def main():
    if os.name != "nt":
        raise SystemExit("Run Build-Windows.bat on a Windows 10/11 64-bit computer.")
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, str(root / "scripts" / "check_offline.py")], cwd=root, check=True)
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--console",
               "--name", "ResultDesk", "--paths", str(root / "src"),
               "--collect-all", "rapidocr", "--collect-all", "onnxruntime",
               "--collect-all", "pypdfium2", "--collect-all", "openpyxl",
               "--collect-data", "result_automation", "--collect-all", "fastapi",
               "--collect-all", "uvicorn", "--collect-all", "python_multipart",
               "--copy-metadata", "rapidocr", str(root / "main.py")]
    subprocess.run(command, cwd=root, check=True)
    # Check the frozen app itself, not just the development environment. This
    # catches missing models, config files, and dynamically imported runtimes.
    report = root / "dist" / "ResultDesk" / "offline-check.json"
    executable = report.parent / "ResultDesk.exe"
    subprocess.run([str(executable), "--check-offline", str(report)], cwd=root, check=True, timeout=120)
    result = json.loads(report.read_text(encoding="utf-8"))
    if not result.get("ok"):
        raise RuntimeError(result.get("message", "Packaged OCR check failed"))
    import shutil
    shutil.copy2(root / "THIRD_PARTY_NOTICES.md", root / "dist" / "ResultDesk")
    print("Built dist/ResultDesk/ResultDesk.exe. Distribute the entire ResultDesk folder.")


if __name__ == "__main__":
    main()
