"""Settings dialog for configuration."""

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from config.settings_manager import SettingsManager
from hue_sync.bridge import HueBridge


class SettingsDialog(Gtk.Dialog):
    def __init__(self, parent, bridge: HueBridge):
        super().__init__(
            title="Settings",
            transient_for=parent,
            modal=True,
            default_width=500,
            default_height=400
        )
        self.settings = SettingsManager.get_instance()
        self.bridge = bridge
        self.discovered_bridges = []

        self._build_ui()

    def _build_ui(self):
        notebook = Gtk.Notebook()
        content_area = self.get_content_area()
        content_area.set_margin_top(10)
        content_area.set_margin_bottom(10)
        content_area.set_margin_start(10)
        content_area.set_margin_end(10)
        content_area.append(notebook)

        bridge_page = self._build_bridge_tab()
        notebook.append_page(bridge_page, Gtk.Label(label="Bridge"))

        capture_page = self._build_capture_tab()
        notebook.append_page(capture_page, Gtk.Label(label="Capture"))

        zone_page = self._build_zone_tab()
        notebook.append_page(zone_page, Gtk.Label(label="Zones"))

        sync_page = self._build_sync_tab()
        notebook.append_page(sync_page, Gtk.Label(label="Sync"))

        add_button = self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        save_button = self.add_button("Save", Gtk.ResponseType.OK)

        self.connect("response", self._on_response)

    def _build_bridge_tab(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        box.set_margin_top(15)
        box.set_margin_bottom(15)
        box.set_margin_start(15)
        box.set_margin_end(15)

        frame = Gtk.Frame(label="Bridge Connection")
        frame_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        frame_box.set_margin_top(10)
        frame_box.set_margin_bottom(10)
        frame_box.set_margin_start(10)
        frame_box.set_margin_end(10)
        frame.set_child(frame_box)

        ip_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        ip_label = Gtk.Label(label="Bridge IP:")
        ip_label.set_size_request(100, -1)
        ip_label.set_xalign(0)
        self.ip_entry = Gtk.Entry(text=self.settings.hue.bridge_ip)
        ip_box.append(ip_label)
        ip_box.append(self.ip_entry)
        frame_box.append(ip_box)

        key_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        key_label = Gtk.Label(label="App Key:")
        key_label.set_size_request(100, -1)
        key_label.set_xalign(0)
        self.key_entry = Gtk.Entry(text=self.settings.hue.app_key)
        key_box.append(key_label)
        key_box.append(self.key_entry)
        frame_box.append(key_box)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        discover_btn = Gtk.Button(label="Discover Bridges")
        discover_btn.connect("clicked", self._on_discover)
        auth_btn = Gtk.Button(label="Authenticate")
        auth_btn.connect("clicked", self._on_authenticate)
        button_box.append(discover_btn)
        button_box.append(auth_btn)
        frame_box.append(button_box)

        box.append(frame)

        status_frame = Gtk.Frame(label="Connection Status")
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        status_box.set_margin_top(10)
        status_box.set_margin_bottom(10)
        status_box.set_margin_start(10)
        status_box.set_margin_end(10)
        status_frame.set_child(status_box)

        self.bridge_status_label = Gtk.Label(label="Not connected")
        self.bridge_status_label.set_xalign(0)
        status_box.append(self.bridge_status_label)

        self.lights_label = Gtk.Label(label="Lights: 0")
        self.lights_label.set_xalign(0)
        status_box.append(self.lights_label)

        self.zones_label = Gtk.Label(label="Zones: 0")
        self.zones_label.set_xalign(0)
        status_box.append(self.zones_label)

        box.append(status_frame)

        self._update_bridge_status()

        return box

    def _build_capture_tab(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        box.set_margin_top(15)
        box.set_margin_bottom(15)
        box.set_margin_start(15)
        box.set_margin_end(15)

        frame = Gtk.Frame(label="Screen Capture")
        frame_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        frame_box.set_margin_top(10)
        frame_box.set_margin_bottom(10)
        frame_box.set_margin_start(10)
        frame_box.set_margin_end(10)
        frame.set_child(frame_box)

        scale_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        scale_label = Gtk.Label(label="Resolution Scale:")
        scale_label.set_size_request(150, -1)
        scale_label.set_xalign(0)
        self.scale_adj = Gtk.Adjustment(
            value=self.settings.capture.scale_factor,
            lower=0.01, upper=1.0, step_increment=0.01, page_increment=0.1
        )
        self.scale_spin = Gtk.SpinButton(adjustment=self.scale_adj)
        self.scale_spin.set_digits(2)
        scale_box.append(scale_label)
        scale_box.append(self.scale_spin)
        frame_box.append(scale_box)

        display_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        display_label = Gtk.Label(label="Display Index:")
        display_label.set_size_request(150, -1)
        display_label.set_xalign(0)
        self.display_adj = Gtk.Adjustment(
            value=self.settings.capture.display_index,
            lower=0, upper=10, step_increment=1
        )
        self.display_spin = Gtk.SpinButton(adjustment=self.display_adj)
        display_box.append(display_label)
        display_box.append(self.display_spin)
        frame_box.append(display_box)

        rotate_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        rotate_label = Gtk.Label(label="Screen Rotation:")
        rotate_label.set_size_request(150, -1)
        rotate_label.set_xalign(0)
        self.rotate_combo = Gtk.ComboBoxText()
        self.rotate_combo.append("0", "0°")
        self.rotate_combo.append("90", "90° CCW")
        self.rotate_combo.append("180", "180°")
        self.rotate_combo.append("270", "270° CCW")
        self.rotate_combo.set_active_id(str(self.settings.capture.rotation))
        rotate_box.append(rotate_label)
        rotate_box.append(self.rotate_combo)
        frame_box.append(rotate_box)

        box.append(frame)

        return box

    def _build_zone_tab(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        box.set_margin_top(15)
        box.set_margin_bottom(15)
        box.set_margin_start(15)
        box.set_margin_end(15)

        frame = Gtk.Frame(label="Zone Configuration")
        frame_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        frame_box.set_margin_top(10)
        frame_box.set_margin_bottom(10)
        frame_box.set_margin_start(10)
        frame_box.set_margin_end(10)
        frame.set_child(frame_box)

        layout_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        layout_label = Gtk.Label(label="Zone Layout:")
        layout_label.set_size_request(150, -1)
        layout_label.set_xalign(0)
        self.layout_combo = Gtk.ComboBoxText()
        self.layout_combo.append("ambilight", "Ambilight")
        self.layout_combo.append("grid", "Grid")
        self.layout_combo.append("custom", "Custom")
        self.layout_combo.set_active_id(self.settings.zones.layout)
        layout_box.append(layout_label)
        layout_box.append(self.layout_combo)
        frame_box.append(layout_box)

        rows_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        rows_label = Gtk.Label(label="Grid Rows:")
        rows_label.set_size_request(150, -1)
        rows_label.set_xalign(0)
        self.rows_adj = Gtk.Adjustment(
            value=self.settings.zones.grid_rows,
            lower=1, upper=64, step_increment=1
        )
        self.rows_spin = Gtk.SpinButton(adjustment=self.rows_adj)
        rows_box.append(rows_label)
        rows_box.append(self.rows_spin)
        frame_box.append(rows_box)

        cols_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        cols_label = Gtk.Label(label="Grid Columns:")
        cols_label.set_size_request(150, -1)
        cols_label.set_xalign(0)
        self.cols_adj = Gtk.Adjustment(
            value=self.settings.zones.grid_cols,
            lower=1, upper=64, step_increment=1
        )
        self.cols_spin = Gtk.SpinButton(adjustment=self.cols_adj)
        cols_box.append(cols_label)
        cols_box.append(self.cols_spin)
        frame_box.append(cols_box)

        box.append(frame)

        return box

    def _build_sync_tab(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        box.set_margin_top(15)
        box.set_margin_bottom(15)
        box.set_margin_start(15)
        box.set_margin_end(15)

        frame = Gtk.Frame(label="Sync Settings")
        frame_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        frame_box.set_margin_top(10)
        frame_box.set_margin_bottom(10)
        frame_box.set_margin_start(10)
        frame_box.set_margin_end(10)
        frame.set_child(frame_box)

        fps_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        fps_label = Gtk.Label(label="Target FPS:")
        fps_label.set_size_request(150, -1)
        fps_label.set_xalign(0)
        self.sync_fps_adj = Gtk.Adjustment(
            value=self.settings.sync.fps,
            lower=1, upper=60, step_increment=1, page_increment=5
        )
        self.sync_fps_spin = Gtk.SpinButton(adjustment=self.sync_fps_adj)
        fps_box.append(fps_label)
        fps_box.append(self.sync_fps_spin)
        frame_box.append(fps_box)

        transition_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        transition_label = Gtk.Label(label="Transition Time (ms):")
        transition_label.set_size_request(150, -1)
        transition_label.set_xalign(0)
        self.transition_adj = Gtk.Adjustment(
            value=self.settings.sync.transition_time_ms,
            lower=0, upper=10000, step_increment=50, page_increment=100
        )
        self.transition_spin = Gtk.SpinButton(adjustment=self.transition_adj)
        transition_box.append(transition_label)
        transition_box.append(self.transition_spin)
        frame_box.append(transition_box)

        brightness_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        brightness_label = Gtk.Label(label="Brightness Scale:")
        brightness_label.set_size_request(150, -1)
        brightness_label.set_xalign(0)
        self.brightness_adj = Gtk.Adjustment(
            value=self.settings.sync.brightness_scale,
            lower=0.0, upper=2.0, step_increment=0.1, page_increment=0.5
        )
        self.brightness_spin = Gtk.SpinButton(adjustment=self.brightness_adj)
        self.brightness_spin.set_digits(1)
        brightness_box.append(brightness_label)
        brightness_box.append(self.brightness_spin)
        frame_box.append(brightness_box)

        smoothing_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        smoothing_label = Gtk.Label(label="Smoothing Factor:")
        smoothing_label.set_size_request(150, -1)
        smoothing_label.set_xalign(0)
        self.smoothing_adj = Gtk.Adjustment(
            value=self.settings.sync.smoothing_factor,
            lower=0.0, upper=1.0, step_increment=0.1, page_increment=0.2
        )
        self.smoothing_spin = Gtk.SpinButton(adjustment=self.smoothing_adj)
        self.smoothing_spin.set_digits(1)
        smoothing_box.append(smoothing_label)
        smoothing_box.append(self.smoothing_spin)
        frame_box.append(smoothing_box)

        box.append(frame)

        return box

    def _on_discover(self, button):
        """Discover Hue bridges on network."""
        self.discovered_bridges = HueBridge.discover_bridges()
        
        if self.discovered_bridges:
            self.ip_entry.set_text(self.discovered_bridges[0])
            self.bridge_status_label.set_text(f"Found {len(self.discovered_bridges)} bridge(s)")
        else:
            self.bridge_status_label.set_text("No bridges found")

    def _on_authenticate(self, button):
        """Authenticate with Hue bridge."""
        ip = self.ip_entry.get_text()
        
        if not ip:
            self.bridge_status_label.set_text("Please enter bridge IP")
            return

        self.bridge_status_label.set_text("Press link button on bridge...")

        app_key = self.bridge.create_user(ip)
        
        if app_key:
            self.key_entry.set_text(app_key)
            # Connect to bridge with new credentials
            if self.bridge.connect():
                self.bridge_status_label.set_text("Authenticated and connected!")
                self._update_bridge_status()
            else:
                self.bridge_status_label.set_text("Authenticated but connection failed")
        else:
            self.bridge_status_label.set_text("Press the bridge button first, then try again")

    def _update_bridge_status(self):
        """Update bridge connection status display."""
        if self.bridge.test_connection():
            self.bridge_status_label.set_text("Connected")
            self.lights_label.set_text(f"Lights: {len(self.bridge.get_light_ids())}")
            self.zones_label.set_text(f"Zones: {len(self.bridge.get_zone_ids())}")
        else:
            self.bridge_status_label.set_text("Not connected")
            self.lights_label.set_text("Lights: 0")
            self.zones_label.set_text("Zones: 0")

    def _on_response(self, dialog, response):
        """Handle dialog response."""
        if response == Gtk.ResponseType.OK:
            self.settings.hue.bridge_ip = self.ip_entry.get_text()
            self.settings.hue.app_key = self.key_entry.get_text()
            self.settings.capture.scale_factor = self.scale_adj.get_value()
            self.settings.capture.display_index = int(self.display_adj.get_value())
            self.settings.capture.rotation = int(self.rotate_combo.get_active_id() or 0)
            self.settings.zones.layout = self.layout_combo.get_active_id()
            self.settings.zones.grid_rows = int(self.rows_adj.get_value())
            self.settings.zones.grid_cols = int(self.cols_adj.get_value())
            self.settings.sync.fps = int(self.sync_fps_adj.get_value())
            self.settings.sync.transition_time_ms = int(self.transition_adj.get_value())
            self.settings.sync.brightness_scale = self.brightness_adj.get_value()
            self.settings.sync.smoothing_factor = self.smoothing_adj.get_value()
            self.settings.save()

        self.destroy()
