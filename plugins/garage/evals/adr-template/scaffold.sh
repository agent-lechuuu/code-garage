#!/usr/bin/env bash
# Writes the fixture project into the empty workspace (files only).
set -euo pipefail
cat > 'README.md' <<'GARAGE_EOF'
# billing-service

The billing service. Design notes live in `docs/`.
GARAGE_EOF
mkdir -p 'docs'
cat > 'docs/overview.md' <<'GARAGE_EOF'
# Overview

Billing owns invoices and payments.
GARAGE_EOF
