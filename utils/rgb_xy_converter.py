"""RGB to XY color space conversion (simplified).

This module provides a minimal RGB->XY conversion without gamma
correction or gamut constraints. The function keeps the original
optional parameters for compatibility but ignores them.
"""

from typing import Tuple, Optional


def rgb_to_xy(r: int, g: int, b: int, light_info: Optional[dict] = None, gamut: Optional[dict] = None) -> Tuple[float, float]:
    """Convert RGB (0-255) to XY coordinates using a linear RGB assumption.

    Note: This version does not apply gamma correction. If `gamut` or
    `light_info` provides gamut points, the result is constrained to the
    triangle defined by the light's RGB gamut.
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

    if light_info and not gamut:
        gamut = light_info.get('gamut')

    if gamut:
        red = gamut.get('red')
        green = gamut.get('green')
        blue = gamut.get('blue')
        if _valid_point(red) and _valid_point(green) and _valid_point(blue):
            x, y = _constrain_to_gamut((x, y), red, green, blue)

    return (x, y)


def _valid_point(point: Optional[dict]) -> bool:
    return isinstance(point, dict) and 'x' in point and 'y' in point


def _constrain_to_gamut(p: Tuple[float, float],
                        r: dict, g: dict, b: dict) -> Tuple[float, float]:
    pr = (float(r['x']), float(r['y']))
    pg = (float(g['x']), float(g['y']))
    pb = (float(b['x']), float(b['y']))

    if _point_in_triangle(p, pr, pg, pb):
        return p

    # Find closest point on triangle edges
    p_rg = _closest_point_on_segment(pr, pg, p)
    p_gb = _closest_point_on_segment(pg, pb, p)
    p_br = _closest_point_on_segment(pb, pr, p)

    dist_rg = _distance(p, p_rg)
    dist_gb = _distance(p, p_gb)
    dist_br = _distance(p, p_br)

    if dist_rg <= dist_gb and dist_rg <= dist_br:
        return p_rg
    if dist_gb <= dist_br:
        return p_gb
    return p_br


def _point_in_triangle(p: Tuple[float, float],
                       a: Tuple[float, float],
                       b: Tuple[float, float],
                       c: Tuple[float, float]) -> bool:
    def sign(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])

    d1 = sign(p, a, b)
    d2 = sign(p, b, c)
    d3 = sign(p, c, a)

    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)

    return not (has_neg and has_pos)


def _closest_point_on_segment(a: Tuple[float, float],
                              b: Tuple[float, float],
                              p: Tuple[float, float]) -> Tuple[float, float]:
    ax, ay = a
    bx, by = b
    px, py = p

    abx = bx - ax
    aby = by - ay
    ab_len_sq = abx * abx + aby * aby
    if ab_len_sq == 0:
        return a

    t = ((px - ax) * abx + (py - ay) * aby) / ab_len_sq
    t = max(0.0, min(1.0, t))
    return (ax + abx * t, ay + aby * t)


def _distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5
