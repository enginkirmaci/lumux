"""Black bar (letterbox/pillarbox) detection for video content."""

import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple

import PIL.Image as Image


@dataclass
class CropRegion:
    """Crop region representing detected black bars."""
    top: int = 0
    bottom: int = 0
    left: int = 0
    right: int = 0
    
    @property
    def has_crop(self) -> bool:
        """Return True if any crop is applied."""
        return self.top > 0 or self.bottom > 0 or self.left > 0 or self.right > 0
    
    def apply_to_image(self, image: Image.Image) -> Image.Image:
        """Apply crop region to PIL Image."""
        if not self.has_crop:
            return image
        width, height = image.size
        left = self.left
        top = self.top
        right = width - self.right
        bottom = height - self.bottom
        return image.crop((left, top, right, bottom))


class BlackBarDetector:
    """Detect black bars (letterbox/pillarbox) in video frames."""
    
    def __init__(self, threshold: int = 10, min_size_percent: float = 5.0):
        """
        Initialize black bar detector.
        
        Args:
            threshold: Luminance threshold (0-255), pixels below this are considered black
            min_size_percent: Minimum size of black bar as percentage of frame dimension
        """
        self.threshold = threshold
        self.min_size_percent = min_size_percent
        self._last_crop: Optional[CropRegion] = None
    
    def detect(self, image: Image.Image) -> CropRegion:
        """
        Detect black bars in image.
        
        Args:
            image: PIL Image to analyze
            
        Returns:
            CropRegion with detected black bar sizes in pixels
        """
        # Convert to numpy array for fast processing
        img_array = np.array(image)
        
        if len(img_array.shape) == 2:
            # Grayscale
            gray = img_array
        elif img_array.shape[2] == 4:
            # RGBA - drop alpha
            gray = np.dot(img_array[:, :, :3], [0.299, 0.587, 0.114])
        else:
            # RGB
            gray = np.dot(img_array[:, :, :3], [0.299, 0.587, 0.114])
        
        height, width = gray.shape
        min_size = int(min(height, width) * self.min_size_percent / 100)
        
        # Row-wise analysis (horizontal bands - letterbox detection)
        row_means = np.mean(gray, axis=1)
        top_crop = self._find_contiguous_below_threshold(row_means, self.threshold, min_size)
        bottom_crop = self._find_contiguous_below_threshold(row_means[::-1], self.threshold, min_size)
        
        # Column-wise analysis (vertical bands - pillarbox detection)
        col_means = np.mean(gray, axis=0)
        left_crop = self._find_contiguous_below_threshold(col_means, self.threshold, min_size)
        right_crop = self._find_contiguous_below_threshold(col_means[::-1], self.threshold, min_size)
        
        crop = CropRegion(
            top=top_crop,
            bottom=bottom_crop,
            left=left_crop,
            right=right_crop
        )
        
        self._last_crop = crop
        return crop
    
    def _find_contiguous_below_threshold(self, values: np.ndarray, threshold: int, min_size: int) -> int:
        """
        Find contiguous region at start of array where values are below threshold.
        
        Args:
            values: 1D array of mean luminance values
            threshold: Luminance threshold
            min_size: Minimum size to consider as a black bar
            
        Returns:
            Size of contiguous black region in pixels
        """
        count = 0
        for value in values:
            if value < threshold:
                count += 1
            else:
                break
        
        # Only return if meets minimum size requirement
        if count >= min_size:
            return count
        return 0
    
    def smooth_crop(self, new_crop: CropRegion, smoothing_factor: float = 0.3) -> CropRegion:
        """
        Smoothly transition between crop regions to avoid flickering.
        
        Args:
            new_crop: Newly detected crop region
            smoothing_factor: How much to blend (0.0 = no change, 1.0 = immediate)
            
        Returns:
            Smoothed crop region
        """
        if self._last_crop is None or smoothing_factor >= 1.0:
            return new_crop
        
        return CropRegion(
            top=int(self._last_crop.top * (1 - smoothing_factor) + new_crop.top * smoothing_factor),
            bottom=int(self._last_crop.bottom * (1 - smoothing_factor) + new_crop.bottom * smoothing_factor),
            left=int(self._last_crop.left * (1 - smoothing_factor) + new_crop.left * smoothing_factor),
            right=int(self._last_crop.right * (1 - smoothing_factor) + new_crop.right * smoothing_factor)
        )
