#!/bin/bash
set -euo pipefail
integration_dir="$(cd "$(dirname "$0")" && pwd)"
target_repo="${1:?Usage: bash apply-rhythmbackend.sh /path/to/RhythmBackend-repository}"
if [[ ! -f "$target_repo/RhythmBackend/Program.cs" ]]; then
  echo "Choose the repository root containing RhythmBackend/Program.cs."
  exit 1
fi
patch_file="$integration_dir/rhythmbackend-mentra.patch"
if git -C "$target_repo" apply --reverse --check "$patch_file" >/dev/null 2>&1; then
  echo "The Mentra integration patch is already applied."
  exit 0
fi
if ! git -C "$target_repo" apply --check "$patch_file"; then
  echo "The patch overlaps repository changes. No files were changed."
  echo "Inspect the patch and merge the changes before continuing."
  exit 1
fi
git -C "$target_repo" apply "$patch_file"
echo "Mentra coaching endpoint installed. Existing API endpoints are retained."
