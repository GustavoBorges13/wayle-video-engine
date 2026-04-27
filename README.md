# 🎬 Wayle Video Engine

An advanced animated wallpaper manager (Videos, GIFs, and Images) featuring a native **GTK3** GUI, specifically built for the **Wayland / Hyprland** ecosystem to integrate with `wayle` and `mpvpaper`.

Designed with **HyDE Project** users in mind, it leverages `awww` for smooth transitions and optimally injects `mpvpaper` under the hood.

![Interface Screenshot](replace_with_your_screenshot_link.jpg)

## ✨ Key Features
* **Eco RAM (Pause):** Instantly pauses videos and transitions to a static high-quality frame, killing the `mpvpaper` process to save 100% of CPU/GPU resources while you game or work.
* **Smart Fit/Fill:** Automatically calculates aspect ratios (e.g., Ultrawide vs 16:9) to decide if a video should be stretched (fill) or fitted with borders (fit).
* **Independent Monitors:** Link the same video across all screens, or select different wallpapers and scaling settings for each individual monitor.
* **Native Mpv Engine:** Adjust brightness and video speed (slow-motion) directly from the GUI in real-time.
* **Smooth Transitions:** Leverages the `wayle/awww` engine to fade between wallpapers natively.
* **Auto-Save & Debounce:** Settings apply instantly without "Apply" buttons, optimized to prevent flickering.

## 📦 Requirements
Being tailored for Arch Linux and Hyprland, it relies on:
* `wayle` (and `awww`)
* `mpvpaper`
* `ffmpeg` (for generating high-quality thumbnails)
* `python-gobject` and `gtk3` (For the GUI)

## 🚀 Installation

Clone this repository and run the install script. It will check for pacman dependencies, install the required python modules, and setup the `systemd` user daemon.

```bash
git clone https://github.com/YOUR_USERNAME/wayle-video-engine.git
cd wayle-video-engine
chmod +x install.sh
./install.sh
```

## ⚙️ How the Magic Works
By default, Wayle does not accept `.mp4` video files natively.
The **Wayle Video Engine** acts as an interceptor:
1. It generates a high-quality, full-resolution thumbnail of your video.
2. It injects this thumbnail into Wayle's `runtime.toml`, triggering `awww` to perform a smooth "Fade/Transition" animation.
3. After the transition delay, it spins up `mpvpaper` seamlessly on top of the static image.

The visual result is identical to heavy engines like *Wallpaper Engine*, but completely native to Wayland.

## 🤝 Contributing
Feel free to open Issues or Pull Requests. Contributions to improve the code or add features are always welcome!