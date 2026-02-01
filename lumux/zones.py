"""Zone processing for screen division."""

import numpy as np
from typing import Dict, Optional, TYPE_CHECKING

import PIL.Image as Image

from lumux.black_bar_detector import BlackBarDetector, CropRegion

if TYPE_CHECKING:
    from config.settings_manager import ZoneSettings


class ZoneProcessor:
    def __init__(self, rows: int = 16, cols: int = 16, settings: Optional["ZoneSettings"] = None):
        self.settings = settings
        if settings is not None:
            self.rows = settings.rows
            self.cols = settings.cols
            # Initialize black bar detector if enabled
            if getattr(settings, 'ignore_black_bars', False):
                self._black_bar_detector = BlackBarDetector(
                    threshold=getattr(settings, 'black_bar_threshold', 10),
                    min_size_percent=5.0
                )
            else:
                self._black_bar_detector = None
        else:
            self.rows = rows
            self.cols = cols
            self._black_bar_detector = None
        self._current_crop: Optional[CropRegion] = None
        self.zones: Dict[str, tuple[int, int, int]] = {}

    def process_image(self, image: Image.Image, apply_black_bar_crop: bool = True) -> Dict[str, tuple[int, int, int]]:
        """Process image and return zone colors.

        Args:
            image: PIL Image to process
            apply_black_bar_crop: Whether to apply black bar crop before processing

        Returns:
            Dictionary mapping zone IDs to RGB tuples
        """
        # Apply black bar crop if enabled and available
        if apply_black_bar_crop and self._current_crop is not None and self._current_crop.has_crop:
            image = self._current_crop.apply_to_image(image)
        return self._process_ambilight(image)

    def update_black_bar_crop(self, crop: CropRegion, smoothing_factor: float = 0.3):
        """Update the current black bar crop region with smoothing.

        Args:
            crop: Newly detected crop region
            smoothing_factor: Smoothing factor (0.0 = no change, 1.0 = immediate)
        """
        if self._black_bar_detector is not None:
            self._current_crop = self._black_bar_detector.smooth_crop(crop, smoothing_factor)
        else:
            self._current_crop = crop

    @property
    def current_crop(self) -> Optional[CropRegion]:
        """Get current black bar crop region."""
        return self._current_crop

    def _process_ambilight(self, image: Image.Image) -> Dict[str, tuple[int, int, int]]:
        """Process only edge zones (top, bottom, left, right)."""
        try:
            img_array = np.array(image)
            
            if len(img_array.shape) == 2:
                img_array = np.stack([img_array] * 3, axis=-1)
            elif img_array.shape[2] == 4:
                img_array = img_array[:, :, :3]

            zones = {}
            height, width = img_array.shape[0], img_array.shape[1]
            
            edge_width = min(width // self.cols, height // 8)
            edge_width = max(edge_width, 5)

            top_count = self.cols
            bottom_count = self.cols
            left_count = self.rows
            right_count = self.rows

            top_zone_width = width // top_count
            bottom_zone_width = width // bottom_count
            left_zone_height = height // left_count
            right_zone_height = height // right_count

            for i in range(top_count):
                x1 = i * top_zone_width
                x2 = min((i + 1) * top_zone_width, width)
                zone_pixels = img_array[0:edge_width, x1:x2]
                avg_color = np.mean(zone_pixels, axis=(0, 1))
                zones[f"top_{i}"] = tuple(avg_color.astype(int))

            for i in range(bottom_count):
                x1 = i * bottom_zone_width
                x2 = min((i + 1) * bottom_zone_width, width)
                y1 = max(0, height - edge_width)
                zone_pixels = img_array[y1:height, x1:x2]
                avg_color = np.mean(zone_pixels, axis=(0, 1))
                zones[f"bottom_{i}"] = tuple(avg_color.astype(int))

            for i in range(left_count):
                y1 = i * left_zone_height
                y2 = min((i + 1) * left_zone_height, height)
                zone_pixels = img_array[y1:y2, 0:edge_width]
                avg_color = np.mean(zone_pixels, axis=(0, 1))
                zones[f"left_{i}"] = tuple(avg_color.astype(int))

            for i in range(right_count):
                y1 = i * right_zone_height
                y2 = min((i + 1) * right_zone_height, height)
                x1 = max(0, width - edge_width)
                zone_pixels = img_array[y1:y2, x1:width]
                avg_color = np.mean(zone_pixels, axis=(0, 1))
                zones[f"right_{i}"] = tuple(avg_color.astype(int))

            return zones
        except Exception as e:
            print(f"Error processing ambilight: {e}")
            return {}