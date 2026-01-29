"""Settings dialog with modern Adwaita preferences styling."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw
from lumux.bridge import HueBridge
from lumux.app_context import AppContext


class SettingsDialog(Adw.PreferencesDialog):
    def __init__(self, parent, app_context: AppContext):
        super().__init__()
        self.app_context = app_context
        self.settings = app_context.settings
        self.bridge = app_context.bridge
        self.discovered_bridges = []
        self._parent = parent

        self.set_title("Settings")
        self.set_search_enabled(True)
        
        self._build_ui()

    def _build_ui(self):
        # Bridge page
        bridge_page = Adw.PreferencesPage()
        bridge_page.set_title("Bridge")
        bridge_page.set_icon_name("network-server-symbolic")
        self.add(bridge_page)

        # Status group (moved to top)
        status_group = Adw.PreferencesGroup()
        status_group.set_title("Connection Status")
        bridge_page.add(status_group)

        self.status_row = Adw.ActionRow()
        self.status_row.set_title("Status")
        self.status_row.set_subtitle("Not connected")
        self.status_icon = Gtk.Image.new_from_icon_name("network-offline-symbolic")
        self.status_row.add_prefix(self.status_icon)
        status_group.add(self.status_row)

        self._update_bridge_status()

        # Connection group
        connection_group = Adw.PreferencesGroup()
        connection_group.set_title("Connection")
        connection_group.set_description("Configure your Philips Hue bridge connection")
        bridge_page.add(connection_group)

        # Bridge IP row
        self.ip_row = Adw.EntryRow()
        self.ip_row.set_title("Bridge IP Address")
        self.ip_row.set_text(self.settings.hue.bridge_ip)
        self.ip_row.set_show_apply_button(False)
        connection_group.add(self.ip_row)

        # App Key row (password)
        self.key_row = Adw.PasswordEntryRow()
        self.key_row.set_title("App Key")
        self.key_row.set_text(self.settings.hue.app_key)
        connection_group.add(self.key_row)

        # Client Key row (password)
        self.client_key_row = Adw.PasswordEntryRow()
        self.client_key_row.set_title("Client Key")
        self.client_key_row.set_text(self.settings.hue.client_key)
        connection_group.add(self.client_key_row)

        # Action buttons row
        actions_row = Adw.ActionRow()
        actions_row.set_title("Bridge Actions")
        actions_row.set_subtitle("Discover bridges on network or authenticate")
        
        discover_btn = Gtk.Button(label="Discover")
        discover_btn.add_css_class("flat")
        discover_btn.set_valign(Gtk.Align.CENTER)
        discover_btn.connect("clicked", self._on_discover)
        actions_row.add_suffix(discover_btn)
        
        auth_btn = Gtk.Button(label="Authenticate")
        auth_btn.add_css_class("suggested-action")
        auth_btn.set_valign(Gtk.Align.CENTER)
        auth_btn.connect("clicked", self._on_authenticate)
        actions_row.add_suffix(auth_btn)
        connection_group.add(actions_row)

        # Entertainment group
        ent_group = Adw.PreferencesGroup()
        ent_group.set_title("Entertainment Zone")
        ent_group.set_description("Select an entertainment zone for streaming")
        bridge_page.add(ent_group)

        # Entertainment zone combo
        self.ent_row = Adw.ComboRow()
        self.ent_row.set_title("Entertainment Zone")
        self.ent_row.set_subtitle("Zone used for light control")
        self._entertainment_configs = []
        self._load_entertainment_configs()
        ent_group.add(self.ent_row)

        # Refresh button
        refresh_row = Adw.ActionRow()
        refresh_row.set_title("Refresh Zones")
        refresh_row.set_subtitle("Reload entertainment zones from bridge")
        refresh_btn = Gtk.Button()
        refresh_btn.set_icon_name("view-refresh-symbolic")
        refresh_btn.add_css_class("flat")
        refresh_btn.set_valign(Gtk.Align.CENTER)
        refresh_btn.connect("clicked", self._on_refresh_entertainment_configs)
        refresh_row.add_suffix(refresh_btn)
        refresh_row.set_activatable_widget(refresh_btn)
        ent_group.add(refresh_row)

        # Capture page
        capture_page = Adw.PreferencesPage()
        capture_page.set_title("Capture")
        capture_page.set_icon_name("video-display-symbolic")
        self.add(capture_page)

        capture_group = Adw.PreferencesGroup()
        capture_group.set_title("Screen Capture")
        capture_group.set_description("Configure how the screen is captured")
        capture_page.add(capture_group)

        # Resolution scale
        self.scale_row = Adw.SpinRow.new_with_range(0.01, 1.0, 0.01)
        self.scale_row.set_title("Resolution Scale")
        self.scale_row.set_subtitle("Lower values improve performance")
        self.scale_row.set_digits(2)
        self.scale_row.set_value(self.settings.capture.scale_factor)
        capture_group.add(self.scale_row)

        # Zones page
        zones_page = Adw.PreferencesPage()
        zones_page.set_title("Zones")
        zones_page.set_icon_name("view-grid-symbolic")
        self.add(zones_page)

        zones_group = Adw.PreferencesGroup()
        zones_group.set_title("Zone Configuration")
        zones_group.set_description("Ambilight captures colors from screen edges")
        zones_page.add(zones_group)

        # Preview toggle
        self.preview_row = Adw.SwitchRow()
        self.preview_row.set_title("Show Zone Preview")
        self.preview_row.set_subtitle("Display real-time zone visualization")
        self.preview_row.set_active(self.settings.zones.show_preview)
        zones_group.add(self.preview_row)

        # Zone grid size (rows / columns)
        self.rows_row = Adw.SpinRow.new_with_range(1, 64, 1)
        self.rows_row.set_title("Edge Rows")
        self.rows_row.set_subtitle("Number of zones along left/right edges")
        self.rows_row.set_digits(0)
        self.rows_row.set_value(self.settings.zones.rows)
        zones_group.add(self.rows_row)

        self.cols_row = Adw.SpinRow.new_with_range(1, 64, 1)
        self.cols_row.set_title("Edge Columns")
        self.cols_row.set_subtitle("Number of zones along top/bottom edges")
        self.cols_row.set_digits(0)
        self.cols_row.set_value(self.settings.zones.cols)
        zones_group.add(self.cols_row)

        # Sync page
        sync_page = Adw.PreferencesPage()
        sync_page.set_title("Sync")
        sync_page.set_icon_name("emblem-synchronizing-symbolic")
        self.add(sync_page)

        sync_group = Adw.PreferencesGroup()
        sync_group.set_title("Sync Settings")
        sync_group.set_description("Fine-tune synchronization behavior")
        sync_page.add(sync_group)

        # Target FPS
        self.fps_row = Adw.SpinRow.new_with_range(1, 60, 1)
        self.fps_row.set_title("Target FPS")
        self.fps_row.set_subtitle("Frames per second for sync updates")
        self.fps_row.set_value(self.settings.sync.fps)
        sync_group.add(self.fps_row)

        # Transition time (max 1000 ms)
        self.transition_row = Adw.SpinRow.new_with_range(0, 1000, 50)
        self.transition_row.set_title("Transition Time")
        self.transition_row.set_subtitle("Milliseconds for color transitions")
        self.transition_row.set_value(self.settings.sync.transition_time_ms)
        sync_group.add(self.transition_row)

        # Color group
        color_group = Adw.PreferencesGroup()
        color_group.set_title("Color Adjustments")
        color_group.set_description("Adjust brightness and color processing")
        sync_page.add(color_group)

        # Brightness scale
        self.brightness_row = Adw.SpinRow.new_with_range(0.0, 2.0, 0.1)
        self.brightness_row.set_title("Brightness Scale")
        self.brightness_row.set_subtitle("Multiply light brightness")
        self.brightness_row.set_digits(1)
        self.brightness_row.set_value(self.settings.sync.brightness_scale)
        color_group.add(self.brightness_row)

        # Gamma
        self.gamma_row = Adw.SpinRow.new_with_range(0.1, 3.0, 0.1)
        self.gamma_row.set_title("Gamma")
        self.gamma_row.set_subtitle("Gamma correction for colors")
        self.gamma_row.set_digits(2)
        self.gamma_row.set_value(self.settings.sync.gamma)
        color_group.add(self.gamma_row)

        # Smoothing factor (minimum 0.1)
        self.smoothing_row = Adw.SpinRow.new_with_range(0.1, 1.0, 0.1)
        self.smoothing_row.set_title("Smoothing Factor")
        self.smoothing_row.set_subtitle("Smooth color transitions")
        self.smoothing_row.set_digits(1)
        self.smoothing_row.set_value(self.settings.sync.smoothing_factor)
        color_group.add(self.smoothing_row)

        # Connect close signal to save settings
        self.connect("closed", self._on_closed)

    def _on_discover(self, button):
        """Discover Hue bridges on network."""
        self.discovered_bridges = HueBridge.discover_bridges()
        
        if self.discovered_bridges:
            self.ip_row.set_text(self.discovered_bridges[0])
            self.status_row.set_subtitle(f"Found {len(self.discovered_bridges)} bridge(s)")
        else:
            self.status_row.set_subtitle("No bridges found")

    def _on_authenticate(self, button):
        """Authenticate with Hue bridge."""
        ip = self.ip_row.get_text()
        
        if not ip:
            self.status_row.set_subtitle("Please enter bridge IP")
            return

        self.status_row.set_subtitle("Press link button on bridge...")

        result = self.bridge.create_user(ip)
        
        if result:
            app_key = result.get('app_key', '')
            client_key = result.get('client_key', '')
            self.key_row.set_text(app_key)
            self.client_key_row.set_text(client_key)
            # Connect to bridge with new credentials
            if self.bridge.connect():
                self.status_row.set_subtitle("Authenticated and connected!")
                self.status_icon.set_from_icon_name("network-transmit-receive-symbolic")
                self._update_bridge_status()
                # Refresh entertainment configs after authentication
                self._load_entertainment_configs()
            else:
                self.status_row.set_subtitle("Authenticated but connection failed")
        else:
            self.status_row.set_subtitle("Press the bridge button first, then try again")

    def _update_bridge_status(self):
        """Update bridge connection status display."""
        status = self.app_context.get_bridge_status(attempt_connect=True)
        if status.connected:
            self.status_row.set_subtitle("Connected")
            self.status_icon.set_from_icon_name("network-transmit-receive-symbolic") 
        else:
            self.status_row.set_subtitle("Not connected")
            self.status_icon.set_from_icon_name("network-offline-symbolic") 

    def _load_entertainment_configs(self):
        """Load entertainment configurations from bridge."""
        self._entertainment_configs = []
        
        if not self.bridge.test_connection():
            model = Gtk.StringList.new(["(Connect to bridge first)"])
            self.ent_row.set_model(model)
            self.ent_row.set_selected(0)
            return
        
        configs = self.bridge.get_entertainment_configurations()
        self._entertainment_configs = configs
        
        if not configs:
            model = Gtk.StringList.new(["(No entertainment zones found)"])
            self.ent_row.set_model(model)
            self.ent_row.set_selected(0)
            return
        
        current_id = self.settings.hue.entertainment_config_id
        selected_idx = 0
        labels = []
        
        for i, config in enumerate(configs):
            config_id = config.get('id', '')
            name = config.get('name', 'Unknown')
            channels = len(config.get('channels', []))
            label = f"{name} ({channels} channels)"
            labels.append(label)
            if config_id == current_id:
                selected_idx = i
        
        model = Gtk.StringList.new(labels)
        self.ent_row.set_model(model)
        self.ent_row.set_selected(selected_idx)

    def _on_refresh_entertainment_configs(self, button):
        """Refresh entertainment configuration list."""
        self._load_entertainment_configs()

    def _on_closed(self, dialog):
        """Handle dialog close - save settings."""
        self._save_settings()

    def _save_settings(self):
        """Save all settings from the dialog."""
        self.settings.hue.bridge_ip = self.ip_row.get_text()
        self.settings.hue.app_key = self.key_row.get_text()
        self.settings.hue.client_key = self.client_key_row.get_text()
        
        # Get entertainment config ID
        selected = self.ent_row.get_selected()
        if self._entertainment_configs and selected < len(self._entertainment_configs):
            self.settings.hue.entertainment_config_id = self._entertainment_configs[selected].get('id', '')
        else:
            self.settings.hue.entertainment_config_id = ""
        
        self.settings.capture.scale_factor = self.scale_row.get_value()
        
        # Zone settings
        self.settings.zones.show_preview = self.preview_row.get_active()
        # Grid size
        try:
            self.settings.zones.rows = int(self.rows_row.get_value())
        except Exception:
            self.settings.zones.rows = 16
        try:
            self.settings.zones.cols = int(self.cols_row.get_value())
        except Exception:
            self.settings.zones.cols = 16
        
        # Sync settings
        self.settings.sync.fps = int(self.fps_row.get_value())
        self.settings.sync.transition_time_ms = int(self.transition_row.get_value())
        self.settings.sync.brightness_scale = self.brightness_row.get_value()
        self.settings.sync.gamma = self.gamma_row.get_value()
        self.settings.sync.smoothing_factor = self.smoothing_row.get_value()
        
        self.settings.save()
