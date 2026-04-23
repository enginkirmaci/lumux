"""Zone processing for screen division."""

import numpy as np
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from lumux.config.settings_manager import ZoneSettings


class ZoneProcessor:
    def __init__(
        self, rows: int = 16, cols: int = 16, settings: Optional["ZoneSettings"] = None
    ):
        if settings is not None:
            self.rows = settings.rows
            self.cols = settings.cols
        else:
            self.rows = rows
            self.cols = cols
        self.zones: Dict[str, tuple[int, int, int]] = {}

    def _rebuild_zone_ids(self):
        self.zones = {}

    def process_image(self, image: np.ndarray) -> Dict[str, tuple[int, int, int]]:
        """Process image and return zone colors.

        Args:
            image: numpy array (H, W, 3), dtype uint8

        Returns:
            Dictionary mapping zone IDs to RGB tuples
        """
        return self._process_ambilight(image)

    def _process_ambilight(
        self, img_array: np.ndarray
    ) -> Dict[str, tuple[int, int, int]]:
        """Process only edge zones (top, bottom, left, right)."""
        try:
            if img_array is None or img_array.size == 0:
                return {}

            height, width = img_array.shape[0], img_array.shape[1]

            if len(img_array.shape) == 2:
                img_array = np.stack([img_array] * 3, axis=-1)
            elif img_array.shape[2] == 4:
                img_array = img_array[:, :, :3]

            if height < 2 or width < 2:
                return {}

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

            zones = {}

            for i in range(top_count):
                x1 = i * top_zone_width
                x2 = min((i + 1) * top_zone_width, width)
                avg_color = np.mean(img_array[0:edge_width, x1:x2], axis=(0, 1))
                zones[f"top_{i}"] = (
                    int(avg_color[0]),
                    int(avg_color[1]),
                    int(avg_color[2]),
                )

            for i in range(bottom_count):
                x1 = i * bottom_zone_width
                x2 = min((i + 1) * bottom_zone_width, width)
                y1 = max(0, height - edge_width)
                avg_color = np.mean(img_array[y1:height, x1:x2], axis=(0, 1))
                zones[f"bottom_{i}"] = (
                    int(avg_color[0]),
                    int(avg_color[1]),
                    int(avg_color[2]),
                )

            for i in range(left_count):
                y1 = i * left_zone_height
                y2 = min((i + 1) * left_zone_height, height)
                avg_color = np.mean(img_array[y1:y2, 0:edge_width], axis=(0, 1))
                zones[f"left_{i}"] = (
                    int(avg_color[0]),
                    int(avg_color[1]),
                    int(avg_color[2]),
                )

            for i in range(right_count):
                y1 = i * right_zone_height
                y2 = min((i + 1) * right_zone_height, height)
                x1 = max(0, width - edge_width)
                avg_color = np.mean(img_array[y1:y2, x1:width], axis=(0, 1))
                zones[f"right_{i}"] = (
                    int(avg_color[0]),
                    int(avg_color[1]),
                    int(avg_color[2]),
                )

            return zones
        except Exception as e:
            print(f"Error processing ambilight: {e}")
            return {}
