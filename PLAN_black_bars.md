# Feature Plan: Ignore Black Letterbox / Pillarbox Areas

## Overview
Detect and exclude black bars (letterbox/pillarbox) during video playback so ambient lighting reflects actual picture content, not black bars.

## Problem
When watching widescreen movies (2.39:1) on 16:9 displays, black bars appear at top/bottom. Current zone averaging includes these black pixels, resulting in dim/wrong colors for edge zones.

## Solution Approach

### Phase 1: Detection Algorithm (2 days)

**1.1 Per-frame Black Bar Detection**
- Analyze each captured frame to detect contiguous low-brightness bands
- Compute row-wise and column-wise mean luminance
- Identify bands where mean brightness < threshold (default: 10/255)
- Require minimum region size (e.g., 5% of frame dimension) to avoid false positives

**1.2 Edge Mask Building**
```python
# Pseudocode
def detect_black_bars(image_array, threshold=10, min_size_percent=5):
    height, width = image_array.shape[:2]
    min_size = int(min(height, width) * min_size_percent / 100)
    
    # Convert to grayscale luminance
    gray = np.dot(image_array[...,:3], [0.299, 0.587, 0.114])
    
    # Row-wise (horizontal bands - letterbox)
    row_means = np.mean(gray, axis=1)
    top_crop = find_contiguous_below_threshold(row_means, threshold, min_size)
    bottom_crop = find_contiguous_below_threshold(row_means[::-1], threshold, min_size)
    
    # Column-wise (vertical bands - pillarbox)
    col_means = np.mean(gray, axis=0)
    left_crop = find_contiguous_below_threshold(col_means, threshold, min_size)
    right_crop = find_contiguous_below_threshold(col_means[::-1], threshold, min_size)
    
    return CropRegion(top_crop, bottom_crop, left_crop, right_crop)
```

### Phase 2: Configuration & Settings (1 day)

**2.1 New Settings in `ZoneSettings`**
```python
@dataclass
class ZoneSettings:
    show_preview: bool = True
    rows: int = 16
    cols: int = 16
    ignore_black_bars: bool = True          # NEW
    black_bar_threshold: int = 10            # NEW: 0-255, default 10
    min_black_bar_size: int = 5              # NEW: percent, default 5%
    force_ignore_top: bool = False           # NEW: manual override
    force_ignore_bottom: bool = False        # NEW: manual override
    force_ignore_left: bool = False          # NEW: manual override
    force_ignore_right: bool = False         # NEW: manual override
```

**2.2 UI Controls in SettingsDialog**
- Master toggle: "Ignore black bars (letterbox/pillarbox)"
- Sensitivity slider: "Detection threshold" (0-50)
- Minimum size slider: "Minimum bar size" (1-20%)
- Manual overrides: 4 switches for force-ignore edges

### Phase 3: Zone Processing Integration (1 day)

**3.1 Modify `ZoneProcessor.process_image()`**
```python
def process_image(self, image: Image.Image, crop_region: Optional[CropRegion] = None) -> Dict[str, RGB]:
    if self.settings.ignore_black_bars and crop_region:
        effective_image = self._apply_crop(image, crop_region)
    else:
        effective_image = image
    return self._process_ambilight(effective_image)
```

**3.2 Real-time Crop Detection in Sync Loop**
- Run detection every N frames (e.g., every 30 frames = ~2s at 15fps) to save CPU
- Smooth transitions between detected crops (avoid flickering)
- Fallback to full frame if detection fails or variance is too high

### Phase 4: Visual Feedback (Optional, 1 day)

**4.1 Zone Preview Enhancement**
- Show detected crop region as overlay on zone preview
- Indicate which zones are being excluded with dimmed/hatched appearance

## Files to Modify

1. **config/settings_manager.py**
   - Add black bar settings to `ZoneSettings`
   - Add validation for new settings

2. **lumux/black_bar_detector.py** (NEW FILE)
   - `BlackBarDetector` class with detection algorithm
   - `CropRegion` dataclass for storing crop values

3. **lumux/zones.py**
   - Modify `ZoneProcessor` to accept and apply crop regions
   - Add `_apply_crop()` method

4. **lumux/sync.py**
   - Integrate black bar detection into sync loop
   - Run periodically and smooth transitions

5. **gui/settings_dialog.py**
   - Add new page: "Black Bar Detection"
   - Add all UI controls for configuration

6. **gui/zone_preview_widget.py**
   - (Optional) Show crop region overlay

## Testing Strategy

1. **Test videos:**
   - 2.39:1 movie (top/bottom bars)
   - 4:3 content on 16:9 (left/right bars)
   - Mixed content (switching between aspect ratios)
   - Dark scenes (potential false positives)

2. **Validation:**
   - Zone colors should ignore black bars
   - Smooth transitions when aspect ratio changes
   - No false positives on dark but non-black content

## Implementation Notes

- Use numpy for fast row/column mean calculations
- Consider frame-to-frame smoothing to avoid jitter
- Detection should be fast enough to not impact sync FPS
- Provide manual override for edge cases (some movies have creative black bars)

## Effort Estimate
- Phase 1: 2 days
- Phase 2: 1 day  
- Phase 3: 1 day
- Phase 4: 1 day (optional)
**Total: 4-5 days (or 3-4 days without Phase 4)**
