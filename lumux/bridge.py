"""Hue bridge connection and control.

Refactored to use unified BridgeClient instead of python-hue-v2.
"""

import socket
from datetime import datetime
from typing import Dict, List, Optional

from lumux.bridge_client import BridgeClient, BridgeError


def _timed_print(*args, **kwargs):
    """Print with timestamp prefix."""
    prefix = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    print(prefix, *args, **kwargs)


class HueBridge:
    """High-level interface to Philips Hue Bridge.
    
    Manages connection state, device caching, and provides
    convenient methods for light/zone control.
    """
    
    def __init__(self, bridge_ip: str, app_key: str):
        """Initialize bridge connection.
        
        Args:
            bridge_ip: IP address of the Hue bridge
            app_key: Application key for authentication
        """
        self.bridge_ip = bridge_ip
        self.app_key = app_key
        self._client: Optional[BridgeClient] = None
        
        # Cached device info
        self.lights: Dict[str, dict] = {}
        self.zones: Dict[str, dict] = {}
        self.light_info: Dict[str, dict] = {}

    @property
    def client(self) -> Optional[BridgeClient]:
        """Get or create bridge client."""
        if self._client is None and self.bridge_ip and self.app_key:
            self._client = BridgeClient(self.bridge_ip, self.app_key)
        return self._client

    def connect(self) -> bool:
        """Connect to Hue bridge using existing credentials."""
        if not self.bridge_ip or not self.app_key:
            return False
        
        try:
            self.refresh_devices()
            return True
        except BridgeError as e:
            print(f"Error connecting to bridge: {e}")
            return False

    def create_user(self, bridge_ip: str, application_name: str = "lumux") -> Optional[dict]:
        """Create a new user/app key on the bridge.

        User must press the link button on the bridge before calling this.
        Returns dict with 'app_key' and 'client_key' on success, None on failure.
        """
        try:
            result = BridgeClient.create_user(bridge_ip, application_name)
            if result:
                self.app_key = result['app_key']
                self.bridge_ip = bridge_ip
                self._client = None  # Reset client with new credentials
            return result
        except BridgeError as e:
            print(f"Error creating user: {e}")
            return None

    def refresh_devices(self):
        """Fetch all lights, zones, and entertainment configs from bridge."""
        if not self.client:
            return

        try:
            # Fetch lights
            lights = self.client.get_lights()
            self.lights = {light.get('id'): light for light in lights if light.get('id')}
            
            # Build light info cache
            self.light_info = {}
            for light_id, light_data in self.lights.items():
                metadata = light_data.get('metadata', {})
                gradient_data = light_data.get('gradient', {})
                color_data = light_data.get('color', {})
                
                self.light_info[light_id] = {
                    'id': light_id,
                    'name': metadata.get('name', f'Light {light_id}'),
                    'archetype': metadata.get('archetype', 'unknown'),
                    'modelid': light_data.get('product_data', {}).get('model_id', ''),
                    'type': light_data.get('type', ''),
                    'state': light_data.get('on', {}).get('on', False),
                    'is_gradient': 'points' in gradient_data or 'points_capable' in gradient_data,
                    'gradient_points': gradient_data.get('points_capable', 0),
                    'gamut_type': color_data.get('gamut_type'),
                    'gamut': color_data.get('gamut'),
                    'position': None  # Filled from entertainment config
                }

            # Fetch spatial data from entertainment configurations
            self._refresh_spatial_data()

            # Fetch zones
            zones = self.client.get_zones()
            self.zones = {zone.get('id'): zone for zone in zones if zone.get('id')}

        except BridgeError as e:
            print(f"Error refreshing devices: {e}")

    def _refresh_spatial_data(self):
        """Fetch and map spatial positions from entertainment configurations."""
        if not self.client:
            return

        try:
            # 1. Get devices to map light service IDs to entertainment service IDs
            devices = self.client.get_devices()
            
            service_map: Dict[str, str] = {}  # light_rid -> entertainment_rid
            for device in devices:
                services = device.get('services', [])
                light_rids = [s['rid'] for s in services if s.get('rtype') == 'light']
                ent_rids = [s['rid'] for s in services if s.get('rtype') == 'entertainment']
                if light_rids and ent_rids:
                    for light_rid in light_rids:
                        service_map[light_rid] = ent_rids[0]

            # 2. Get entertainment configurations
            ent_configs = self.client.get_entertainment_configurations()
            
            found_count = 0
            for config in ent_configs:
                locations = config.get('locations', {}).get('service_locations', [])
                for location in locations:
                    ent_rid = location.get('service', {}).get('rid')
                    position = location.get('position')
                    if not ent_rid or not position:
                        continue
                    
                    # Find light_id for this entertainment_rid
                    for light_rid, mapped_ent_rid in service_map.items():
                        if mapped_ent_rid == ent_rid and light_rid in self.light_info:
                            self.light_info[light_rid]['position'] = position
                            found_count += 1
            
            if found_count > 0:
                print(f"Spatial data refreshed: Found positions for {found_count} lights.")
            else:
                print("Spatial data refreshed: No light positions found in entertainment zones.")
            
        except BridgeError as e:
            print(f"Error refreshing spatial data: {e}")

    def set_light_color(
        self, 
        light_id: str, 
        xy: tuple, 
        brightness: int,
        transition_time: int = 100
    ):
        """Set individual light color and brightness.

        Args:
            light_id: Light ID from bridge
            xy: Tuple of (x, y) coordinates
            brightness: Brightness value (0-254)
            transition_time: Transition time in milliseconds
        """
        if not self.client:
            return
        
        # Validate inputs
        if not light_id or not isinstance(xy, (tuple, list)) or len(xy) != 2:
            print(f"Invalid light color parameters: light_id={light_id}, xy={xy}")
            return
        
        try:
            if self.client.set_light_color(light_id, xy, brightness, transition_time):
                _timed_print(f"Set light {light_id} color to xy={xy}, brightness={brightness}")
        except BridgeError as e:
            print(f"Error setting light color: {e}")

    def set_light_gradient(
        self, 
        light_id: str, 
        fixed_points: List[Dict], 
        brightness: int,
        transition_time: Optional[int] = None
    ):
        """Set gradient light colors.

        Args:
            light_id: Light ID
            fixed_points: List of {'color': {'xy': {'x': x, 'y': y}}}
            brightness: Brightness (0-254)
            transition_time: Optional transition time in milliseconds
        """
        if not self.client:
            return

        try:
            if self.client.set_light_gradient(light_id, fixed_points, brightness, transition_time):
                _timed_print(f"Set light {light_id} gradient with {len(fixed_points)} points, brightness={brightness}")
        except BridgeError as e:
            print(f"Error setting light gradient: {e}")

    def set_zone_color(
        self, 
        zone_id: str, 
        xy: tuple, 
        brightness: int,
        transition_time: int = 100
    ):
        """Set entire zone color and brightness.

        Args:
            zone_id: Zone ID from bridge
            xy: Tuple of (x, y) coordinates
            brightness: Brightness value (0-254)
            transition_time: Transition time in centiseconds (100 = 1 second)
        """
        if not self.client:
            return

        try:
            self.client.set_zone_color(zone_id, xy, brightness)
        except BridgeError as e:
            print(f"Error setting zone color: {e}")

    def get_light_ids(self) -> List[str]:
        """Get list of all light IDs."""
        return list(self.lights.keys())

    def get_light_name(self, light_id: str) -> str:
        """Get light name from ID."""
        info = self.light_info.get(light_id)
        return info.get('name', f"Light {light_id}") if info else f"Light {light_id}"

    def get_light_names(self) -> Dict[str, str]:
        """Get mapping of light IDs to names."""
        return {
            light_id: info.get('name', f"Light {light_id}")
            for light_id, info in self.light_info.items()
        }

    @classmethod
    def discover_bridges(cls) -> List[str]:
        """Discover Hue bridges on local network using SSDP.

        Returns:
            List of bridge IP addresses
        """
        bridges = []

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(2)
            
            ssdp_request = (
                b"M-SEARCH * HTTP/1.1\r\n"
                b"HOST: 239.255.255.250:1900\r\n"
                b"MAN: \"ssdp:discover\"\r\n"
                b"MX: 3\r\n"
                b"ST: ssdp:all\r\n"
                b"\r\n"
            )
            
            sock.sendto(ssdp_request, ("239.255.255.250", 1900))
            
            while True:
                try:
                    data, addr = sock.recvfrom(1024)
                    response = data.decode('utf-8', errors='ignore')
                    
                    if "hue-bridgeid" in response.lower():
                        ip_address = addr[0]
                        if ip_address not in bridges:
                            bridges.append(ip_address)
                except socket.timeout:
                    break
            
            sock.close()
        except Exception as e:
            print(f"Error discovering bridges: {e}")

        return bridges

    def test_connection(self) -> bool:
        """Test if bridge is accessible."""
        if not self.client:
            return False
        return self.client.test_connection()

    def get_entertainment_configurations(self) -> List[dict]:
        """Fetch all entertainment configurations from the bridge."""
        if not self.client:
            return []
        
        try:
            configs = self.client.get_entertainment_configurations()
            return [
                {
                    'id': config.get('id'),
                    'name': config.get('metadata', {}).get('name', 'Unknown'),
                    'status': config.get('status'),
                    'configuration_type': config.get('configuration_type'),
                    'channels': config.get('channels', []),
                    'locations': config.get('locations', {})
                }
                for config in configs
            ]
        except BridgeError as e:
            print(f"Error fetching entertainment configurations: {e}")
            return []

    def get_entertainment_configuration(self, config_id: str) -> Optional[dict]:
        """Fetch a specific entertainment configuration by ID."""
        if not self.client:
            return None
        
        try:
            config = self.client.get_entertainment_configuration(config_id)
            if config:
                return {
                    'id': config.get('id'),
                    'name': config.get('metadata', {}).get('name', 'Unknown'),
                    'status': config.get('status'),
                    'configuration_type': config.get('configuration_type'),
                    'channels': config.get('channels', []),
                    'locations': config.get('locations', {})
                }
        except BridgeError as e:
            print(f"Error fetching entertainment configuration: {e}")
        return None

    def activate_entertainment_streaming(self, config_id: str) -> bool:
        """Activate entertainment streaming for a configuration."""
        if not self.client:
            return False
        
        try:
            if self.client.activate_entertainment_streaming(config_id):
                _timed_print(f"Entertainment streaming activated for config {config_id}")
                return True
            return False
        except BridgeError as e:
            print(f"Failed to activate streaming: {e}")
            return False

    def deactivate_entertainment_streaming(self, config_id: str) -> bool:
        """Deactivate entertainment streaming for a configuration."""
        if not self.client:
            return False
        
        try:
            if self.client.deactivate_entertainment_streaming(config_id):
                _timed_print(f"Entertainment streaming deactivated for config {config_id}")
                return True
            return False
        except BridgeError as e:
            print(f"Failed to deactivate streaming: {e}")
            return False
    
    def get_application_id(self) -> Optional[str]:
        """Get hue-application-id for DTLS PSK identity."""
        if not self.client:
            return None
        return self.client.get_application_id()
