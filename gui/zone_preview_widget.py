"""Zone preview widget for GUI."""

import math

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


class ZonePreviewWidget(Gtk.DrawingArea):
    __gtype_name__ = 'ZonePreviewWidget'

    def __init__(self, rows: int = 8, cols: int = 8):
        super().__init__()
        self.rows = rows
        self.cols = cols
        self.layout = "grid"
        self.zone_colors: dict = {}
        self.zone_ids: list[str] = []
        
        self.set_size_request(400, 300)
        self.set_draw_func(self._draw)

    def set_layout(self, layout: str, rows: int = 16, cols: int = 16):
        """Update zone layout.

        Args:
            layout: 'grid' or 'ambilight'
            rows: Number of rows for grid layout
            cols: Number of columns for grid/ambilight layout
        """
        self.layout = layout.lower()
        self.rows = rows
        self.cols = cols
        self.zone_ids = self._generate_zone_ids()
        self.zone_colors = {}
        self.queue_draw()

    def _generate_zone_ids(self) -> list[str]:
        """Generate zone IDs based on current layout."""
        if self.layout == "ambilight":
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
        else:
            return [str(i) for i in range(self.rows * self.cols)]

    def update_colors(self, zone_colors: dict):
        """Update zone colors and redraw.

        Args:
            zone_colors: Dictionary mapping zone IDs to RGB tuples
        """
        self.zone_colors = zone_colors
        self.queue_draw()

    def _draw(self, widget, ctx, width, height):
        """Draw zone grid with current colors."""
        if self.layout == "ambilight":
            self._draw_ambilight(ctx, width, height)
        else:
            self._draw_grid(ctx, width, height)

    def _draw_grid(self, ctx, width, height):
        """Draw standard grid layout."""
        cell_width = width / self.cols
        cell_height = height / self.rows

        for row in range(self.rows):
            for col in range(self.cols):
                zone_id = str(row * self.cols + col)
                rgb = self.zone_colors.get(zone_id, (50, 50, 50))
                
                x = col * cell_width
                y = row * cell_height
                
                ctx.set_source_rgb(rgb[0]/255, rgb[1]/255, rgb[2]/255)
                ctx.rectangle(x, y, cell_width, cell_height)
                ctx.fill_preserve()
                
                ctx.set_source_rgb(0, 0, 0)
                ctx.set_line_width(0.5)
                ctx.stroke()

    def _draw_ambilight(self, ctx, width, height):
        """Draw ambilight layout (borders only)."""
        edge_thickness = min(30, height // 8)
        inner_width = width - 2 * edge_thickness
        inner_height = height - 2 * edge_thickness
        
        top_count = self.cols
        bottom_count = self.cols
        left_count = self.rows
        right_count = self.rows

        top_zone_width = width / top_count
        bottom_zone_width = width / bottom_count
        left_zone_height = inner_height / left_count
        right_zone_height = inner_height / right_count

        idx = 0

        for i in range(top_count):
            zone_id = f"top_{i}"
            rgb = self.zone_colors.get(zone_id, (50, 50, 50))
            
            x = i * top_zone_width
            y = 0
            w = top_zone_width
            h = edge_thickness
            
            ctx.set_source_rgb(rgb[0]/255, rgb[1]/255, rgb[2]/255)
            ctx.rectangle(x, y, w, h)
            ctx.fill_preserve()
            
            ctx.set_source_rgb(0, 0, 0)
            ctx.set_line_width(0.5)
            ctx.stroke()

        for i in range(bottom_count):
            zone_id = f"bottom_{i}"
            rgb = self.zone_colors.get(zone_id, (50, 50, 50))
            
            x = i * bottom_zone_width
            y = height - edge_thickness
            w = bottom_zone_width
            h = edge_thickness
            
            ctx.set_source_rgb(rgb[0]/255, rgb[1]/255, rgb[2]/255)
            ctx.rectangle(x, y, w, h)
            ctx.fill_preserve()
            
            ctx.set_source_rgb(0, 0, 0)
            ctx.set_line_width(0.5)
            ctx.stroke()

        for i in range(left_count):
            zone_id = f"left_{i}"
            rgb = self.zone_colors.get(zone_id, (50, 50, 50))
            
            x = 0
            y = edge_thickness + i * left_zone_height
            w = edge_thickness
            h = left_zone_height
            
            ctx.set_source_rgb(rgb[0]/255, rgb[1]/255, rgb[2]/255)
            ctx.rectangle(x, y, w, h)
            ctx.fill_preserve()
            
            ctx.set_source_rgb(0, 0, 0)
            ctx.set_line_width(0.5)
            ctx.stroke()

        for i in range(right_count):
            zone_id = f"right_{i}"
            rgb = self.zone_colors.get(zone_id, (50, 50, 50))
            
            x = width - edge_thickness
            y = edge_thickness + i * right_zone_height
            w = edge_thickness
            h = right_zone_height
            
            ctx.set_source_rgb(rgb[0]/255, rgb[1]/255, rgb[2]/255)
            ctx.rectangle(x, y, w, h)
            ctx.fill_preserve()
            
            ctx.set_source_rgb(0, 0, 0)
            ctx.set_line_width(0.5)
            ctx.stroke()

        ctx.set_source_rgb(0.1, 0.1, 0.1)
        ctx.rectangle(edge_thickness, edge_thickness, inner_width, inner_height)
        ctx.fill()
