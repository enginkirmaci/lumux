"""System tray icon implementation for Lumux.

Provides cross-desktop-environment tray icon support using:
1. D-Bus StatusNotifierItem (SNI) - Modern standard for KDE, GNOME (with extension), XFCE, LXQt, etc.
2. AppIndicator3/AyatanaAppIndicator3 fallback - For Ubuntu and systems with appindicator

This implementation runs the tray icon in a separate process to avoid
GTK3/GTK4 conflicts that arise when mixing AppIndicator3/GTK3 with GTK4 apps.

For Flatpak support, the manifest must include:
  - --talk-name=org.kde.StatusNotifierWatcher
  - --talk-name=org.freedesktop.Notifications
"""

import os
import sys
import subprocess
import threading
import json
from typing import Optional


def _get_icon_path() -> str:
    """Get the app icon path, handling both development and installed scenarios.
    
    Returns icon path suitable for the current environment (Flatpak or native).
    """
    # Flatpak installed location
    flatpak_icon = "/app/share/icons/hicolor/scalable/apps/io.github.enginkirmaci.lumux.svg"
    if os.path.exists(flatpak_icon):
        return flatpak_icon
    
    # Development/native location (next to main.py)
    dev_icon = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "io.github.enginkirmaci.lumux.svg"
    )
    if os.path.exists(dev_icon):
        return dev_icon
    
    # Fallback to icon name (requires icon to be in theme)
    return "io.github.enginkirmaci.lumux"


def _is_running_in_flatpak() -> bool:
    """Check if the application is running inside a Flatpak sandbox."""
    return os.path.exists("/.flatpak-info")


APP_ICON_PATH = _get_icon_path()


class TrayIcon:
    """System tray icon with menu for Lumux application.
    
    This implementation runs the tray icon in a separate process to avoid
    GTK3/GTK4 conflicts that arise when using AppIndicator3 with GTK4 apps.
    
    Supports multiple tray backends:
    - D-Bus StatusNotifierItem (SNI) - Modern cross-desktop standard
    - AppIndicator3 / AyatanaAppIndicator3 - Fallback for Ubuntu/Unity
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
        self._backend = None  # Will be set to 'sni', 'ayatana', or 'appindicator'
        
        self._start_tray_process()
    
    def _detect_tray_backend(self) -> Optional[str]:
        """Detect the best available tray backend.
        
        Returns:
            Backend name ('sni', 'ayatana', 'appindicator') or None if unavailable
        """
        check_script = """import sys, os
try:
    from pydbus import SessionBus
    bus = SessionBus()
    for w in ["org.kde.StatusNotifierWatcher", "org.freedesktop.StatusNotifierWatcher"]:
        try:
            if bus.get(w).IsStatusNotifierHostRegistered: print("sni"); sys.exit(0)
        except Exception: pass
except Exception: pass
if os.path.exists("/.flatpak-info"):
    try: import pydbus; print("sni"); sys.exit(0)
    except Exception: pass
try:
    import gi
    try: gi.require_version('AyatanaAppIndicator3', '0.1'); from gi.repository import AyatanaAppIndicator3; print("ayatana"); sys.exit(0)
    except Exception: pass
    try: gi.require_version('AppIndicator3', '0.1'); from gi.repository import AppIndicator3; print("appindicator"); sys.exit(0)
    except Exception: pass
except Exception: pass
print("none"); sys.exit(1)"""
        try:
            result = subprocess.run(
                [sys.executable, "-c", check_script],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception as e:
            print(f"Note: Could not detect tray backend: {e}")
            return None
    
    def _start_tray_process(self):
        """Start the tray icon subprocess."""
        backend = self._detect_tray_backend()
        
        if not backend:
            print("Note: System tray not available.")
            print("For tray support, install one of:")
            print("  - AppIndicator extension for GNOME")
            print("  - gir1.2-ayatanaappindicator3-0.1 (Ubuntu/Debian)")
            print("  - libappindicator-gtk3 (Arch)")
            return
        
        self._backend = backend
        
        if backend == "sni":
            tray_script = self._generate_sni_script()
        else:
            tray_script = self._generate_appindicator_script(backend)
        
        try:
            self._process = subprocess.Popen(
                [sys.executable, "-c", tray_script],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=None, # Inherit stderr for debugging
                text=True,
                bufsize=1
            )
            
            # Start listener thread
            self._listener_thread = threading.Thread(
                target=self._listen_for_commands,
                daemon=True
            )
            self._listener_thread.start()
            
            self._available = True
            print(f"Tray icon started using {backend} backend")
            
        except Exception as e:
            print(f"Warning: Could not start tray process: {e}")
            self._process = None
    
    def _generate_sni_script(self) -> str:
        """Generate Python script for D-Bus StatusNotifierItem backend.
        
        This implements the org.kde.StatusNotifierItem D-Bus interface directly,
        providing cross-desktop compatibility without GTK3 dependencies.
        """
        icon_path = APP_ICON_PATH
        return f'''import sys, os, json, threading, gi
gi.require_version('GdkPixbuf', '2.0')
from pydbus import SessionBus
from pydbus.generic import signal
from gi.repository import GLib, GdkPixbuf

SNI_INTERFACE = """<node><interface name="org.kde.StatusNotifierItem"><property name="Category" type="s" access="read"/><property name="Id" type="s" access="read"/><property name="Title" type="s" access="read"/><property name="Status" type="s" access="read"/><property name="IconName" type="s" access="read"/><property name="IconPixmap" type="a(iiay)" access="read"/><property name="AttentionIconName" type="s" access="read"/><property name="AttentionIconPixmap" type="a(iiay)" access="read"/><property name="ToolTip" type="(sa(iiay)ss)" access="read"/><property name="ItemIsMenu" type="b" access="read"/><property name="Menu" type="o" access="read"/><method name="ContextMenu"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method><method name="Activate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method><method name="SecondaryActivate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method><method name="Scroll"><arg name="delta" type="i" direction="in"/><arg name="orientation" type="s" direction="in"/></method><signal name="NewTitle"/><signal name="NewIcon"/><signal name="NewAttentionIcon"/><signal name="NewOverlayIcon"/><signal name="NewToolTip"/><signal name="NewStatus"><arg name="status" type="s"/></signal></interface></node>"""

DBUSMENU_INTERFACE = """<node><interface name="com.canonical.dbusmenu"><property name="Version" type="u" access="read"/><property name="TextDirection" type="s" access="read"/><property name="Status" type="s" access="read"/><property name="IconThemePath" type="as" access="read"/><method name="GetLayout"><arg name="parentId" type="i" direction="in"/><arg name="recursionDepth" type="i" direction="in"/><arg name="propertyNames" type="as" direction="in"/><arg name="revision" type="u" direction="out"/><arg name="layout" type="(ia{{sv}}av)" direction="out"/></method><method name="GetGroupProperties"><arg name="ids" type="ai" direction="in"/><arg name="propertyNames" type="as" direction="in"/><arg name="properties" type="a(ia{{sv}})" direction="out"/></method><method name="GetProperty"><arg name="id" type="i" direction="in"/><arg name="name" type="s" direction="in"/><arg name="value" type="v" direction="out"/></method><method name="Event"><arg name="id" type="i" direction="in"/><arg name="eventId" type="s" direction="in"/><arg name="data" type="v" direction="in"/><arg name="timestamp" type="u" direction="in"/></method><method name="EventGroup"><arg name="events" type="a(isvu)" direction="in"/><arg name="idErrors" type="ai" direction="out"/></method><method name="AboutToShow"><arg name="id" type="i" direction="in"/><arg name="needUpdate" type="b" direction="out"/></method><method name="AboutToShowGroup"><arg name="ids" type="ai" direction="in"/><arg name="updatesNeeded" type="ai" direction="out"/><arg name="idErrors" type="ai" direction="out"/></method><signal name="ItemsPropertiesUpdated"><arg name="updatedProps" type="a(ia{{sv}})"/><arg name="removedProps" type="a(ias)"/></signal><signal name="LayoutUpdated"><arg name="revision" type="u"/><arg name="parent" type="i"/></signal><signal name="ItemActivationRequested"><arg name="id" type="i"/><arg name="timestamp" type="u"/></signal></interface></node>"""

class DBusMenu:
    dbus = DBUSMENU_INTERFACE
    Version, TextDirection, Status, IconThemePath = 3, "ltr", "normal", []
    
    def __init__(self, on_click):
        self.on_click, self.is_syncing, self._revision = on_click, False, 1
    
    def GetLayout(self, pId, depth, props):
        sync_lbl = "Stop Sync" if self.is_syncing else "Start Sync"
        children = [
            (1, {{"label": GLib.Variant("s", "Show Lumux"), "visible": GLib.Variant("b", True)}}, []),
            (2, {{"type": GLib.Variant("s", "separator"), "visible": GLib.Variant("b", True)}}, []),
            (3, {{"label": GLib.Variant("s", sync_lbl), "visible": GLib.Variant("b", True)}}, []),
            (4, {{"type": GLib.Variant("s", "separator"), "visible": GLib.Variant("b", True)}}, []),
            (5, {{"label": GLib.Variant("s", "Settings"), "visible": GLib.Variant("b", True)}}, []),
            (6, {{"type": GLib.Variant("s", "separator"), "visible": GLib.Variant("b", True)}}, []),
            (7, {{"label": GLib.Variant("s", "Quit"), "visible": GLib.Variant("b", True)}}, []),
        ]
        return (self._revision, (0, {{"children-display": GLib.Variant("s", "submenu")}}, [GLib.Variant("(ia{{sv}}av)", c) for c in children]))
    
    def GetGroupProperties(self, ids, props):
        res = []
        for id in ids:
            p = {{}}
            if id == 1: p = {{"label": GLib.Variant("s", "Show Lumux")}}
            elif id == 3: p = {{"label": GLib.Variant("s", "Stop Sync" if self.is_syncing else "Start Sync")}}
            elif id == 5: p = {{"label": GLib.Variant("s", "Settings")}}
            elif id == 7: p = {{"label": GLib.Variant("s", "Quit")}}
            elif id in [2, 4, 6]: p = {{"type": GLib.Variant("s", "separator")}}
            res.append((id, p))
        return res
    
    def GetProperty(self, id, name): return GLib.Variant("s", "")
    def Event(self, id, eid, data, ts):
        if eid == "clicked": self.on_click(id)
    def EventGroup(self, evs):
        for e in evs:
            if e[1] == "clicked": self.on_click(e[0])
        return []
    def AboutToShow(self, id): return False
    def AboutToShowGroup(self, ids): return ([], [])
    def update_sync(self, syncing):
        self.is_syncing = syncing; self._revision += 1
    
    ItemsPropertiesUpdated = signal()
    LayoutUpdated = signal()
    ItemActivationRequested = signal()

class StatusNotifierItem:
    dbus = SNI_INTERFACE
    Category, Id, Title = "ApplicationStatus", "io.github.enginkirmaci.lumux", "Lumux - Hue Screen Sync"
    ItemIsMenu, Menu = False, "/MenuBar"
    
    def __init__(self, bus, menu, send):
        self.bus, self.menu, self.send = bus, menu, send
        self._status = "Active"
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale("{icon_path}", 22, 22, True)
            w, h, rs, pixels = pb.get_width(), pb.get_height(), pb.get_rowstride(), pb.read_pixel_bytes().get_data()
            argb = bytearray(w * h * 4)
            for y in range(h):
                for x in range(w):
                    si, di = (y * rs) + (x * 4), (y * w * 4) + (x * 4)
                    argb[di:di+4] = bytes([pixels[si+2], pixels[si+1], pixels[si], pixels[si+3]])
            self._icon_pixmap = [(w, h, GLib.Variant("ay", bytes(argb)))]
        except: self._icon_pixmap = []

    @property
    def Status(self): return self._status
    @property
    def IconName(self): return "io.github.enginkirmaci.lumux"
    @property
    def IconPixmap(self): return self._icon_pixmap
    @property
    def AttentionIconName(self): return "io.github.enginkirmaci.lumux"
    @property
    def AttentionIconPixmap(self): return self._icon_pixmap
    @property
    def ToolTip(self): return ("io.github.enginkirmaci.lumux", self._icon_pixmap, "Lumux", "Hue Screen Sync")
    
    def ContextMenu(self, x, y): pass
    def Activate(self, x, y): self.send({{"action": "show"}})
    def SecondaryActivate(self, x, y): self.send({{"action": "toggle_sync"}})
    def Scroll(self, d, o): pass
    
    NewTitle = signal(); NewIcon = signal(); NewAttentionIcon = signal(); NewOverlayIcon = signal(); NewToolTip = signal(); NewStatus = signal()

class TrayApp:
    def __init__(self):
        self.loop = GLib.MainLoop()
        self.bus = SessionBus()
        self.menu = DBusMenu(self.on_click)
        self.sni = StatusNotifierItem(self.bus, self.menu, self.send)
        import random; self.svc = f"io.github.enginkirmaci.lumux.Tray"
        try: self.bus.publish(self.svc, ("/StatusNotifierItem", self.sni), ("/MenuBar", self.menu))
        except: sys.exit(1)
        
        for w in ["org.kde.StatusNotifierWatcher", "org.freedesktop.StatusNotifierWatcher"]:
            try: self.bus.get(w, "/StatusNotifierWatcher").RegisterStatusNotifierItem(self.svc); break
            except: pass
            
        threading.Thread(target=self.listen, daemon=True).start()
    
    def on_click(self, id):
        acts = {{1: "show", 3: "toggle_sync", 5: "settings", 7: "quit"}}
        if id in acts:
            self.send({{"action": acts[id]}})
            if id == 7: self.loop.quit()

    def listen(self):
        try:
            for l in sys.stdin:
                if l := l.strip():
                    try: GLib.idle_add(self.handle, json.loads(l))
                    except: pass
        except: GLib.idle_add(self.loop.quit)

    def handle(self, cmd):
        if cmd.get("action") == "quit": self.loop.quit()
        elif cmd.get("action") == "update_sync":
            self.menu.update_sync(cmd.get("is_syncing", False))
            self.menu.LayoutUpdated.emit(self.menu._revision, 0)
        return False

    def send(self, cmd): print(json.dumps(cmd), flush=True)
    def run(self): self.loop.run()

if __name__ == "__main__":
    try: TrayApp().run()
    except: sys.exit(1)
'''
    
    def _generate_appindicator_script(self, indicator_type: str) -> str:
        """Generate Python script for AppIndicator backend.
        
        This is the fallback for systems without SNI support but with AppIndicator.
        """
        icon_value = APP_ICON_PATH if os.path.exists(APP_ICON_PATH) else "io.github.enginkirmaci.lumux"
        
        return f'''import sys, json, threading, gi
gi.require_version('Gtk', '3.0')
if "{indicator_type}" == "ayatana":
    gi.require_version('AyatanaAppIndicator3', '0.1')
    from gi.repository import AyatanaAppIndicator3 as AppIndicator
else:
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import AppIndicator3 as AppIndicator

from gi.repository import Gtk, GLib

class TrayApp:
    def __init__(self):
        self.is_syncing = False
        self.ind = AppIndicator.Indicator.new("io.github.enginkirmaci.lumux", "{icon_value}", AppIndicator.IndicatorCategory.APPLICATION_STATUS)
        self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.ind.set_title("Lumux - Hue Screen Sync")
        self.menu = Gtk.Menu()
        
        def add(lbl, cb=None):
            i = Gtk.MenuItem(label=lbl)
            if cb: i.connect("activate", cb)
            self.menu.append(i); return i
            
        add("Show Lumux", lambda w: self.send({{"action": "show"}}))
        self.menu.append(Gtk.SeparatorMenuItem())
        self.sync_item = add("Start Sync", lambda w: self.send({{"action": "toggle_sync"}}))
        self.menu.append(Gtk.SeparatorMenuItem())
        add("Settings", lambda w: self.send({{"action": "settings"}}))
        self.menu.append(Gtk.SeparatorMenuItem())
        add("Quit", lambda w: (self.send({{"action": "quit"}}), Gtk.main_quit()))
        
        self.menu.show_all()
        self.ind.set_menu(self.menu)
        threading.Thread(target=self.listen, daemon=True).start()
    
    def listen(self):
        try:
            for l in sys.stdin:
                if l := l.strip():
                    try: GLib.idle_add(self.handle, json.loads(l))
                    except: pass
        except: GLib.idle_add(Gtk.main_quit)
    
    def handle(self, cmd):
        if cmd.get("action") == "quit": Gtk.main_quit()
        elif cmd.get("action") == "update_sync":
            self.is_syncing = cmd.get("is_syncing", False)
            self.sync_item.set_label("Stop Sync" if self.is_syncing else "Start Sync")
        return False
    
    def send(self, cmd): print(json.dumps(cmd), flush=True)

if __name__ == "__main__":
    TrayApp()
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
        
        def _show(): 
            if self.main_window: self.main_window.present()
        def _sync(): 
            if self.main_window: self.main_window._on_sync_toggle(None)
        def _settings(): 
            if self.main_window: self.main_window.present(); self.main_window._on_settings_clicked(None)
            
        handlers = {
            "show": _show,
            "toggle_sync": _sync,
            "settings": _settings,
            "quit": lambda: self.app.quit() if self.app else None
        }
        
        if handler := handlers.get(cmd.get("action")):
            GLib.idle_add(handler)
    
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
    
    @property
    def backend(self) -> Optional[str]:
        """Get the active tray backend name."""
        return self._backend
    
    def destroy(self):
        """Clean up the tray icon."""
        if self._process:
            try:
                # Try to send quit command first
                self._send_to_tray({"action": "quit"})
            except Exception:
                pass
            
            try:
                # Close stdin to prevent BrokenPipeError
                if self._process.stdin:
                    self._process.stdin.close()
            except Exception:
                pass
            
            try:
                # Wait for graceful shutdown
                self._process.wait(timeout=2)
            except Exception:
                # Force kill if it doesn't exit gracefully
                try:
                    self._process.terminate()
                    self._process.wait(timeout=1)
                except Exception:
                    try:
                        self._process.kill()
                    except Exception:
                        pass
            
            self._process = None

