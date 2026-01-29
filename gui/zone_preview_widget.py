"""Zone preview widget with modern styling."""

import math

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk
import cairo


class ZonePreviewWidget(Gtk.DrawingArea):
    __gtype_name__ = 'ZonePreviewWidget'

    def __init__(self, rows: int = 8, cols: int = 8):
        super().__init__()
        self.rows = rows
        self.cols = cols
        self.zone_colors: dict = {}
        self.zone_ids: list[str] = []
        self._corner_radius = 12
        self._cell_gap = 2
        self._glow_enabled = True
        
        self.set_size_request(400, 300)
        self.set_draw_func(self._draw)

    def set_layout(self, rows: int = 16, cols: int = 16):
        """Update zone layout.

        Args:
            rows: Number of rows for ambilight layout
            cols: Number of columns for ambilight layout
        """
        self.rows = rows
        self.cols = cols
        self.zone_ids = self._generate_zone_ids()
        self.zone_colors = {}
        self.queue_draw()

    def _generate_zone_ids(self) -> list[str]:
        """Generate zone IDs for ambilight layout."""
        zones = []
        for i in range(self.cols):
            zones.append(f"top_{i}")
        for i in range(self.cols):
            zones.append(f"bottom_{i}")
        for i in range(self.rows):
            zones.append(f"left_{i}")
        for i in range(self.rows):
            zones.append(f"right_{i}")
        return zones

    def update_colors(self, zone_colors: dict):
        """Update zone colors and redraw.

        Args:
            zone_colors: Dictionary mapping zone IDs to RGB tuples
        """
        self.zone_colors = zone_colors
        self.queue_draw()

    def _draw(self, widget, ctx, width, height):
        """Draw zone grid with current colors."""
        # Draw background with rounded corners
        self._draw_rounded_rect(ctx, 0, 0, width, height, self._corner_radius)
        ctx.set_source_rgb(0.08, 0.08, 0.08)
        ctx.fill()
        
        self._draw_ambilight(ctx, width, height)

    def _draw_rounded_rect(self, ctx, x, y, width, height, radius):
        """Draw a rounded rectangle path."""
        degrees = math.pi / 180.0
        ctx.new_sub_path()
        ctx.arc(x + width - radius, y + radius, radius, -90 * degrees, 0 * degrees)
        ctx.arc(x + width - radius, y + height - radius, radius, 0 * degrees, 90 * degrees)
        ctx.arc(x + radius, y + height - radius, radius, 90 * degrees, 180 * degrees)
        ctx.arc(x + radius, y + radius, radius, 180 * degrees, 270 * degrees)
        ctx.close_path()

    def _draw_cell(self, ctx, x, y, w, h, rgb, corner_radius=6):
        """Draw a single cell with optional glow effect."""
        r, g, b = rgb[0]/255, rgb[1]/255, rgb[2]/255
        
        # Draw glow effect for bright colors
        if self._glow_enabled and (r > 0.3 or g > 0.3 or b > 0.3):
            brightness = (r + g + b) / 3
            glow_radius = 4 + brightness * 6
            
            # Outer glow
            for i in range(3):
                alpha = 0.1 * (1 - i/3) * brightness
                ctx.set_source_rgba(r, g, b, alpha)
                self._draw_rounded_rect(ctx, x - glow_radius + i*2, y - glow_radius + i*2, 
                                        w + glow_radius*2 - i*4, h + glow_radius*2 - i*4, 
                                        corner_radius + glow_radius - i*2)
                ctx.fill()
        
        # Main cell fill with gradient
        pattern = cairo.LinearGradient(x, y, x, y + h)
        pattern.add_color_stop_rgb(0, min(1, r * 1.2), min(1, g * 1.2), min(1, b * 1.2))
        pattern.add_color_stop_rgb(1, r * 0.85, g * 0.85, b * 0.85)
        
        self._draw_rounded_rect(ctx, x, y, w, h, corner_radius)
        ctx.set_source(pattern)
        ctx.fill()
        
        # Subtle border
        ctx.set_source_rgba(1, 1, 1, 0.1)
        self._draw_rounded_rect(ctx, x, y, w, h, corner_radius)
        ctx.set_line_width(0.5)
        ctx.stroke()

    def _draw_ambilight(self, ctx, width, height):
        """Draw ambilight layout with modern styling."""
        edge_thickness = min(36, height // 6)
        inner_padding = 4
        inner_width = width - 2 * edge_thickness - 2 * inner_padding
        inner_height = height - 2 * edge_thickness - 2 * inner_padding
        
        top_count = self.cols
        bottom_count = self.cols
        left_count = self.rows
        right_count = self.rows

        # Calculate zone sizes with gaps
        top_zone_width = (width - (top_count + 1) * self._cell_gap) / top_count
        bottom_zone_width = (width - (bottom_count + 1) * self._cell_gap) / bottom_count
        left_zone_height = (inner_height - (left_count - 1) * self._cell_gap) / left_count
        right_zone_height = (inner_height - (right_count - 1) * self._cell_gap) / right_count

        # Draw top zones
        for i in range(top_count):
            zone_id = f"top_{i}"
            rgb = self.zone_colors.get(zone_id, (30, 30, 30))
            
            x = self._cell_gap + i * (top_zone_width + self._cell_gap)
            y = self._cell_gap
            w = top_zone_width
            h = edge_thickness - self._cell_gap
            
            self._draw_cell(ctx, x, y, w, h, rgb)

        # Draw bottom zones
        for i in range(bottom_count):
            zone_id = f"bottom_{i}"
            rgb = self.zone_colors.get(zone_id, (30, 30, 30))
            
            x = self._cell_gap + i * (bottom_zone_width + self._cell_gap)
            y = height - edge_thickness
            w = bottom_zone_width
            h = edge_thickness - self._cell_gap
            
            self._draw_cell(ctx, x, y, w, h, rgb)

        # Draw left zones
        for i in range(left_count):
            zone_id = f"left_{i}"
            rgb = self.zone_colors.get(zone_id, (30, 30, 30))
            
            x = self._cell_gap
            y = edge_thickness + inner_padding + i * (left_zone_height + self._cell_gap)
            w = edge_thickness - self._cell_gap
            h = left_zone_height
            
            self._draw_cell(ctx, x, y, w, h, rgb)

        # Draw right zones
        for i in range(right_count):
            zone_id = f"right_{i}"
            rgb = self.zone_colors.get(zone_id, (30, 30, 30))
            
            x = width - edge_thickness
            y = edge_thickness + inner_padding + i * (right_zone_height + self._cell_gap)
            w = edge_thickness - self._cell_gap
            h = right_zone_height
            
            self._draw_cell(ctx, x, y, w, h, rgb)

        # Draw inner "screen" area with monitor bezel effect
        screen_x = edge_thickness + inner_padding
        screen_y = edge_thickness + inner_padding
        
        # Monitor bezel
        self._draw_rounded_rect(ctx, screen_x - 2, screen_y - 2, 
                                inner_width + 4, inner_height + 4, 8)
        ctx.set_source_rgb(0.15, 0.15, 0.15)
        ctx.fill()
        
        # Screen surface
        self._draw_rounded_rect(ctx, screen_x, screen_y, inner_width, inner_height, 6)
        
        # Create a subtle gradient for the screen
        pattern = cairo.LinearGradient(screen_x, screen_y, screen_x, screen_y + inner_height)
        pattern.add_color_stop_rgb(0, 0.06, 0.06, 0.08)
        pattern.add_color_stop_rgb(0.5, 0.04, 0.04, 0.06)
        pattern.add_color_stop_rgb(1, 0.02, 0.02, 0.04)
        ctx.set_source(pattern)
        ctx.fill()
        
        # Screen reflection highlight
        ctx.set_source_rgba(1, 1, 1, 0.02)
        self._draw_rounded_rect(ctx, screen_x, screen_y, inner_width, inner_height / 3, 6)
        ctx.fill()

