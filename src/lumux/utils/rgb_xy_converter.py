from typing import Tuple, Optional


def _srgb_to_linear(value: float) -> float:
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(value: float) -> float:
    if value <= 0.0031308:
        return 12.92 * value
    return 1.055 * (value ** (1.0 / 2.4)) - 0.055


def rgb_to_xy(
    r: int,
    g: int,
    b: int,
    light_info: Optional[dict] = None,
    gamut: Optional[dict] = None,
) -> Tuple[float, float]:
    r_norm = _srgb_to_linear(r / 255.0)
    g_norm = _srgb_to_linear(g / 255.0)
    b_norm = _srgb_to_linear(b / 255.0)

    X = r_norm * 0.4124564 + g_norm * 0.3575761 + b_norm * 0.1804375
    Y = r_norm * 0.2126729 + g_norm * 0.7151522 + b_norm * 0.0721750
    Z = r_norm * 0.0193339 + g_norm * 0.1191920 + b_norm * 0.9503041

    total = X + Y + Z
    if total == 0:
        return (0.3227, 0.3290)

    x = X / total
    y = Y / total

    if light_info and not gamut:
        gamut = light_info.get("gamut")

    if gamut:
        red = gamut.get("red")
        green = gamut.get("green")
        blue = gamut.get("blue")
        if _valid_point(red) and _valid_point(green) and _valid_point(blue):
            x, y = _constrain_to_gamut((x, y), red, green, blue)

    return (x, y)


def xy_to_rgb(x: float, y: float, as_int: bool = True) -> Tuple:
    """Convert CIE XY to RGB.

    Args:
        x: CIE x coordinate (0-1)
        y: CIE y coordinate (0-1)
        as_int: If True, return (R, G, B) as ints in 0-255 range.
                If False, return (r, g, b) as floats in 0-1 range.

    Returns:
        RGB tuple, either (int, int, int) in 0-255 or (float, float, float) in 0-1
    """
    if y == 0:
        return (255, 255, 255) if as_int else (1.0, 1.0, 1.0)

    Y = 1.0
    X = (x * Y) / y
    Z = ((1 - x - y) * Y) / y

    r = X * 3.2406 + Y * -1.5372 + Z * -0.4986
    g = X * -0.9689 + Y * 1.8758 + Z * 0.0415
    b = X * 0.0557 + Y * -0.2040 + Z * 1.0570

    r = _linear_to_srgb(r)
    g = _linear_to_srgb(g)
    b = _linear_to_srgb(b)

    r = max(0.0, min(1.0, r))
    g = max(0.0, min(1.0, g))
    b = max(0.0, min(1.0, b))

    if as_int:
        return (int(r * 255), int(g * 255), int(b * 255))
    return (r, g, b)


def _valid_point(point: Optional[dict]) -> bool:
    return isinstance(point, dict) and "x" in point and "y" in point


def _constrain_to_gamut(
    p: Tuple[float, float], r: dict, g: dict, b: dict
) -> Tuple[float, float]:
    pr = (float(r["x"]), float(r["y"]))
    pg = (float(g["x"]), float(g["y"]))
    pb = (float(b["x"]), float(b["y"]))

    if _point_in_triangle(p, pr, pg, pb):
        return p

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


def _point_in_triangle(
    p: Tuple[float, float],
    a: Tuple[float, float],
    b: Tuple[float, float],
    c: Tuple[float, float],
) -> bool:
    def sign(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])

    d1 = sign(p, a, b)
    d2 = sign(p, b, c)
    d3 = sign(p, c, a)

    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)

    return not (has_neg and has_pos)


def _closest_point_on_segment(
    a: Tuple[float, float], b: Tuple[float, float], p: Tuple[float, float]
) -> Tuple[float, float]:
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
