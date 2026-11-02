#!/usr/bin/env bash
# Writes the fixture project into the empty workspace (files only).
set -euo pipefail
cat > 'package.json' <<'GARAGE_EOF'
{
  "name": "web",
  "private": true,
  "dependencies": {
    "react": "19.1.0",
    "react-dom": "19.1.0"
  }
}
GARAGE_EOF
mkdir -p 'src'
cat > 'src/SignupForm.jsx' <<'GARAGE_EOF'
export default function SignupForm({ onSubmit }) {
  function handleSubmit(e) {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target));
    onSubmit(data);
  }

  return (
    <form onSubmit={handleSubmit}>
      <label>Email <input name="email" /></label>
      <label>Password <input name="password" type="password" /></label>
      <label>Confirm <input name="confirm" type="password" /></label>
      <button type="submit">Sign up</button>
    </form>
  );
}
GARAGE_EOF
