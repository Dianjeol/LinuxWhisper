#!/bin/bash
# Script to fix LinuxWhisper installation
set -e

echo "🔧 Fixing LinuxWhisper Installation (using /opt/LinuxWhisper/venv)..."

VENV_Py="/opt/LinuxWhisper/venv/bin/python3"
VENV_PIP="/opt/LinuxWhisper/venv/bin/pip"

# Ensure venv exists
if [ ! -f "$VENV_Py" ]; then
    echo "❌ Virtual environment not found at /opt/LinuxWhisper/venv"
    echo "Creating one..."
    sudo python3 -m venv /opt/LinuxWhisper/venv
fi

# 1. Install dependencies and the package into the VENV
echo "📦 Installing dependencies into venv..."
sudo "$VENV_PIP" install -r requirements.txt || true # Try requirements if exists
sudo "$VENV_PIP" install -e .

# 2. Update the global launcher script
echo "🚀 Updating /usr/local/bin/linuxwhisper launcher..."

LAUNCHER_CONTENT='#!/bin/bash
/opt/LinuxWhisper/venv/bin/python3 -m linuxwhisper "$@"'

echo "$LAUNCHER_CONTENT" | sudo tee /usr/local/bin/linuxwhisper > /dev/null
sudo chmod +x /usr/local/bin/linuxwhisper

echo "✅ Installation repaired!"
echo "➡️  Run 'linuxwhisper' to start the new version."
