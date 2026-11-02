#!/usr/bin/env bash
# Writes the fixture project into the empty workspace (files only).
set -euo pipefail
cat > 'requirements.txt' <<'GARAGE_EOF'
requests==2.32.3
GARAGE_EOF
cat > 'client.py' <<'GARAGE_EOF'
import requests

BASE = "https://api.example.com"


def get_invoice(invoice_id):
    r = requests.get(f"{BASE}/invoices/{invoice_id}", timeout=10)
    r.raise_for_status()
    return r.json()


def create_payment(payload):
    r = requests.post(f"{BASE}/payments", json=payload, timeout=10)
    r.raise_for_status()
    return r.json()
GARAGE_EOF
