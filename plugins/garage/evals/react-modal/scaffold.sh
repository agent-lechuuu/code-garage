#!/usr/bin/env bash
# Writes the fixture project into the empty workspace (files only).
set -euo pipefail
cat > 'package.json' <<'GARAGE_EOF'
{
  "name": "settings-app",
  "private": true,
  "dependencies": {
    "react": "19.1.0",
    "react-dom": "19.1.0"
  }
}
GARAGE_EOF
mkdir -p 'src'
cat > 'src/App.jsx' <<'GARAGE_EOF'
export default function App({ onDelete }) {
  return (
    <main>
      <h1>Account settings</h1>
      <button type="button" onClick={onDelete}>Delete account</button>
    </main>
  );
}
GARAGE_EOF
