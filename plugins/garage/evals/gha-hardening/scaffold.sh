#!/usr/bin/env bash
# Writes the fixture project into the empty workspace (files only).
set -euo pipefail
mkdir -p '.github/workflows'
cat > '.github/workflows/ci.yml' <<'GARAGE_EOF'
name: ci
on:
  push:
  pull_request_target:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
      - run: npm ci
      - run: npm test
      - run: echo "${{ github.event.pull_request.title }}"
GARAGE_EOF
cat > 'package.json' <<'GARAGE_EOF'
{
  "name": "lib",
  "scripts": {
    "test": "node --test"
  }
}
GARAGE_EOF
