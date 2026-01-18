"""RGB to XY color space conversion for Philips Hue lights."""

import math
from typing import Tuple


def rgb_to_xy(r: int, g: int, b: int) -> Tuple[float, float]:
    """Convert RGB (0-255) to XY coordinates for Philips Hue.

    Args:
        r: Red component (0-255)
        g: Green component (0-255)
        b: Blue component (0-255)

    Returns:
        Tuple of (x, y) coordinates in CIE 1931 color space
    """
    # Normalize RGB to 0-1 range
    r_norm = r / 255.0
    g_norm = g / 255.0
    b_norm = b / 255.0

    # Apply gamma correction
    def gamma_correct(c: float) -> float:
        return (c / 12.92) if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r_gamma = gamma_correct(r_norm)
    g_gamma = gamma_correct(g_norm)
    b_gamma = gamma_correct(b_norm)

    # Convert to XYZ using sRGB matrix
    X = r_gamma * 0.664511 + g_gamma * 0.154324 + b_gamma * 0.162028
    Y = r_gamma * 0.283881 + g_gamma * 0.668433 + b_gamma * 0.047685
    Z = r_gamma * 0.000088 + g_gamma * 0.072310 + b_gamma * 0.986039

    # Calculate XY
    total = X + Y + Z
    if total == 0:
        return (0.3227, 0.3290)

    x = X / total
    y = Y / total

    return (x, y)


def get_color_gamut(light_info: dict) -> dict:
    """Retrieve color gamut from Hue light info.

    Args:
        light_info: Light metadata from Hue bridge

    Returns:
        Dictionary with 'red', 'green', 'blue' points
    """
    model = light_info.get('modelid', '')

    # Default to Gamut C (most common for recent bulbs)
    if 'LCT' in model:
        if model.startswith('LCT001') or model.startswith('LCT002') or model.startswith('LCT003'):
            return GAMUT_A
        elif model.startswith('LCT010') or model.startswith('LCT011') or model.startswith('LCT012'):
            return GAMUT_B
        else:
            return GAMUT_C
    elif 'LLC' in model:
        return GAMUT_A
    elif 'LST' in model:
        return GAMUT_A

    return GAMUT_C


# Color gamuts for different Hue light models
GAMUT_A = {
    'red': (0.704, 0.296),
    'green': (0.2151, 0.7106),
    'blue': (0.138, 0.08)
}

GAMUT_B = {
    'red': (0.675, 0.322),
    'green': (0.409, 0.518),
    'blue': (0.167, 0.04)
}

GAMUT_C = {
    'red': (0.6915, 0.3038),
    'green': (0.17, 0.7),
    'blue': (0.1532, 0.0475)
}


def constrain_to_gamut(x: float, y: float, gamut: dict) -> Tuple[float, float]:
    """Ensure XY coordinates are within light's color gamut.

    Args:
        x: X coordinate
        y: Y coordinate
        gamut: Gamut dictionary with red, green, blue points

    Returns:
        Tuple of constrained (x, y) coordinates
    """
    # Check if point is already within gamut
    if point_in_triangle(x, y, gamut['red'], gamut['green'], gamut['blue']):
        return (x, y)

    # Find closest point on triangle edges
    p1 = closest_point_on_line(gamut['red'], gamut['green'], (x, y))
    p2 = closest_point_on_line(gamut['green'], gamut['blue'], (x, y))
    p3 = closest_point_on_line(gamut['blue'], gamut['red'], (x, y))

    # Choose closest point
    d1 = distance((x, y), p1)
    d2 = distance((x, y), p2)
    d3 = distance((x, y), p3)

    if d1 <= d2 and d1 <= d3:
        return p1
    elif d2 <= d1 and d2 <= d3:
        return p2
    else:
        return p3


def point_in_triangle(px: float, py: float, 
                      p1: Tuple[float, float], 
                      p2: Tuple[float, float], 
                      p3: Tuple[float, float]) -> bool:
    """Check if point is inside triangle using barycentric coordinates."""
    def sign(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])

    d1 = sign((px, py), p1, p2)
    d2 = sign((px, py), p2, p3)
    d3 = sign((px, py), p3, p1)

    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)

    return not (has_neg and has_pos)


def closest_point_on_line(a: Tuple[float, float], 
                          b: Tuple[float, float],
                          p: Tuple[float, float]) -> Tuple[float, float]:
    """Find closest point on line segment AB to point P."""
    ap = (p[0] - a[0], p[1] - a[1])
    ab = (b[0] - a[0], b[1] - a[1])

    ab2 = ab[0] * ab[0] + ab[1] * ab[1]
    ap_ab = ap[0] * ab[0] + ap[1] * ab[1]

    t = ap_ab / ab2 if ab2 != 0 else 0
    t = max(0, min(1, t))

    return (a[0] + ab[0] * t, a[1] + ab[1] * t)


def distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Calculate Euclidean distance between two points."""
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)
