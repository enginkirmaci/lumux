"""Hue bridge connection and control."""

import socket
import time
from typing import Dict, List, Optional

from python_hue_v2 import Hue


class HueBridge:
    def __init__(self, bridge_ip: str, app_key: str):
        self.bridge_ip = bridge_ip
        self.app_key = app_key
        self.hue = None
        self.bridge = None
        
        self.lights: Dict[str, dict] = {}
        self.zones: Dict[str, dict] = {}
        self.groups: Dict[str, dict] = {}
        self.light_info: Dict[str, dict] = {}

    def connect(self) -> bool:
        """Connect to Hue bridge using existing credentials."""
        if not self.bridge_ip or not self.app_key:
            return False
        
        try:
            self.hue = Hue(self.bridge_ip, self.app_key)
            self.bridge = self.hue.bridge
            self.refresh_devices()
            return True
        except Exception as e:
            print(f"Error connecting to bridge: {e}")
            return False

    def create_user(self, bridge_ip: str, application_name: str = "hue-sync") -> Optional[str]:
        """Create a new user/app key on the bridge.

        User must press the link button on the bridge before calling this.
        """
        try:
            import requests
            import json
            
            # Use Hue Bridge API v2 to create application key
            url = f"https://{bridge_ip}/api"
            payload = {"devicetype": f"{application_name}#user", "generateclientkey": True}
            
            # Disable SSL verification for self-signed certificate
            response = requests.post(url, json=payload, verify=False, timeout=5)
            
            if response.status_code == 200:
                result = response.json()
                if result and len(result) > 0:
                    if 'success' in result[0]:
                        app_key = result[0]['success']['username']
                        self.app_key = app_key
                        self.bridge_ip = bridge_ip
                        return app_key
                    elif 'error' in result[0]:
                        error_msg = result[0]['error'].get('description', 'Unknown error')
                        print(f"Bridge error: {error_msg}")
        except Exception as e:
            print(f"Error creating user: {e}")
        return None

    def refresh_devices(self):
        """Fetch all lights, zones, and entertainment configs from bridge."""
        if not self.bridge:
            return

        try:
            lights = self.bridge.get_lights()
            # Handle both list and dict responses - use actual light ID (UUID)
            if isinstance(lights, list):
                self.lights = {light.get('id'): light for light in lights if light.get('id')}
            else:
                self.lights = {str(k): v for k, v in lights.items()}
            
            for light_id, light_data in self.lights.items():
                metadata = light_data.get('metadata', {})
                gradient_data = light_data.get('gradient', {})
                self.light_info[light_id] = {
                    'id': light_id,
                    'name': metadata.get('name', f'Light {light_id}'),
                    'archetype': metadata.get('archetype', 'unknown'),
                    'modelid': light_data.get('product_data', {}).get('model_id', ''),
                    'type': light_data.get('type', ''),
                    'state': light_data.get('on', {}).get('on', False),
                    'is_gradient': 'points' in gradient_data or 'points_capable' in gradient_data,
                    'gradient_points': gradient_data.get('points_capable', 0),
                    'position': None # Will be filled from entertainment config
                }

            # Fetch entertainment and device service mappings
            self._refresh_spatial_data()

            zones = self.bridge.get_zones()
            if isinstance(zones, list):
                self.zones = {zone.get('id'): zone for zone in zones if zone.get('id')}
            else:
                self.zones = {str(k): v for k, v in zones.items()}

        except Exception as e:
            print(f"Error refreshing devices: {e}")

    def _refresh_spatial_data(self):
        """Fetch and map spatial positions from entertainment configurations using direct API calls."""
        if not self.bridge_ip or not self.app_key:
            return

        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        headers = {"hue-application-key": self.app_key}
        base_url = f"https://{self.bridge_ip}/clip/v2/resource"
        
        try:
            # 1. Get devices to map light service IDs to entertainment service IDs
            resp = requests.get(f"{base_url}/device", headers=headers, verify=False, timeout=5)
            devices = resp.json().get('data', [])
            
            service_map = {} # light_rid -> entertainment_rid
            for dev in devices:
                services = dev.get('services', [])
                light_rids = [s['rid'] for s in services if s['rtype'] == 'light']
                ent_rids = [s['rid'] for s in services if s['rtype'] == 'entertainment']
                if light_rids and ent_rids:
                    for l_rid in light_rids:
                        service_map[l_rid] = ent_rids[0]

            # 2. Get entertainment configurations
            resp = requests.get(f"{base_url}/entertainment_configuration", headers=headers, verify=False, timeout=5)
            ent_configs = resp.json().get('data', [])
            
            found_count = 0
            for config in ent_configs:
                locations = config.get('locations', {}).get('service_locations', [])
                for loc in locations:
                    ent_rid = loc.get('service', {}).get('rid')
                    pos = loc.get('position')
                    if not ent_rid or not pos: continue
                    
                    # Find light_id for this entertainment_rid
                    for light_rid, mapped_ent_rid in service_map.items():
                        if mapped_ent_rid == ent_rid:
                            if light_rid in self.light_info:
                                self.light_info[light_rid]['position'] = pos
                                found_count += 1
                                # print(f"  Mapped position for light: {self.light_info[light_rid]['name']}")
            
            if found_count > 0:
                print(f"Spatial data refreshed: Found positions for {found_count} lights.")
            else:
                print("Spatial data refreshed: No light positions found in entertainment zones.")
            
        except Exception as e:
            print(f"Error refreshing spatial data: {e}")

    def set_light_color(self, light_id: str, xy: tuple, brightness: int,
                        transition_time: int = 100):
        """Set individual light color and brightness.

        Args:
            light_id: Light ID from bridge
            xy: Tuple of (x, y) coordinates
            brightness: Brightness value (0-254)
            transition_time: Transition time in centiseconds (100 = 1 second)
        """
        if not self.bridge:
            return
        
        # Validate inputs
        if not light_id or not isinstance(xy, (tuple, list)) or len(xy) != 2:
            print(f"Invalid light color parameters: light_id={light_id}, xy={xy}")
            return
        
        # Clamp brightness
        brightness = max(0, min(254, int(brightness)))

        try:
            # Bypass set_light wrapper to send multi-property update
            # xy must be {'x': float, 'y': float} not a tuple
            payload = {
                'color': {'xy': {'x': xy[0], 'y': xy[1]}},
                'dimming': {'brightness': (brightness / 254.0) * 100.0},
                'on': {'on': True},
            }
            
            # If it's a gradient light, we might still want to set a single color occasionally,
            # but usually we use set_light_gradient.
            self.bridge._put_by_id('light', light_id, payload)
        except Exception as e:
            print(f"Error setting light color: {e}")

    def set_light_gradient(self, light_id: str, fixed_points: List[Dict], brightness: int):
        """Set gradient light colors.

        Args:
            light_id: Light ID
            fixed_points: List of {'color': {'xy': {'x': x, 'y': y}}}
            brightness: Brightness (0-254)
        """
        if not self.bridge:
            return

        brightness = max(0, min(254, int(brightness)))
        
        try:
            payload = {
                'gradient': {
                    'points': fixed_points
                },
                'dimming': {'brightness': (brightness / 254.0) * 100.0},
                'on': {'on': True}
            }
            self.bridge._put_by_id('light', light_id, payload)
        except Exception as e:
            print(f"Error setting light gradient: {e}")

    def set_zone_color(self, zone_id: str, xy: tuple, brightness: int,
                      transition_time: int = 100):
        """Set entire zone color and brightness.

        Args:
            zone_id: Zone ID from bridge
            xy: Tuple of (x, y) coordinates
            brightness: Brightness value (0-254)
            transition_time: Transition time in centiseconds (100 = 1 second)
        """
        if not self.bridge:
            return

        try:
            # Bypass set_zone wrapper to send multi-property update
            # xy must be {'x': float, 'y': float} not a tuple
            payload = {
                'color': {'xy': {'x': xy[0], 'y': xy[1]}},
                'dimming': {'brightness': (brightness / 254.0) * 100.0},
                'on': {'on': True},
            }
            self.bridge._put_by_id('zone', zone_id, payload)
        except Exception as e:
            print(f"Error setting zone color: {e}")

    def get_light_ids(self) -> List[str]:
        """Get list of all light IDs."""
        return list(self.lights.keys())

    def get_light_name(self, light_id: str) -> str:
        """Get light name from ID."""
        info = self.light_info.get(light_id)
        if info:
            return info.get('name', f"Light {light_id}")
        return f"Light {light_id}"

    def get_zone_ids(self) -> List[str]:
        """Get list of all zone IDs."""
        return list(self.zones.keys())

    def get_light_names(self) -> Dict[str, str]:
        """Get mapping of light IDs to names."""
        return {light_id: info['name'] for light_id, info in self.light_info.items()}

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
        if not self.bridge:
            return False
        
        try:
            self.bridge.get_lights()
            return True
        except Exception:
            return False
