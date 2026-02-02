"""Application wiring and shared services."""

from dataclasses import dataclass

from config.settings_manager import SettingsManager
from lumux.bridge import HueBridge
from lumux.capture import ScreenCapture
from lumux.colors import ColorAnalyzer
from lumux.entertainment import EntertainmentStream
from lumux.sync import SyncController
from lumux.zones import ZoneProcessor


@dataclass(frozen=True)
class BridgeStatus:
    connected: bool
    configured: bool
    bridge_ip: str
    entertainment_zone_name: str = ""
    entertainment_channel_count: int = 0
    entertainment_connected: bool = False


class AppContext:
    def __init__(self, settings: SettingsManager):
        self.settings = settings

        self.bridge = HueBridge(settings.hue.bridge_ip, settings.hue.app_key)
        self.capture = ScreenCapture(
            scale_factor=settings.capture.scale_factor,
            black_bar_settings=settings.black_bar,
        )
        self.zone_processor = ZoneProcessor(settings=settings.zones)
        self.color_analyzer = ColorAnalyzer(
            brightness_scale=settings.sync.brightness_scale,
            gamma=settings.sync.gamma
        )
        self.zone_mapping = settings.get_zone_mapping()

        # Entertainment streaming (replaces REST-based light updates)
        self.entertainment_stream = None
        if settings.hue.client_key and settings.hue.entertainment_config_id:
            self.entertainment_stream = EntertainmentStream(
                bridge_ip=settings.hue.bridge_ip,
                app_key=settings.hue.app_key,
                client_key=settings.hue.client_key,
                entertainment_config_id=settings.hue.entertainment_config_id
            )

        self.sync_controller = SyncController(
            bridge=self.bridge,
            capture=self.capture,
            zone_processor=self.zone_processor,
            color_analyzer=self.color_analyzer,
            zone_mapping=self.zone_mapping,
            settings=settings.sync,
            entertainment_stream=self.entertainment_stream
        )

    def start(self) -> BridgeStatus:
        """Start background workers and attempt bridge connection."""
        return self.get_bridge_status(attempt_connect=True)

    def start_entertainment(self) -> bool:
        """Connect to entertainment streaming zone."""
        if not self.entertainment_stream:
            print("Entertainment stream not configured. Set client_key and entertainment_config_id.")
            return False
        
        if not self.bridge.test_connection():
            print("Bridge not connected. Connect to bridge first.")
            return False
        
        return self.entertainment_stream.connect(self.bridge)

    def stop_entertainment(self):
        """Disconnect from entertainment streaming zone."""
        if self.entertainment_stream and self.entertainment_stream.is_connected():
            self.entertainment_stream.disconnect(self.bridge)

    def shutdown(self) -> None:
        """Stop background workers and any running sync."""
        try:
            if self.sync_controller.is_running():
                self.sync_controller.stop()
        finally:
            self.stop_entertainment()

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

        # Update black bar detector settings
        self.capture.update_black_bar_settings(self.settings.black_bar)

        self.color_analyzer.brightness_scale = self.settings.sync.brightness_scale
        self.color_analyzer.gamma = self.settings.sync.gamma

        # Apply zone layout settings to the zone processor
        try:
            self.zone_processor.rows = int(self.settings.zones.rows)
        except Exception:
            self.zone_processor.rows = 16
        try:
            self.zone_processor.cols = int(self.settings.zones.cols)
        except Exception:
            self.zone_processor.cols = 16

        # Recreate entertainment stream if settings changed
        if hue.client_key and hue.entertainment_config_id:
            if (self.entertainment_stream is None or 
                self.entertainment_stream.entertainment_config_id != hue.entertainment_config_id):
                # Stop existing stream
                self.stop_entertainment()
                # Create new stream
                self.entertainment_stream = EntertainmentStream(
                    bridge_ip=hue.bridge_ip,
                    app_key=hue.app_key,
                    client_key=hue.client_key,
                    entertainment_config_id=hue.entertainment_config_id
                )
                # Update sync controller
                self.sync_controller.entertainment_stream = self.entertainment_stream

    def get_bridge_status(self, attempt_connect: bool = False) -> BridgeStatus:
        """Return current bridge status, optionally attempting a connection."""
        configured = bool(self.settings.hue.bridge_ip and self.settings.hue.app_key)
        connected = self.bridge.test_connection()

        if attempt_connect and configured and not connected:
            connected = self.bridge.connect()

        entertainment_zone_name = ""
        entertainment_channel_count = 0
        if connected and self.settings.hue.entertainment_config_id:
            configs = self.bridge.get_entertainment_configurations()
            for config in configs:
                if config.get('id') == self.settings.hue.entertainment_config_id:
                    entertainment_zone_name = config.get('name', '')
                    entertainment_channel_count = len(config.get('channels', []))
                    break
        
        entertainment_connected = (self.entertainment_stream is not None and 
                                   self.entertainment_stream.is_connected())
        
        return BridgeStatus(
            connected=connected,
            configured=configured,
            bridge_ip=self.settings.hue.bridge_ip,
            entertainment_zone_name=entertainment_zone_name,
            entertainment_channel_count=entertainment_channel_count,
            entertainment_connected=entertainment_connected
        )
