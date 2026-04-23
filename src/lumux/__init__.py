"""Lumux — Philips Hue Sync for Linux on Wayland.

Public API:
    LumuxApp — main application class (import from lumux.__main__)
    AppContext — dependency injection container
    HueBridge — bridge discovery and connection
    BridgeClient — Hue v2 REST API client
    ScreenCapture — screen capture via PipeWire portal
    ZoneProcessor — ambilight zone processing
    SyncController — main sync loop controller
    ModeManager — Video/Reading mode switching
    EntertainmentStream — DTLS streaming to Hue Entertainment
    ReadingModeController — Reading mode static lighting
    BlackBarDetector — letterbox/pillarbox detection
"""

__version__ = "0.6.0"
__author__ = "Engin Kırmacı"

# Re-export commonly used classes for convenience
from lumux.app_context import AppContext
from lumux.hue_bridge import HueBridge
from lumux.bridge_client import BridgeClient
from lumux.capture import ScreenCapture
from lumux.zones import ZoneProcessor
from lumux.sync import SyncController
from lumux.mode_manager import ModeManager
from lumux.entertainment import EntertainmentStream
from lumux.reading_mode import ReadingModeController
from lumux.black_bar_detector import BlackBarDetector
from lumux.colors import ColorAnalyzer
