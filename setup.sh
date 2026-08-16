#!/bin/bash
set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}🛠  LinuxWhisper Setup${NC}"

# ---------------------------------------------------------------------------
# 1. Detect Distribution
# ---------------------------------------------------------------------------
detect_distro() {
    if command -v pacman &>/dev/null; then
        echo "arch"
    elif command -v dnf &>/dev/null; then
        echo "fedora"
    elif command -v apt &>/dev/null; then
        echo "debian"
    else
        echo "unknown"
    fi
}

DISTRO=$(detect_distro)
echo -e "${BLUE}📋 Detected distribution: ${DISTRO}${NC}"

if [ "$DISTRO" = "unknown" ]; then
    echo -e "${RED}❌ Error: Unsupported distribution. This script supports Debian/Ubuntu (apt), Fedora/RHEL (dnf) and Arch Linux (pacman).${NC}"
    exit 1
fi

# ---------------------------------------------------------------------------
# 2. Detect Session Type
# ---------------------------------------------------------------------------
SESSION_TYPE="${XDG_SESSION_TYPE:-x11}"
echo -e "${BLUE}🖥️  Session type: ${SESSION_TYPE}${NC}"

# ---------------------------------------------------------------------------
# 3. Install System Dependencies
# ---------------------------------------------------------------------------
echo -e "${BLUE}📦 Installing system packages (password may be required)...${NC}"

if [ "$DISTRO" = "debian" ]; then
    sudo apt update
    sudo apt install -y \
        python3-venv python3-pip \
        libgirepository1.0-dev gcc libcairo2-dev pkg-config python3-dev \
        gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 gir1.2-webkit2-4.1 \
        libspeexdsp-dev xclip

    if [ "$SESSION_TYPE" = "wayland" ]; then
        echo -e "${BLUE}📦 Installing Wayland-specific packages...${NC}"
        sudo apt install -y wtype wl-clipboard grim gtk-layer-shell-dev
    else
        sudo apt install -y xdotool gnome-screenshot
    fi

elif [ "$DISTRO" = "fedora" ]; then
    sudo dnf install -y \
        python3 gcc python3-devel pkgconf cairo-devel gobject-introspection-devel \
        gtk3 libayatana-appindicator-gtk3 webkit2gtk4.1 speexdsp-devel \
        python3-pip xclip

    if [ "$SESSION_TYPE" = "wayland" ]; then
        echo -e "${BLUE}📦 Installing Wayland-specific packages...${NC}"
        sudo dnf install -y wtype wl-clipboard grim gtk-layer-shell-devel
    else
        sudo dnf install -y xdotool gnome-screenshot
    fi

elif [ "$DISTRO" = "arch" ]; then
    sudo pacman -Syu --noconfirm --needed \
        python python-pip \
        gobject-introspection gcc cairo pkgconf \
        gtk3 libayatana-appindicator webkit2gtk-4.1 \
        speexdsp python-evdev

    if [ "$SESSION_TYPE" = "wayland" ]; then
        echo -e "${BLUE}📦 Installing Wayland-specific packages...${NC}"
        sudo pacman -S --noconfirm --needed wtype wl-clipboard grim gtk-layer-shell
    else
        sudo pacman -S --noconfirm --needed xdotool xclip gnome-screenshot
    fi
fi

# ---------------------------------------------------------------------------
# 4. Check input group (required for evdev hotkeys)
# ---------------------------------------------------------------------------
if ! groups "$USER" | grep -qw input; then
    echo ""
    echo -e "${YELLOW}⚠️  Your user is not in the 'input' group.${NC}"
    echo "   This is required for global hotkeys to work."
    read -p "   Add $USER to the 'input' group? (Y/n): " add_input
    if [[ ! "$add_input" =~ ^[nN] ]]; then
        sudo usermod -aG input "$USER"
        echo -e "${GREEN}✅ Added $USER to 'input' group.${NC}"
        echo -e "${YELLOW}   ⚠️ You need to log out and back in for this to take effect!${NC}"
    else
        echo -e "${YELLOW}   ⚠️ Skipping. Hotkeys may not work without 'input' group access.${NC}"
    fi
fi

# ---------------------------------------------------------------------------
# 5. Create Virtual Environment
# ---------------------------------------------------------------------------
if [ ! -d "venv" ]; then
    echo -e "${BLUE}🐍 Creating Python virtual environment (--system-site-packages)...${NC}"
    python3 -m venv --system-site-packages venv
else
    echo -e "${BLUE}🐍 Virtual environment already exists.${NC}"
fi

# ---------------------------------------------------------------------------
# 6. Install Package (editable mode)
# ---------------------------------------------------------------------------
echo -e "${BLUE}⬇️  Installing LinuxWhisper package...${NC}"
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -e .

# ---------------------------------------------------------------------------
# 7. Optional Autostart
# ---------------------------------------------------------------------------
echo ""
echo -e "${BLUE}🚀 Autostart Setup${NC}"
read -p "Add LinuxWhisper to autostart? (y/N): " add_autostart
if [[ "$add_autostart" =~ ^[yYjJ] ]]; then
    # Parse GROQ_API_KEY from .bashrc or environment if it exists
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
    echo "Comment=Voice-Assistant & AI Companion for Linux" >> "$DESKTOP_FILE"
    echo "Icon=$PWD/assets/logo.png" >> "$DESKTOP_FILE"
    
    EXEC_CMD="$PWD/venv/bin/linuxwhisper"
    
    if [ -n "$API_KEY" ]; then
        echo "Exec=env GROQ_API_KEY=\"$API_KEY\" $EXEC_CMD" >> "$DESKTOP_FILE"
        echo -e "${GREEN}✅ GROQ_API_KEY loaded from .bashrc and added to autostart!${NC}"
    else
        echo "Exec=$EXEC_CMD" >> "$DESKTOP_FILE"
        echo -e "${BLUE}ℹ️ No GROQ_API_KEY found in .bashrc. Autostart created without key.${NC}"
    fi
    
    echo "Terminal=false" >> "$DESKTOP_FILE"
    echo "Categories=AudioVideo;Utility;" >> "$DESKTOP_FILE"
    
    echo -e "${GREEN}✅ Autostart entry created at $DESKTOP_FILE${NC}"
fi

# ---------------------------------------------------------------------------
# 8. Niri Configuration Hint (if on Wayland + niri)
# ---------------------------------------------------------------------------
if [ "$SESSION_TYPE" = "wayland" ] && command -v niri &>/dev/null; then
    echo ""
    echo -e "${BLUE}📝 Niri Tip:${NC} For best overlay behaviour, add this to ~/.config/niri/config.kdl:"
    echo ""
    echo '  layer-rule {
      match namespace="linuxwhisper-recording"
      // Recording overlay: no shadow, no blur
      shadow { on false }
  }

  layer-rule {
      match namespace="linuxwhisper-chat"
      // Chat overlay
      shadow { on false }
  }'
    echo ""
fi

# ---------------------------------------------------------------------------
# 9. Success Message
# ---------------------------------------------------------------------------
echo -e "${GREEN}✅ Installation complete!${NC}"
echo -e "${BLUE}🔒 Setting permissions for multi-user access...${NC}"
chmod -R a+rX venv

echo ""
echo "To run LinuxWhisper:"
echo "  1. Set your API key: export GROQ_API_KEY=\"your_key\""
echo "  2. Run: linuxwhisper"
echo "     Or:  python -m linuxwhisper"
echo ""
echo "Session: $SESSION_TYPE | Distro: $DISTRO"
echo ""
