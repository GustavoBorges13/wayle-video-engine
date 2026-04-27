#!/usr/bin/env python3
import os
import time
import random
import subprocess
import json
from pathlib import Path
import tomlkit

# ================= PATHS =================
DEFAULT_VIDEOS_DIR = Path.home() / "wallpapers/videos"
CACHE_DIR = Path.home() / ".cache" / "wayle_video_engine"
THUMBS_DIR = CACHE_DIR / "thumbs"
TOML_PATH = Path.home() / ".config/wayle/runtime.toml"
SETTINGS_PATH = Path.home() / ".config/wayle/video_engine_settings.json"

SUPPORTED_VIDEOS = [".mp4", ".mkv", ".webm"]
SUPPORTED_IMAGES = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif"]
ALL_SUPPORTED = SUPPORTED_VIDEOS + SUPPORTED_IMAGES

THUMBS_DIR.mkdir(parents=True, exist_ok=True)
current_playing_dict = {}

def load_settings():
    default = {
        "cycle_enabled": True, "interval_minutes": 5, "cycle_mode": "shuffle", 
        "mute": True, "shared_monitors": True, "videos_path": str(DEFAULT_VIDEOS_DIR), 
        "transition_delay": 2.0, "transition_type": "fade", "is_paused": False, 
        "fit_modes": {}, "fixed_wallpapers": {}, "playback_speed": 1.0, "brightness": 0
    }
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, "r") as f: return {**default, **json.load(f)}
        except: pass
    return default

def get_monitors_from_toml():
    try:
        with open(TOML_PATH, "r") as f: doc = tomlkit.load(f)
        return [m["name"] for m in doc.get("wallpaper", {}).get("monitors", [])]
    except: return ["DP-3", "HDMI-A-1"]

MONITORS = get_monitors_from_toml()

def is_video(file_path): return Path(file_path).suffix.lower() in SUPPORTED_VIDEOS

def get_monitor_aspect(mon_name):
    try:
        out = subprocess.check_output(["hyprctl", "monitors", "-j"]).decode()
        for m in json.loads(out):
            if m["name"] == mon_name: return m["width"] / m["height"]
    except: pass
    return 16/9

def get_file_aspect(file_path):
    try:
        cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", str(file_path)]
        w, h = map(int, subprocess.check_output(cmd).decode().strip().split("x"))
        return w / h
    except: return 16/9

def resolve_fit_mode(fit_preference, file_path, mon_name):
    if fit_preference != "auto": return fit_preference
    v_asp = get_file_aspect(file_path)
    m_asp = get_monitor_aspect(mon_name)
    if abs(v_asp - m_asp) > 0.2: return "fit" 
    return "fill"

def generate_thumbnail(file_path):
    thumb_path = THUMBS_DIR / f"{file_path.stem}.png"
    if not thumb_path.exists():
        cmd = [
            "ffmpeg", "-y", "-i", str(file_path),
            "-ss", "00:00:00.000", "-vframes", "1",
            "-q:v", "2", str(thumb_path)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return thumb_path

def update_wayle_toml(monitor_file_dict, monitor_thumb_dict, cfg, force_transition=None):
    try:
        with open(TOML_PATH, "r") as f: doc = tomlkit.load(f)
        doc["wallpaper"]["cycling-enabled"] = False
        doc["wallpaper"]["transition-type"] = force_transition if force_transition else cfg["transition_type"]
        
        if "wallpaper" in doc and "monitors" in doc["wallpaper"]:
            for m in doc["wallpaper"]["monitors"]:
                mon_name = m["name"]
                if mon_name in monitor_thumb_dict:
                    pref = cfg["fit_modes"].get(mon_name, "fill") # Fill as native default
                    m["fit-mode"] = resolve_fit_mode(pref, monitor_file_dict[mon_name], mon_name)
                    m["wallpaper"] = str(monitor_thumb_dict[mon_name])
                
        with open(TOML_PATH, "w") as f: tomlkit.dump(doc, f)
    except Exception as e: print(f"[!] TOML Error: {e}")

def kill_mpvpaper():
    os.system("killall -q mpvpaper")
    time.sleep(0.2)

def start_mpvpaper(monitor_video_dict, cfg):
    kill_mpvpaper()
    for mon, file_path in monitor_video_dict.items():
        if is_video(file_path):
            audio_flag = "no-audio" if cfg["mute"] else ""
            pref = cfg["fit_modes"].get(mon, "fill")
            actual_mode = resolve_fit_mode(pref, file_path, mon)
            
            mpv_options = f"loop {audio_flag}"
            if actual_mode == "fill": mpv_options += " --panscan=1.0"
            
            # Add MPV Speed and Brightness options
            speed = cfg.get("playback_speed", 1.0)
            brightness = cfg.get("brightness", 0)
            mpv_options += f" --speed={speed} --brightness={brightness}"
            
            subprocess.Popen(["mpvpaper", "-o", mpv_options, mon, str(file_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def apply_wallpapers(monitor_file_dict, cfg):
    global current_playing_dict
    current_playing_dict = monitor_file_dict
    monitor_thumb_dict = {}
    has_video = False
    
    for mon, file_path in monitor_file_dict.items():
        if is_video(file_path):
            monitor_thumb_dict[mon] = generate_thumbnail(file_path)
            has_video = True
        else: monitor_thumb_dict[mon] = file_path
            
    update_wayle_toml(monitor_file_dict, monitor_thumb_dict, cfg)
    if has_video:
        time.sleep(float(cfg["transition_delay"]))
        start_mpvpaper(monitor_file_dict, cfg)
    else: kill_mpvpaper()

def handle_pause(cfg):
    paused_imgs = {}
    for mon, file_path in current_playing_dict.items():
        if is_video(file_path): paused_imgs[mon] = generate_thumbnail(file_path)
        else: paused_imgs[mon] = file_path
    update_wayle_toml(current_playing_dict, paused_imgs, cfg, force_transition="simple")
    kill_mpvpaper()

def main_loop():
    global current_playing_dict
    print("=== Wayle Video Engine Started ===")
    
    last_cfg = load_settings()
    was_paused = last_cfg["is_paused"]
    time_elapsed = 0
    last_index = 0
    
    while True:
        cfg = load_settings()
        videos_dir = Path(cfg["videos_path"])
        files = [f for f in videos_dir.glob("*.*") if f.suffix.lower() in ALL_SUPPORTED]
        
        if cfg["is_paused"] and not was_paused: handle_pause(cfg); was_paused = True
        elif not cfg["is_paused"] and was_paused: apply_wallpapers(current_playing_dict, cfg); was_paused = False

        if cfg["is_paused"] or not files:
            time.sleep(1)
            continue

        if time_elapsed >= (cfg["interval_minutes"] * 60) or not current_playing_dict:
            time_elapsed = 0
            monitor_file_dict = {}
            if not cfg["cycle_enabled"]:
                if cfg["shared_monitors"]:
                    vid = Path(cfg["fixed_wallpapers"].get("all", files[0]))
                    for m in MONITORS: monitor_file_dict[m] = vid
                else:
                    for m in MONITORS: monitor_file_dict[m] = Path(cfg["fixed_wallpapers"].get(m, files[0]))
            else:
                if cfg["shared_monitors"]:
                    if cfg["cycle_mode"] == "shuffle": vid = random.choice(files)
                    else:
                        files.sort()
                        vid = files[last_index % len(files)]
                        last_index += 1
                    for m in MONITORS: monitor_file_dict[m] = vid
                else:
                    for m in MONITORS: monitor_file_dict[m] = random.choice(files)

            if monitor_file_dict != current_playing_dict: apply_wallpapers(monitor_file_dict, cfg)

        time.sleep(1)
        time_elapsed += 1

if __name__ == "__main__":
    try: main_loop()
    except KeyboardInterrupt: kill_mpvpaper()