#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/backend"

echo "=== ESCAP Trade Analyzer — Setup ==="

# Create virtualenv
if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
fi

source venv/bin/activate

echo "Installing Python dependencies (this may take a few minutes)..."
pip install -q -r requirements.txt

# Create .env if missing
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo ">>> ACTION REQUIRED: add your Anthropic API key to backend/.env"
  echo "    ANTHROPIC_API_KEY=sk-ant-..."
  echo ""
else
  echo ".env already exists."
fi

# Create uploads dir
mkdir -p uploads

echo ""
echo "=== Setup complete ==="
echo ""
echo "To start the server:"
echo "  cd backend && source venv/bin/activate && uvicorn main:app --reload --port 8000"
echo ""
echo "Then open: http://localhost:8000"
