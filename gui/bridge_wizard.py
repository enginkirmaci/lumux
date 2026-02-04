"""Bridge setup wizard with Adwaita styling."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GObject, GLib
from typing import List, Optional, Callable
from lumux.bridge import HueBridge


class BridgeWizard(Adw.NavigationPage):
    """Wizard for setting up Hue bridge connection with 3 steps:
    
    1. Find Bridge - Discovery + manual entry
    2. Connect - Authentication flow  
    3. Select Entertainment Zone - Choose entertainment configuration
    """
    
    __gsignals__ = {
        'finished': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'cancelled': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }
    
    def __init__(self, app_context=None, on_finished: Optional[Callable] = None):
        super().__init__()
        
        self.app_context = app_context
        self.on_finished_callback = on_finished
        
        # Bridge info
        self.bridge_ip: str = ""
        self.app_key: str = ""
        self.client_key: str = ""
        self.selected_ent_config_id: str = ""
        self.entertainment_configs: List[dict] = []
        self.discovered_bridges: List[str] = []
        
        # Create a temp bridge for discovery/auth
        self._temp_bridge: Optional[HueBridge] = None
        
        self._build_ui()
        self._update_ui_state()
    
    def _build_ui(self):
        """Build the main wizard UI."""
        self.set_title("Bridge Setup")
        
        # Main container
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(self.main_box)
        
        # Header
        self.header = Adw.HeaderBar()
        self.header.set_show_end_title_buttons(False)
        self.main_box.append(self.header)
        
        # Header navigation button (Next/Finish)
        self.header_next_btn = Gtk.Button(label="Next")
        self.header_next_btn.add_css_class("suggested-action")
        self.header_next_btn.set_sensitive(False)
        self.header.pack_end(self.header_next_btn)
        
        # Content stack for wizard steps
        self.content_stack = Gtk.Stack()
        self.content_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.content_stack.set_vexpand(True)
        self.main_box.append(self.content_stack)
        
        # Build each step
        self._build_step1_find_bridge()
        self._build_step2_connect()
        self._build_step3_select_zone()
        
        # Show first step
        self.content_stack.set_visible_child_name("step1")
        
        # Connect header button
        self._update_header_button()
    
    def _build_step1_find_bridge(self):
        """Build Step 1: Find Bridge page."""
        page = Adw.PreferencesPage()
        page.set_title("Find Bridge")
        
        # Discovery group
        discovery_group = Adw.PreferencesGroup()
        discovery_group.set_title("Bridge Discovery")
        discovery_group.set_description("Automatically discover your Hue bridge on the network")
        page.add(discovery_group)
        
        # Status row with spinner
        self.discovery_status_row = Adw.ActionRow()
        self.discovery_status_row.set_title("Status")
        self.discovery_status_row.set_subtitle("Ready to discover")
        
        self.discovery_spinner = Gtk.Spinner()
        self.discovery_spinner.set_visible(False)
        self.discovery_spinner.set_valign(Gtk.Align.CENTER)
        self.discovery_status_row.add_suffix(self.discovery_spinner)
        discovery_group.add(self.discovery_status_row)
        
        # Discover button
        discover_row = Adw.ActionRow()
        discover_row.set_title("Search Network")
        discover_row.set_subtitle("Scan for bridges using SSDP, mDNS, and cloud discovery")
        
        self.discover_btn = Gtk.Button(label="Discover")
        self.discover_btn.add_css_class("suggested-action")
        self.discover_btn.set_valign(Gtk.Align.CENTER)
        self.discover_btn.connect("clicked", self._on_discover_clicked)
        discover_row.add_suffix(self.discover_btn)
        discovery_group.add(discover_row)
        
        # Discovered bridges list
        self.discovered_row = Adw.ComboRow()
        self.discovered_row.set_title("Discovered Bridges")
        self.discovered_row.set_subtitle("Select a bridge from the list")
        self.discovered_row.set_sensitive(False)
        self.discovered_row.connect("notify::selected", self._on_bridge_selected)
        discovery_group.add(self.discovered_row)
        
        # Manual entry group
        manual_group = Adw.PreferencesGroup()
        manual_group.set_title("Manual Entry")
        manual_group.set_description("Enter your bridge IP address manually")
        page.add(manual_group)
        
        # IP entry
        self.ip_entry = Adw.EntryRow()
        self.ip_entry.set_title("Bridge IP Address")
        self.ip_entry.set_text("")  # Clear any default text
        # Note: EntryRow doesn't support placeholder_text, using title for hint
        self.ip_entry.connect("changed", self._on_ip_changed)
        manual_group.add(self.ip_entry)
        
        self.content_stack.add_named(page, "step1")
    
    def _build_step2_connect(self):
        """Build Step 2: Connect/Authentication page."""
        page = Adw.PreferencesPage()
        page.set_title("Connect to Bridge")
        
        # Bridge info group
        info_group = Adw.PreferencesGroup()
        info_group.set_title("Bridge Information")
        page.add(info_group)
        
        # IP display
        self.connect_ip_row = Adw.ActionRow()
        self.connect_ip_row.set_title("Bridge IP")
        self.connect_ip_row.set_subtitle("Not set")
        info_group.add(self.connect_ip_row)
        
        # Connection status
        self.connect_status_row = Adw.ActionRow()
        self.connect_status_row.set_title("Connection Status")
        self.connect_status_row.set_subtitle("Not connected")
        
        self.connect_spinner = Gtk.Spinner()
        self.connect_spinner.set_visible(False)
        self.connect_spinner.set_valign(Gtk.Align.CENTER)
        self.connect_status_row.add_suffix(self.connect_spinner)
        info_group.add(self.connect_status_row)
        
        # Authentication group
        auth_group = Adw.PreferencesGroup()
        auth_group.set_title("Authentication")
        auth_group.set_description("Press the link button on your Hue bridge, then click Authenticate")
        page.add(auth_group)
        
        # Authentication button
        auth_row = Adw.ActionRow()
        auth_row.set_title("Link Bridge")
        auth_row.set_subtitle("Create application key for Lumux")
        
        self.auth_btn = Gtk.Button(label="Authenticate")
        self.auth_btn.add_css_class("suggested-action")
        self.auth_btn.set_valign(Gtk.Align.CENTER)
        self.auth_btn.connect("clicked", self._on_authenticate_clicked)
        auth_row.add_suffix(self.auth_btn)
        auth_group.add(auth_row)
        
        # Credentials group (shows after auth)
        self.creds_group = Adw.PreferencesGroup()
        self.creds_group.set_title("Credentials")
        self.creds_group.set_visible(False)
        page.add(self.creds_group)
        
        # App key
        self.app_key_row = Adw.PasswordEntryRow()
        self.app_key_row.set_title("App Key")
        self.app_key_row.set_editable(False)
        self.app_key_row.set_show_apply_button(False)
        self.creds_group.add(self.app_key_row)
        
        # Client key
        self.client_key_row = Adw.PasswordEntryRow()
        self.client_key_row.set_title("Client Key")
        self.client_key_row.set_editable(False)
        self.client_key_row.set_show_apply_button(False)
        self.creds_group.add(self.client_key_row)
        
        self.content_stack.add_named(page, "step2")
    
    def _build_step3_select_zone(self):
        """Build Step 3: Select Entertainment Zone page."""
        page = Adw.PreferencesPage()
        page.set_title("Select Entertainment Zone")
        
        # Zone selection group
        zone_group = Adw.PreferencesGroup()
        zone_group.set_title("Entertainment Zone")
        zone_group.set_description("Choose an entertainment zone for streaming")
        page.add(zone_group)
        
        # Loading status
        self.zone_status_row = Adw.ActionRow()
        self.zone_status_row.set_title("Status")
        self.zone_status_row.set_subtitle("Not loaded")
        
        self.zone_spinner = Gtk.Spinner()
        self.zone_spinner.set_visible(False)
        self.zone_spinner.set_valign(Gtk.Align.CENTER)
        self.zone_status_row.add_suffix(self.zone_spinner)
        zone_group.add(self.zone_status_row)
        
        # Zone combo
        self.zone_row = Adw.ComboRow()
        self.zone_row.set_title("Available Zones")
        self.zone_row.set_subtitle("Select a zone")
        self.zone_row.set_sensitive(False)
        self.zone_row.connect("notify::selected", self._on_zone_selected)
        zone_group.add(self.zone_row)
        
        # Refresh button
        refresh_row = Adw.ActionRow()
        refresh_row.set_title("Refresh")
        refresh_row.set_subtitle("Reload entertainment zones from bridge")
        
        self.refresh_btn = Gtk.Button()
        self.refresh_btn.set_icon_name("view-refresh-symbolic")
        self.refresh_btn.add_css_class("flat")
        self.refresh_btn.set_valign(Gtk.Align.CENTER)
        self.refresh_btn.connect("clicked", self._on_refresh_zones)
        refresh_row.add_suffix(self.refresh_btn)
        zone_group.add(refresh_row)
        
        # Zone info group
        self.zone_info_group = Adw.PreferencesGroup()
        self.zone_info_group.set_title("Zone Information")
        self.zone_info_group.set_visible(False)
        page.add(self.zone_info_group)
        
        # Zone name
        self.zone_name_row = Adw.ActionRow()
        self.zone_name_row.set_title("Name")
        self.zone_info_group.add(self.zone_name_row)
        
        # Channel count
        self.zone_channels_row = Adw.ActionRow()
        self.zone_channels_row.set_title("Channels")
        self.zone_info_group.add(self.zone_channels_row)
        
        self.content_stack.add_named(page, "step3")
    
    # UI State Updates
    def _update_ui_state(self):
        """Update UI based on current state."""
        self._update_header_button()
    
    def _update_header_button(self):
        """Update header button based on current step and state."""
        current_step = self.content_stack.get_visible_child_name()
        
        # Disconnect old handler if any
        if hasattr(self, '_header_btn_handler_id') and self._header_btn_handler_id:
            self.header_next_btn.disconnect(self._header_btn_handler_id)
        
        if current_step == "step1":
            # Step 1 - enable next if IP is set
            has_ip = bool(self.bridge_ip)
            self.header_next_btn.set_label("Next")
            self.header_next_btn.set_sensitive(has_ip)
            self._header_btn_handler_id = self.header_next_btn.connect("clicked", self._on_step1_next)
            
        elif current_step == "step2":
            # Step 2 - enable next if authenticated
            has_auth = bool(self.app_key)
            self.header_next_btn.set_label("Next")
            self.header_next_btn.set_sensitive(has_auth)
            self._header_btn_handler_id = self.header_next_btn.connect("clicked", self._on_step2_next)
            
        elif current_step == "step3":
            # Step 3 - enable finish if zone selected
            has_zone = bool(self.selected_ent_config_id)
            self.header_next_btn.set_label("Finish")
            self.header_next_btn.set_sensitive(has_zone)
            self._header_btn_handler_id = self.header_next_btn.connect("clicked", self._on_step3_finish)
    
    # Step 1: Find Bridge
    def _on_discover_clicked(self, button):
        """Start bridge discovery."""
        self.discover_btn.set_sensitive(False)
        self.discovery_spinner.set_visible(True)
        self.discovery_spinner.start()
        self.discovery_status_row.set_subtitle("Searching...")
        
        # Run discovery in background
        import threading
        thread = threading.Thread(target=self._discover_worker)
        thread.daemon = True
        thread.start()
    
    def _discover_worker(self):
        """Worker thread for bridge discovery."""
        try:
            bridges = HueBridge.discover_bridges(max_retries=3, timeout=5.0)
            GLib.idle_add(self._on_discover_complete, bridges)
        except Exception as e:
            GLib.idle_add(self._on_discover_error, str(e))
    
    def _on_discover_complete(self, bridges: List[str]):
        """Handle discovery completion."""
        self.discovery_spinner.stop()
        self.discovery_spinner.set_visible(False)
        self.discover_btn.set_sensitive(True)
        
        self.discovered_bridges = bridges
        
        if bridges:
            # Populate combo
            model = Gtk.StringList.new(bridges)
            self.discovered_row.set_model(model)
            self.discovered_row.set_sensitive(True)
            self.discovered_row.set_selected(0)
            
            # Auto-select first bridge
            self.bridge_ip = bridges[0]
            self.ip_entry.set_text(self.bridge_ip)
            
            self.discovery_status_row.set_subtitle(f"Found {len(bridges)} bridge(s)")
        else:
            model = Gtk.StringList.new(["No bridges found"])
            self.discovered_row.set_model(model)
            self.discovered_row.set_sensitive(False)
            self.discovery_status_row.set_subtitle("No bridges found. Try manual entry.")
        
        self._update_ui_state()
    
    def _on_discover_error(self, error: str):
        """Handle discovery error."""
        self.discovery_spinner.stop()
        self.discovery_spinner.set_visible(False)
        self.discover_btn.set_sensitive(True)
        self.discovery_status_row.set_subtitle(f"Error: {error}")
    
    def _on_bridge_selected(self, combo, pspec):
        """Handle bridge selection from combo."""
        selected = combo.get_selected()
        if 0 <= selected < len(self.discovered_bridges):
            self.bridge_ip = self.discovered_bridges[selected]
            self.ip_entry.set_text(self.bridge_ip)
            self._update_ui_state()
    
    def _on_ip_changed(self, entry):
        """Handle manual IP entry."""
        self.bridge_ip = entry.get_text().strip()
        self._update_ui_state()
    
    def _on_step1_next(self, button):
        """Proceed to step 2."""
        self.connect_ip_row.set_subtitle(self.bridge_ip)
        self.content_stack.set_visible_child_name("step2")
        self._update_header_button()
    
    # Step 2: Connect
    def _on_authenticate_clicked(self, button):
        """Start authentication flow."""
        if not self.bridge_ip:
            return
        
        self.auth_btn.set_sensitive(False)
        self.connect_spinner.set_visible(True)
        self.connect_spinner.start()
        self.connect_status_row.set_subtitle("Press link button on bridge...")
        
        # Run auth in background
        import threading
        thread = threading.Thread(target=self._authenticate_worker)
        thread.daemon = True
        thread.start()
    
    def _authenticate_worker(self):
        """Worker thread for authentication."""
        try:
            self._temp_bridge = HueBridge(self.bridge_ip, "")
            result = self._temp_bridge.create_user(
                self.bridge_ip,
                max_retries=3,
                timeout=10.0
            )
            GLib.idle_add(self._on_auth_complete, result)
        except Exception as e:
            GLib.idle_add(self._on_auth_error, str(e))
    
    def _on_auth_complete(self, result: Optional[dict]):
        """Handle authentication completion."""
        self.connect_spinner.stop()
        self.connect_spinner.set_visible(False)
        
        if result:
            self.app_key = result.get('app_key', '')
            self.client_key = result.get('client_key', '')
            
            self.app_key_row.set_text(self.app_key)
            self.client_key_row.set_text(self.client_key)
            
            self.creds_group.set_visible(True)
            self.connect_status_row.set_subtitle("Authenticated and connected")
            self.auth_btn.set_label("Re-authenticate")
            self.auth_btn.set_sensitive(True)
            
            # Try to connect the bridge
            if self._temp_bridge and self._temp_bridge.connect():
                self.connect_status_row.set_subtitle("Connected!")
        else:
            self.connect_status_row.set_subtitle("Authentication failed. Press link button and try again.")
            self.auth_btn.set_sensitive(True)
        
        self._update_ui_state()
    
    def _on_auth_error(self, error: str):
        """Handle authentication error."""
        self.connect_spinner.stop()
        self.connect_spinner.set_visible(False)
        self.auth_btn.set_sensitive(True)
        self.connect_status_row.set_subtitle(f"Error: {error}")
    
    def _on_step2_next(self, button):
        """Proceed to step 3."""
        self.content_stack.set_visible_child_name("step3")
        self._update_header_button()
        # Auto-load zones when entering step 3
        self._load_entertainment_zones()
    
    # Step 3: Select Zone
    def _load_entertainment_zones(self):
        """Load entertainment zones from bridge."""
        if not self._temp_bridge:
            # Create bridge if not exists
            self._temp_bridge = HueBridge(self.bridge_ip, self.app_key)
            if not self._temp_bridge.connect():
                self.zone_status_row.set_subtitle("Failed to connect to bridge")
                return
        
        self.zone_spinner.set_visible(True)
        self.zone_spinner.start()
        self.zone_status_row.set_subtitle("Loading zones...")
        self.refresh_btn.set_sensitive(False)
        
        # Run in background
        import threading
        thread = threading.Thread(target=self._load_zones_worker)
        thread.daemon = True
        thread.start()
    
    def _load_zones_worker(self):
        """Worker thread for loading zones."""
        try:
            configs = self._temp_bridge.get_entertainment_configurations()
            GLib.idle_add(self._on_zones_loaded, configs)
        except Exception as e:
            GLib.idle_add(self._on_zones_error, str(e))
    
    def _on_zones_loaded(self, configs: List[dict]):
        """Handle zones loaded."""
        self.zone_spinner.stop()
        self.zone_spinner.set_visible(False)
        self.refresh_btn.set_sensitive(True)
        
        self.entertainment_configs = configs
        
        if configs:
            labels = []
            for config in configs:
                name = config.get('name', 'Unknown')
                channels = len(config.get('channels', []))
                label = f"{name} ({channels} channels)"
                labels.append(label)
            
            model = Gtk.StringList.new(labels)
            self.zone_row.set_model(model)
            self.zone_row.set_sensitive(True)
            self.zone_row.set_selected(0)
            
            # Auto-select first zone
            self.selected_ent_config_id = configs[0].get('id', '')
            self._update_zone_info(configs[0])
            
            self.zone_status_row.set_subtitle(f"Found {len(configs)} zone(s)")
            self.zone_info_group.set_visible(True)
        else:
            model = Gtk.StringList.new(["No entertainment zones found"])
            self.zone_row.set_model(model)
            self.zone_row.set_sensitive(False)
            self.zone_status_row.set_subtitle("No entertainment zones found")
            self.zone_info_group.set_visible(False)
        
        self._update_ui_state()
    
    def _on_zones_error(self, error: str):
        """Handle zones load error."""
        self.zone_spinner.stop()
        self.zone_spinner.set_visible(False)
        self.refresh_btn.set_sensitive(True)
        self.zone_status_row.set_subtitle(f"Error: {error}")
    
    def _update_zone_info(self, config: dict):
        """Update zone info display."""
        self.zone_name_row.set_subtitle(config.get('name', 'Unknown'))
        channels = len(config.get('channels', []))
        self.zone_channels_row.set_subtitle(str(channels))
    
    def _on_zone_selected(self, combo, pspec):
        """Handle zone selection."""
        selected = combo.get_selected()
        if 0 <= selected < len(self.entertainment_configs):
            config = self.entertainment_configs[selected]
            self.selected_ent_config_id = config.get('id', '')
            self._update_zone_info(config)
            self.zone_info_group.set_visible(True)
        else:
            self.selected_ent_config_id = ""
            self.zone_info_group.set_visible(False)
        
        self._update_ui_state()
    
    def _on_refresh_zones(self, button):
        """Refresh entertainment zones."""
        self._load_entertainment_zones()
    
    def _on_step3_finish(self, button):
        """Finish wizard."""
        self.emit('finished')
        if self.on_finished_callback:
            self.on_finished_callback(
                self.bridge_ip,
                self.app_key,
                self.client_key,
                self.selected_ent_config_id
            )
    
    def _on_cancel(self, button):
        """Cancel wizard."""
        self.emit('cancelled')
    
    # Public API
    def get_bridge_settings(self) -> dict:
        """Get the configured bridge settings.
        
        Returns:
            Dict with bridge_ip, app_key, client_key, entertainment_config_id
        """
        return {
            'bridge_ip': self.bridge_ip,
            'app_key': self.app_key,
            'client_key': self.client_key,
            'entertainment_config_id': self.selected_ent_config_id,
        }
    
    def set_bridge_settings(self, bridge_ip: str = "", app_key: str = "",
                           client_key: str = "", entertainment_config_id: str = ""):
        """Set initial bridge settings (for editing existing config)."""
        self.bridge_ip = bridge_ip
        self.app_key = app_key
        self.client_key = client_key
        self.selected_ent_config_id = entertainment_config_id
        
        # Update UI
        if bridge_ip:
            self.ip_entry.set_text(bridge_ip)
            self.connect_ip_row.set_subtitle(bridge_ip)
        
        if app_key:
            self.app_key_row.set_text(app_key)
            self.client_key_row.set_text(client_key)
            self.creds_group.set_visible(True)
            self.connect_status_row.set_subtitle("Previously authenticated")
            self.auth_btn.set_label("Re-authenticate")
        
        self._update_ui_state()


class BridgeWizardDialog(Adw.Dialog):
    """Dialog wrapper for BridgeWizard."""
    
    __gsignals__ = {
        'finished': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }
    
    def __init__(self, parent=None, app_context=None, on_finished: Optional[Callable] = None):
        super().__init__()
        
        self.set_title("Bridge Setup Wizard")
        self.set_content_width(500)
        self.set_content_height(600)
        
        self.wizard = BridgeWizard(app_context, on_finished=self._on_wizard_finished)
        self.wizard.connect('finished', self._on_wizard_finished_signal)
        self.wizard.connect('cancelled', self._on_wizard_cancelled)
        
        self.set_child(self.wizard)
        
        self.on_finished_callback = on_finished
        self._parent = parent
    
    def _on_wizard_finished(self, bridge_ip: str, app_key: str,
                           client_key: str, entertainment_config_id: str):
        """Handle wizard finish with data."""
        if self.on_finished_callback:
            self.on_finished_callback(bridge_ip, app_key, client_key, entertainment_config_id)
    
    def _on_wizard_finished_signal(self, wizard):
        """Handle wizard finished signal."""
        self.emit('finished')
        self.close()
    
    def _on_wizard_cancelled(self, wizard):
        """Handle wizard cancelled."""
        self.close()
    
    def present(self, parent=None):
        """Present the dialog."""
        if parent:
            super().present(parent)
        elif self._parent:
            super().present(self._parent)
        else:
            super().present()
    
    def get_bridge_settings(self) -> dict:
        """Get the configured bridge settings."""
        return self.wizard.get_bridge_settings()
    
    def set_bridge_settings(self, **kwargs):
        """Set initial bridge settings."""
        self.wizard.set_bridge_settings(**kwargs)
