"""Settings management for Hue Sync application."""

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional, List
from config.zone_mapping import ZoneMapping
import sys
import os
import shlex


def is_running_in_flatpak() -> bool:
    """Return True when running inside a Flatpak sandbox."""
    return os.path.exists("/.flatpak-info") or bool(os.environ.get("FLATPAK_ID"))


@dataclass
class HueSettings:
    bridge_ip: str = ""
    app_key: str = ""
    client_key: str = ""  # PSK for DTLS entertainment streaming
    entertainment_config_id: str = ""  # Selected entertainment zone
    auto_discover: bool = True


@dataclass
class CaptureSettings:
    scale_factor: float = 0.125


@dataclass
class ZoneSettings:
    show_preview: bool = True
    rows: int = 16
    cols: int = 16


@dataclass
class SyncSettings:
    fps: int = 15
    transition_time_ms: int = 100
    brightness_scale: float = 1.0
    gamma: float = 1.0
    smoothing_factor: float = 0.3


@dataclass
class UISettings:
    start_at_startup: bool = False
    minimize_to_tray_on_sync: bool = False


@dataclass
class BlackBarSettings:
    enabled: bool = False
    threshold: int = 10
    detection_rate: int = 30
    smooth_factor: float = 0.3


@dataclass
class ReadingModeSettings:
    color_xy: tuple = field(default_factory=lambda: (0.5, 0.4))  # Warm white default
    brightness: int = 150  # 0-254
    auto_activate: bool = True  # Auto-switch to reading mode when video sync stops
    light_ids: List[str] = field(default_factory=list)  # Explicit light IDs for reading mode (empty = auto)


@dataclass
class Settings:
    hue: HueSettings = field(default_factory=HueSettings)
    capture: CaptureSettings = field(default_factory=CaptureSettings)
    zones: ZoneSettings = field(default_factory=ZoneSettings)
    sync: SyncSettings = field(default_factory=SyncSettings)
    ui: UISettings = field(default_factory=UISettings)
    black_bar: BlackBarSettings = field(default_factory=BlackBarSettings)
    reading_mode: ReadingModeSettings = field(default_factory=ReadingModeSettings)


class SettingsManager:
    _instance: Optional['SettingsManager'] = None

    def __new__(cls) -> 'SettingsManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._settings = Settings()
        self._config_dir = self._get_config_dir()
        self._settings_file = self._config_dir / 'settings.json'
        self._load_settings()

    def _get_config_dir(self) -> Path:
        """Get the config directory, respecting XDG dirs for Flatpak compatibility."""
        if is_running_in_flatpak():
            # In Flatpak, use XDG_CONFIG_HOME which is mapped to a persistent location
            # Usually: ~/.var/app/io.github.enginkirmaci.lumux/config/
            xdg_config = os.environ.get('XDG_CONFIG_HOME')
            if xdg_config:
                return Path(xdg_config) / 'lumux'
        # Default: ~/.config/lumux
        return Path.home() / '.config' / 'lumux'

    @classmethod
    def get_instance(cls) -> 'SettingsManager':
        return cls()

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def hue(self) -> HueSettings:
        return self._settings.hue

    @property
    def capture(self) -> CaptureSettings:
        return self._settings.capture

    @property
    def zones(self) -> ZoneSettings:
        return self._settings.zones

    @property
    def sync(self) -> SyncSettings:
        return self._settings.sync

    @property
    def ui(self):
        return self._settings.ui

    @property
    def black_bar(self) -> BlackBarSettings:
        return self._settings.black_bar

    @property
    def reading_mode(self) -> ReadingModeSettings:
        return self._settings.reading_mode

    def get_zone_mapping(self) -> ZoneMapping:
        """Return a ZoneMapping instance stored in the config directory.

        Zone mappings are not persisted; mapping is regenerated on each sync start.
        """
        
        return ZoneMapping()

    def _load_settings(self):
        """Load settings from config file."""
        if self._settings_file.exists():
            try:
                with open(self._settings_file, 'r') as f:
                    data = json.load(f)
                
                self._settings.hue = HueSettings(**data.get('hue', {}))
                self._settings.capture = CaptureSettings(**data.get('capture', {}))
                # Ensure we pass show_preview through when present
                self._settings.zones = ZoneSettings(**data.get('zones', {}))
                self._settings.sync = SyncSettings(**data.get('sync', {}))
                # UI settings (optional)
                self._settings.ui = UISettings(**data.get('ui', {}))
                # Black bar settings (optional)
                self._settings.black_bar = BlackBarSettings(**data.get('black_bar', {}))
                # Reading mode settings (optional)
                reading_data = data.get('reading_mode', {})
                # Handle tuple serialization for color_xy
                if 'color_xy' in reading_data and isinstance(reading_data['color_xy'], list):
                    reading_data['color_xy'] = tuple(reading_data['color_xy'])
                # Handle light_ids serialization (ensure it's a list)
                if 'light_ids' in reading_data and not isinstance(reading_data['light_ids'], list):
                    reading_data['light_ids'] = []
                self._settings.reading_mode = ReadingModeSettings(**reading_data)
            except (json.JSONDecodeError, TypeError) as e:
                print(f"Error loading settings: {e}")
                self._validate_settings()

        self._ensure_config_dir()
        self._validate_settings()

    def save(self):
        """Save settings to config file."""
        self._ensure_config_dir()
        self._validate_settings()

        data = {
            'hue': asdict(self._settings.hue),
            'capture': asdict(self._settings.capture),
            'zones': asdict(self._settings.zones),
            'sync': asdict(self._settings.sync),
            'ui': asdict(self._settings.ui),
            'black_bar': asdict(self._settings.black_bar),
            'reading_mode': asdict(self._settings.reading_mode)
        }

        with open(self._settings_file, 'w') as f:
            json.dump(data, f, indent=2)

    def _validate_settings(self):
        """Validate and clamp settings to valid ranges."""
        self._settings.capture.scale_factor = max(0.01, min(1.0, self._settings.capture.scale_factor))
        self._settings.sync.fps = max(1, min(60, self._settings.sync.fps))
        self._settings.sync.transition_time_ms = max(0, min(1000, self._settings.sync.transition_time_ms))
        self._settings.sync.brightness_scale = max(0.0, min(2.0, self._settings.sync.brightness_scale))
        self._settings.sync.gamma = max(0.1, min(3.0, self._settings.sync.gamma))
        self._settings.sync.smoothing_factor = max(0.1, min(1.0, self._settings.sync.smoothing_factor))
        # Zone grid size bounds
        try:
            self._settings.zones.rows = int(self._settings.zones.rows)
        except Exception:
            self._settings.zones.rows = 16
        try:
            self._settings.zones.cols = int(self._settings.zones.cols)
        except Exception:
            self._settings.zones.cols = 16

        self._settings.zones.rows = max(1, min(64, self._settings.zones.rows))
        self._settings.zones.cols = max(1, min(64, self._settings.zones.cols))

        # UI settings validation
        try:
            self._settings.ui.start_at_startup = bool(self._settings.ui.start_at_startup)
        except Exception:
            self._settings.ui.start_at_startup = False
        try:
            self._settings.ui.minimize_to_tray_on_sync = bool(self._settings.ui.minimize_to_tray_on_sync)
        except Exception:
            self._settings.ui.minimize_to_tray_on_sync = False

        # Black bar settings validation
        try:
            self._settings.black_bar.enabled = bool(self._settings.black_bar.enabled)
        except Exception:
            self._settings.black_bar.enabled = False
        try:
            self._settings.black_bar.threshold = int(self._settings.black_bar.threshold)
        except Exception:
            self._settings.black_bar.threshold = 10
        try:
            self._settings.black_bar.detection_rate = int(self._settings.black_bar.detection_rate)
        except Exception:
            self._settings.black_bar.detection_rate = 30
        try:
            self._settings.black_bar.smooth_factor = float(self._settings.black_bar.smooth_factor)
        except Exception:
            self._settings.black_bar.smooth_factor = 0.3

        self._settings.black_bar.threshold = max(0, min(50, self._settings.black_bar.threshold))
        self._settings.black_bar.detection_rate = max(1, min(120, self._settings.black_bar.detection_rate))
        self._settings.black_bar.smooth_factor = max(0.1, min(1.0, self._settings.black_bar.smooth_factor))

        # Reading mode settings validation
        try:
            if isinstance(self._settings.reading_mode.color_xy, (list, tuple)) and len(self._settings.reading_mode.color_xy) == 2:
                x, y = self._settings.reading_mode.color_xy
                self._settings.reading_mode.color_xy = (float(x), float(y))
            else:
                self._settings.reading_mode.color_xy = (0.5, 0.4)
        except Exception:
            self._settings.reading_mode.color_xy = (0.5, 0.4)
        
        # Clamp XY to valid CIE color space range
        x, y = self._settings.reading_mode.color_xy
        self._settings.reading_mode.color_xy = (max(0.0, min(1.0, x)), max(0.0, min(1.0, y)))
        
        try:
            self._settings.reading_mode.brightness = int(self._settings.reading_mode.brightness)
        except Exception:
            self._settings.reading_mode.brightness = 150
        self._settings.reading_mode.brightness = max(0, min(254, self._settings.reading_mode.brightness))
        
        try:
            self._settings.reading_mode.auto_activate = bool(self._settings.reading_mode.auto_activate)
        except Exception:
            self._settings.reading_mode.auto_activate = True
        
        # Validate light_ids is a list
        try:
            if not isinstance(self._settings.reading_mode.light_ids, list):
                self._settings.reading_mode.light_ids = []
        except Exception:
            self._settings.reading_mode.light_ids = []

    def _ensure_config_dir(self):
        """Ensure config directory exists."""
        self._config_dir.mkdir(parents=True, exist_ok=True)

    def enable_autostart(self):
        """Enable autostart by creating .desktop file in autostart directory."""
        return self._enable_autostart_file()
    
    def _enable_autostart_file(self) -> bool:
        """Enable autostart by writing .desktop file."""

        autostart_dir = Path.home() / '.config' / 'autostart'
        autostart_dir.mkdir(parents=True, exist_ok=True)

        desktop_path = autostart_dir / 'io.github.enginkirmaci.lumux.desktop'

        if is_running_in_flatpak():
            exec_cmd = "flatpak run io.github.enginkirmaci.lumux"
        else:
            try:
                exe = shlex.quote(sys.executable)
                script = os.path.abspath(sys.argv[0]) if len(sys.argv) > 0 else ''
                if script:
                    exec_cmd = f"{exe} {shlex.quote(script)}"
                else:
                    exec_cmd = exe
            except Exception:
                exec_cmd = shlex.quote(sys.executable)

        content = f"""[Desktop Entry]
Type=Application
Name=Lumux
Exec={exec_cmd}
Icon=io.github.enginkirmaci.lumux
Terminal=false
X-GNOME-Autostart-enabled=true
NoDisplay=false
"""

        try:
            with open(desktop_path, 'w') as f:
                f.write(content)
            return True
        except PermissionError:
            # Flatpak without host filesystem access
            raise PermissionError("Cannot write to autostart directory. Flatpak needs filesystem=host permission.")
        except Exception as e:
            print(f"Failed to write autostart file: {e}")
            return False

    def disable_autostart(self):
        """Disable autostart by removing .desktop file."""
        return self._disable_autostart_file()
    
    def _disable_autostart_file(self) -> bool:
        """Disable autostart by removing .desktop file."""
        desktop_path = Path.home() / '.config' / 'autostart' / 'io.github.enginkirmaci.lumux.desktop'
        try:
            if desktop_path.exists():
                desktop_path.unlink()
            return True
        except Exception as e:
            print(f"Failed to remove autostart file: {e}")
            return False

    def is_autostart_enabled(self) -> bool:
        """Check if autostart is enabled by looking for .desktop file."""
        desktop_path = Path.home() / '.config' / 'autostart' / 'io.github.enginkirmaci.lumux.desktop'
        return desktop_path.exists()

    def get_autostart_status(self) -> tuple[bool, str]:
        """Get autostart status and a message explaining the current state.
        
        Returns:
            Tuple of (is_enabled, status_message)
        """
        is_enabled = self.is_autostart_enabled()
        if is_enabled:
            if is_running_in_flatpak():
                return True, "Autostart enabled (Flatpak)"
            return True, "Autostart enabled"
        else:
            return False, "Autostart disabled"
