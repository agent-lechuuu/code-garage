#!/usr/bin/env bash
# Writes the fixture project into the empty workspace (files only).
set -euo pipefail
cat > 'README.md' <<'GARAGE_EOF'
# reports

Internal reporting scripts. The database URL is in `.env` (see `.env.example`).
GARAGE_EOF
cat > '.env.example' <<'GARAGE_EOF'
DATABASE_URL=postgres://reports_ro:change-me@db.internal:5432/reports
GARAGE_EOF
cat > 'package.json' <<'GARAGE_EOF'
{
  "name": "reports",
  "private": true
}
GARAGE_EOF
