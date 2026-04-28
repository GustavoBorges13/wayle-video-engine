# 🎬 Wayle Video Engine

An advanced animated wallpaper manager (Videos, GIFs, and Images) featuring a native **GTK3** GUI, specifically built for the **Wayland / Hyprland** ecosystem to integrate with `wayle` and `mpvpaper`.

This software fills the gap for video wallpapers in Hyprland, behaving similarly to highly praised programs like *Wallpaper Engine*, but running completely natively on top of the Wayland protocol.

## 🎥 Demonstrations & Performance

**Video 1:** Testing `.mp4` video wallpaper changes (powered by `mpvpaper`).

https://github.com/user-attachments/assets/c735c6bf-0a44-4ffd-992a-f699002a6953

**Video 2:** Testing static images and `.gif` wallpaper changes (handled natively by `awww`).

https://github.com/user-attachments/assets/3cb023e5-803c-4c46-9796-49fbe1e2f90e

> **📈 The Result:** As shown in the resource monitoring terminal, `mpvpaper` only consumes hardware resources when a video is actively playing. `awww` acts as a lightweight background fallback engine—handling beautiful transition animations and taking over entirely if you switch to a static image or GIF.  

---

## ⚙️ How the Magic Works
By default, the Wayland ecosystem and Wayle do not accept `.mp4` video files natively as dynamic wallpapers. Wayle expects static images to run background scripts.

The **Wayle Video Engine** acts as an interceptor to overcome this limitation:
1. It automatically generates a high-quality, full-resolution thumbnail of your video's first frame using `ffmpeg`.
2. It injects this thumbnail into Wayle's `runtime.toml`, triggering `awww` to perform a smooth "Fade/Transition" animation.
3. After the transition animation is complete (timed by the *Transition Delay* slider), it spins up `mpvpaper` seamlessly directly on top of that static image.

The visual result is a flawless experience without tearing or black flickers between video loops or background changes.

## ✨ Key Features
* **Eco RAM (Pause):** Instantly pauses videos and transitions to a static high-quality frame, killing the `mpvpaper` process to save 100% of CPU/GPU resources while you game or work.
* **Favorites System ❤️:** Bookmark your preferred images, gifs, and videos with a simple click on the floating heart icon on thumbnails.
* **Smart Fit/Fill:** Automatically calculates aspect ratios (e.g., Ultrawide vs 16:9) to decide if a video should be stretched (fill) or fitted with borders (fit).
* **Independent Monitors:** Link the same video across all screens, or select different wallpapers and scaling settings for each individual monitor.
* **Native Mpv Engine:** Adjust brightness and video speed (slow-motion) directly from the GUI in real-time.
* **Smooth Transitions:** Leverages the `wayle/awww` engine to fade between wallpapers natively.
* **Auto-Save & Debounce:** Settings apply instantly without "Apply" buttons, optimized to prevent flickering.

---

## ✨ HyDE Project & Wallbash Integration
If you enable HyDE Integration in the settings, the engine will attempt to link with HyDE's `wallpaper.sh`. 

Whenever you pick a video wallpaper:
1. The engine extracts the high-quality first frame.
2. It sends it directly to HyDE.
3. HyDE uses **Wallbash** to read the dominant colors of that specific video frame and themes your entire system (terminal, borders, bars) instantly based on the video you just launched!

⚠️ **Disclaimer:** The HyDE / Wallbash integration is highly experimental and has not been thoroughly tested under all setups yet. It may cause unexpected CPU spikes or fail to apply colors depending on your HyDE version. Use it with caution.

---

## 📦 Requirements
Being tailored for Arch Linux and Hyprland, it relies on:
* `wayle` (and `awww`)
* `mpvpaper`
* `ffmpeg` (for generating high-quality thumbnails)
* `python-gobject` and `gtk3` (For the GUI)

## 🚀 Installation

Clone this repository and run the install script. It will check for pacman dependencies, install the required python modules, and setup the `systemd` user daemon.

```bash
git clone https://github.com/GustavoBorges13/wayle-video-engine.git
cd wayle-video-engine
chmod +x install.sh
./install.sh
```

## 🤝 Contributing
Feel free to open Issues or Pull Requests. Contributions to improve the code or add features are always welcome!