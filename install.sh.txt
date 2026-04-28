#!/usr/bin/env bash

echo "=============================================="
echo "Installer - Wayle Video Engine"
echo "=============================================="

# 1. Check system dependencies (Arch Linux)
echo "[*] Checking system dependencies..."
DEPS=("mpvpaper" "ffmpeg" "python-gobject" "gtk3")
for dep in "${DEPS[@]}"; do
    if ! command -v $dep &> /dev/null && ! pacman -Qs $dep &> /dev/null; then
        echo "[!] Missing dependency: $dep. Installing..."
        sudo pacman -S --noconfirm $dep
    fi
done

# 2. Python dependencies
echo "[*] Installing Python dependencies..."
pip install tomlkit Pillow --break-system-packages --quiet

# 3. Create necessary directories
echo "[*] Creating user directories..."
mkdir -p ~/.config/wayle
mkdir -p ~/.config/systemd/user
mkdir -p ~/.local/share/applications

# 4. Copy Python scripts
echo "[*] Installing python scripts..."
cp wayle_video_engine.py ~/.config/wayle/
cp wayle_engine_gui.py ~/.config/wayle/
chmod +x ~/.config/wayle/wayle_video_engine.py
chmod +x ~/.config/wayle/wayle_engine_gui.py

# 5. Create .desktop shortcut dynamically
echo "[*] Creating application shortcut..."
cat <<EOF > ~/.local/share/applications/wayle-video-engine.desktop
[Desktop Entry]
Type=Application
Name=Wayle Video Engine
Comment=Animated Wallpaper Engine for Wayle (HyDE)
Exec=sh -c "\$HOME/.config/wayle/wayle_engine_gui.py"
Icon=video-display
Terminal=false
Categories=Settings;DesktopSettings;
EOF

# 6. Install and enable systemd user service
echo "[*] Enabling background daemon..."
cp wayle-video.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now wayle-video.service
systemctl --user restart wayle-video.service

echo "=============================================="
echo "✅ Installation Complete!"
echo "You can now launch 'Wayle Video Engine' from your app launcher."
echo "=============================================="