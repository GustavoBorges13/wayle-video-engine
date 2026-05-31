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
import fcntl
import sys

TOML_PATH = Path.home() / ".config/wayle/runtime.toml"
SETTINGS_PATH = Path.home() / ".config/wayle/video_engine_settings.json"
CACHE_DIR = Path.home() / ".cache" / "wayle_video_engine"
THUMBS_DIR = CACHE_DIR / "thumbs"
LOCK_FILE = CACHE_DIR / "gui.lock"

VIDEO_EXTS = [".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv"]
GIF_EXTS = [".gif"]
IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".webp", ".avif", ".bmp", ".svg", ".tga", ".tiff", ".jxl", ".pnm"]
SUPPORTED = VIDEO_EXTS + GIF_EXTS + IMAGE_EXTS

TRANSITIONS = ["none", "simple", "fade", "left", "right", "top", "bottom", "wipe", "wave", "grow", "center", "any", "random", "outer"]
FILTERS = ["All Wallpapers", "Favorites ❤️", "Videos 🎬", "Images 🖼️", "GIFs 🎞️"]

THUMBS_DIR.mkdir(parents=True, exist_ok=True)

# Ensures only one instance of the GUI is running
def acquire_single_instance_lock():
    try:
        global lock_fd
        lock_fd = open(LOCK_FILE, 'w')
        fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("[!] Another instance is already running. Exiting...")
        sys.exit(0)

class WayleEngineApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="Wayle Video Engine")
        self.set_default_size(1200, 750)
        self.set_position(Gtk.WindowPosition.CENTER)

        self.apply_custom_css()

        self.is_loading_ui = True
        self.save_timer = None
        self.pending_reload = False 
        self.wallpapers_dirty = False 
        self.current_load_id = 0 # Previne bugs se o usuário clicar rápido nas categorias
        
        self.settings = self.load_settings()
        self.current_filter = self.settings.get("active_filter", "All Wallpapers")
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

    def apply_custom_css(self):
        css = b"""
        button.fav-btn {
            background: transparent;
            border: none;
            box-shadow: none;
            text-shadow: 0px 0px 5px rgba(0, 0, 0, 1.0);
            padding: 2px;
        }
        button.fav-btn:hover, button.fav-btn:active {
            background: transparent;
            border: none;
            box-shadow: none;
        }
        .loading-overlay {
            background-color: rgba(0, 0, 0, 0.75);
            border-radius: 10px;
        }
        """
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def get_monitors_from_toml(self):
        try:
            with open(TOML_PATH, "r") as f: doc = tomlkit.load(f)
            return [m["name"] for m in doc.get("wallpaper", {}).get("monitors", [])]
        except: return ["DP-3", "HDMI-A-1"]

    def load_settings(self):
        self.default_settings = {
            "cycle_enabled": True, "interval_minutes": 5, "cycle_mode": "shuffle", "mute": True, 
            "shared_monitors": True, "videos_path": str(Path.home() / "wallpapers/videos"), 
            "transition_delay": 2.0, "transition_type": "fade", "is_paused": False, 
            "fit_modes": {}, "fixed_wallpapers": {}, "playback_speed": 1.0, "brightness": 0,
            "force_reload": False, "active_filter": "All Wallpapers",
            "hyde_integration": True, "startup_behavior": "restore", "favorites": [],
            "search_subfolders": False # Nova configuração
        }
        if SETTINGS_PATH.exists():
            try:
                with open(SETTINGS_PATH, "r") as f: return {**self.default_settings, **json.load(f)}
            except: pass
        return dict(self.default_settings)

    def block_scroll(self, widget, event):
        return True

    def create_title(self, text):
        lbl = Gtk.Label(xalign=0)
        lbl.set_margin_top(10)
        lbl.set_markup(f"<b>{text}</b>")
        self.sidebar_box.pack_start(lbl, False, False, 0)

    def create_row(self, label_text, widget, default_val=None):
        widget.connect("scroll-event", self.block_scroll)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        lbl = Gtk.Label(label=label_text, xalign=0)
        box.pack_start(lbl, True, True, 0)
        box.pack_start(widget, False, False, 0)

        if default_val is not None:
            btn_reset = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.MENU)
            btn_reset.set_relief(Gtk.ReliefStyle.NONE)
            btn_reset.set_tooltip_text("Restore default")
            btn_reset.set_no_show_all(True)
            btn_reset.connect("clicked", lambda b: widget.set_active(default_val))
            
            def check_diff(w, param): btn_reset.set_visible(w.get_active() != default_val)
            widget.connect("notify::active", check_diff)
            check_diff(widget, None)
            box.pack_start(btn_reset, False, False, 0)
            
        self.sidebar_box.pack_start(box, False, False, 0)

    def add_sidebar_control(self, label_text, widget, default_val=None, is_combo=False):
        widget.connect("scroll-event", self.block_scroll)
        lbl = Gtk.Label(label=label_text, xalign=0, margin_top=5)
        self.sidebar_box.pack_start(lbl, False, False, 0)
        
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        row.pack_start(widget, True, True, 0)
        
        if default_val is not None:
            btn_reset = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.MENU)
            btn_reset.set_relief(Gtk.ReliefStyle.NONE)
            btn_reset.set_tooltip_text("Restore default")
            btn_reset.set_no_show_all(True)
            
            if is_combo:
                btn_reset.connect("clicked", lambda b: widget.set_active(default_val))
                def check_combo_diff(w): btn_reset.set_visible(w.get_active() != default_val)
                widget.connect("changed", lambda w: check_combo_diff(w))
                check_combo_diff(widget)
            else:
                btn_reset.connect("clicked", lambda b: widget.set_value(default_val))
                def check_scale_diff(w): btn_reset.set_visible(w.get_value() != default_val)
                widget.connect("value-changed", lambda w: check_scale_diff(w))
                check_scale_diff(widget)

            row.pack_start(btn_reset, False, False, 0)
        
        self.sidebar_box.pack_start(row, False, False, 0)

    # ================= SIDEBAR =================
    def create_sidebar(self):
        self.create_title("🖥️ Displays & Layout")
        
        self.sw_shared = Gtk.Switch(active=self.settings["shared_monitors"])
        self.sw_shared.connect("notify::active", self.on_setting_changed_silent)
        self.sw_shared.connect("notify::active", self.update_target_selector)
        self.create_row("Link Displays", self.sw_shared, self.default_settings["shared_monitors"])

        self.combo_fit = Gtk.ComboBoxText()
        for opt in ["fill", "fit", "auto"]: self.combo_fit.append_text(opt)
        self.combo_fit.set_active(["fill", "fit", "auto"].index(self.settings.get("fit_modes", {}).get(self.monitors[0], "fill")))
        self.combo_fit.connect("changed", self.on_fit_change)
        self.add_sidebar_control("Scaling Mode:", self.combo_fit, 0, is_combo=True)

        self.create_title("🎛️ Video Engine (Mpv)")
        
        self.sw_pause = Gtk.Switch(active=self.settings["is_paused"])
        self.sw_pause.connect("notify::active", self.on_setting_changed_silent)
        self.create_row("Pause (Eco RAM)", self.sw_pause, self.default_settings["is_paused"])

        self.sw_mute = Gtk.Switch(active=self.settings["mute"])
        self.sw_mute.connect("notify::active", self.on_setting_changed_silent) 
        self.create_row("Mute Audio", self.sw_mute, self.default_settings["mute"])

        self.scale_speed = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.25, 2.0, 0.25)
        self.scale_speed.set_value(self.settings["playback_speed"])
        self.scale_speed.connect("value-changed", self.on_setting_changed_silent) 
        self.add_sidebar_control("Playback Speed:", self.scale_speed, self.default_settings["playback_speed"])

        self.scale_bright = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -50, 50, 5)
        self.scale_bright.set_value(self.settings["brightness"])
        self.scale_bright.connect("value-changed", self.on_setting_changed_silent) 
        self.add_sidebar_control("Brightness:", self.scale_bright, self.default_settings["brightness"])

        self.create_title("🔄 Cycle & Transition")

        self.sw_cycle = Gtk.Switch(active=self.settings["cycle_enabled"])
        self.sw_cycle.connect("notify::active", self.on_setting_changed_silent)
        self.create_row("Enable Cycle", self.sw_cycle, self.default_settings["cycle_enabled"])

        self.combo_mode = Gtk.ComboBoxText()
        for opt in ["shuffle", "sequential"]: self.combo_mode.append_text(opt)
        self.combo_mode.set_active(["shuffle", "sequential"].index(self.settings["cycle_mode"]))
        self.combo_mode.connect("changed", self.on_setting_changed_silent)
        self.add_sidebar_control("Cycle Mode:", self.combo_mode, 0, is_combo=True)

        self.scale_interval = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 60, 1)
        self.scale_interval.set_value(self.settings["interval_minutes"])
        self.scale_interval.connect("value-changed", self.on_setting_changed_silent)
        self.add_sidebar_control("Interval (Minutes):", self.scale_interval, self.default_settings["interval_minutes"])

        self.combo_trans = Gtk.ComboBoxText()
        current_trans = self.settings.get("transition_type", "fade")
        if current_trans not in TRANSITIONS: current_trans = "fade"
        for opt in TRANSITIONS: self.combo_trans.append_text(opt)
        self.combo_trans.set_active(TRANSITIONS.index(current_trans))
        self.combo_trans.connect("changed", self.on_setting_changed_silent) 
        self.add_sidebar_control("Transition Style:", self.combo_trans, TRANSITIONS.index(self.default_settings["transition_type"]), is_combo=True)

    # ================= MAIN AREA =================
    def create_gallery_view(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        self.target_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.target_buttons = {}
        first_btn = None
        for mon in self.monitors:
            btn = Gtk.RadioButton.new_with_label_from_widget(first_btn, mon)
            if not first_btn: first_btn = btn
            btn.set_mode(False)
            btn.connect("toggled", self.on_target_toggled, mon)
            self.target_box.pack_start(btn, False, False, 0)
            self.target_buttons[mon] = btn

        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        filter_box.pack_start(Gtk.Label(label="Filter:"), False, False, 0)
        self.combo_filter = Gtk.ComboBoxText()
        self.combo_filter.connect("scroll-event", self.block_scroll)
        for opt in FILTERS:
            self.combo_filter.append_text(opt)
        try:
            self.combo_filter.set_active(FILTERS.index(self.current_filter))
        except:
            self.combo_filter.set_active(0)
        self.combo_filter.connect("changed", self.on_filter_changed)
        filter_box.pack_start(self.combo_filter, False, False, 0)

        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        top_bar.set_margin_top(10)
        top_bar.set_margin_bottom(10)
        top_bar.set_margin_start(10)
        top_bar.set_margin_end(10)
        
        top_bar.pack_start(self.target_box, False, False, 0)
        top_bar.pack_start(Gtk.Label(), True, True, 0) 
        top_bar.pack_start(filter_box, False, False, 0)

        vbox.pack_start(top_bar, False, False, 0)

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

        # Loading Overlay (Tela escura de carregamento)
        self.loading_overlay_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.loading_overlay_box.set_halign(Gtk.Align.FILL)
        self.loading_overlay_box.set_valign(Gtk.Align.FILL)
        self.loading_overlay_box.get_style_context().add_class("loading-overlay")
        
        center_loading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        center_loading.set_halign(Gtk.Align.CENTER)
        center_loading.set_valign(Gtk.Align.CENTER)
        
        self.loading_spinner = Gtk.Spinner()
        self.loading_spinner.set_size_request(60, 60)
        center_loading.pack_start(self.loading_spinner, False, False, 0)
        
        self.loading_label = Gtk.Label(label="Scanning files...")
        self.loading_label.set_markup("<span size='large' weight='bold' color='white'>Scanning files...</span>")
        center_loading.pack_start(self.loading_label, False, False, 0)
        
        self.loading_overlay_box.pack_start(center_loading, True, True, 0)

        self.gallery_overlay = Gtk.Overlay()
        self.gallery_overlay.add(vbox)
        self.gallery_overlay.add_overlay(self.loading_overlay_box)

        self.stack.add_named(self.gallery_overlay, "gallery")
        self.update_target_selector()

    def create_config_view(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=30)
        vbox.set_margin_top(40)
        vbox.set_margin_start(40)

        lbl = Gtk.Label(xalign=0)
        lbl.set_markup("<span size='x-large' weight='bold'>System Configuration</span>")
        vbox.pack_start(lbl, False, False, 0)

        box_hyde = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        lbl_hyde = Gtk.Label(xalign=0)
        lbl_hyde.set_markup("<b>✨ HyDE Project Integration</b>")
        box_hyde.pack_start(lbl_hyde, False, False, 0)
        
        row_hyde = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.sw_hyde = Gtk.Switch(active=self.settings.get("hyde_integration", True))
        self.sw_hyde.connect("notify::active", self.on_setting_changed_silent)
        row_hyde.pack_start(Gtk.Label(label="Enable 'hydectl' Sync (Generates Wallbash colors)", xalign=0), True, True, 0)
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

        def make_section(title, path_txt, btn_text, callback):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            lbl_title = Gtk.Label(xalign=0)
            lbl_title.set_markup(f"<b>{title}</b>")
            box.pack_start(lbl_title, False, False, 0)
            box.pack_start(Gtk.Label(label=path_txt, xalign=0), False, False, 0)
            btn = Gtk.Button(label=btn_text)
            btn.set_halign(Gtk.Align.START)
            btn.connect("clicked", callback)
            box.pack_start(btn, False, False, 0)
            vbox.pack_start(box, False, False, 0)

        self.lbl_folder = Gtk.Label(label=str(self.videos_dir), xalign=0)
        box1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        lbl_f = Gtk.Label(xalign=0)
        lbl_f.set_markup("<b>📁 Wallpapers Folder</b>")
        box1.pack_start(lbl_f, False, False, 0)
        
        row_folder = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row_folder.pack_start(self.lbl_folder, False, False, 0)
        
        self.sw_subfolders = Gtk.Switch(active=self.settings.get("search_subfolders", False))
        self.sw_subfolders.connect("notify::active", self.on_subfolder_changed)
        lbl_sub = Gtk.Label(label="Search in subfolders")
        lbl_sub.set_margin_start(20)
        row_folder.pack_start(lbl_sub, False, False, 0)
        row_folder.pack_start(self.sw_subfolders, False, False, 0)
        
        box1.pack_start(row_folder, False, False, 0)
        
        btn_f = Gtk.Button(label="Change Main Folder")
        btn_f.set_halign(Gtk.Align.START)
        btn_f.connect("clicked", self.change_folder)
        box1.pack_start(btn_f, False, False, 0)
        vbox.pack_start(box1, False, False, 0)

        make_section("🗄️ Cache & Thumbnails", str(CACHE_DIR), "Clear Cache & Reload", self.clear_cache)
        
        box_git = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        lbl_g = Gtk.Label(xalign=0)
        lbl_g.set_markup("<b>🌟 Support the Project</b>")
        box_git.pack_start(lbl_g, False, False, 0)
        btn_git = Gtk.LinkButton(uri="https://github.com/GustavoBorges13/wayle-video-engine", label="⭐ Star Wayle on GitHub")
        btn_git.set_halign(Gtk.Align.START)
        box_git.pack_start(btn_git, False, False, 0)
        vbox.pack_start(box_git, False, False, 0)

        box_reset = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        lbl_r = Gtk.Label(xalign=0)
        lbl_r.set_markup("<b>⚠️ Danger Zone</b>")
        box_reset.pack_start(lbl_r, False, False, 0)
        btn_reset_all = Gtk.Button(label="Reset All Settings to Default")
        btn_reset_all.set_halign(Gtk.Align.START)
        btn_reset_all.connect("clicked", self.reset_all_settings)
        box_reset.pack_start(btn_reset_all, False, False, 0)
        vbox.pack_start(box_reset, False, False, 0)

        self.stack.add_named(vbox, "config")

    # ================= LOGIC & EVENTS =================
    def toggle_view(self, btn):
        if self.stack.get_visible_child_name() == "gallery":
            self.stack.set_visible_child_name("config")
            self.btn_config.set_label("◀ Back")
            self.sidebar_scrolled.hide()
        else:
            self.stack.set_visible_child_name("gallery")
            self.btn_config.set_label("⚙️ Settings")
            self.sidebar_scrolled.show()

    def on_subfolder_changed(self, switch, gparam):
        if self.is_loading_ui: return
        self.trigger_save(needs_reload=True)
        self.refresh_gallery()

    def reset_all_settings(self, btn):
        dialog = Gtk.MessageDialog(
            transient_for=self, flags=0, message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL, text="Reset All Settings?"
        )
        dialog.format_secondary_text("This will restore all configurations to their default values. Are you sure?")
        response = dialog.run()
        dialog.destroy()
        
        if response == Gtk.ResponseType.OK:
            self.settings = dict(self.default_settings)
            self.videos_dir = Path(self.settings["videos_path"])
            self.lbl_folder.set_label(str(self.videos_dir))
            
            self.is_loading_ui = True
            self.sw_shared.set_active(self.default_settings["shared_monitors"])
            self.combo_fit.set_active(0)
            self.sw_pause.set_active(self.default_settings["is_paused"])
            self.sw_mute.set_active(self.default_settings["mute"])
            self.scale_speed.set_value(self.default_settings["playback_speed"])
            self.scale_bright.set_value(self.default_settings["brightness"])
            self.sw_cycle.set_active(self.default_settings["cycle_enabled"])
            self.combo_mode.set_active(0)
            self.scale_interval.set_value(self.default_settings["interval_minutes"])
            self.combo_trans.set_active(TRANSITIONS.index(self.default_settings["transition_type"]))
            self.sw_hyde.set_active(self.default_settings["hyde_integration"])
            self.combo_startup.set_active(0)
            self.sw_subfolders.set_active(self.default_settings["search_subfolders"])
            self.is_loading_ui = False
            
            self.trigger_save(needs_reload=True)
            self.update_target_selector()
            self.toggle_view(None) 
            self.refresh_gallery()

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

    def on_filter_changed(self, combo):
        if self.is_loading_ui: return
        self.current_filter = combo.get_active_text()
        self.trigger_save(needs_reload=False)
        self.refresh_gallery()

    def trigger_save(self, needs_reload=False):
        if needs_reload: self.pending_reload = True
        if self.save_timer: GLib.source_remove(self.save_timer)
        self.save_timer = GLib.timeout_add(500, self.do_save_and_apply)

    def do_save_and_apply(self):
        self.save_timer = None
        try:
            with open(SETTINGS_PATH, "r") as f: disk_settings = json.load(f)
        except:
            disk_settings = {}
            
        if getattr(self, 'wallpapers_dirty', False):
            final_wallpapers = self.settings.get("fixed_wallpapers", {})
            self.wallpapers_dirty = False
        else:
            final_wallpapers = disk_settings.get("fixed_wallpapers", self.settings.get("fixed_wallpapers", {}))
            self.settings["fixed_wallpapers"] = final_wallpapers

        new_settings = {
            "cycle_enabled": self.sw_cycle.get_active(),
            "interval_minutes": int(self.scale_interval.get_value()),
            "cycle_mode": self.combo_mode.get_active_text(),
            "mute": self.sw_mute.get_active(),
            "shared_monitors": self.sw_shared.get_active(),
            "videos_path": str(self.videos_dir),
            "transition_delay": 2.0, 
            "transition_type": self.combo_trans.get_active_text(),
            "is_paused": self.sw_pause.get_active(),
            "fit_modes": self.settings.get("fit_modes", {}),
            "fixed_wallpapers": final_wallpapers, 
            "playback_speed": float(self.scale_speed.get_value()),
            "brightness": int(self.scale_bright.get_value()),
            "force_reload": getattr(self, 'pending_reload', False),
            "active_filter": self.current_filter,
            "hyde_integration": self.sw_hyde.get_active(),
            "startup_behavior": "clear" if self.combo_startup.get_active() == 1 else "restore",
            "favorites": self.settings.get("favorites", []),
            "search_subfolders": self.sw_subfolders.get_active()
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

    def update_loading_label(self, text):
        self.loading_label.set_markup(f"<span size='large' weight='bold' color='white'>{text}</span>")
        return False

    def refresh_gallery(self):
        self.current_load_id += 1  # Invalida threads anteriores
        load_id = self.current_load_id
        
        self.combo_filter.set_sensitive(False)
        self.target_box.set_sensitive(False)
        
        for child in self.flowbox.get_children(): 
            self.flowbox.remove(child)
            
        self.loading_overlay_box.show_all()
        self.loading_spinner.start()
        self.update_loading_label("Scanning directory...")
        
        threading.Thread(target=self.async_load_thumbs, args=(load_id,), daemon=True).start()

    def async_load_thumbs(self, load_id):
        # 1. Search Logic (Recursiva ou Normal)
        use_rglob = self.settings.get("search_subfolders", False)
        
        if use_rglob:
            all_files = [f for f in self.videos_dir.rglob("*.*") if f.suffix.lower() in SUPPORTED]
        else:
            all_files = [f for f in self.videos_dir.glob("*.*") if f.suffix.lower() in SUPPORTED]
            
        if load_id != self.current_load_id: return
        
        # 2. Filtro
        files = []
        if "Favorites" in self.current_filter:
            favs = self.settings.get("favorites", [])
            files = [f for f in all_files if f.name in favs]
        elif "Videos" in self.current_filter:
            files = [f for f in all_files if f.suffix.lower() in VIDEO_EXTS]
        elif "Images" in self.current_filter:
            files = [f for f in all_files if f.suffix.lower() in IMAGE_EXTS]
        elif "GIFs" in self.current_filter:
            files = [f for f in all_files if f.suffix.lower() in GIF_EXTS]
        else:
            files = all_files

        if not files:
            GLib.idle_add(self.finish_loading, f"No files found for '{self.current_filter}'.", load_id)
            return

        # 3. Geração de Thumbnails (com ffmpeg)
        missing = [f for f in files if not (THUMBS_DIR / f"{f.stem}.png").exists()]
        if missing:
            GLib.idle_add(self.update_loading_label, f"Generating {len(missing)} High-Quality thumbnails...")
            for f in missing:
                if load_id != self.current_load_id: return
                t = THUMBS_DIR / f"{f.stem}.png"
                cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(f), "-ss", "00:00:00.000", "-vframes", "1", "-q:v", "2", str(t)]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # 4. Carregamento Progressivo Assíncrono da UI
        # O resize da imagem (GdkPixbuf) é o que travava a interface. 
        # Agora ele roda na thread de background.
        GLib.idle_add(self.update_loading_label, "Building gallery...")
        
        favorites = self.settings.get("favorites", [])
        
        for original_file in files:
            if load_id != self.current_load_id: return
            
            t = THUMBS_DIR / f"{original_file.stem}.png"
            if not t.exists(): continue
            
            try:
                # TRABALHO PESADO: Redimensiona na RAM sem travar a interface
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(t), 180, 101, False)
                is_fav = original_file.name in favorites
                
                # Envia apenas a montagem rápida para a Thread Principal
                GLib.idle_add(self.add_single_thumbnail, original_file, pixbuf, is_fav, load_id)
            except:
                continue 
                
        GLib.idle_add(self.finish_loading, "", load_id)

    def add_single_thumbnail(self, original_file, pixbuf, is_fav, load_id):
        if load_id != self.current_load_id: return False
        
        ext = original_file.suffix.lower()
        if ext in VIDEO_EXTS: badge = "🎬"
        elif ext in GIF_EXTS: badge = "🎞️"
        else: badge = "🖼️"

        img = Gtk.Image.new_from_pixbuf(pixbuf)
        
        overlay = Gtk.Overlay()
        overlay.set_halign(Gtk.Align.CENTER) 
        overlay.set_valign(Gtk.Align.CENTER)
        overlay.add(img)
        
        btn_fav = Gtk.Button()
        btn_fav.get_style_context().add_class("fav-btn")
        
        lbl_fav = Gtk.Label()
        lbl_fav.set_markup(f"<span size='large'>{'❤️' if is_fav else '🤍'}</span>")
        btn_fav.add(lbl_fav)
        
        btn_fav.set_halign(Gtk.Align.END)
        btn_fav.set_valign(Gtk.Align.START)
        btn_fav.set_margin_top(4) 
        btn_fav.set_margin_end(4) 
        btn_fav.set_opacity(0.85)
        
        btn_fav.connect("clicked", self.toggle_favorite, original_file.name, lbl_fav)
        
        overlay.add_overlay(btn_fav)
        overlay.show_all()
        
        lbl = Gtk.Label(label=f"{badge} {original_file.stem[:15]}...", margin_top=5)
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_halign(Gtk.Align.CENTER)
        box.pack_start(overlay, False, False, 0)
        box.pack_start(lbl, False, False, 0)
        
        btn = Gtk.Button()
        btn.add(box)
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.connect("clicked", self.on_image_click, str(original_file))
        
        self.flowbox.add(btn)
        self.flowbox.show_all()
        return False # Remove da fila do idle_add

    def toggle_favorite(self, btn, file_name, lbl_fav):
        favorites = self.settings.get("favorites", [])
        if file_name in favorites:
            favorites.remove(file_name)
            lbl_fav.set_markup("<span size='large'>🤍</span>")
        else:
            favorites.append(file_name)
            lbl_fav.set_markup("<span size='large'>❤️</span>")
        
        self.settings["favorites"] = favorites
        self.trigger_save(needs_reload=False)
        
        if "Favorites" in self.current_filter:
            self.refresh_gallery()

    def finish_loading(self, text, load_id):
        if load_id != self.current_load_id: return False
        
        self.combo_filter.set_sensitive(True)
        self.target_box.set_sensitive(True)
        
        self.loading_spinner.stop()
        self.loading_overlay_box.hide()
        
        if text:
            lbl = Gtk.Label(label=text)
            lbl.show()
            self.flowbox.add(lbl)
        return False

    def on_image_click(self, btn, file_path):
        active_target = self.get_active_target()
        try:
            with open(SETTINGS_PATH, "r") as f: disk_settings = json.load(f)
            fixed = disk_settings.get("fixed_wallpapers", {})
        except:
            fixed = self.settings.get("fixed_wallpapers", {})
            
        if self.sw_shared.get_active(): fixed["all"] = file_path
        else: fixed[active_target] = file_path

        self.settings["fixed_wallpapers"] = fixed
        self.wallpapers_dirty = True
        self.trigger_save(needs_reload=True) 

if __name__ == "__main__":
    acquire_single_instance_lock()
    app = WayleEngineApp()
    app.connect("destroy", Gtk.main_quit)
    app.show_all()
    Gtk.main()