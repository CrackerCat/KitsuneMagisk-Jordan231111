#!/usr/bin/env bash
set -euo pipefail

# PR10 prepares evidence only. Production signing, update publication and
# promotion remain the explicit PR10/PR16 gates in DEVELOPMENT_ROADMAP.md.
cd "$(dirname "$0")/.."
case "${1:-}" in
  verify|metadata)
    scripts/env.py python3 tools/next_system_baseline.py \
      --manifest docs/next-system-pr14.json --source --artifacts out \
      --report out/release-info.json
    ;;
  tag-name)
    scripts/env.py python3 tools/build_info.py --release-tag
    ;;
  *)
    echo "Usage: $0 <verify | metadata | tag-name>" >&2
    exit 1
    ;;
esac
