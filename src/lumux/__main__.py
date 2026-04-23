"""Main application entry point for Lumux."""

import os
import signal
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib, Gdk
from lumux.config.settings_manager import SettingsManager
from lumux.gui.main_window import MainWindow
from lumux.app_context import AppContext
from lumux.utils.logging import timed_print

# Get the app icon path (relative to this file's location in src/lumux/)
# Icon is at project_root/io.github.enginkirmaci.lumux.svg
APP_ICON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "io.github.enginkirmaci.lumux.svg"
)
APP_ICON_PATH = os.path.normpath(APP_ICON_PATH)


class LumuxApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="io.github.enginkirmaci.lumux",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self.connect("activate", self.on_activate)
        self.main_window = None
        self._setup_actions()

        # Register signal handlers for clean shutdown
        # Ensures Hue lights are turned off when system sends SIGTERM/SIGINT
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum, frame):
        """Handle SIGTERM/SIGINT by triggering clean shutdown."""
        timed_print(f"Received signal {signum}, shutting down...")
        GLib.idle_add(self._quit_safely)

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
        if self.main_window:
            self.main_window._quitting = True
        self.quit()

    def _quit_safely(self):
        """Safely quit from signal handler (called on GLib idle)."""
        if self.main_window:
            self.main_window._quitting = True
        self.quit()
        return False  # Don't repeat

    def _auto_activate_reading_mode(self):
        """Auto-activate reading mode after startup delay.

        Retries periodically if the bridge isn't ready yet (common at
        system startup when the network stack may still be initializing).

        Returns False to stop the GLib timeout (on success or max retries).
        """
        if not (self.app_context and self.app_context.mode_manager):
            self._auto_activate_retries = getattr(self, "_auto_activate_retries", 0) + 1
            if self._auto_activate_retries < 20:
                GLib.timeout_add(1000, self._auto_activate_reading_mode)
            return False

        try:
            if self.app_context.mode_manager.is_reading_active():
                timed_print("Reading mode already active")
                self._auto_activate_retries = 0
                return False

            if not self.app_context.bridge.test_connection():
                self.app_context.bridge.connect()

            result = self.app_context.mode_manager.switch_to_reading()
            if result:
                timed_print("Reading mode auto-activated on startup")
                self._auto_activate_retries = 0
                return False
            else:
                self._auto_activate_retries = (
                    getattr(self, "_auto_activate_retries", 0) + 1
                )
                if self._auto_activate_retries < 20:
                    timed_print(
                        f"Bridge not ready, retrying reading mode activation ({self._auto_activate_retries}/20)..."
                    )
                    GLib.timeout_add(1000, self._auto_activate_reading_mode)
                else:
                    timed_print(
                        "Giving up on auto-activating reading mode after 20 retries"
                    )
        except Exception as e:
            timed_print(f"Error auto-activating reading mode: {e}")
            self._auto_activate_retries = getattr(self, "_auto_activate_retries", 0) + 1
            if self._auto_activate_retries < 20:
                GLib.timeout_add(1000, self._auto_activate_reading_mode)
        return False

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
            timed_print(f"Connected to Hue bridge at {bridge_status.bridge_ip}")
        else:
            timed_print("Warning: Could not connect to Hue bridge")
            timed_print("Please configure bridge IP and app key in Settings")

        self.main_window = MainWindow(self, self.app_context)

        # Minimize at startup if setting is enabled and tray is available
        if settings.ui.minimize_at_startup and self.main_window._tray_icon:
            self.main_window.hide()
        else:
            self.main_window.present()

        # Auto-activate reading mode on startup if enabled.
        # Even if bridge is not connected yet, schedule retries since
        # the network may still be initializing at system startup.
        if settings.reading_mode.auto_activate_on_startup:
            if bridge_status.connected:
                timed_print("Auto-activating reading mode on startup...")
                GLib.timeout_add(500, self._auto_activate_reading_mode)
            else:
                timed_print(
                    "Bridge not connected yet, will retry reading mode activation..."
                )
                self._auto_activate_retries = 0
                GLib.timeout_add(2000, self._auto_activate_reading_mode)

    def _setup_app_icon(self):
        """Set up the application icon."""
        if os.path.exists(APP_ICON_PATH):
            try:
                icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
                icon_dir = os.path.dirname(APP_ICON_PATH)
                icon_theme.add_search_path(icon_dir)
            except Exception as e:
                timed_print(f"Warning: Could not load app icon: {e}")

    def do_shutdown(self):
        """Cleanup on shutdown."""
        timed_print("Shutting down...")
        if getattr(self, "app_context", None):
            self.app_context.shutdown()
        Adw.Application.do_shutdown(self)


def main():
    app = LumuxApp()
    app.run(None)


if __name__ == "__main__":
    main()
