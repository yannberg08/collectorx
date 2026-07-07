#!/usr/bin/env bash
# Cross-compile the doubao-export single binary for all platforms into ../bin.
set -euo pipefail
cd "$(dirname "$0")/src"
out="$(cd .. && pwd)/bin"; mkdir -p "$out"
CGO_ENABLED=0 GOOS=darwin  GOARCH=arm64 go build -trimpath -o "$out/doubao-export-darwin-arm64"     .
CGO_ENABLED=0 GOOS=darwin  GOARCH=amd64 go build -trimpath -o "$out/doubao-export-darwin-amd64"     .
CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -trimpath -o "$out/doubao-export-windows-amd64.exe" .
CGO_ENABLED=0 GOOS=linux   GOARCH=amd64 go build -trimpath -o "$out/doubao-export-linux-amd64"      .
echo "built 4 binaries -> $out"
