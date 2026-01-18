"""Main application entry point for Philips Hue Sync."""

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
from gui.main_window import MainWindow
from hue_sync.light_updater import LightUpdateWorker


class HueSyncApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='com.github.huesync')
        self.connect('activate', self.on_activate)

    def on_activate(self, app):
        """Initialize and show main window."""
        settings = SettingsManager.get_instance()

        bridge = HueBridge(settings.hue.bridge_ip, settings.hue.app_key)
        bridge_connected = bridge.connect()

        if bridge_connected:
            print(f"Connected to Hue bridge at {settings.hue.bridge_ip}")
        else:
            print("Warning: Could not connect to Hue bridge")
            print("Please configure bridge IP and app key in Settings")

        capture = ScreenCapture(
            scale_factor=settings.capture.scale_factor,
            display_index=settings.capture.display_index,
            rotation=settings.capture.rotation
        )

        zone_processor = ZoneProcessor(
            layout=settings.zones.layout,
            rows=settings.zones.grid_rows,
            cols=settings.zones.grid_cols
        )

        color_analyzer = ColorAnalyzer(
            brightness_scale=settings.sync.brightness_scale
        )

        zone_mapping_file = SettingsManager.get_instance()._config_dir / 'zones.json'
        zone_mapping = ZoneMapping(mapping_file=zone_mapping_file)
        
        # Save default mapping if file doesn't exist
        if not zone_mapping_file.exists():
            zone_mapping.save(zone_mapping_file)

        # Instantiate and start background light updater (coalesces and flushes updates)
        light_worker = LightUpdateWorker(bridge, flush_interval_ms=100)
        light_worker.start()

        sync_controller = SyncController(
            bridge=bridge,
            capture=capture,
            zone_processor=zone_processor,
            color_analyzer=color_analyzer,
            zone_mapping=zone_mapping,
            settings=settings.sync,
            light_updater=light_worker
        )

        win = MainWindow(self, sync_controller)
        win.present()

    def do_shutdown(self):
        """Cleanup on shutdown."""
        print("Shutting down...")
        Gtk.Application.do_shutdown(self)


def main():
    app = HueSyncApp()
    app.run(None)


if __name__ == '__main__':
    main()
