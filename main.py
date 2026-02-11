"""Main application entry point for Lumux."""

import os
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib, GdkPixbuf, Gdk
from config.settings_manager import SettingsManager
from gui.main_window import MainWindow
from lumux.app_context import AppContext

# Get the app icon path (relative to this file)
APP_ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "io.github.enginkirmaci.lumux.svg")


class LumuxApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='io.github.enginkirmaci.lumux',
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.connect('activate', self.on_activate)
        self.main_window = None
        self._setup_actions()
    
    def _setup_actions(self):
        """Setup application actions for tray menu."""
        # Show window action
        show_action = Gio.SimpleAction.new("show", None)
        show_action.connect("activate", self._on_show_window)
        self.add_action(show_action)
        
        # Toggle sync action
        toggle_sync_action = Gio.SimpleAction.new("toggle-sync", None)
        toggle_sync_action.connect("activate", self._on_toggle_sync)
        self.add_action(toggle_sync_action)
        
        # Quit action
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", self._on_quit)
        self.add_action(quit_action)
    
    def _on_show_window(self, action, param):
        """Show the main window."""
        if self.main_window:
            self.main_window.present()
    
    def _on_toggle_sync(self, action, param):
        """Toggle sync on/off."""
        if self.main_window:
            self.main_window._on_sync_toggle(None)
    
    def _on_quit(self, action, param):
        """Quit the application."""
        self.quit()
    
    def _auto_activate_reading_mode(self):
        """Auto-activate reading mode after startup delay.
        
        Returns False to stop the GLib timeout.
        """
        try:
            if self.app_context and self.app_context.mode_manager:
                result = self.app_context.mode_manager.switch_to_reading()
                if result:
                    print("Reading mode auto-activated on startup")
                else:
                    print("Failed to auto-activate reading mode")
        except Exception as e:
            print(f"Error auto-activating reading mode: {e}")
        return False  # Stop the timeout

    def on_activate(self, app):
        """Initialize and show main window."""
        # If window already exists, just present it
        if self.main_window:
            self.main_window.present()
            return
        
        # Apply Adwaita dark color scheme
        style_manager = Adw.StyleManager.get_default()
        style_manager.set_color_scheme(Adw.ColorScheme.PREFER_DARK)
        
        # Set up the application icon
        self._setup_app_icon()
        
        settings = SettingsManager.get_instance()
        self.app_context = AppContext(settings)
        bridge_status = self.app_context.start()

        if bridge_status.connected:
            print(f"Connected to Hue bridge at {bridge_status.bridge_ip}")
        else:
            print("Warning: Could not connect to Hue bridge")
            print("Please configure bridge IP and app key in Settings")

        self.main_window = MainWindow(self, self.app_context)
        self.main_window.present()
        
        # Auto-activate reading mode on startup if enabled
        if (bridge_status.connected and 
            settings.reading_mode.auto_activate_on_startup):
            print("Auto-activating reading mode on startup...")
            GLib.timeout_add(500, self._auto_activate_reading_mode)
    
    def _setup_app_icon(self):
        """Set up the application icon."""
        if os.path.exists(APP_ICON_PATH):
            # Add the icon directory to the search path
            icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
            icon_dir = os.path.dirname(APP_ICON_PATH)
            icon_theme.add_search_path(icon_dir)
            
            # Register the icon with GTK
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(APP_ICON_PATH)
                # Create multiple sizes for different use cases
                for size in [16, 24, 32, 48, 64, 128, 256, 512]:
                    scaled = pixbuf.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
                    if scaled:
                        pass  # Icons are registered via theme
            except Exception as e:
                print(f"Warning: Could not load app icon: {e}")

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
