"""Main application window with modern Adwaita styling."""

import os
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GLib, Adw, Gdk, Gio, GdkPixbuf
from lumux.app_context import AppContext
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
        self.settings = app_context.settings
        self.bridge_connected = False
        self._is_syncing = False
        # Window size presets
        self._preview_size = (800, 640)
        self._compact_size = (500, 400)
        
        # System tray icon
        self._tray_icon = None

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
        
        # Sync toggle button (large, prominent)
        self.sync_button = Gtk.Button()
        self.sync_button.add_css_class("control-button")
        self.sync_button.add_css_class("suggested-action")
        self.sync_button.add_css_class("pill")
        
        # Create box with icon and label for the button
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
        control_box.append(self.sync_button)

        

        main_box.append(control_box)

        # Apply initial window sizing based on preview setting
        self._apply_window_size()

    def _update_sync_button_state(self, is_syncing: bool):
        """Update sync button appearance based on state."""
        self._is_syncing = is_syncing
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
        
        if state == "syncing":
            self.status_card.add_css_class("status-syncing")
            self.status_icon.set_from_icon_name("emblem-synchronizing-symbolic")
        elif state == "connected":
            self.status_card.add_css_class("status-connected")
            self.status_icon.set_from_icon_name("network-transmit-receive-symbolic")
        else:
            self.status_card.add_css_class("status-disconnected")
            self.status_icon.set_from_icon_name("network-offline-symbolic")

    def _on_about_clicked(self, button):
        """Show about dialog."""
        about = Adw.AboutDialog(
            application_name="Lumux for Philips Hue Sync",
            application_icon="io.github.enginkirmaci.lumux",
            developer_name="Engin Kırmacı",
            version="0.2.0",
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
        if self._is_syncing:
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

        # Show the settings button when either disconnected or not configured
        if hasattr(self, 'open_bridge_settings_btn'):
            show_btn = (not self.bridge_connected) or (not getattr(status, 'configured', True))
            self.open_bridge_settings_btn.set_visible(bool(show_btn))

    def _apply_window_size(self):
        """Set default and attempt runtime resize according to `show_preview` setting."""
        preview = getattr(self.settings.zones, 'show_preview', True)
        if preview:
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
        """Start sync."""
        if not self.bridge_connected:
            self.status_label.set_text("Cannot Start")
            self.status_subtitle.set_text("Bridge not connected")
            return
            
        if not self.sync_controller.is_running():
            # Connect entertainment streaming first
            if not self.app_context.start_entertainment():
                self.status_label.set_text("Connection Failed")
                self.status_subtitle.set_text("Check client_key and entertainment zone settings")
                self._update_status_card("disconnected")
                return
            
            self.sync_controller.start()
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

    def _on_stop_clicked(self, button):
        """Stop sync."""
        if self.sync_controller.is_running():
            self.sync_controller.stop()
            # Disconnect entertainment streaming
            self.app_context.stop_entertainment()
            self._update_sync_button_state(False)
            self.sync_button.set_sensitive(True)
            self.status_label.set_text("Stopping...")
            self.status_subtitle.set_text("Disconnecting...")
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
        if self.sync_controller.is_running():
            self.sync_controller.stop()
        
        if self.status_timeout_id:
            GLib.source_remove(self.status_timeout_id)
            self.status_timeout_id = None
        
        # Clean up tray icon
        if self._tray_icon:
            self._tray_icon.destroy()
            self._tray_icon = None
        
        return False
