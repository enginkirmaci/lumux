"""Main application entry point for Lumux."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw
from config.settings_manager import SettingsManager
from gui.main_window import MainWindow
from lumux.app_context import AppContext


class LumuxApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.github.lumux')
        self.connect('activate', self.on_activate)

    def on_activate(self, app):
        """Initialize and show main window."""
        # Apply Adwaita dark color scheme
        style_manager = Adw.StyleManager.get_default()
        style_manager.set_color_scheme(Adw.ColorScheme.PREFER_DARK)
        
        settings = SettingsManager.get_instance()
        self.app_context = AppContext(settings)
        bridge_status = self.app_context.start()

        if bridge_status.connected:
            print(f"Connected to Hue bridge at {bridge_status.bridge_ip}")
        else:
            print("Warning: Could not connect to Hue bridge")
            print("Please configure bridge IP and app key in Settings")

        win = MainWindow(self, self.app_context)
        win.present()

    def do_shutdown(self):
        """Cleanup on shutdown."""
        print("Shutting down...")
        if getattr(self, "app_context", None):
            self.app_context.shutdown()
        Adw.Application.do_shutdown(self)


def main():
    app = LumuxApp()
    app.run(None)


if __name__ == '__main__':
    main()
