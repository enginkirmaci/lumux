"""Main application window."""

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

from hue_sync.bridge import HueBridge
from hue_sync.capture import ScreenCapture
from hue_sync.zones import ZoneProcessor
from hue_sync.colors import ColorAnalyzer
from hue_sync.sync import SyncController
from config.settings_manager import SettingsManager
from config.zone_mapping import ZoneMapping
from gui.settings_dialog import SettingsDialog
from gui.zone_preview_widget import ZonePreviewWidget


class MainWindow(Gtk.ApplicationWindow):
    __gtype_name__ = 'HueSyncMainWindow'

    def __init__(self, app, sync_controller: SyncController):
        super().__init__(application=app)
        self.sync_controller = sync_controller
        self.settings = SettingsManager.get_instance()
        self.bridge_connected = False

        self._build_ui()
        self._check_bridge_connection()
        
        self.status_timeout_id = GLib.timeout_add(100, self._update_status)

    def _build_ui(self):
        """Build main window layout."""
        self.set_title("Philips Hue Sync")
        self.set_default_size(900, 700)

        header = Gtk.HeaderBar()
        settings_btn = Gtk.Button(label="Settings")
        settings_btn.connect("clicked", self._on_settings_clicked)
        header.pack_end(settings_btn)
        self.set_titlebar(header)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_top(20)
        main_box.set_margin_bottom(20)
        main_box.set_margin_start(20)
        main_box.set_margin_end(20)
        self.set_child(main_box)

        status_frame = Gtk.Frame(label="Status")
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        status_box.set_margin_top(10)
        status_box.set_margin_bottom(10)
        status_box.set_margin_start(10)
        status_box.set_margin_end(10)
        status_frame.set_child(status_box)

        self.status_label = Gtk.Label(label="Ready")
        self.status_label.set_xalign(0)
        status_box.append(self.status_label)

        self.fps_label = Gtk.Label(label="FPS: 0")
        self.fps_label.set_xalign(0)
        status_box.append(self.fps_label)

        self.frames_label = Gtk.Label(label="Frames: 0")
        self.frames_label.set_xalign(0)
        status_box.append(self.frames_label)

        main_box.append(status_frame)

        preview_frame = Gtk.Frame(label="Zone Preview")
        preview_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        preview_box.set_margin_top(10)
        preview_box.set_margin_bottom(10)
        preview_box.set_margin_start(10)
        preview_box.set_margin_end(10)
        preview_frame.set_child(preview_box)

        self.zone_preview = ZonePreviewWidget(
            rows=self.settings.zones.grid_rows,
            cols=self.settings.zones.grid_cols
        )
        self.zone_preview.set_layout(
            self.settings.zones.layout,
            self.settings.zones.grid_rows,
            self.settings.zones.grid_cols
        )
        preview_box.append(self.zone_preview)

        main_box.append(preview_frame)

        control_frame = Gtk.Frame(label="Controls")
        control_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        control_box.set_margin_top(10)
        control_box.set_margin_bottom(10)
        control_box.set_margin_start(10)
        control_box.set_margin_end(10)
        control_frame.set_child(control_box)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_box.set_halign(Gtk.Align.CENTER)

        self.start_btn = Gtk.Button(label="Start Sync")
        self.start_btn.set_size_request(120, 40)
        self.start_btn.connect("clicked", self._on_start_clicked)
        
        self.stop_btn = Gtk.Button(label="Stop Sync")
        self.stop_btn.set_size_request(120, 40)
        self.stop_btn.set_sensitive(False)
        self.stop_btn.connect("clicked", self._on_stop_clicked)

        btn_box.append(self.start_btn)
        btn_box.append(self.stop_btn)
        control_box.append(btn_box)

        info_label = Gtk.Label(
            label="Configure your Hue bridge in Settings before starting sync."
        )
        info_label.set_wrap(True)
        info_label.set_halign(Gtk.Align.CENTER)
        control_box.append(info_label)

        main_box.append(control_frame)

    def _check_bridge_connection(self):
        """Check if bridge is connected and update UI accordingly."""
        self.bridge_connected = self.sync_controller.bridge.test_connection()
        
        if self.bridge_connected:
            num_lights = len(self.sync_controller.bridge.get_light_ids())
            if num_lights > 0:
                self.status_label.set_text(f"Connected - {num_lights} light(s) found")
            else:
                self.status_label.set_text("Connected - No lights found")
            self.start_btn.set_sensitive(True)
        else:
            if not self.settings.hue.bridge_ip or not self.settings.hue.app_key:
                self.status_label.set_text("Not configured - Open Settings to configure bridge")
            else:
                self.status_label.set_text(f"Not connected to bridge at {self.settings.hue.bridge_ip}")
            self.start_btn.set_sensitive(False)

    def _update_status(self) -> bool:
        """Check for status updates from sync thread."""
        # Drain the queue to get the latest status
        last_status = None
        while True:
            status = self.sync_controller.get_status()
            if status is None:
                break
            last_status = status
        
        if last_status:
            status_type, message = last_status[:2]
            
            if status_type == 'status':
                if message == 'syncing':
                    self.status_label.set_text("Syncing...")
                    zone_colors = last_status[2]
                    if zone_colors:
                        self.zone_preview.update_colors(zone_colors)
                elif message == 'stopped':
                    self.status_label.set_text("Stopped")
                    self.start_btn.set_sensitive(True)
                    self.stop_btn.set_sensitive(False)
            elif status_type == 'error':
                self.status_label.set_text(f"Error: {message}")
                self.start_btn.set_sensitive(True)
                self.stop_btn.set_sensitive(False)

        stats = self.sync_controller.get_stats()
        if stats:
            self.fps_label.set_text(f"FPS: {stats['fps']:.1f}")
            self.frames_label.set_text(f"Frames: {stats['frame_count']}")

        return True

    def _on_start_clicked(self, button):
        """Start sync."""
        if not self.bridge_connected:
            self.status_label.set_text("Cannot start - Bridge not connected")
            return
            
        if not self.sync_controller.is_running():
            self.sync_controller.start()
            self.start_btn.set_sensitive(False)
            self.stop_btn.set_sensitive(True)
            self.status_label.set_text("Starting sync...")

    def _on_stop_clicked(self, button):
        """Stop sync."""
        if self.sync_controller.is_running():
            self.sync_controller.stop()
            self.start_btn.set_sensitive(True)
            self.stop_btn.set_sensitive(False)
            self.status_label.set_text("Stopping sync...")

    def _on_settings_clicked(self, button):
        """Open settings dialog."""
        dialog = SettingsDialog(self, self.sync_controller.bridge)
        dialog.connect("close-request", self._on_settings_closed)
        dialog.present()
    
    def _on_settings_closed(self, dialog):
        """Handle settings dialog close - refresh configuration."""
        self._check_bridge_connection()
        
        # Refresh Zone Preview widget with new layout/grid size
        self.zone_preview.set_layout(
            self.settings.zones.layout,
            self.settings.zones.grid_rows,
            self.settings.zones.grid_cols
        )
        
        # Update components with new settings
        self.sync_controller.capture.scale_factor = self.settings.capture.scale_factor
        self.sync_controller.capture.display_index = self.settings.capture.display_index
        self.sync_controller.capture.rotation = self.settings.capture.rotation
        
        self.sync_controller.zone_processor.layout = self.settings.zones.layout
        self.sync_controller.zone_processor.rows = self.settings.zones.grid_rows
        self.sync_controller.zone_processor.cols = self.settings.zones.grid_cols
        
        return False

    def do_close_request(self) -> bool:
        """Handle window close request."""
        if self.sync_controller.is_running():
            self.sync_controller.stop()
        
        if self.status_timeout_id:
            GLib.source_remove(self.status_timeout_id)
            self.status_timeout_id = None
        
        return False
