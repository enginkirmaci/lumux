"""RGB to XY color space conversion (simplified).

This module provides a minimal RGB->XY conversion without gamma
correction or gamut constraints. The function keeps the original
optional parameters for compatibility but ignores them.
"""

from typing import Tuple, Optional


def rgb_to_xy(r: int, g: int, b: int, light_info: Optional[dict] = None, gamut: Optional[dict] = None) -> Tuple[float, float]:
    """Convert RGB (0-255) to XY coordinates using a linear RGB assumption.

    Note: This version does not apply gamma correction and does not
    constrain the result to any color gamut. The `light_info` and
    `gamut` parameters are accepted for backward compatibility but are
    ignored.
    """
    # Normalize RGB to 0-1 range (no gamma correction)
    r_norm = r / 255.0
    g_norm = g / 255.0
    b_norm = b / 255.0

    # Convert to XYZ using sRGB matrix (linear RGB)
    X = r_norm * 0.664511 + g_norm * 0.154324 + b_norm * 0.162028
    Y = r_norm * 0.283881 + g_norm * 0.668433 + b_norm * 0.047685
    Z = r_norm * 0.000088 + g_norm * 0.072310 + b_norm * 0.986039

    total = X + Y + Z
    if total == 0:
        return (0.3227, 0.3290)

    x = X / total
    y = Y / total

    return (x, y)
