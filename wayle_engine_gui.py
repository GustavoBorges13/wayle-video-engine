#!/usr/bin/env python3
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GdkPixbuf, GLib, Gdk
import json
import os
import subprocess
from pathlib import Path
import tomlkit
import threading
import shutil

TOML_PATH = Path.home() / ".config/wayle/runtime.toml"
SETTINGS_PATH = Path.home() / ".config/wayle/video_engine_settings.json"
CACHE_DIR = Path.home() / ".cache" / "wayle_video_engine"
THUMBS_DIR = CACHE_DIR / "thumbs"
SUPPORTED = [".mp4", ".mkv", ".webm", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif"]
TRANSITIONS = ["none", "simple", "fade", "left", "right", "top", "bottom", "wipe", "wave", "grow", "center", "any", "random", "outer"]

THUMBS_DIR.mkdir(parents=True, exist_ok=True)

class WayleEngineApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="Wayle Video Engine")
        self.set_default_size(1200, 750)
        self.set_position(Gtk.WindowPosition.CENTER)

        self.is_loading_ui = True
        self.save_timer = None
        self.pending_reload = False 
        self.settings = self.load_settings()
        self.videos_dir = Path(self.settings["videos_path"])
        self.monitors = self.get_monitors_from_toml()

        self.header = Gtk.HeaderBar()
        self.header.set_show_close_button(True)
        self.header.set_title("Wayle Video Engine")
        self.set_titlebar(self.header)

        self.btn_config = Gtk.Button(label="⚙️ Settings")
        self.btn_config.connect("clicked", self.toggle_view)
        self.header.pack_end(self.btn_config)

        self.paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(self.paned)

        self.sidebar_scrolled = Gtk.ScrolledWindow()
        self.sidebar_scrolled.set_size_request(320, -1)
        self.sidebar_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        self.sidebar_box.set_margin_top(20)
        self.sidebar_box.set_margin_bottom(20)
        self.sidebar_box.set_margin_start(20)
        self.sidebar_box.set_margin_end(20)
        self.sidebar_scrolled.add(self.sidebar_box)
        self.paned.pack1(self.sidebar_scrolled, False, False)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.paned.pack2(self.stack, True, False)

        self.create_sidebar()
        self.create_gallery_view()
        self.create_config_view()

        self.is_loading_ui = False
        self.refresh_gallery()

    def get_monitors_from_toml(self):
        try:
            with open(TOML_PATH, "r") as f: doc = tomlkit.load(f)
            return [m["name"] for m in doc.get("wallpaper", {}).get("monitors", [])]
        except: return ["DP-3", "HDMI-A-1"]

    def load_settings(self):
        default = {
            "cycle_enabled": True, "interval_minutes": 5, "cycle_mode": "shuffle", "mute": True, 
            "shared_monitors": True, "videos_path": str(Path.home() / "wallpapers/videos"), 
            "transition_delay": 2.0, "transition_type": "fade", "is_paused": False, 
            "fit_modes": {}, "fixed_wallpapers": {}, "playback_speed": 1.0, "brightness": 0,
            "force_reload": False,
            "hyde_integration": True, "startup_behavior": "restore" # NOVAS OPÇÕES
        }
        if SETTINGS_PATH.exists():
            try:
                with open(SETTINGS_PATH, "r") as f: return {**default, **json.load(f)}
            except: pass
        return default

    def create_title(self, text):
        lbl = Gtk.Label(label=f"<b>{text}</b>", use_markup=True, xalign=0)
        lbl.set_margin_top(10)
        self.sidebar_box.pack_start(lbl, False, False, 0)

    def create_row(self, label_text, widget):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl = Gtk.Label(label=label_text, xalign=0)
        box.pack_start(lbl, True, True, 0)
        box.pack_start(widget, False, False, 0)
        self.sidebar_box.pack_start(box, False, False, 0)

    # ================= SIDEBAR =================
    def create_sidebar(self):
        self.create_title("🖥️ Displays & Layout")
        
        self.sw_shared = Gtk.Switch(active=self.settings["shared_monitors"])
        self.sw_shared.connect("notify::active", self.on_setting_changed_silent)
        self.sw_shared.connect("notify::active", self.update_target_selector)
        self.create_row("Link Displays", self.sw_shared)

        self.sidebar_box.pack_start(Gtk.Label(label="Scaling Mode:", xalign=0, margin_top=5), False, False, 0)
        self.combo_fit = Gtk.ComboBoxText()
        for opt in ["fill", "fit", "auto"]: self.combo_fit.append_text(opt)
        self.combo_fit.set_active(["fill", "fit", "auto"].index(self.settings.get("fit_modes", {}).get(self.monitors[0], "fill")))
        self.combo_fit.connect("changed", self.on_fit_change)
        self.sidebar_box.pack_start(self.combo_fit, False, False, 0)

        self.create_title("🎛️ Video Engine (Mpv)")
        
        self.sw_pause = Gtk.Switch(active=self.settings["is_paused"])
        self.sw_pause.connect("notify::active", self.on_setting_changed_silent)
        self.create_row("Pause (Eco RAM)", self.sw_pause)

        self.sw_mute = Gtk.Switch(active=self.settings["mute"])
        self.sw_mute.connect("notify::active", self.on_setting_changed_silent) 
        self.create_row("Mute Audio", self.sw_mute)

        self.sidebar_box.pack_start(Gtk.Label(label="Playback Speed:", xalign=0, margin_top=5), False, False, 0)
        self.scale_speed = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.25, 2.0, 0.25)
        self.scale_speed.set_value(self.settings["playback_speed"])
        self.scale_speed.connect("value-changed", self.on_setting_changed_silent) 
        self.sidebar_box.pack_start(self.scale_speed, False, False, 0)

        self.sidebar_box.pack_start(Gtk.Label(label="Brightness:", xalign=0, margin_top=5), False, False, 0)
        self.scale_bright = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -50, 50, 5)
        self.scale_bright.set_value(self.settings["brightness"])
        self.scale_bright.connect("value-changed", self.on_setting_changed_silent) 
        self.sidebar_box.pack_start(self.scale_bright, False, False, 0)

        self.create_title("🔄 Cycle & Transition")

        self.sw_cycle = Gtk.Switch(active=self.settings["cycle_enabled"])
        self.sw_cycle.connect("notify::active", self.on_setting_changed_silent)
        self.create_row("Enable Cycle", self.sw_cycle)

        self.combo_mode = Gtk.ComboBoxText()
        for opt in ["shuffle", "sequential"]: self.combo_mode.append_text(opt)
        self.combo_mode.set_active(["shuffle", "sequential"].index(self.settings["cycle_mode"]))
        self.combo_mode.connect("changed", self.on_setting_changed_silent)
        self.sidebar_box.pack_start(self.combo_mode, False, False, 0)

        self.sidebar_box.pack_start(Gtk.Label(label="Interval (Minutes):", xalign=0, margin_top=5), False, False, 0)
        self.scale_interval = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 60, 1)
        self.scale_interval.set_value(self.settings["interval_minutes"])
        self.scale_interval.connect("value-changed", self.on_setting_changed_silent)
        self.sidebar_box.pack_start(self.scale_interval, False, False, 0)

        self.sidebar_box.pack_start(Gtk.Label(label="Transition Style:", xalign=0, margin_top=5), False, False, 0)
        self.combo_trans = Gtk.ComboBoxText()
        current_trans = self.settings.get("transition_type", "fade")
        if current_trans not in TRANSITIONS: current_trans = "fade"
        for opt in TRANSITIONS: self.combo_trans.append_text(opt)
        self.combo_trans.set_active(TRANSITIONS.index(current_trans))
        self.combo_trans.connect("changed", self.on_setting_changed_silent) 
        self.sidebar_box.pack_start(self.combo_trans, False, False, 0)

    # ================= MAIN AREA =================
    def create_gallery_view(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        self.target_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.target_box.set_margin_top(10)
        self.target_box.set_margin_bottom(10)
        self.target_box.set_margin_start(10)
        
        self.target_buttons = {}
        first_btn = None
        for mon in self.monitors:
            btn = Gtk.RadioButton.new_with_label_from_widget(first_btn, mon)
            if not first_btn: first_btn = btn
            btn.set_mode(False)
            btn.connect("toggled", self.on_target_toggled, mon)
            self.target_box.pack_start(btn, False, False, 0)
            self.target_buttons[mon] = btn

        vbox.pack_start(self.target_box, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_max_children_per_line(10)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flowbox.set_margin_top(10)
        self.flowbox.set_margin_start(10)
        self.flowbox.set_margin_end(10)
        
        scroll.add(self.flowbox)
        vbox.pack_start(scroll, True, True, 0)

        self.loading_spinner = Gtk.Spinner()
        self.loading_spinner.set_size_request(50, 50)
        self.loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.loading_box.set_halign(Gtk.Align.CENTER)
        self.loading_box.set_valign(Gtk.Align.CENTER)
        self.loading_box.pack_start(self.loading_spinner, False, False, 0)
        self.loading_label = Gtk.Label(label="Loading library...")
        self.loading_box.pack_start(self.loading_label, False, False, 0)

        self.gallery_overlay = Gtk.Overlay()
        self.gallery_overlay.add(vbox)
        self.gallery_overlay.add_overlay(self.loading_box)

        self.stack.add_named(self.gallery_overlay, "gallery")
        self.update_target_selector()

    def create_config_view(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=30)
        vbox.set_margin_top(40)
        vbox.set_margin_start(40)

        lbl = Gtk.Label(label="<span size='x-large' weight='bold'>System Configuration</span>", use_markup=True, xalign=0)
        vbox.pack_start(lbl, False, False, 0)

        # === HYDE INTEGRATION SECTION ===
        box_hyde = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box_hyde.pack_start(Gtk.Label(label="<b>✨ HyDE Project Integration</b>", use_markup=True, xalign=0), False, False, 0)
        
        row_hyde = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.sw_hyde = Gtk.Switch(active=self.settings.get("hyde_integration", True))
        self.sw_hyde.connect("notify::active", self.on_setting_changed_silent)
        row_hyde.pack_start(Gtk.Label(label="Enable 'hydectl' Sync (Generates Wallbash colors & saves state)", xalign=0), True, True, 0)
        row_hyde.pack_start(self.sw_hyde, False, False, 0)
        box_hyde.pack_start(row_hyde, False, False, 0)

        row_startup = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.combo_startup = Gtk.ComboBoxText()
        for opt in ["Restore Last Wallpaper", "Clear Screen (Black)"]: 
            self.combo_startup.append_text(opt)
        idx = 1 if self.settings.get("startup_behavior", "restore") == "clear" else 0
        self.combo_startup.set_active(idx)
        self.combo_startup.connect("changed", self.on_setting_changed_silent)
        row_startup.pack_start(Gtk.Label(label="On System Login/Boot:", xalign=0), True, True, 0)
        row_startup.pack_start(self.combo_startup, False, False, 0)
        box_hyde.pack_start(row_startup, False, False, 0)

        vbox.pack_start(box_hyde, False, False, 0)
        # ================================

        def make_section(title, path_txt, btn_text, callback):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            box.pack_start(Gtk.Label(label=f"<b>{title}</b>", use_markup=True, xalign=0), False, False, 0)
            box.pack_start(Gtk.Label(label=path_txt, xalign=0), False, False, 0)
            btn = Gtk.Button(label=btn_text)
            btn.set_halign(Gtk.Align.START)
            btn.connect("clicked", callback)
            box.pack_start(btn, False, False, 0)
            vbox.pack_start(box, False, False, 0)

        self.lbl_folder = Gtk.Label(label=str(self.videos_dir), xalign=0)
        box1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        box1.pack_start(Gtk.Label(label="<b>📁 Wallpapers Folder</b>", use_markup=True, xalign=0), False, False, 0)
        box1.pack_start(self.lbl_folder, False, False, 0)
        btn_f = Gtk.Button(label="Change Folder")
        btn_f.set_halign(Gtk.Align.START)
        btn_f.connect("clicked", self.change_folder)
        box1.pack_start(btn_f, False, False, 0)
        vbox.pack_start(box1, False, False, 0)

        make_section("🗄️ Cache & Thumbnails", str(CACHE_DIR), "Clear Cache & Reload", self.clear_cache)
        
        box3 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        box3.pack_start(Gtk.Label(label="<b>📜 Engine Config File</b>", use_markup=True, xalign=0), False, False, 0)
        box3.pack_start(Gtk.Label(label=str(SETTINGS_PATH), xalign=0), False, False, 0)
        vbox.pack_start(box3, False, False, 0)

        self.stack.add_named(vbox, "config")

    # ================= LOGIC & EVENTS =================
    def toggle_view(self, btn):
        if self.stack.get_visible_child_name() == "gallery":
            self.stack.set_visible_child_name("config")
            self.btn_config.set_label("◀ Back")
        else:
            self.stack.set_visible_child_name("gallery")
            self.btn_config.set_label("⚙️ Settings")

    def update_target_selector(self, *args):
        is_shared = self.sw_shared.get_active()
        for mon, btn in self.target_buttons.items():
            btn.set_sensitive(not is_shared)
        if is_shared:
            self.target_buttons[self.monitors[0]].set_active(True)
            self.target_box.set_opacity(0.5)
        else:
            self.target_box.set_opacity(1.0)
        self.update_fit_combo_for_current_target()

    def get_active_target(self):
        for mon, btn in self.target_buttons.items():
            if btn.get_active(): return mon
        return self.monitors[0]

    def on_target_toggled(self, btn, mon):
        if btn.get_active(): self.update_fit_combo_for_current_target()

    def update_fit_combo_for_current_target(self):
        self.is_loading_ui = True
        target = self.get_active_target()
        modes = self.settings.get("fit_modes", {})
        val = modes.get(target, "fill")
        try: self.combo_fit.set_active(["fill", "fit", "auto"].index(val))
        except: self.combo_fit.set_active(0)
        self.is_loading_ui = False

    def on_fit_change(self, combo):
        if self.is_loading_ui: return
        target = self.get_active_target()
        val = combo.get_active_text()
        if "fit_modes" not in self.settings: self.settings["fit_modes"] = {}
        self.settings["fit_modes"][target] = val
        self.trigger_save() 

    def on_setting_changed_silent(self, *args):
        if self.is_loading_ui: return
        self.trigger_save(needs_reload=False)

    def trigger_save(self, needs_reload=False):
        if needs_reload: self.pending_reload = True
        if self.save_timer: GLib.source_remove(self.save_timer)
        self.save_timer = GLib.timeout_add(500, self.do_save_and_apply)

    def do_save_and_apply(self):
        self.save_timer = None
        new_settings = {
            "cycle_enabled": self.sw_cycle.get_active(),
            "interval_minutes": int(self.scale_interval.get_value()),
            "cycle_mode": self.combo_mode.get_active_text(),
            "mute": self.sw_mute.get_active(),
            "shared_monitors": self.sw_shared.get_active(),
            "videos_path": str(self.videos_dir),
            "transition_delay": float(self.settings.get("transition_delay", 2.0)),
            "transition_type": self.combo_trans.get_active_text(),
            "is_paused": self.sw_pause.get_active(),
            "fit_modes": self.settings.get("fit_modes", {}),
            "fixed_wallpapers": self.settings.get("fixed_wallpapers", {}),
            "playback_speed": float(self.scale_speed.get_value()),
            "brightness": int(self.scale_bright.get_value()),
            "force_reload": getattr(self, 'pending_reload', False),
            "hyde_integration": self.sw_hyde.get_active(),
            "startup_behavior": "clear" if self.combo_startup.get_active() == 1 else "restore"
        }
        self.pending_reload = False
        
        with open(SETTINGS_PATH, "w") as f: json.dump(new_settings, f, indent=4)
        return False

    def clear_cache(self, btn):
        shutil.rmtree(THUMBS_DIR, ignore_errors=True)
        THUMBS_DIR.mkdir(parents=True, exist_ok=True)
        self.toggle_view(None)
        self.refresh_gallery()

    def change_folder(self, btn):
        dialog = Gtk.FileChooserDialog(title="Select Folder", parent=self, action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, "Select", Gtk.ResponseType.OK)
        dialog.set_current_folder(str(self.videos_dir))
        if dialog.run() == Gtk.ResponseType.OK:
            self.videos_dir = Path(dialog.get_filename())
            self.lbl_folder.set_label(str(self.videos_dir))
            self.trigger_save()
            self.toggle_view(None)
            self.refresh_gallery()
        dialog.destroy()

    def refresh_gallery(self):
        for child in self.flowbox.get_children(): self.flowbox.remove(child)
        self.loading_box.show_all()
        self.loading_spinner.start()
        threading.Thread(target=self.async_load_thumbs, daemon=True).start()

    def async_load_thumbs(self):
        files = [f for f in self.videos_dir.glob("*.*") if f.suffix.lower() in SUPPORTED]
        if not files:
            GLib.idle_add(self.finish_loading, "No compatible files found.")
            return

        missing = [f for f in files if not (THUMBS_DIR / f"{f.stem}.png").exists()]
        if missing:
            GLib.idle_add(self.loading_label.set_label, f"Generating {len(missing)} High-Quality thumbnails...")
            for f in missing:
                t = THUMBS_DIR / f"{f.stem}.png"
                cmd = ["ffmpeg", "-y", "-i", str(f), "-ss", "00:00:00.000", "-vframes", "1", "-q:v", "2", str(t)]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        GLib.idle_add(self.draw_gallery, files)

    def draw_gallery(self, files):
        files_dict = {f.stem: f for f in files}
        thumbs = sorted([t for t in THUMBS_DIR.glob("*.png") if t.stem in files_dict])
        
        for t in thumbs:
            original_file = files_dict[t.stem]
            is_vid = original_file.suffix.lower() in [".mp4", ".webm", ".mkv"]
            badge = "🎬" if is_vid else "🖼️"

            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(t), 180, 101, False)
            img = Gtk.Image.new_from_pixbuf(pixbuf)
            
            lbl = Gtk.Label(label=f"{badge} {t.stem[:15]}...", margin_top=5)
            
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            box.pack_start(img, False, False, 0)
            box.pack_start(lbl, False, False, 0)
            
            btn = Gtk.Button()
            btn.add(box)
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.connect("clicked", self.on_image_click, str(original_file))
            
            self.flowbox.add(btn)
            
        self.flowbox.show_all()
        self.finish_loading("")
        return False

    def finish_loading(self, text):
        self.loading_spinner.stop()
        self.loading_box.hide()
        if text:
            lbl = Gtk.Label(label=text)
            lbl.show()
            self.flowbox.add(lbl)
        return False

    def on_image_click(self, btn, file_path):
        active_target = self.get_active_target()
        fixed = self.settings.get("fixed_wallpapers", {})
        
        if self.sw_shared.get_active(): fixed["all"] = file_path
        else: fixed[active_target] = file_path

        self.settings["fixed_wallpapers"] = fixed
        self.trigger_save(needs_reload=True) 

if __name__ == "__main__":
    app = WayleEngineApp()
    app.connect("destroy", Gtk.main_quit)
    app.show_all()
    Gtk.main()