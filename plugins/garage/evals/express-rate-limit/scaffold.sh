#!/usr/bin/env bash
# Writes the fixture project into the empty workspace (files only).
set -euo pipefail
cat > 'package.json' <<'GARAGE_EOF'
{
  "name": "orders-api",
  "version": "1.0.0",
  "main": "src/server.js",
  "dependencies": {
    "express": "4.21.2"
  }
}
GARAGE_EOF
mkdir -p 'src'
cat > 'src/app.js' <<'GARAGE_EOF'
const express = require('express');

const app = express();
app.use(express.json());

const orders = [];

app.get('/health', (req, res) => res.json({ ok: true }));
app.get('/api/orders', (req, res) => res.json(orders));
app.post('/api/orders', (req, res) => {
  const order = { id: orders.length + 1, ...req.body };
  orders.push(order);
  res.status(201).json(order);
});

module.exports = app;
GARAGE_EOF
mkdir -p 'src'
cat > 'src/server.js' <<'GARAGE_EOF'
const app = require('./app');

app.listen(process.env.PORT || 3000);
GARAGE_EOF
