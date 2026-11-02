#!/usr/bin/env bash
# Writes the fixture project into the empty workspace (files only).
set -euo pipefail
mkdir -p 'src'
cat > 'src/retry.js' <<'GARAGE_EOF'
async function withRetry(fn) {
  let tmp = 0;
  for (;;) {
    try {
      return await fn();
    } catch (e) {
      tmp++;
      if (tmp >= 3) throw e;
    }
  }
}

module.exports = { withRetry };
GARAGE_EOF
