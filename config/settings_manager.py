"""Settings management for Hue Sync application."""

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional, List
from config.zone_mapping import ZoneMapping


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
class Settings:
    hue: HueSettings = field(default_factory=HueSettings)
    capture: CaptureSettings = field(default_factory=CaptureSettings)
    zones: ZoneSettings = field(default_factory=ZoneSettings)
    sync: SyncSettings = field(default_factory=SyncSettings)


class SettingsManager:
    _instance: Optional['SettingsManager'] = None

    def __new__(cls) -> 'SettingsManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._settings = Settings()
        self._config_dir = Path.home() / '.config' / 'lumux'
        self._settings_file = self._config_dir / 'settings.json'
        self._load_settings()

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
            'sync': asdict(self._settings.sync)
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

    def _ensure_config_dir(self):
        """Ensure config directory exists."""
        self._config_dir.mkdir(parents=True, exist_ok=True)
