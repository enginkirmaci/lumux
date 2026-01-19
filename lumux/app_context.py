"""Application wiring and shared services."""

from dataclasses import dataclass

from config.settings_manager import SettingsManager
from lumux.bridge import HueBridge
from lumux.capture import ScreenCapture
from lumux.colors import ColorAnalyzer
from lumux.light_updater import LightUpdateWorker
from lumux.sync import SyncController
from lumux.zones import ZoneProcessor


@dataclass(frozen=True)
class BridgeStatus:
    connected: bool
    configured: bool
    bridge_ip: str
    light_count: int


class AppContext:
    def __init__(self, settings: SettingsManager):
        self.settings = settings

        self.bridge = HueBridge(settings.hue.bridge_ip, settings.hue.app_key)
        self.capture = ScreenCapture(
            scale_factor=settings.capture.scale_factor,
        )
        self.zone_processor = ZoneProcessor(
            layout=settings.zones.layout,
            rows=settings.zones.grid_rows,
            cols=settings.zones.grid_cols
        )
        self.color_analyzer = ColorAnalyzer(
            brightness_scale=settings.sync.brightness_scale,
            gamma=settings.sync.gamma
        )
        self.zone_mapping = settings.get_zone_mapping()

        self.light_worker = LightUpdateWorker(self.bridge, flush_interval_ms=100)
        self.sync_controller = SyncController(
            bridge=self.bridge,
            capture=self.capture,
            zone_processor=self.zone_processor,
            color_analyzer=self.color_analyzer,
            zone_mapping=self.zone_mapping,
            settings=settings.sync,
            light_updater=self.light_worker
        )

    def start(self) -> BridgeStatus:
        """Start background workers and attempt bridge connection."""
        self.light_worker.start()
        return self.get_bridge_status(attempt_connect=True)

    def shutdown(self) -> None:
        """Stop background workers and any running sync."""
        try:
            if self.sync_controller.is_running():
                self.sync_controller.stop()
        finally:
            self.light_worker.stop()

    def apply_settings(self) -> None:
        """Apply current settings to live components."""
        hue = self.settings.hue
        if (self.bridge.bridge_ip, self.bridge.app_key) != (hue.bridge_ip, hue.app_key):
            self.bridge.bridge_ip = hue.bridge_ip
            self.bridge.app_key = hue.app_key
            self.bridge.hue = None
            self.bridge.bridge = None

        capture = self.settings.capture
        self.capture.scale_factor = capture.scale_factor

        zones = self.settings.zones
        self.zone_processor.layout = zones.layout
        self.zone_processor.rows = zones.grid_rows
        self.zone_processor.cols = zones.grid_cols
        self.zone_mapping.layout = zones.layout

        self.color_analyzer.brightness_scale = self.settings.sync.brightness_scale
        self.color_analyzer.gamma = self.settings.sync.gamma

    def get_bridge_status(self, attempt_connect: bool = False) -> BridgeStatus:
        """Return current bridge status, optionally attempting a connection."""
        configured = bool(self.settings.hue.bridge_ip and self.settings.hue.app_key)
        connected = self.bridge.test_connection()

        if attempt_connect and configured and not connected:
            connected = self.bridge.connect()

        light_count = len(self.bridge.get_light_ids()) if connected else 0
        return BridgeStatus(
            connected=connected,
            configured=configured,
            bridge_ip=self.settings.hue.bridge_ip,
            light_count=light_count
        )
