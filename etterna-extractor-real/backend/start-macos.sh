#!/bin/bash
# Run from any directory: bash /path/to/backend/start-macos.sh
set -euo pipefail
cd "$(dirname "$0")"
if [[ "$(uname -s)" != Darwin ]]; then
  echo "This launcher is for macOS. Elsewhere, use python3 -m uvicorn server:app."
  exit 1
fi

extractor_python="${ETTERNA_PYTHON:-}"
if [[ -z "$extractor_python" ]]; then
  for candidate in "${VIRTUAL_ENV:-/nonexistent}/bin/python3" .venv-local/bin/python3 .venv/bin/python3 python3; do
    if "$candidate" -c 'import uvicorn, cv2, pytesseract' >/dev/null 2>&1; then
      extractor_python="$candidate"
      break
    fi
  done
fi
if [[ -z "$extractor_python" ]]; then
  echo "No working Python with the backend dependencies was found. Run:"
  echo "python3 -m venv .venv-local"
  echo "./.venv-local/bin/python3 -m pip install -r requirements.txt"
  exit 1
fi

export OCR_ENGINE="${OCR_ENGINE:-rapidocr}"
if [[ "$OCR_ENGINE" == apple || "$OCR_ENGINE" == auto ]]; then
  if [[ ! -x apple-ocr || AppleOCR.swift -nt apple-ocr ]]; then
    if ! command -v swiftc >/dev/null 2>&1; then
      echo "Install Apple's compiler with: xcode-select --install"
      echo "Then run this launcher again. For Tesseract: OCR_ENGINE=tesseract bash start-macos.sh"
      exit 1
    fi
    swiftc AppleOCR.swift -O -o apple-ocr
  fi
fi
"$extractor_python" -c 'from native_ocr import engine; print("Starting combined backend 16.0; OCR:", engine(), flush=True)'
exec "$extractor_python" -m uvicorn server:app --host 0.0.0.0 --port 8000
