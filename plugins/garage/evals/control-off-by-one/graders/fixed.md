---
type: regex
target:
  source: file
  path: pagination.py
pattern: 'len\(items\) - page_size'
match: not_contains
---
