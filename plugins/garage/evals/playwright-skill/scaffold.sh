#!/usr/bin/env bash
# Writes the fixture project into the empty workspace (files only).
set -euo pipefail
cat > 'package.json' <<'GARAGE_EOF'
{
  "name": "shop-web",
  "private": true,
  "scripts": {
    "dev": "vite",
    "test:e2e": "playwright test"
  },
  "devDependencies": {
    "@playwright/test": "1.55.0",
    "vite": "7.1.5"
  }
}
GARAGE_EOF
cat > 'index.html' <<'GARAGE_EOF'
<!doctype html><title>Shop</title><div id="app"></div>
GARAGE_EOF
