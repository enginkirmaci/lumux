"""Black bar (letterbox/pillarbox) detection for screen capture.

Analyzes row and column luminance to detect contiguous black regions
around the video content, enabling accurate color sampling from
non-black areas only.
"""

import numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class CropRegion:
    """Represents a detected crop region."""

    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0

    def is_valid(self, width: int, height: int) -> bool:
        """Check if crop region is valid (non-empty and within bounds)."""
        return (
            self.left >= 0
            and self.top >= 0
            and self.right <= width
            and self.bottom > self.top
            and self.right > self.left
            and self.bottom <= height
        )

    def width(self) -> int:
        """Return cropped width."""
        return self.right - self.left

    def height(self) -> int:
        """Return cropped height."""
        return self.bottom - self.top


class BlackBarDetector:
    """Detects black letterbox/pillarbox bars in video content.

    Uses luminance analysis on numpy arrays for efficiency. Detection
    runs at configurable intervals with smooth transitions between
    detected crop regions to avoid jarring changes.
    """

    def __init__(
        self,
        enabled: bool = True,
        threshold: int = 10,
        detection_rate: int = 30,
        smooth_factor: float = 0.3,
    ):
        """Initialize black bar detector.

        Args:
            enabled: Whether detection is enabled
            threshold: Luminance threshold (0-50) for black detection
            detection_rate: Run detection every N frames (1-120)
            smooth_factor: Transition smoothing factor (0-1)
        """
        self.enabled = enabled
        self.threshold = max(0, min(50, threshold))
        self.detection_rate = max(1, min(120, detection_rate))
        self.smooth_factor = max(0.1, min(1.0, smooth_factor))

        self._frame_counter = 0
        self._current_crop = CropRegion()
        self._target_crop = CropRegion()
        self._image_size: Optional[Tuple[int, int]] = None

        self._min_content_ratio = 0.5

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable detection."""
        self.enabled = enabled
        if not enabled:
            self._current_crop = CropRegion()
            self._target_crop = CropRegion()

    def set_threshold(self, threshold: int) -> None:
        """Set luminance threshold (0-50)."""
        self.threshold = max(0, min(50, threshold))

    def set_detection_rate(self, rate: int) -> None:
        """Set detection rate (frames between detection runs)."""
        self.detection_rate = max(1, min(120, rate))

    def process(self, image: np.ndarray) -> Optional[CropRegion]:
        """Process image and return crop region if bars detected.

        Args:
            image: Input numpy array (H, W, 3), dtype uint8

        Returns:
            CropRegion if cropping is needed, None if no crop needed
        """
        if not self.enabled:
            return None

        height, width = image.shape[0], image.shape[1]
        if height <= 0 or width <= 0:
            return None

        self._image_size = (width, height)

        if self._current_crop.left == 0 and self._current_crop.right == 0:
            self._current_crop = CropRegion(0, 0, width, height)
            self._target_crop = CropRegion(0, 0, width, height)

        self._frame_counter += 1
        if self._frame_counter >= self.detection_rate:
            self._frame_counter = 0
            self._detect_bars(image, width, height)

        self._apply_smoothing(width, height)

        crop_width = self._current_crop.width()
        crop_height = self._current_crop.height()

        if crop_width <= 0 or crop_height <= 0:
            self._current_crop = CropRegion(0, 0, width, height)
            self._target_crop = CropRegion(0, 0, width, height)
            return None

        if self._should_crop(width, height):
            return CropRegion(
                self._current_crop.left,
                self._current_crop.top,
                self._current_crop.right,
                self._current_crop.bottom,
            )

        return None

    def get_crop_region(self) -> Optional[CropRegion]:
        """Get current crop region (for zone processing alignment).

        Returns:
            Current crop region or None if no cropping applied
        """
        if not self.enabled or self._image_size is None:
            return None

        width, height = self._image_size
        if not self._should_crop(width, height):
            return None

        return CropRegion(
            self._current_crop.left,
            self._current_crop.top,
            self._current_crop.right,
            self._current_crop.bottom,
        )

    def _detect_bars(self, image: np.ndarray, width: int, height: int) -> None:
        """Detect black bars in image.

        Analyzes row and column luminance to find contiguous black regions.
        Works directly on numpy array to avoid PIL conversions.
        """
        try:
            if image.shape[2] == 4:
                img_array = image[:, :, :3]
            elif image.shape[2] == 1:
                img_array = np.stack([image[:, :, 0]] * 3, axis=2)
            else:
                img_array = image

            luminance = (
                0.299 * img_array[:, :, 0]
                + 0.587 * img_array[:, :, 1]
                + 0.114 * img_array[:, :, 2]
            )

            row_luminance = np.mean(luminance, axis=1)
            col_luminance = np.mean(luminance, axis=0)

            top = self._find_black_region(row_luminance, from_start=True)
            bottom = self._find_black_region(row_luminance, from_start=False)
            left = self._find_black_region(col_luminance, from_start=True)
            right = self._find_black_region(col_luminance, from_start=False)

            min_width = int(width * self._min_content_ratio)
            min_height = int(height * self._min_content_ratio)

            if width - left - right < min_width:
                left = 0
                right = 0

            if height - top - bottom < min_height:
                top = 0
                bottom = 0

            max_crop_x = width // 2 - 1
            max_crop_y = height // 2 - 1
            left = min(left, max_crop_x)
            right = min(right, max_crop_x)
            top = min(top, max_crop_y)
            bottom = min(bottom, max_crop_y)

            self._target_crop = CropRegion(
                left=left,
                top=top,
                right=width - right,
                bottom=height - bottom,
            )
        except Exception:
            self._target_crop = CropRegion(0, 0, width, height)

    def _find_black_region(self, luminance: np.ndarray, from_start: bool) -> int:
        """Find length of contiguous black region from start or end.

        Args:
            luminance: Array of luminance values
            from_start: If True, search from start; else from end

        Returns:
            Number of contiguous black pixels
        """
        if from_start:
            iterator = range(len(luminance))
        else:
            iterator = range(len(luminance) - 1, -1, -1)

        count = 0
        for i in iterator:
            if luminance[i] <= self.threshold:
                count += 1
            else:
                break

        return count

    def _apply_smoothing(self, width: int, height: int) -> None:
        """Apply smooth transition between current and target crop."""
        self._current_crop.left = int(
            self._current_crop.left
            + self.smooth_factor * (self._target_crop.left - self._current_crop.left)
        )
        self._current_crop.top = int(
            self._current_crop.top
            + self.smooth_factor * (self._target_crop.top - self._current_crop.top)
        )
        self._current_crop.right = int(
            self._current_crop.right
            + self.smooth_factor * (self._target_crop.right - self._current_crop.right)
        )
        self._current_crop.bottom = int(
            self._current_crop.bottom
            + self.smooth_factor
            * (self._target_crop.bottom - self._current_crop.bottom)
        )

        self._current_crop.left = max(0, min(width - 1, self._current_crop.left))
        self._current_crop.top = max(0, min(height - 1, self._current_crop.top))
        self._current_crop.right = max(1, min(width, self._current_crop.right))
        self._current_crop.bottom = max(1, min(height, self._current_crop.bottom))

        if self._current_crop.right <= self._current_crop.left:
            self._current_crop.right = width
            self._current_crop.left = 0
        if self._current_crop.bottom <= self._current_crop.top:
            self._current_crop.bottom = height
            self._current_crop.top = 0

        if self._current_crop.right - self._current_crop.left < 2:
            self._current_crop.left = 0
            self._current_crop.right = width
        if self._current_crop.bottom - self._current_crop.top < 2:
            self._current_crop.top = 0
            self._current_crop.bottom = height

    def _should_crop(self, width: int, height: int) -> bool:
        """Check if current crop region requires actual cropping."""
        crop_width = self._current_crop.width()
        crop_height = self._current_crop.height()

        width_diff = abs(crop_width - width) / width if width > 0 else 0
        height_diff = abs(crop_height - height) / height if height > 0 else 0

        return width_diff > 0.02 or height_diff > 0.02

    def reset(self) -> None:
        """Reset detector state (e.g., when changing video sources)."""
        self._frame_counter = 0
        self._current_crop = CropRegion()
        self._target_crop = CropRegion()
        self._image_size = None
