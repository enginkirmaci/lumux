"""System tray icon implementation for Lumux.

Uses a subprocess-based approach to avoid GTK3/GTK4 conflicts,
as AppIndicator3 requires GTK3 menus while the main app uses GTK4.
"""

import os
import sys
import subprocess
import threading
import json
from typing import Optional

# App icon path
APP_ICON_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "com.github.lumux.svg")


class TrayIcon:
    """System tray icon with menu for Lumux application.
    
    This implementation runs the tray icon in a separate process to avoid
    GTK3/GTK4 conflicts that arise when using AppIndicator3 with GTK4 apps.
    """
    
    def __init__(self, app, main_window):
        """Initialize tray icon.
        
        Args:
            app: The main Adw.Application instance
            main_window: The MainWindow instance for callbacks
        """
        self.app = app
        self.main_window = main_window
        self._process: Optional[subprocess.Popen] = None
        self._listener_thread: Optional[threading.Thread] = None
        self._available = False
        self._is_syncing = False
        
        self._start_tray_process()
    
    def _start_tray_process(self):
        """Start the tray icon subprocess."""
        # Check if AppIndicator is available before starting
        check_script = """
import sys
try:
    import gi
    gi.require_version('AyatanaAppIndicator3', '0.1')
    from gi.repository import AyatanaAppIndicator3
    print("ayatana")
    sys.exit(0)
except (ValueError, ImportError):
    pass
try:
    import gi
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import AppIndicator3
    print("appindicator")
    sys.exit(0)
except (ValueError, ImportError):
    pass
print("none")
sys.exit(1)
"""
        try:
            result = subprocess.run([sys.executable, "-c", check_script],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                print("Note: System tray not available.")
                print("Install libayatana-appindicator3-dev for tray support:")
                print("  sudo apt install gir1.2-ayatanaappindicator3-0.1")
                return
            
            indicator_type = result.stdout.strip()
        except Exception as e:
            print(f"Note: Could not check for tray support: {e}")
            return
        
        # Create the tray subprocess script
        tray_script = self._generate_tray_script(indicator_type)
        
        try:
            self._process = subprocess.Popen(
                [sys.executable, "-c", tray_script],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            # Start listener thread
            self._listener_thread = threading.Thread(target=self._listen_for_commands, daemon=True)
            self._listener_thread.start()
            
            self._available = True
            
        except Exception as e:
            print(f"Warning: Could not start tray process: {e}")
            self._process = None
    
    def _generate_tray_script(self, indicator_type: str) -> str:
        """Generate the Python script for the tray subprocess."""
        icon_path = APP_ICON_PATH if os.path.exists(APP_ICON_PATH) else "video-display"
        
        return f'''
import sys
import json
import gi

# Use GTK3 for the tray (AppIndicator requires it)
gi.require_version('Gtk', '3.0')
if "{indicator_type}" == "ayatana":
    gi.require_version('AyatanaAppIndicator3', '0.1')
    from gi.repository import AyatanaAppIndicator3 as AppIndicator
else:
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import AppIndicator3 as AppIndicator

from gi.repository import Gtk, GLib
import threading

class TrayApp:
    def __init__(self):
        self.is_syncing = False
        
        # Create indicator
        self.indicator = AppIndicator.Indicator.new(
            "com.github.lumux",
            "{icon_path}",
            AppIndicator.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.indicator.set_title("Lumux - Hue Screen Sync")
        
        # Create menu
        self.menu = Gtk.Menu()
        
        # Show Window item
        show_item = Gtk.MenuItem(label="Show Lumux")
        show_item.connect("activate", self.on_show)
        self.menu.append(show_item)
        
        # Separator
        self.menu.append(Gtk.SeparatorMenuItem())
        
        # Start/Stop Sync item
        self.sync_item = Gtk.MenuItem(label="Start Sync")
        self.sync_item.connect("activate", self.on_toggle_sync)
        self.menu.append(self.sync_item)
        
        # Separator
        self.menu.append(Gtk.SeparatorMenuItem())
        
        # Settings item
        settings_item = Gtk.MenuItem(label="Settings")
        settings_item.connect("activate", self.on_settings)
        self.menu.append(settings_item)
        
        # Separator
        self.menu.append(Gtk.SeparatorMenuItem())
        
        # Quit item
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self.on_quit)
        self.menu.append(quit_item)
        
        self.menu.show_all()
        self.indicator.set_menu(self.menu)
        
        # Start stdin listener
        self.stdin_thread = threading.Thread(target=self.listen_stdin, daemon=True)
        self.stdin_thread.start()
    
    def listen_stdin(self):
        """Listen for commands from parent process."""
        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    cmd = json.loads(line)
                    GLib.idle_add(self.handle_command, cmd)
                except json.JSONDecodeError:
                    pass
        except Exception:
            GLib.idle_add(Gtk.main_quit)
    
    def handle_command(self, cmd):
        """Handle command from parent."""
        action = cmd.get("action")
        if action == "quit":
            Gtk.main_quit()
        elif action == "update_sync":
            self.is_syncing = cmd.get("is_syncing", False)
            label = "Stop Sync" if self.is_syncing else "Start Sync"
            self.sync_item.set_label(label)
        return False
    
    def send_command(self, cmd):
        """Send command to parent process."""
        print(json.dumps(cmd), flush=True)
    
    def on_show(self, item):
        self.send_command({{"action": "show"}})
    
    def on_toggle_sync(self, item):
        self.send_command({{"action": "toggle_sync"}})
    
    def on_settings(self, item):
        self.send_command({{"action": "settings"}})
    
    def on_quit(self, item):
        self.send_command({{"action": "quit"}})
        Gtk.main_quit()

if __name__ == "__main__":
    app = TrayApp()
    Gtk.main()
'''
    
    def _listen_for_commands(self):
        """Listen for commands from the tray subprocess."""
        if not self._process or not self._process.stdout:
            return
        
        try:
            for line in self._process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    cmd = json.loads(line)
                    self._handle_tray_command(cmd)
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
    
    def _handle_tray_command(self, cmd: dict):
        """Handle command from tray subprocess."""
        from gi.repository import GLib
        
        action = cmd.get("action")
        if action == "show":
            GLib.idle_add(self._do_show)
        elif action == "toggle_sync":
            GLib.idle_add(self._do_toggle_sync)
        elif action == "settings":
            GLib.idle_add(self._do_settings)
        elif action == "quit":
            GLib.idle_add(self._do_quit)
    
    def _do_show(self):
        """Show the main window."""
        if self.main_window:
            self.main_window.present()
        return False
    
    def _do_toggle_sync(self):
        """Toggle sync."""
        if self.main_window:
            self.main_window._on_sync_toggle(None)
        return False
    
    def _do_settings(self):
        """Open settings."""
        if self.main_window:
            self.main_window.present()
            self.main_window._on_settings_clicked(None)
        return False
    
    def _do_quit(self):
        """Quit the application."""
        if self.app:
            self.app.quit()
        return False
    
    def _send_to_tray(self, cmd: dict):
        """Send command to tray subprocess."""
        if self._process and self._process.stdin:
            try:
                self._process.stdin.write(json.dumps(cmd) + "\n")
                self._process.stdin.flush()
            except Exception:
                pass
    
    def update_sync_status(self, is_syncing: bool):
        """Update the sync menu item label based on state.
        
        Args:
            is_syncing: Whether sync is currently active
        """
        self._is_syncing = is_syncing
        self._send_to_tray({"action": "update_sync", "is_syncing": is_syncing})
    
    @property
    def is_available(self) -> bool:
        """Check if tray icon is available."""
        return self._available
    
    def destroy(self):
        """Clean up the tray icon."""
        if self._process:
            try:
                self._send_to_tray({"action": "quit"})
                self._process.terminate()
                self._process.wait(timeout=2)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
