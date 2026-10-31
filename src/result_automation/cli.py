from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from .document import open_document
from .extract import extract_document
from .storage import export_csv, export_xlsx, save_session


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Extract student rolls and rightmost marks entirely offline.")
    parser.add_argument("source", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True, help="Destination .csv or .xlsx")
    parser.add_argument("--force-ocr", action="store_true", help="Ignore PDF text and test the local image OCR path")
    parser.add_argument("--max-mark", type=float)
    parser.add_argument("--session", type=Path, help="Also save an editable .json review session")
    args = parser.parse_args(argv)
    if args.output.suffix.lower() not in {".csv", ".xlsx"}:
        parser.error("--output must end in .csv or .xlsx")
    if args.max_mark is not None and (args.max_mark <= 0 or not math.isfinite(args.max_mark)):
        parser.error("--max-mark must be a finite positive number")
    try:
        document = open_document(args.source, force_ocr=args.force_ocr,
                                 progress=lambda message: print(message, file=sys.stderr))
        document.max_mark = args.max_mark
        extract_document(document)
        for warning in document.warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        if not document.records:
            print("No rows were extracted. Open the desktop app to select columns manually.", file=sys.stderr)
            return 2
        exporter = export_xlsx if args.output.suffix.lower() == ".xlsx" else export_csv
        exporter(document, args.output)
        if args.session:
            save_session(document, args.session)
        flagged = sum(bool(row.issues) for row in document.records)
        print(f"Exported {len(document.records)} rows across {len(document.pages)} pages; "
              f"{flagged} need review. Saved {args.output}")
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
