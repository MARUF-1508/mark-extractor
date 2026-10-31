"""CPU-only OCR. Explicit model paths prevent runtime model downloads."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .models import Word


class LocalOCR:
    def __init__(self):
        self._engine = None

    def _load(self):
        import onnxruntime
        import rapidocr
        from rapidocr import RapidOCR

        onnxruntime.disable_telemetry_events()
        model_dir = Path(rapidocr.__file__).parent / "models"
        names = {
            "Det": "PP-OCRv6_det_small.onnx",
            "Rec": "PP-OCRv6_rec_small.onnx",
            "Cls": "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
        }
        params = {
            "EngineConfig.onnxruntime.intra_op_num_threads": 4,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            "Global.log_level": "error",
            "Global.text_score": 0.25,
            "Global.max_side_len": 3000,
        }
        for task, name in names.items():
            path = model_dir / name
            if not path.is_file():
                raise RuntimeError(
                    f"Bundled OCR model is missing: {name}. "
                    "Repair/reinstall Result Desk. Models are never downloaded at runtime."
                )
            params[f"{task}.model_path"] = str(path)
        self._engine = RapidOCR(params=params)

    def recognize(self, image: Image.Image) -> list[Word]:
        if self._engine is None:
            self._load()
        # RapidOCR expects OpenCV's BGR order for ndarray inputs.
        result = self._engine(np.asarray(image.convert("RGB"))[:, :, ::-1].copy())
        if result.boxes is None or result.txts is None:
            return []
        width, height = image.size
        words = []
        for points, text, score in zip(result.boxes, result.txts, result.scores):
            x0, y0 = points.min(axis=0)
            x1, y1 = points.max(axis=0)
            words.append(Word(text, (float(x0 / width), float(y0 / height),
                                     float(x1 / width), float(y1 / height)), float(score)))
        return words
