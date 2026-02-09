"""Settings dialog with modern Adwaita preferences styling."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk
from pathlib import Path
from lumux.hue_bridge import HueBridge
from lumux.app_context import AppContext
from config.settings_manager import is_running_in_flatpak
from gui.bridge_wizard import BridgeWizard


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

        # Wizard setup row
        wizard_row = Adw.ActionRow()
        wizard_row.set_title("Bridge Setup")
        wizard_row.set_subtitle("Launch wizard to discover and configure bridge")
        
        wizard_btn = Gtk.Button(label="Setup Bridge")
        wizard_btn.add_css_class("suggested-action")
        wizard_btn.set_valign(Gtk.Align.CENTER)
        wizard_btn.connect("clicked", self._on_start_wizard)
        wizard_row.add_suffix(wizard_btn)
        connection_group.add(wizard_row)

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

        # General / Application page
        general_page = Adw.PreferencesPage()
        general_page.set_title("General")
        general_page.set_icon_name("preferences-system-symbolic")
        self.add(general_page)

        general_group = Adw.PreferencesGroup()
        general_group.set_title("Application")
        general_group.set_description("Application behavior and startup options")
        general_page.add(general_group)

        # Start at startup
        self.startup_row = Adw.SwitchRow()
        self.startup_row.set_title("Start at Login")
        
        # Get current autostart status
        is_autostart_enabled = self.settings.is_autostart_enabled()
        self.startup_row.set_active(is_autostart_enabled)
        
        # Set subtitle
        if is_autostart_enabled:
            self.startup_row.set_subtitle("Launch Lumux when you log in (enabled)")
        else:
            self.startup_row.set_subtitle("Launch Lumux when you log in")
        
        # Connect to notify::active for immediate action
        self.startup_row.connect("notify::active", self._on_startup_toggled)
        general_group.add(self.startup_row)

        # Minimize to tray when sync starts
        self.minimize_row = Adw.SwitchRow()
        self.minimize_row.set_title("Minimize to Tray on Sync")
        self.minimize_row.set_subtitle("Automatically minimize the main window when sync starts")
        try:
            self.minimize_row.set_active(self.settings.ui.minimize_to_tray_on_sync)
        except Exception:
            self.minimize_row.set_active(False)
        general_group.add(self.minimize_row)

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

        # Black bar detection group
        blackbar_group = Adw.PreferencesGroup()
        blackbar_group.set_title("Black Bar Detection")
        blackbar_group.set_description("Automatically detect and ignore letterbox/pillarbox bars")
        capture_page.add(blackbar_group)

        # Enable black bar detection
        self.blackbar_enable_row = Adw.SwitchRow()
        self.blackbar_enable_row.set_title("Enable Detection")
        self.blackbar_enable_row.set_subtitle("Ignore black bars around video content")
        self.blackbar_enable_row.set_active(self.settings.black_bar.enabled)
        blackbar_group.add(self.blackbar_enable_row)

        # Threshold
        self.blackbar_threshold_row = Adw.SpinRow.new_with_range(0, 50, 1)
        self.blackbar_threshold_row.set_title("Luminance Threshold")
        self.blackbar_threshold_row.set_subtitle("Brightness level considered black (0-50)")
        self.blackbar_threshold_row.set_digits(0)
        self.blackbar_threshold_row.set_value(self.settings.black_bar.threshold)
        blackbar_group.add(self.blackbar_threshold_row)

        # Detection rate
        self.blackbar_rate_row = Adw.SpinRow.new_with_range(1, 120, 1)
        self.blackbar_rate_row.set_title("Detection Rate")
        self.blackbar_rate_row.set_subtitle("Run detection every N frames (1-120)")
        self.blackbar_rate_row.set_digits(0)
        self.blackbar_rate_row.set_value(self.settings.black_bar.detection_rate)
        blackbar_group.add(self.blackbar_rate_row)

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

        # Reading Mode page
        reading_page = Adw.PreferencesPage()
        reading_page.set_title("Reading")
        reading_page.set_icon_name("weather-clear-night-symbolic")
        self.add(reading_page)

        reading_group = Adw.PreferencesGroup()
        reading_group.set_title("Reading Mode")
        reading_group.set_description("Static lighting for reading and relaxation")
        reading_page.add(reading_group)

        # Default color row
        color_row = Adw.ActionRow()
        color_row.set_title("Default Color")
        color_row.set_subtitle("Color used when activating reading mode")
        
        self.reading_color_btn = Gtk.ColorDialogButton()
        color_dialog = Gtk.ColorDialog()
        color_dialog.set_title("Select Default Reading Color")
        self.reading_color_btn.set_dialog(color_dialog)
        # Set current color from settings
        rgba = Gdk.RGBA()
        xy = self.settings.reading_mode.color_xy
        # Approximate XY to RGB conversion for display
        r, g, b = self._xy_to_rgb(xy[0], xy[1])
        rgba.red = r
        rgba.green = g
        rgba.blue = b
        rgba.alpha = 1.0
        self.reading_color_btn.set_rgba(rgba)
        self.reading_color_btn.set_valign(Gtk.Align.CENTER)
        color_row.add_suffix(self.reading_color_btn)
        reading_group.add(color_row)

        # Default brightness
        self.reading_brightness_row = Adw.SpinRow.new_with_range(0, 254, 1)
        self.reading_brightness_row.set_title("Default Brightness")
        self.reading_brightness_row.set_subtitle("Brightness level for reading mode (0-254)")
        self.reading_brightness_row.set_digits(0)
        self.reading_brightness_row.set_value(self.settings.reading_mode.brightness)
        reading_group.add(self.reading_brightness_row)

        # Auto-activate reading mode
        self.reading_auto_row = Adw.SwitchRow()
        self.reading_auto_row.set_title("Auto-activate on Stop")
        self.reading_auto_row.set_subtitle("Automatically switch to reading mode when video sync stops")
        self.reading_auto_row.set_active(self.settings.reading_mode.auto_activate)
        reading_group.add(self.reading_auto_row)

        # Connect close signal to save settings
        self.connect("closed", self._on_closed)

    def _on_start_wizard(self, button):
        """Launch the bridge setup wizard."""
        wizard = BridgeWizard(
            app_context=self.settings,
            on_finished=self._on_wizard_finished
        )
        wizard.connect('finished', self._on_wizard_close)
        wizard.connect('cancelled', self._on_wizard_close)
        self.push_subpage(wizard)
    
    def _on_wizard_close(self, wizard):
        """Close the wizard and return to settings."""
        self.pop_subpage()

    def _on_wizard_finished(self, bridge_ip: str, app_key: str, client_key: str, entertainment_config_id: str):
        """Called when wizard is completed successfully."""
        # Save settings
        self.settings.hue.bridge_ip = bridge_ip
        self.settings.hue.app_key = app_key
        self.settings.hue.client_key = client_key
        self.settings.hue.entertainment_config_id = entertainment_config_id
        
        # Persist settings to disk
        self.settings.save()
        
        # Apply settings to live components (recreates entertainment stream)
        self.app_context.apply_settings()
        
        # Update UI with new settings
        self.ip_row.set_text(bridge_ip)
        self.key_row.set_text(app_key)
        self.client_key_row.set_text(client_key)
        
        # Update status
        self._update_bridge_status()
        
        # Refresh entertainment zones
        self._load_entertainment_configs()

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

    def _on_startup_toggled(self, switch, pspec):
        """Handle startup toggle change immediately."""
        state = switch.get_active()
        if state:
            try:
                result = self.settings.enable_autostart()
                if result:

                    self.settings.ui.start_at_startup = True
                    self.startup_row.set_subtitle("Launch Lumux when you log in (enabled)")
                else:
                    # Failed to enable but not a permission error (e.g., venv)

                    self._show_flatpak_permission_dialog()
                    switch.set_active(False)
            except PermissionError:
                # Flatpak without host filesystem access - show permission dialog
                switch.set_active(False)
                self._show_flatpak_permission_dialog()
        else:
            self.settings.disable_autostart()
            self.settings.ui.start_at_startup = False
            self.startup_row.set_subtitle("Launch Lumux when you log in")

    def _show_flatpak_permission_dialog(self):
        """Show dialog explaining how to grant Flatpak permission for autostart."""
        dialog = Adw.MessageDialog(
            transient_for=self._parent,
            heading="Permission Required",
            body="Lumux needs access to your home directory to enable automatic startup. This permission allows Lumux to create a startup entry in your system.",
        )
        dialog.set_default_size(440, -1)
        
        # Add the command as a selectable label
        command = "flatpak override --user --filesystem=host io.github.enginkirmaci.lumux"
        
        dialog.add_response("copy", "Copy Command")
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.set_close_response("close")
        
        # Add extra content with the command
        extra_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        extra_box.set_margin_top(12)
        
        command_label = Gtk.Label(label="Run this command in your terminal:")
        command_label.set_xalign(0)
        command_label.add_css_class("dim-label")
        extra_box.append(command_label)
        
        # Command entry (selectable)
        command_entry = Gtk.Entry()
        command_entry.set_text(command)
        command_entry.set_editable(False)
        command_entry.set_can_focus(True)
        extra_box.append(command_entry)
        
        # Restart note
        restart_label = Gtk.Label(label="After running the command, restart Lumux to apply the changes.")
        restart_label.set_xalign(0)
        restart_label.add_css_class("dim-label")
        restart_label.set_wrap(True)
        extra_box.append(restart_label)
        
        dialog.set_extra_child(extra_box)
        
        dialog.connect("response", self._on_flatpak_dialog_response, command)
        dialog.present()
    
    def _on_flatpak_dialog_response(self, dialog, response, command):
        """Handle Flatpak permission dialog response."""
        if response == "copy":
            # Copy command to clipboard
            clipboard = self.get_clipboard()
            clipboard.set(command)
            
            # Show a brief toast notification if available
            # (Adw.Toast is not directly available on MessageDialog, so we just close)

    def _on_closed(self, dialog):
        """Handle dialog close - save settings."""
        self._save_settings()

    def _xy_to_rgb(self, x: float, y: float) -> tuple:
        """Convert CIE XY color coordinates to RGB (approximate)."""
        if y == 0:
            return (1.0, 1.0, 1.0)
        
        # Convert xy to XYZ
        Y = 1.0
        X = (Y / y) * x
        Z = (Y / y) * (1 - x - y)
        
        # Convert XYZ to RGB (sRGB D65)
        r = X * 3.2406 + Y * -1.5372 + Z * -0.4986
        g = X * -0.9689 + Y * 1.8758 + Z * 0.0415
        b = X * 0.0557 + Y * -0.2040 + Z * 1.0570
        
        # Apply gamma correction
        def gamma_correct(c):
            if c <= 0.0031308:
                return 12.92 * c
            else:
                return 1.055 * pow(c, 1/2.4) - 0.055
        
        r = gamma_correct(r)
        g = gamma_correct(g)
        b = gamma_correct(b)
        
        # Clamp to 0-1
        return (max(0.0, min(1.0, r)), max(0.0, min(1.0, g)), max(0.0, min(1.0, b)))

    def _rgb_to_xy(self, r: float, g: float, b: float) -> tuple:
        """Convert RGB to CIE XY color coordinates."""
        # Apply gamma correction
        r = pow(r, 2.4) if r > 0.04045 else r / 12.92
        g = pow(g, 2.4) if g > 0.04045 else g / 12.92
        b = pow(b, 2.4) if b > 0.04045 else b / 12.92
        
        # Convert to XYZ
        X = r * 0.664511 + g * 0.154324 + b * 0.162028
        Y = r * 0.283881 + g * 0.668433 + b * 0.047685
        Z = r * 0.000088 + g * 0.072310 + b * 0.986039
        
        # Convert to xy
        sum_xyz = X + Y + Z
        if sum_xyz == 0:
            return (0.0, 0.0)
        
        x = X / sum_xyz
        y = Y / sum_xyz
        
        return (max(0.0, min(1.0, x)), max(0.0, min(1.0, y)))

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
        
        # Black bar settings
        try:
            self.settings.black_bar.enabled = bool(self.blackbar_enable_row.get_active())
        except Exception:
            self.settings.black_bar.enabled = False
        try:
            self.settings.black_bar.threshold = int(self.blackbar_threshold_row.get_value())
        except Exception:
            self.settings.black_bar.threshold = 10
        try:
            self.settings.black_bar.detection_rate = int(self.blackbar_rate_row.get_value())
        except Exception:
            self.settings.black_bar.detection_rate = 30
        
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
        # UI settings - startup is handled immediately in _on_startup_toggled
        # but we ensure the setting matches the current state
        if hasattr(self, "startup_row"):
            try:
                self.settings.ui.start_at_startup = bool(self.startup_row.get_active())
            except Exception:
                pass

        try:
            self.settings.ui.minimize_to_tray_on_sync = bool(self.minimize_row.get_active())
        except Exception:
            pass
        
        # Reading mode settings
        rgba = self.reading_color_btn.get_rgba()
        xy = self._rgb_to_xy(rgba.red, rgba.green, rgba.blue)
        self.settings.reading_mode.color_xy = xy
        self.settings.reading_mode.brightness = int(self.reading_brightness_row.get_value())
        self.settings.reading_mode.auto_activate = bool(self.reading_auto_row.get_active())
        
        self.settings.save()
