"""Zone processing for screen division."""

import numpy as np
from typing import Dict, Optional

import PIL.Image as Image


class ZoneProcessor:
    def __init__(self, layout: str = "ambilight", rows: int = 16, cols: int = 16):
        self.layout = layout.lower()
        self.rows = rows
        self.cols = cols
        self.zones: Dict[str, tuple[int, int, int]] = {}

    def process_image(self, image: Image.Image) -> Dict[str, tuple[int, int, int]]:
        """Process image and return zone colors.

        Args:
            image: PIL Image to process

        Returns:
            Dictionary mapping zone IDs to RGB tuples
        """
        if self.layout == "ambilight":
            return self._process_ambilight(image)
        elif self.layout == "grid":
            return self._process_grid(image) 
        else:
            return self._process_grid(image)

    def _process_grid(self, image: Image.Image) -> Dict[str, tuple[int, int, int]]:
        """Divide image into grid and calculate zone averages."""
        try:
            img_array = np.array(image)
            
            if len(img_array.shape) == 2:
                img_array = np.stack([img_array] * 3, axis=-1)
            elif img_array.shape[2] == 4:
                img_array = img_array[:, :, :3]

            zone_height = max(1, img_array.shape[0] // self.rows)
            zone_width = max(1, img_array.shape[1] // self.cols)

            zones = {}
            
            for row in range(self.rows):
                for col in range(self.cols):
                    y1 = row * zone_height
                    y2 = min((row + 1) * zone_height, img_array.shape[0])
                    x1 = col * zone_width
                    x2 = min((col + 1) * zone_width, img_array.shape[1])

                    if y2 > y1 and x2 > x1:
                        zone_pixels = img_array[y1:y2, x1:x2]
                        h = zone_pixels.shape[0]
                        w = zone_pixels.shape[1]
                        # Use only the perimeter (edge) pixels of the zone for averaging
                        if h > 2 and w > 2:
                            mask = np.zeros((h, w), dtype=bool)
                            mask[0, :] = True
                            mask[-1, :] = True
                            mask[:, 0] = True
                            mask[:, -1] = True
                            edge_pixels = zone_pixels[mask]
                            avg_color = np.mean(edge_pixels, axis=0)
                        else:
                            # Fallback to full zone when too small
                            avg_color = np.mean(zone_pixels, axis=(0, 1))
                        rgb = tuple(avg_color.astype(int))
                        zones[str(row * self.cols + col)] = rgb
                    else:
                        zones[str(row * self.cols + col)] = (0, 0, 0)

            return zones
        except Exception as e:
            print(f"Error processing grid: {e}")
            return {}

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
            left_count = max(1, self.rows // 2)
            right_count = max(1, self.rows // 2)

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
 
    def get_zone_count(self) -> int:
        """Get total number of zones based on layout."""
        if self.layout == "ambilight":
            top_count = self.cols
            bottom_count = self.cols
            left_count = max(1, self.rows // 2)
            right_count = max(1, self.rows // 2)
            return top_count + bottom_count + left_count + right_count
        else:
            return self.rows * self.cols

    def get_zone_ids(self) -> list[str]:
        """Get list of all zone IDs for current layout."""
        if self.layout == "ambilight":
            top_count = self.cols
            bottom_count = self.cols
            left_count = max(1, self.rows // 2)
            right_count = max(1, self.rows // 2)
            
            zones = []
            for i in range(top_count):
                zones.append(f"top_{i}")
            for i in range(bottom_count):
                zones.append(f"bottom_{i}")
            for i in range(left_count):
                zones.append(f"left_{i}")
            for i in range(right_count):
                zones.append(f"right_{i}")
            return zones
        else:
            return [str(i) for i in range(self.rows * self.cols)]
