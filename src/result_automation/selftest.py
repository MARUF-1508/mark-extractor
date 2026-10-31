"""Exercise bundled models while blocking Python socket/DNS access."""
from pathlib import Path
import socket
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont

from .ocr import LocalOCR


def offline_check() -> str:
    def deny_network(*args, **kwargs):
        raise AssertionError("A runtime component attempted a network connection")

    image = Image.new("RGB", (500, 100), "white")
    candidates = [Path("C:/Windows/Fonts/arial.ttf"), Path("/usr/share/fonts/TTF/DejaVuSans.ttf")]
    font_path = next((path for path in candidates if path.exists()), None)
    font = ImageFont.truetype(str(font_path), 40) if font_path else ImageFont.load_default(size=40)
    ImageDraw.Draw(image).text((25, 20), "328     39.5", font=font, fill="black")
    with patch.object(socket.socket, "connect", deny_network), \
            patch.object(socket, "create_connection", deny_network), \
            patch.object(socket, "getaddrinfo", deny_network):
        words = LocalOCR().recognize(image)
    recognized = " ".join(word.text for word in words)
    if "328" not in recognized or "39.5" not in recognized:
        raise RuntimeError(f"OCR smoke check returned an unexpected result: {recognized!r}")
    return "Offline OCR check passed: bundled CPU models recognized 328 and 39.5 with networking blocked."
