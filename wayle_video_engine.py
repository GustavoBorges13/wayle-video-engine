#!/usr/bin/env python3
import os
import time
import random
import subprocess
import json
import signal
import sys
import threading
import shutil
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
mpvpaper_processes = []
current_transition_id = 0


def sig_handler(signum, frame):
    kill_mpvpaper()
    sys.exit(0)


signal.signal(signal.SIGTERM, sig_handler)


def load_settings():
    default = {
        "cycle_enabled": True,
        "interval_minutes": 5,
        "cycle_mode": "shuffle",
        "mute": True,
        "shared_monitors": True,
        "videos_path": str(DEFAULT_VIDEOS_DIR),
        "transition_delay": 2.0,
        "transition_type": "fade",
        "is_paused": False,
        "fit_modes": {},
        "fixed_wallpapers": {},
        "playback_speed": 1.0,
        "brightness": 0,
        "force_reload": False,
        "hyde_integration": True,
        "startup_behavior": "restore"
    }
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, "r") as f:
                return {**default, **json.load(f)}
        except:
            pass
    return default


def clear_flags(cfg):
    cfg["force_reload"] = False
    try:
        with open(SETTINGS_PATH, "w") as f:
            json.dump(cfg, f, indent=4)
    except:
        pass


def get_monitors_from_toml():
    try:
        with open(TOML_PATH, "r") as f:
            doc = tomlkit.load(f)
        return [m["name"] for m in doc.get("wallpaper", {}).get("monitors", [])]
    except:
        return ["DP-3", "HDMI-A-1"]


MONITORS = get_monitors_from_toml()


def is_video(file_path):
    return Path(file_path).suffix.lower() in SUPPORTED_VIDEOS


def get_monitor_aspect(mon_name):
    try:
        out = subprocess.check_output(["hyprctl", "monitors", "-j"]).decode()
        for m in json.loads(out):
            if m["name"] == mon_name:
                return m["width"] / m["height"]
    except:
        pass
    return 16 / 9


def get_file_aspect(file_path):
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=s=x:p=0",
            str(file_path),
        ]
        w, h = map(int, subprocess.check_output(cmd).decode().strip().split("x"))
        return w / h
    except:
        return 16 / 9


def resolve_fit_mode(fit_preference, file_path, mon_name):
    if fit_preference != "auto":
        return fit_preference
    v_asp = get_file_aspect(file_path)
    m_asp = get_monitor_aspect(mon_name)
    if abs(v_asp - m_asp) > 0.2:
        return "fit"
    return "fill"


def generate_thumbnail(file_path):
    thumb_path = THUMBS_DIR / f"{file_path.stem}.png"
    if not thumb_path.exists():
        print(f"[DEBUG] Generating thumbnail for {file_path.name}...", flush=True)
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(file_path),
            "-ss",
            "00:00:00.000",
            "-vframes",
            "1",
            "-q:v",
            "2",
            str(thumb_path),
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return thumb_path


def update_wayle_toml(monitor_file_dict, monitor_thumb_dict, cfg, force_transition=None):
    try:
        with open(TOML_PATH, "r") as f:
            doc = tomlkit.load(f)
        doc["wallpaper"]["cycling-enabled"] = False
        doc["wallpaper"]["transition-type"] = (
            force_transition if force_transition else cfg["transition_type"]
        )

        if "wallpaper" in doc and "monitors" in doc["wallpaper"]:
            for m in doc["wallpaper"]["monitors"]:
                mon_name = m["name"]
                if mon_name in monitor_thumb_dict:
                    pref = cfg["fit_modes"].get(mon_name, "fill")
                    m["fit-mode"] = resolve_fit_mode(
                        pref, monitor_file_dict[mon_name], mon_name
                    )
                    m["wallpaper"] = str(monitor_thumb_dict[mon_name])

        with open(TOML_PATH, "w") as f:
            tomlkit.dump(doc, f)
    except:
        pass


def kill_mpvpaper():
    global mpvpaper_processes
    for proc in mpvpaper_processes:
        try:
            proc.terminate()
        except:
            pass
    mpvpaper_processes = []
    os.system("killall -q mpvpaper")


# ================= FIX: AMBIENTE GLOBAL =================
# Esta função garante que comandos como mpvpaper e hydectl 
# rodem com as variáveis de ambiente corretas do Wayland/Hyprland
def get_dynamic_env():
    dynamic_env = os.environ.copy()
    try:
        sys_env = subprocess.check_output(
            ["systemctl", "--user", "show-environment"], text=True
        )
        for line in sys_env.splitlines():
            if "=" in line:
                key, val = line.split("=", 1)
                dynamic_env[key] = val
    except Exception as e:
        print(f"[DEBUG] Could not fetch systemd environment: {e}", flush=True)
    return dynamic_env
# ========================================================


def start_mpvpaper(monitor_video_dict, cfg):
    global mpvpaper_processes
    kill_mpvpaper()
    env = get_dynamic_env()
 
    for mon, file_path in monitor_video_dict.items():
        if is_video(file_path):
            try:
                audio_flag = "no-audio" if cfg["mute"] else ""
                pref = cfg["fit_modes"].get(mon, "fill")
                actual_mode = resolve_fit_mode(pref, file_path, mon)

                mpv_options = f"loop {audio_flag} --hwdec=auto"
                if actual_mode == "fill":
                    mpv_options += " --panscan=1.0"

                speed = cfg.get("playback_speed", 1.0)
                brightness = cfg.get("brightness", 0)
                mpv_options += f" --speed={speed} --brightness={brightness}"

                proc = subprocess.Popen(
                    ["mpvpaper", "-o", mpv_options, mon, str(file_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=env,
                )
                mpvpaper_processes.append(proc)
            except Exception as e:
                print(f"[ERROR] Failed to start mpvpaper: {e}", flush=True)


def delayed_mpv_start(monitor_file_dict, cfg, expected_id):
    time.sleep(float(cfg["transition_delay"]))
    if current_transition_id == expected_id:
        start_mpvpaper(monitor_file_dict, cfg)

def execute_hyde_integration(img_path, cfg):
    """Executa o wallpaper.sh nativo do HyDE para gerar cache, cores e aplicar na tela."""
    if not cfg.get("hyde_integration", True):
        print("[DEBUG] HyDE integration is DISABLED in settings.", flush=True)
        return

    # Busca o executável raiz do HyDE (wallpaper.sh)
    wall_sh = shutil.which("wallpaper.sh")
    if not wall_sh:
        fallback = Path.home() / ".local/lib/hyde/wallpaper.sh"
        if fallback.exists():
            wall_sh = str(fallback)

    if not wall_sh:
        print("[DEBUG] wallpaper.sh NOT FOUND in system. Skipping HyDE integration.", flush=True)
        return

    print(f"[DEBUG] HyDE wallpaper.sh detected! Injecting thumbnail...", flush=True)
    env = get_dynamic_env()
    
    try:
        # COMANDO MÁGICO DO HYDE:
        # -s : Set specified wallpaper
        # -b awww : Use awww backend
        # -G : Set as global (Gera o cache do Wallbash e recarrega as cores do sistema)
        cmd = [wall_sh, "-s", str(img_path), "-b", "awww", "-G"]
        
        print(f"[DEBUG] Executing: {' '.join(cmd)}", flush=True)
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"[ERROR] HyDE apply failed with exit code {result.returncode}!", flush=True)
            print(f"[ERROR] STDOUT: {result.stdout}", flush=True)
            print(f"[ERROR] STDERR: {result.stderr}", flush=True)
        else:
            print(f"[DEBUG] HyDE applied successfully! Colors, Cache, and Wallpaper updated.", flush=True)
    except Exception as e:
        print(f"[ERROR] Exception occurred while running HyDE integration: {e}", flush=True)


def apply_wallpapers(monitor_file_dict, cfg):
    global current_playing_dict, current_transition_id
    current_playing_dict = monitor_file_dict
    monitor_thumb_dict = {}
    has_video = False

    current_transition_id = time.time()
    kill_mpvpaper()

    for mon, file_path in monitor_file_dict.items():
        if is_video(file_path):
            monitor_thumb_dict[mon] = generate_thumbnail(file_path)
            has_video = True
        else:
            monitor_thumb_dict[mon] = file_path

    # ======= INTEGRAÇÃO HYDE PROJECT =======
    primary_img = list(monitor_thumb_dict.values())[0]
    execute_hyde_integration(primary_img, cfg)
    # =======================================

    # Atualiza o TOML do Wayle
    update_wayle_toml(monitor_file_dict, monitor_thumb_dict, cfg)

    if has_video and not cfg["is_paused"]:
        threading.Thread(
            target=delayed_mpv_start,
            args=(monitor_file_dict, cfg, current_transition_id),
            daemon=True,
        ).start()


def handle_pause(cfg):
    global current_transition_id
    current_transition_id = time.time()
    paused_imgs = {}
    for mon, file_path in current_playing_dict.items():
        if is_video(file_path):
            paused_imgs[mon] = generate_thumbnail(file_path)
        else:
            paused_imgs[mon] = file_path
            
    # ======= INTEGRAÇÃO HYDE PROJECT =======
    primary_img = list(paused_imgs.values())[0]
    execute_hyde_integration(primary_img, cfg)
    # =======================================

    update_wayle_toml(current_playing_dict, paused_imgs, cfg, force_transition="simple")
    kill_mpvpaper()


def main_loop():
    global current_playing_dict
    print("=== Wayle Video Engine Started ===", flush=True)

    last_cfg = load_settings()
    
    # ======= COMPORTAMENTO DE STARTUP =======
    if last_cfg.get("startup_behavior") == "clear":
        print("[*] Clearing wallpaper on startup as requested...", flush=True)
        os.system("swww clear")
        os.system("awww clear")
    else:
        print("[*] Startup behavior: Restoring last wallpaper...", flush=True)
    # ========================================

    was_paused = last_cfg["is_paused"]
    
    # FIX: O tempo deve iniciar zerado para não pular o wallpaper no boot
    time_elapsed = 0
    last_index = 0
    
    # Guarda o estado do ciclo para saber quando ele foi ativado/desativado
    was_cycle_enabled = last_cfg["cycle_enabled"]

    while True:
        try:
            cfg = load_settings()
            videos_dir = Path(cfg["videos_path"])
            files = [
                f for f in videos_dir.glob("*.*") if f.suffix.lower() in ALL_SUPPORTED
            ]

            if not files:
                time.sleep(1)
                continue

            # FIX: Zera o cronômetro se o usuário acabou de ativar o Ciclo na interface
            if cfg["cycle_enabled"] and not was_cycle_enabled:
                print("[DEBUG] Cycle enabled! Resetting timer...", flush=True)
                time_elapsed = 0
            was_cycle_enabled = cfg["cycle_enabled"]

            if not current_playing_dict:
                monitor_file_dict = {}
                if cfg["shared_monitors"]:
                    vid = Path(cfg["fixed_wallpapers"].get("all", files[0]))
                    for m in MONITORS:
                        monitor_file_dict[m] = vid
                else:
                    for m in MONITORS:
                        monitor_file_dict[m] = Path(
                            cfg["fixed_wallpapers"].get(m, files[0])
                        )

                if cfg["is_paused"]:
                    current_playing_dict = monitor_file_dict
                    handle_pause(cfg)
                else:
                    apply_wallpapers(monitor_file_dict, cfg)
                    
            if cfg["is_paused"] and not was_paused:
                handle_pause(cfg)
                was_paused = True
            elif not cfg["is_paused"] and was_paused:
                apply_wallpapers(current_playing_dict, cfg)
                was_paused = False

            needs_visual_reload = False

            if cfg.get("force_reload", False):
                needs_visual_reload = True
                clear_flags(cfg)
                time_elapsed = 0

            elif (
                cfg["fit_modes"] != last_cfg.get("fit_modes", {})
                or cfg["playback_speed"] != last_cfg.get("playback_speed")
                or cfg["brightness"] != last_cfg.get("brightness")
                or cfg["mute"] != last_cfg.get("mute")
                or cfg["fixed_wallpapers"] != last_cfg.get("fixed_wallpapers", {})
            ):
                needs_visual_reload = True

            if needs_visual_reload:
                monitor_file_dict = {}
                if cfg["shared_monitors"]:
                    vid = Path(cfg["fixed_wallpapers"].get("all", files[0]))
                    for m in MONITORS:
                        monitor_file_dict[m] = vid
                else:
                    for m in MONITORS:
                        monitor_file_dict[m] = Path(
                            cfg["fixed_wallpapers"].get(m, files[0])
                        )

                if cfg["is_paused"]:
                    current_playing_dict = monitor_file_dict
                    handle_pause(cfg)
                else:
                    apply_wallpapers(monitor_file_dict, cfg)

            if (
                not cfg["is_paused"]
                and cfg["cycle_enabled"]
                and time_elapsed >= (cfg["interval_minutes"] * 60)
            ):
                monitor_file_dict = {}
                if cfg["shared_monitors"]:
                    if cfg["cycle_mode"] == "shuffle":
                        vid = random.choice(files)
                    else:
                        files.sort()
                        vid = files[last_index % len(files)]
                        last_index += 1
                    for m in MONITORS:
                        monitor_file_dict[m] = vid
                else:
                    for m in MONITORS:
                        monitor_file_dict[m] = random.choice(files)

                if monitor_file_dict != current_playing_dict:

                    fixed = cfg.get("fixed_wallpapers", {})
                    if cfg["shared_monitors"]:
                        fixed["all"] = str(monitor_file_dict[MONITORS[0]])
                    else:
                        for m in MONITORS:
                            fixed[m] = str(monitor_file_dict[m])
                    cfg["fixed_wallpapers"] = fixed
                    try:
                        with open(SETTINGS_PATH, "w") as f:
                            json.dump(cfg, f, indent=4)
                    except:
                        pass

                    apply_wallpapers(monitor_file_dict, cfg)
                time_elapsed = 0

            last_cfg = cfg
            time.sleep(1)

            # Só avança o cronômetro se o vídeo não estiver pausado e o ciclo estiver ativo
            if not cfg["is_paused"] and cfg["cycle_enabled"]:
                time_elapsed += 1

        except Exception as e:
            time.sleep(2)

if __name__ == "__main__":
    time.sleep(2)
    try: main_loop()
    except KeyboardInterrupt: kill_mpvpaper()