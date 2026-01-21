"""Color analysis and conversion for Hue sync."""

from typing import Dict, Tuple, Optional

from utils.rgb_xy_converter import rgb_to_xy
import numpy as np


class ColorAnalyzer:
    def __init__(self, brightness_scale: float = 1.0, gamma: float = 1.0):
        self.brightness_scale = brightness_scale
        self.gamma = gamma
        self.previous_colors: Dict[str, Tuple[Tuple[float, float], int]] = {}

    def analyze_zone(self, rgb: Tuple[int, int, int], 
                    light_info: Optional[dict] = None) -> Tuple[Tuple[float, float], int]:
        """Calculate Hue color for a zone.

        Args:
            rgb: RGB tuple (0-255)
            light_info: Optional light metadata for gamut correction

        Returns:
            Tuple of ((x, y), brightness)
        """
        corrected_rgb = self._apply_gamma(rgb)
        r, g, b = corrected_rgb
        xy = rgb_to_xy(r, g, b, light_info=light_info)
        
        brightness = self._calculate_brightness(corrected_rgb)
        
        return (xy, brightness)

    def _calculate_brightness(self, rgb: Tuple[int, int, int]) -> int:
        """Calculate brightness (0-254) from RGB.

        Uses luminance formula: 0.2126*R + 0.7152*G + 0.0722*B
        """
        r, g, b = rgb
        luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
        brightness = int((luminance / 255.0) * 254.0 * self.brightness_scale)
        return max(1, min(254, brightness))

    def _apply_gamma(self, rgb: Tuple[int, int, int]) -> Tuple[int, int, int]:
        """Apply gamma correction to RGB values."""
        gamma = self.gamma if self.gamma > 0 else 1.0
        corrected = []
        for channel in rgb:
            normalized = max(0.0, min(1.0, channel / 255.0))
            adjusted = normalized ** gamma
            corrected.append(int(round(adjusted * 255.0)))
        return tuple(corrected)  # type: ignore[return-value]

    def apply_smoothing(self, current: Dict[str, Tuple[Tuple[float, float], int]],
                      factor: float = 0.3) -> Dict[str, Tuple[Tuple[float, float], int]]:
        """Smooth color transitions between updates.

        Uses exponential moving average:
        smoothed = previous + factor * (current - previous)

        Args:
            current: Current zone colors
            factor: Smoothing factor (0-1), higher = faster changes

        Returns:
            Smoothed zone colors
        """
        smoothed = {}
        
        for zone_id, curr_value in current.items():
            if zone_id in self.previous_colors:
                curr_xy, curr_bri = curr_value
                prev_xy, prev_bri = self.previous_colors[zone_id]
                
                smooth_xy = (
                    prev_xy[0] + factor * (curr_xy[0] - prev_xy[0]),
                    prev_xy[1] + factor * (curr_xy[1] - prev_xy[1])
                )
                smooth_bri = int(prev_bri + factor * (curr_bri - prev_bri))
                
                smoothed[zone_id] = (smooth_xy, smooth_bri)
            else:
                smoothed[zone_id] = curr_value

        self.previous_colors = smoothed.copy()
        return smoothed

    def analyze_zones_batch(self, zone_colors: Dict[str, Tuple[int, int, int]],
                          light_info_map: Optional[Dict[str, dict]] = None) -> Dict[str, Tuple[Tuple[float, float], int]]:
        """Analyze multiple zones at once.

        Args:
            zone_colors: Dictionary mapping zone IDs to RGB tuples
            light_info_map: Optional mapping of zones to light info

        Returns:
            Dictionary mapping zone IDs to ((x, y), brightness)
        """
        hue_colors = {}
        
        for zone_id, rgb in zone_colors.items():
            light_info = None
            if light_info_map and zone_id in light_info_map:
                light_info = light_info_map[zone_id]
            
            hue_colors[zone_id] = self.analyze_zone(rgb, light_info)
        
        return hue_colors
