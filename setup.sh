#!/bin/bash
set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🛠  LinuxWhisper Setup${NC}"

# 1. Check for apt (Debian/Ubuntu)
if ! command -v apt &> /dev/null; then
    echo "❌ Error: 'apt' not found. This script supports Debian/Ubuntu based systems."
    exit 1
fi

# 2. Install System Dependencies
echo -e "${BLUE}📦 Installing system packages (password may be required)...${NC}"
sudo apt update
sudo apt install -y python3-venv python3-pip \
                    libgirepository1.0-dev gcc libcairo2-dev pkg-config python3-dev \
                    gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 \
                    xdotool gnome-screenshot

# 3. Create Virtual Environment
if [ ! -d "venv" ]; then
    echo -e "${BLUE}🐍 Creating Python virtual environment (--system-site-packages)...${NC}"
    python3 -m venv --system-site-packages venv
else
    echo -e "${BLUE}🐍 Virtual environment already exists.${NC}"
fi

# 4. Install Python Dependencies
echo -e "${BLUE}⬇️  Installing Python requirements...${NC}"
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 5. Success Message
echo -e "${GREEN}✅ Installation complete!${NC}"
echo ""
echo "To run LinuxWhisper:"
echo "  1. Set your API key (see README.md)"
echo "  2. Run: ./venv/bin/python linuxwhisper.py"
echo ""
