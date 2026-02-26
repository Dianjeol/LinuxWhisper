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
                    gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 gir1.2-webkit2-4.1 \
                    xdotool gnome-screenshot libspeexdsp-dev

# 3. Create Virtual Environment
if [ ! -d "venv" ]; then
    echo -e "${BLUE}🐍 Creating Python virtual environment (--system-site-packages)...${NC}"
    python3 -m venv --system-site-packages venv
else
    echo -e "${BLUE}🐍 Virtual environment already exists.${NC}"
fi

# 4. Install Package (editable mode)
echo -e "${BLUE}⬇️  Installing LinuxWhisper package...${NC}"
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -e .


# 5. Optional Autostart
echo ""
echo -e "${BLUE}🚀 Autostart Setup${NC}"
read -p "Möchtest du LinuxWhisper zum Autostart hinzufügen? (j/N): " add_autostart
if [[ "$add_autostart" =~ ^[jJ] ]]; then
    # Parse GROQ_API_KEY from .bashrc if it exists
    API_KEY=""
    if [ -f "$HOME/.bashrc" ]; then
        API_KEY=$(grep -s "^export GROQ_API_KEY=" "$HOME/.bashrc" | tail -n 1 | cut -d'=' -f2- | tr -d "\"'")
    fi

    AUTOSTART_DIR="$HOME/.config/autostart"
    mkdir -p "$AUTOSTART_DIR"
    DESKTOP_FILE="$AUTOSTART_DIR/linuxwhisper.desktop"
    
    # Write desktop file
    echo "[Desktop Entry]" > "$DESKTOP_FILE"
    echo "Type=Application" >> "$DESKTOP_FILE"
    echo "Name=LinuxWhisper" >> "$DESKTOP_FILE"
    echo "Comment=Whisper Dictation" >> "$DESKTOP_FILE"
    echo "Icon=$PWD/assets/logo.png" >> "$DESKTOP_FILE"
    
    EXEC_CMD="$PWD/venv/bin/linuxwhisper"
    
    if [ -n "$API_KEY" ]; then
        echo "Exec=env GROQ_API_KEY=\"$API_KEY\" $EXEC_CMD" >> "$DESKTOP_FILE"
        echo -e "${GREEN}✅ GROQ_API_KEY aus .bashrc geladen und zum Autostart hinzugefügt!${NC}"
    else
        echo "Exec=$EXEC_CMD" >> "$DESKTOP_FILE"
        echo -e "${BLUE}ℹ️ Kein GROQ_API_KEY in .bashrc gefunden. Autostart ohne Key erstellt.${NC}"
    fi
    
    echo "Terminal=false" >> "$DESKTOP_FILE"
    echo "Categories=AudioVideo;Utility;" >> "$DESKTOP_FILE"
    
    echo -e "${GREEN}✅ Autostart-Eintrag erstellt in $DESKTOP_FILE${NC}"
fi

# 6. Success Message
echo -e "${GREEN}✅ Installation complete!${NC}"
echo -e "${BLUE}🔒 Setting permissions for multi-user access...${NC}"
chmod -R a+rX venv

echo ""
echo "To run LinuxWhisper:"
echo "  1. Set your API key (see README.md)"
echo "  2. Run: linuxwhisper"
echo "     Or:  python -m linuxwhisper"
echo ""
