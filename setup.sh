#!/bin/bash
# ============================================================
#  AutoTrade Bot — One-shot Phase 1 Setup Script
#  Run this once on a fresh machine:
#      chmod +x setup.sh && ./setup.sh
# ============================================================

set -e  # Exit on first error

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}"
echo "  ██████╗ ██╗   ██╗████████╗ ██████╗ ████████╗██████╗  █████╗ ██████╗ ███████╗"
echo "  ██╔══██╗██║   ██║╚══██╔══╝██╔═══██╗╚══██╔══╝██╔══██╗██╔══██╗██╔══██╗██╔════╝"
echo "  ███████║██║   ██║   ██║   ██║   ██║   ██║   ██████╔╝███████║██║  ██║█████╗  "
echo "  ██╔══██║██║   ██║   ██║   ██║   ██║   ██║   ██╔══██╗██╔══██║██║  ██║██╔══╝  "
echo "  ██║  ██║╚██████╔╝   ██║   ╚██████╔╝   ██║   ██║  ██║██║  ██║██████╔╝███████╗"
echo "  ╚═╝  ╚═╝ ╚═════╝    ╚═╝    ╚═════╝    ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚══════╝"
echo -e "${NC}"
echo "  Phase 1 Setup — AutoTrade Bot"
echo "  ─────────────────────────────"

# ── Step 1: Python version check ─────────────────────────────────
echo -e "\n${YELLOW}[1/6] Checking Python version...${NC}"
python_version=$(python3 --version 2>&1 | awk '{print $2}')
required="3.10"
if python3 -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)"; then
    echo -e "  ✅ Python $python_version — OK"
else
    echo -e "  ${RED}❌ Python 3.10+ required. You have $python_version${NC}"
    echo "  Install from: https://www.python.org/downloads/"
    exit 1
fi

# ── Step 2: Virtual environment ───────────────────────────────────
echo -e "\n${YELLOW}[2/6] Creating virtual environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "  ✅ venv created"
else
    echo -e "  ✅ venv already exists"
fi

# Activate
source venv/bin/activate
echo -e "  ✅ venv activated"

# ── Step 3: Install dependencies ──────────────────────────────────
echo -e "\n${YELLOW}[3/6] Installing dependencies...${NC}"
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo -e "  ✅ All packages installed"

# ── Step 4: .env setup ────────────────────────────────────────────
echo -e "\n${YELLOW}[4/6] Setting up .env...${NC}"
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "  ✅ .env created from template"
    echo -e "  ${YELLOW}⚠️  Open .env and fill in your API keys before continuing!${NC}"
else
    echo -e "  ✅ .env already exists"
fi

# ── Step 5: Git setup ────────────────────────────────────────────
echo -e "\n${YELLOW}[5/6] Setting up Git...${NC}"
if [ ! -d ".git" ]; then
    git init
    git add .
    git commit -m "chore: initial project scaffold — Phase 1"
    echo -e "  ✅ Git repo initialised"
else
    echo -e "  ✅ Git repo already exists"
fi

# ── Step 6: Verify install ────────────────────────────────────────
echo -e "\n${YELLOW}[6/6] Verifying install...${NC}"
python3 -c "import pandas, numpy, kiteconnect, binance, streamlit, backtrader; print('  ✅ All imports successful')"

# ── Done ──────────────────────────────────────────────────────────
echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Phase 1 Setup Complete! 🎉"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Next steps:"
echo "  1. Edit .env and add your API keys"
echo "  2. Get Kite access token:"
echo "     python -m src.data.kite_client --login"
echo "  3. Run connection tests:"
echo "     python -m pytest tests/test_connections.py -v"
echo "  4. Move on to Phase 2 — Data Pipeline!"
echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
