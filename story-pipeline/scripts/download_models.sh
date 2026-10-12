#!/usr/bin/env bash
# Download local model files that are fetched outside pip.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/models/kokoro"
cd "$ROOT/models/kokoro"
BASE=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
for f in kokoro-v1.0.onnx voices-v1.0.bin; do
  [ -f "$f" ] || { echo "downloading $f"; curl -fL -o "$f.part" "$BASE/$f" && mv "$f.part" "$f"; }
done
echo "Kokoro voices ready in models/kokoro"
