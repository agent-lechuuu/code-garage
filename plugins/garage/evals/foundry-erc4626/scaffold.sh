#!/usr/bin/env bash
# Writes the fixture project into the empty workspace (files only).
set -euo pipefail
cat > 'foundry.toml' <<'GARAGE_EOF'
[profile.default]
src = "src"
out = "out"
libs = ["lib"]
solc = "0.8.26"
GARAGE_EOF
mkdir -p 'src'
: > 'src/.gitkeep'
mkdir -p 'test'
: > 'test/.gitkeep'
cat > 'README.md' <<'GARAGE_EOF'
# usdc-vault

A USDC yield vault. Build with `forge build`.
GARAGE_EOF
