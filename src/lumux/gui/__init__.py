"""Lumux GUI components (GTK4 + libadwaita).

Public widgets:
    MainWindow — main application window
    SettingsDialog — preferences dialog
    BridgeWizard — 3-step bridge setup wizard
    ZonePreviewWidget — real-time zone color visualization
    TrayIcon — system tray integration
"""

from lumux.gui.main_window import MainWindow
from lumux.gui.settings_dialog import SettingsDialog
from lumux.gui.bridge_wizard import BridgeWizard
from lumux.gui.zone_preview_widget import ZonePreviewWidget
from lumux.gui.tray_icon import TrayIcon

__all__ = [
    "MainWindow",
    "SettingsDialog",
    "BridgeWizard",
    "ZonePreviewWidget",
    "TrayIcon",
]
