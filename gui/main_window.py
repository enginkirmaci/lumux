"""Main application window with modern Adwaita styling."""

import os
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GLib, Adw, Gdk, Gio, GdkPixbuf
from lumux.app_context import AppContext
from lumux.mode_manager import Mode
from gui.settings_dialog import SettingsDialog
from gui.zone_preview_widget import ZonePreviewWidget
from gui.tray_icon import TrayIcon

# App icon path
APP_ICON_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "io.github.enginkirmaci.lumux.svg")


class MainWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'LumuxMainWindow'

    def __init__(self, app, app_context: AppContext):
        super().__init__(application=app)
        self.app_context = app_context
        self.sync_controller = app_context.sync_controller
        self.mode_manager = app_context.mode_manager
        self.settings = app_context.settings
        self.bridge_connected = False
        self._current_mode = Mode.OFF
        # Window size presets
        self._preview_size = (800, 700)
        self._compact_size = (500, 500)
        # Reading mode now uses same size as video mode for consistency
        self._reading_mode_size = (800, 700)
        
        # System tray icon
        self._tray_icon = None
        
        # Brightness slider debounce timer
        self._brightness_timeout_id = None

        # Connect mode change callback
        self.mode_manager.set_mode_changed_callback(self._on_mode_changed)

        self._setup_app_icon()
        self._setup_css()
        self._build_ui()
        self._setup_tray_icon()
        # Run an initial bridge connection check so UI reflects state
        self._check_bridge_connection()

        self.status_timeout_id = GLib.timeout_add(100, self._update_status)
    
    def _setup_app_icon(self):
        """Set up the window icon."""
        if os.path.exists(APP_ICON_PATH):
            try:
                # Load and set window icon
                texture = Gdk.Texture.new_from_filename(APP_ICON_PATH)
                # For GTK4, we need to use paintable for window icon
                # Store for use in about dialog
                self._app_icon_file = Gio.File.new_for_path(APP_ICON_PATH)
            except Exception as e:
                print(f"Warning: Could not load app icon: {e}")
                self._app_icon_file = None
        else:
            self._app_icon_file = None
    
    def _setup_tray_icon(self):
        """Set up the system tray icon."""
        try:
            self._tray_icon = TrayIcon(self.get_application(), self)
            if not self._tray_icon.is_available:
                self._tray_icon = None
        except Exception as e:
            print(f"Note: System tray not available: {e}")
            self._tray_icon = None

    def _setup_css(self):
        """Apply custom CSS styling."""
        css_provider = Gtk.CssProvider()
        css_provider.load_from_string("""
            .status-card {
                padding: 16px;
                border-radius: 12px;
            }
            .status-connected {
                background: alpha(@success_color, 0.1);
                border: 1px solid alpha(@success_color, 0.3);
            }
            .status-disconnected {
                background: alpha(@warning_color, 0.1);
                border: 1px solid alpha(@warning_color, 0.3);
            }
            .status-syncing {
                background: linear-gradient(135deg, alpha(@accent_color, 0.15), alpha(@purple_3, 0.15));
                border: 1px solid alpha(@accent_color, 0.4);
            }
            .status-reading {
                background: alpha(@yellow_3, 0.15);
                border: 1px solid alpha(@yellow_3, 0.4);
            }
            .preview-card {
                background: alpha(@card_bg_color, 0.8);
                padding: 8px;
                border-radius: 10px;
            }
            .control-button {
                padding: 12px 32px;
                font-weight: bold;
                font-size: 14px;
            }
            .stats-label {
                font-size: 12px;
                font-weight: 600;
                letter-spacing: 0.5px;
                opacity: 0.7;
            }
            .stats-value {
                font-size: 24px;
                font-weight: 700;
            }
            .info-banner {
                background: alpha(@accent_color, 0.1);
                padding: 12px 16px;
            }
            .main-title {
                font-size: 13px;
                font-weight: 600;
                letter-spacing: 0.5px;
                opacity: 0.6;
            }
            .mode-toggle {
                background: alpha(@card_bg_color, 0.6);
                border-radius: 24px;
                padding: 4px;
            }
            .reading-controls {
                background: alpha(@card_bg_color, 0.6);
                border-radius: 16px;
                padding: 24px;
            }
            .reading-preset-btn {
                min-width: 48px;
                min-height: 48px;
                border-radius: 24px;
                padding: 0;
                margin: 4px;
            }
            .reading-preset-btn:hover {
                box-shadow: 0 0 0 3px alpha(@accent_color, 0.5);
            }
            .reading-preset-active {
                box-shadow: 0 0 0 3px @accent_color;
            }
            .reading-label {
                font-weight: 600;
                font-size: 14px;
            }
            .reading-value-label {
                font-feature-settings: "tnum";
                min-width: 40px;
                font-weight: 600;
                opacity: 0.8;
            }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _build_ui(self):
        """Build main window layout with modern Adwaita design."""
        self.set_title("Lumux")

        # Header bar with modern styling
        header = Adw.HeaderBar()
        header.set_centering_policy(Adw.CenteringPolicy.STRICT)
        
        # Settings button with icon
        settings_btn = Gtk.Button()
        settings_btn.set_icon_name("emblem-system-symbolic")
        settings_btn.set_tooltip_text("Settings")
        settings_btn.add_css_class("flat")
        settings_btn.connect("clicked", self._on_settings_clicked)
        header.pack_end(settings_btn)
        
        # About button
        about_btn = Gtk.Button()
        about_btn.set_icon_name("help-about-symbolic")
        about_btn.set_tooltip_text("About Lumux")
        about_btn.add_css_class("flat")
        about_btn.connect("clicked", self._on_about_clicked)
        header.pack_end(about_btn)

        # Main content with toolbar view
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        self.set_content(toolbar_view)

        # Scrollable content
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        toolbar_view.set_content(scrolled)

        # Main clamp for content width
        clamp = Adw.Clamp()
        clamp.set_maximum_size(800)
        clamp.set_tightening_threshold(600)
        scrolled.set_child(clamp)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        clamp.set_child(main_box)

        # Status card
        self.status_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.status_card.add_css_class("status-card")
        self.status_card.add_css_class("status-disconnected")
        
        # Status header with icon
        status_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.status_icon = Gtk.Image.new_from_icon_name("network-offline-symbolic")
        self.status_icon.set_pixel_size(24)
        status_header.append(self.status_icon)
        
        status_text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.status_label = Gtk.Label(label="Ready")
        self.status_label.set_xalign(0)
        self.status_label.add_css_class("title-3")
        status_text_box.append(self.status_label)
        
        self.status_subtitle = Gtk.Label(label="Connect to your Hue bridge to get started")
        self.status_subtitle.set_xalign(0)
        self.status_subtitle.add_css_class("dim-label")
        status_text_box.append(self.status_subtitle)
        status_text_box.set_hexpand(True)
        status_header.append(status_text_box)

        # Stats box (placed to the right in the header)
        self.stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self.stats_box.set_halign(Gtk.Align.END)
        self.stats_box.set_valign(Gtk.Align.CENTER)
        self.stats_box.set_visible(False)

        # FPS stat
        fps_stat = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        fps_label = Gtk.Label(label="FPS")
        fps_label.add_css_class("stats-label")
        fps_stat.append(fps_label)
        self.fps_value = Gtk.Label(label="0")
        self.fps_value.add_css_class("stats-value")
        fps_stat.append(self.fps_value)
        self.stats_box.append(fps_stat)

        # Frames stat
        frames_stat = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        frames_label = Gtk.Label(label="FRAMES")
        frames_label.add_css_class("stats-label")
        frames_stat.append(frames_label)
        self.frames_value = Gtk.Label(label="0")
        self.frames_value.add_css_class("stats-value")
        frames_stat.append(self.frames_value)
        self.stats_box.append(frames_stat)

        # Add stats box into the header so it appears to the right
        status_header.append(self.stats_box)

        # Button to open bridge settings when disconnected (placed in header)
        self.open_bridge_settings_btn = Gtk.Button()
        self.open_bridge_settings_btn.set_label("Open Bridge Settings")
        self.open_bridge_settings_btn.add_css_class("flat")
        self.open_bridge_settings_btn.connect("clicked", self._on_settings_clicked)
        self.open_bridge_settings_btn.set_halign(Gtk.Align.END)
        self.open_bridge_settings_btn.set_valign(Gtk.Align.CENTER)
        self.open_bridge_settings_btn.set_visible(False)
        status_header.append(self.open_bridge_settings_btn)

        self.status_card.append(status_header)
        main_box.append(self.status_card)

        # Mode toggle (Video / Reading) - moved under status for video mode
        self.mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.mode_box.add_css_class("mode-toggle")
        self.mode_box.set_halign(Gtk.Align.CENTER)
        self.mode_box.set_margin_top(8)
        
        self.video_mode_btn = Gtk.ToggleButton()
        self.video_mode_btn.set_label("Video Mode")
        self.video_mode_btn.set_size_request(120, 40)
        self.video_mode_btn.connect("toggled", self._on_video_mode_toggled)
        self.mode_box.append(self.video_mode_btn)
        
        self.reading_mode_btn = Gtk.ToggleButton()
        self.reading_mode_btn.set_label("Reading Mode")
        self.reading_mode_btn.set_size_request(120, 40)
        self.reading_mode_btn.set_group(self.video_mode_btn)
        self.reading_mode_btn.connect("toggled", self._on_reading_mode_toggled)
        self.mode_box.append(self.reading_mode_btn)
        
        main_box.append(self.mode_box)

        # Zone preview section
        self.preview_group = Adw.PreferencesGroup()
        self.preview_group.set_title("Zone Preview")
        self.preview_group.set_description("Real-time visualization of screen zones")
        
        preview_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        preview_card.add_css_class("preview-card")
        
        # Initialize preview with configured layout
        self.zone_preview = ZonePreviewWidget(rows=self.settings.zones.rows,
                              cols=self.settings.zones.cols)
        self.zone_preview.set_layout(self.settings.zones.rows, self.settings.zones.cols)
        self.zone_preview.set_size_request(-1, 250)
        preview_card.append(self.zone_preview)
        
        self.preview_group.add(preview_card)
        self.preview_group.set_visible(self.settings.zones.show_preview)
        main_box.append(self.preview_group)

        # Control section
        control_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        
        # Video mode controls (Start/Stop button)
        self.video_controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        
        self.sync_button = Gtk.Button()
        self.sync_button.add_css_class("control-button")
        self.sync_button.add_css_class("suggested-action")
        self.sync_button.add_css_class("pill")
        
        self.sync_button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.sync_button_box.set_halign(Gtk.Align.CENTER)
        self.sync_icon = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
        self.sync_label = Gtk.Label(label="Start Sync")
        self.sync_button_box.append(self.sync_icon)
        self.sync_button_box.append(self.sync_label)
        self.sync_button.set_child(self.sync_button_box)
        
        self.sync_button.connect("clicked", self._on_sync_toggle)
        self.sync_button.set_halign(Gtk.Align.CENTER)
        self.sync_button.set_size_request(200, 48)
        self.video_controls.append(self.sync_button)
        control_box.append(self.video_controls)
        
        # Reading mode controls container
        self.reading_controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        
        # Quick Presets card
        presets_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        presets_card.add_css_class("reading-controls")
        
        # Preset colors section
        presets_title = Gtk.Label(label="Quick Presets")
        presets_title.add_css_class("reading-label")
        presets_title.set_halign(Gtk.Align.START)
        presets_card.append(presets_title)
        
        # Preset color buttons row
        presets_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        presets_box.set_halign(Gtk.Align.CENTER)
        
        # Define preset colors: (name, hex_color, tooltip)
        self._reading_presets = [
            ("warm_white", "#FFD6A5", "Warm White (2700K)"),
            ("cool_white", "#F0F4FF", "Cool White (4000K)"),
            ("daylight", "#FFFEF0", "Daylight (6500K)"),
            ("candle", "#FF9B50", "Candlelight"),
            ("sunset", "#FF7B7B", "Sunset"),
            ("relax", "#A78BFA", "Relax"),
            ("focus", "#60A5FA", "Focus"),
            ("reading", "#34D399", "Reading"),
        ]
        self._preset_buttons = {}
        
        for preset_id, hex_color, tooltip in self._reading_presets:
            btn = Gtk.Button()
            btn.add_css_class("reading-preset-btn")
            btn.set_tooltip_text(tooltip)
            
            # Create color swatch using a drawing area
            swatch = Gtk.Box()
            swatch.set_size_request(40, 40)
            swatch.set_margin_start(4)
            swatch.set_margin_end(4)
            swatch.set_margin_top(4)
            swatch.set_margin_bottom(4)
            
            # Apply color via CSS
            css_provider = Gtk.CssProvider()
            css_provider.load_from_string(f"""
                box {{
                    background-color: {hex_color};
                    border-radius: 20px;
                }}
            """)
            swatch.get_style_context().add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            
            btn.set_child(swatch)
            btn.connect("clicked", self._on_preset_clicked, preset_id, hex_color)
            presets_box.append(btn)
            self._preset_buttons[preset_id] = btn
        
        presets_card.append(presets_box)
        self.reading_controls.append(presets_card)
        
        # Custom Settings card
        custom_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        custom_card.add_css_class("reading-controls")
        
        # Custom Settings title
        custom_title = Gtk.Label(label="Custom Settings")
        custom_title.add_css_class("reading-label")
        custom_title.set_halign(Gtk.Align.START)
        custom_card.append(custom_title)
        
        # Custom color and brightness in one row
        controls_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        controls_row.set_halign(Gtk.Align.CENTER)
        
        # Custom color
        color_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        color_label = Gtk.Label(label="Color")
        color_label.add_css_class("reading-label")
        color_box.append(color_label)
        
        self.color_btn = Gtk.ColorDialogButton()
        color_dialog = Gtk.ColorDialog()
        color_dialog.set_title("Select Reading Light Color")
        self.color_btn.set_dialog(color_dialog)
        # Set default from settings or warm white
        rgba = Gdk.RGBA()
        default_xy = self.settings.reading_mode.color_xy
        default_rgb = self._xy_to_rgb(default_xy[0], default_xy[1])
        rgba.parse(f"#{default_rgb[0]:02x}{default_rgb[1]:02x}{default_rgb[2]:02x}")
        self.color_btn.set_rgba(rgba)
        self.color_btn.connect("notify::rgba", self._on_color_changed)
        color_box.append(self.color_btn)
        controls_row.append(color_box)
        
        # Brightness
        brightness_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        brightness_label = Gtk.Label(label="Brightness")
        brightness_label.add_css_class("reading-label")
        brightness_box.append(brightness_label)
        
        self.brightness_value_label = Gtk.Label(label=str(self.settings.reading_mode.brightness))
        self.brightness_value_label.add_css_class("reading-value-label")
        brightness_box.append(self.brightness_value_label)
        
        self.brightness_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL)
        self.brightness_scale.set_range(0, 254)
        self.brightness_scale.set_value(self.settings.reading_mode.brightness)
        self.brightness_scale.set_size_request(180, -1)
        self.brightness_scale.set_draw_value(False)
        self.brightness_scale.connect("value-changed", self._on_brightness_changed)
        brightness_box.append(self.brightness_scale)
        controls_row.append(brightness_box)
        
        custom_card.append(controls_row)
        

        
        self.reading_controls.append(custom_card)
        
        self.reading_controls.set_visible(False)
        control_box.append(self.reading_controls)

        main_box.append(control_box)

        # Apply initial window sizing based on mode and preview setting
        self._apply_window_size()

    def _update_sync_button_state(self, is_syncing: bool):
        """Update sync button appearance based on state."""
        self.sync_button.remove_css_class("suggested-action")
        self.sync_button.remove_css_class("destructive-action")

        if is_syncing:
            self.sync_icon.set_from_icon_name("media-playback-stop-symbolic")
            self.sync_label.set_label("Stop Sync")
            self.sync_button.add_css_class("destructive-action")
        else:
            self.sync_icon.set_from_icon_name("media-playback-start-symbolic")
            self.sync_label.set_label("Start Sync")
            self.sync_button.add_css_class("suggested-action")
        
        # Update tray icon status
        if self._tray_icon:
            self._tray_icon.update_sync_status(is_syncing)

    def _update_status_card(self, state: str):
        """Update status card styling based on connection state."""
        self.status_card.remove_css_class("status-connected")
        self.status_card.remove_css_class("status-disconnected")
        self.status_card.remove_css_class("status-syncing")
        self.status_card.remove_css_class("status-reading")
        
        if state == "syncing":
            self.status_card.add_css_class("status-syncing")
            self.status_icon.set_from_icon_name("emblem-synchronizing-symbolic")
        elif state == "reading":
            self.status_card.add_css_class("status-reading")
            self.status_icon.set_from_icon_name("weather-clear-night-symbolic")
        elif state == "connected":
            self.status_card.add_css_class("status-connected")
            self.status_icon.set_from_icon_name("network-transmit-receive-symbolic")
        else:
            self.status_card.add_css_class("status-disconnected")
            self.status_icon.set_from_icon_name("network-offline-symbolic")

    def _on_video_mode_toggled(self, button):
        """Handle video mode button toggle."""
        if button.get_active():
            self._switch_to_video_mode()

    def _on_reading_mode_toggled(self, button):
        """Handle reading mode button toggle."""
        if button.get_active():
            self._switch_to_reading_mode()

    def _switch_to_video_mode(self):
        """Switch UI to video mode."""
        self.video_controls.set_visible(True)
        self.reading_controls.set_visible(False)
        self.preview_group.set_visible(self.settings.zones.show_preview)
        self.stats_box.set_visible(True)
        self._apply_window_size()

    def _switch_to_reading_mode(self):
        """Switch UI to reading mode."""
        self.video_controls.set_visible(False)
        self.reading_controls.set_visible(True)
        self.preview_group.set_visible(False)  # No preview in reading mode
        self.stats_box.set_visible(False)
        self._apply_window_size()

    def _on_mode_changed(self, mode: Mode):
        """Called when mode manager changes mode."""
        self._current_mode = mode
        
        if mode == Mode.VIDEO:
            self.video_mode_btn.set_active(True)
            self.status_label.set_text("Video Mode")
            self.status_subtitle.set_text("Syncing screen colors to lights")
            self._update_status_card("syncing")
            self._switch_to_video_mode()
        elif mode == Mode.READING:
            self.reading_mode_btn.set_active(True)
            self.status_label.set_text("Reading Mode")
            self.status_subtitle.set_text("Static lighting active")
            self._update_status_card("reading")
            self._update_sync_button_state(False)  # Sync is not running in reading mode
            self.sync_button.set_sensitive(True)
        else:  # OFF
            self._update_sync_button_state(False)
            self.sync_button.set_sensitive(True)
            if self.video_mode_btn.get_active():
                self.status_label.set_text("Ready")
                self.status_subtitle.set_text("Select a mode to begin")
                self._update_status_card("connected")
            else:
                self.status_label.set_text("Ready")
                self.status_subtitle.set_text("Select a mode to begin")
                self._update_status_card("connected")

    def _on_color_changed(self, button, param):
        """Handle color picker change - auto-apply."""
        self._apply_reading_settings()

    def _on_brightness_changed(self, scale):
        """Handle brightness slider change - debounced auto-apply."""
        # Update the value label immediately for visual feedback
        if hasattr(self, 'brightness_value_label'):
            self.brightness_value_label.set_text(str(int(scale.get_value())))
        
        # Debounce: cancel existing timer and start new one
        if self._brightness_timeout_id:
            GLib.source_remove(self._brightness_timeout_id)
            self._brightness_timeout_id = None
        
        # Schedule apply after 150ms of no changes (user released slider)
        self._brightness_timeout_id = GLib.timeout_add(150, self._on_brightness_change_done)
    
    def _on_preset_clicked(self, button, preset_id: str, hex_color: str):
        """Handle preset color button click."""
        # Update color button
        rgba = Gdk.RGBA()
        rgba.parse(hex_color)
        self.color_btn.set_rgba(rgba)
        
        # Clear active state from all presets
        for btn in self._preset_buttons.values():
            btn.remove_css_class("reading-preset-active")
        
        # Add active state to clicked preset
        button.add_css_class("reading-preset-active")
        
        # Auto-apply the preset
        self._apply_reading_settings()
    
    def _xy_to_rgb(self, x: float, y: float) -> tuple:
        """Convert CIE XY to approximate RGB for color picker initialization.
        
        This is a simplified inverse of the RGB to XY conversion.
        """
        # Avoid division by zero
        if y == 0:
            return (255, 255, 255)
        
        # Convert xy to XYZ (assume Y=1 for brightness)
        Y = 1.0
        X = (x * Y) / y
        Z = ((1 - x - y) * Y) / y
        
        # XYZ to RGB matrix (sRGB D65)
        r = X *  3.2406 + Y * -1.5372 + Z * -0.4986
        g = X * -0.9689 + Y *  1.8758 + Z *  0.0415
        b = X *  0.0557 + Y * -0.2040 + Z *  1.0570
        
        # Apply gamma correction (inverse)
        def gamma_correct(c):
            if c > 0.0031308:
                return 1.055 * (c ** (1.0 / 2.4)) - 0.055
            else:
                return 12.92 * c
        
        r = gamma_correct(r)
        g = gamma_correct(g)
        b = gamma_correct(b)
        
        # Clamp and convert to 0-255
        r = max(0, min(1, r))
        g = max(0, min(1, g))
        b = max(0, min(1, b))
        
        return (int(r * 255), int(g * 255), int(b * 255))

    def _on_brightness_change_done(self):
        """Called when brightness slider change is complete (debounced)."""
        self._brightness_timeout_id = None
        self._apply_reading_settings()
        return False  # Don't repeat
    
    def _apply_reading_settings(self):
        """Apply reading mode settings automatically when changed."""
        rgba = self.color_btn.get_rgba()
        brightness = int(self.brightness_scale.get_value())
        
        # Convert RGB to XY color space (approximate)
        xy = self._rgb_to_xy(rgba.red, rgba.green, rgba.blue)
        
        # Save settings
        self.settings.reading_mode.color_xy = xy
        self.settings.reading_mode.brightness = brightness
        self.settings.save()
        
        # Activate reading mode
        if not self.mode_manager.is_reading_active():
            self.mode_manager.switch_to_reading(xy=xy, brightness=brightness)
        else:
            # Update color if already active
            self.mode_manager.get_reading_controller().update_color(xy=xy, brightness=brightness)

    def _rgb_to_xy(self, r: float, g: float, b: float) -> tuple:
        """Convert RGB to CIE XY color coordinates."""
        # Apply gamma correction
        r = pow(r, 2.4) if r > 0.04045 else r / 12.92
        g = pow(g, 2.4) if g > 0.04045 else g / 12.92
        b = pow(b, 2.4) if b > 0.04045 else b / 12.92
        
        # Convert to XYZ
        X = r * 0.664511 + g * 0.154324 + b * 0.162028
        Y = r * 0.283881 + g * 0.668433 + b * 0.047685
        Z = r * 0.000088 + g * 0.072310 + b * 0.986039
        
        # Convert to xy
        sum_xyz = X + Y + Z
        if sum_xyz == 0:
            return (0.0, 0.0)
        
        x = X / sum_xyz
        y = Y / sum_xyz
        
        return (max(0.0, min(1.0, x)), max(0.0, min(1.0, y)))

    def _on_about_clicked(self, button):
        """Show about dialog."""
        about = Adw.AboutDialog(
            application_name="Lumux",
            application_icon="io.github.enginkirmaci.lumux",
            developer_name="Engin Kırmacı",
            version="0.3.0",
            comments=("Sync your Philips Hue lights with your screen in real time. "
                      "Lumux captures screen content, maps it to your configured entertainment "
                      "zones on the Hue bridge, and streams low-latency color updates to create "
                      "immersive ambient lighting.") ,
            license_type=Gtk.License.MIT_X11,
            website="https://github.com/enginkirmaci/lumux",
        )
        about.present(self)

    def _on_sync_toggle(self, button):
        """Toggle sync on/off."""
        if self.sync_controller.is_running():
            self._on_stop_clicked(button)
        else:
            self._on_start_clicked(button)

    def _check_bridge_connection(self):
        """Check if bridge is connected and update UI accordingly."""
        status = self.app_context.get_bridge_status(attempt_connect=True)
        self.bridge_connected = status.connected
        # Determine visibility and texts based on connection/configuration
        if self.bridge_connected:
            if status.entertainment_zone_name:
                channels = f"{status.entertainment_channel_count} channel(s)" if status.entertainment_channel_count else ""
                self.status_label.set_text("Connected")
                self.status_subtitle.set_text(f"Zone: {status.entertainment_zone_name} • {channels}")
            else:
                self.status_label.set_text("Connected")
                self.status_subtitle.set_text("No entertainment zone configured")
            self._update_status_card("connected")
            self.sync_button.set_sensitive(True)
            self.stats_box.set_visible(True)
            self.video_mode_btn.set_sensitive(True)
            self.reading_mode_btn.set_sensitive(True)
        else:
            if not status.configured:
                self.status_label.set_text("Not Configured")
                self.status_subtitle.set_text("Open Settings to configure your bridge")
            else:
                self.status_label.set_text("Disconnected")
                self.status_subtitle.set_text(f"Cannot reach bridge at {status.bridge_ip}")
            self._update_status_card("disconnected")
            self.sync_button.set_sensitive(False)
            self.stats_box.set_visible(False)
            self.video_mode_btn.set_sensitive(False)
            self.reading_mode_btn.set_sensitive(False)

        # Show the settings button when either disconnected or not configured
        if hasattr(self, 'open_bridge_settings_btn'):
            show_btn = (not self.bridge_connected) or (not getattr(status, 'configured', True))
            self.open_bridge_settings_btn.set_visible(bool(show_btn))

    def _apply_window_size(self):
        """Set default and attempt runtime resize according to current mode."""
        if self._current_mode == Mode.READING or self.reading_mode_btn.get_active():
            self.set_default_size(*self._reading_mode_size)
        elif getattr(self.settings.zones, 'show_preview', True):
            self.set_default_size(*self._preview_size)
        else:
            self.set_default_size(*self._compact_size)

    def _update_status(self) -> bool:
        """Check for status updates from sync thread."""
        # Drain the queue to get the latest status
        last_status = None
        while True:
            status = self.sync_controller.get_status()
            if status is None:
                break
            last_status = status
        
        if last_status:
            status_type, message = last_status[:2]
            
            if status_type == 'status':
                if message == 'syncing':
                    self.status_label.set_text("Syncing")
                    self.status_subtitle.set_text("Entertainment streaming active")
                    self._update_status_card("syncing")
                    zone_colors = last_status[2]
                    if zone_colors and getattr(self.settings.zones, 'show_preview', True):
                        try:
                            self.zone_preview.update_colors(zone_colors)
                        except Exception:
                            pass
                elif message == 'stopped':
                    self.status_label.set_text("Stopped")
                    self.status_subtitle.set_text("Ready to sync")
                    self._update_status_card("connected")
                    self._update_sync_button_state(False)
                    self.sync_button.set_sensitive(True)
                    # Restore window if it was hidden via minimize-on-sync
                    try:
                        if getattr(self.settings, 'ui', None) and getattr(self.settings.ui, 'minimize_to_tray_on_sync', False):
                            try:
                                self.present()
                            except Exception:
                                pass
                    except Exception:
                        pass
            elif status_type == 'error':
                self.status_label.set_text("Error")
                self.status_subtitle.set_text(message)
                self._update_status_card("disconnected")
                self._update_sync_button_state(False)
                self.sync_button.set_sensitive(True)

        stats = self.sync_controller.get_stats()
        if stats:
            self.fps_value.set_text(f"{stats['fps']:.1f}")
            self.frames_value.set_text(f"{stats['frame_count']}")

        return True

    def _on_start_clicked(self, button):
        """Start video sync."""
        if not self.bridge_connected:
            self.status_label.set_text("Cannot Start")
            self.status_subtitle.set_text("Bridge not connected")
            return
        
        # Use mode manager to switch to video mode
        if self.mode_manager.switch_to_video():
            self._update_sync_button_state(True)
            self.sync_button.set_sensitive(True)
            self.status_label.set_text("Starting...")
            self.status_subtitle.set_text("Connecting entertainment streaming")
            self._update_status_card("syncing")
            # Optionally minimize to tray when sync begins
            try:
                if getattr(self.settings, 'ui', None) and getattr(self.settings.ui, 'minimize_to_tray_on_sync', False):
                    try:
                        self.hide()
                    except Exception:
                        pass
            except Exception:
                pass
        else:
            self.status_label.set_text("Connection Failed")
            self.status_subtitle.set_text("Check entertainment zone settings")
            self._update_status_card("disconnected")

    def _on_stop_clicked(self, button):
        """Stop video sync."""
        if not self.sync_controller.is_running():
            return
            
        # Check if auto-activate reading mode is enabled
        auto_activate = (
            getattr(self.settings, 'reading_mode', None) and 
            getattr(self.settings.reading_mode, 'auto_activate', False)
        )
        
        if auto_activate:
            # Just stop sync - the callback will auto-activate reading mode
            self.sync_controller.stop()
            # UI will be updated via mode change callback
        else:
            # Turn off everything
            self.mode_manager.turn_off(turn_off_lights=False)
            self._update_sync_button_state(False)
            self.sync_button.set_sensitive(True)
            self.status_label.set_text("Stopped")
            self.status_subtitle.set_text("Ready to sync")
            self._update_status_card("ready")
        
        # Restore window if it was hidden via minimize-on-sync
        try:
            if getattr(self.settings, 'ui', None) and getattr(self.settings.ui, 'minimize_to_tray_on_sync', False):
                try:
                    self.present()
                except Exception:
                    pass
        except Exception:
            pass

    def _on_settings_clicked(self, button):
        """Open settings dialog."""
        dialog = SettingsDialog(self, self.app_context)
        dialog.connect("closed", self._on_settings_closed)
        dialog.present(self)
    
    def _on_settings_closed(self, dialog=None):
        """Handle settings dialog close - refresh configuration."""
        self.app_context.apply_settings()
        self._check_bridge_connection()
        
        # Update preview visibility and layout
        self.preview_group.set_visible(self.settings.zones.show_preview)
        self.zone_preview.set_layout(self.settings.zones.rows, self.settings.zones.cols)

        # Apply window sizing centrally
        self._apply_window_size()

    def do_close_request(self) -> bool:
        """Handle window close request."""
        if hasattr(self, 'mode_manager'):
            self.mode_manager.turn_off(turn_off_lights=False)
        elif self.sync_controller.is_running():
            self.sync_controller.stop()
        
        if self.status_timeout_id:
            GLib.source_remove(self.status_timeout_id)
            self.status_timeout_id = None
        
        # Clean up brightness debounce timer
        if self._brightness_timeout_id:
            GLib.source_remove(self._brightness_timeout_id)
            self._brightness_timeout_id = None
        
        # Clean up tray icon
        if self._tray_icon:
            self._tray_icon.destroy()
            self._tray_icon = None
        
        return False
