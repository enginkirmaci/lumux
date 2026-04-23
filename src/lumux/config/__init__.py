"""Lumux configuration management.

Public API:
    SettingsManager — singleton settings with dataclasses
    ZoneMapping — zone to light mapping management
"""

from lumux.config.settings_manager import SettingsManager
from lumux.config.zone_mapping import ZoneMapping

__all__ = ["SettingsManager", "ZoneMapping"]
