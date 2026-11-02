#!/usr/bin/env bash
# Writes the fixture project into the empty workspace (files only).
set -euo pipefail
cat > 'pagination.py' <<'GARAGE_EOF'
def paginate(items, page_size):
    pages = []
    for start in range(0, len(items) - page_size, page_size):
        pages.append(items[start:start + page_size])
    return pages
GARAGE_EOF
