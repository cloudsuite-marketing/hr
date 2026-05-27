#!/bin/bash
cd "$(dirname "$0")"

# Laad .env als het bestaat
if [ -f ".env" ]; then
  export $(grep -v '^#' .env | xargs)
fi

if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo ""
  echo "⚠️  ANTHROPIC_API_KEY is niet ingesteld."
  echo ""
  echo "1. Kopieer .env.example naar .env:"
  echo "   cp .env.example .env"
  echo ""
  echo "2. Open .env en vul je Anthropic API-sleutel in."
  echo "   (verkrijgbaar via: https://console.anthropic.com)"
  echo ""
  exit 1
fi

echo "✅  CloudSuite HR Assistent wordt gestart op http://localhost:5050"
python3 app.py
