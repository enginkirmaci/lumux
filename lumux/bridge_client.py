"""Unified Hue Bridge API client.

Replaces python-hue-v2 with a clean, consistent interface to the Hue v2 REST API.
"""

import json
import ssl
import time
import urllib.request
import urllib3
from typing import Any, Dict, List, Optional

import requests

# Disable SSL warnings once at module level
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class BridgeError(Exception):
    """Raised when bridge API calls fail."""
    pass


class BridgeConnectionError(BridgeError):
    """Raised when unable to connect to bridge."""
    pass


class BridgeAuthError(BridgeError):
    """Raised when authentication fails."""
    pass


class BridgeClient:
    """Unified client for Philips Hue Bridge v2 API.
    
    Handles all REST API calls with consistent error handling,
    SSL configuration, and request formatting.
    """
    
    def __init__(self, bridge_ip: str, app_key: str, timeout: float = 5.0):
        """Initialize bridge client.
        
        Args:
            bridge_ip: IP address of the Hue bridge
            app_key: Application key for authentication
            timeout: Default timeout for requests in seconds
        """
        self.bridge_ip = bridge_ip
        self.app_key = app_key
        self.timeout = timeout
        self._session = requests.Session()
        # Hue bridge uses self-signed certificate
        self._session.verify = False
        
    def _request(
        self, 
        method: str, 
        path: str, 
        json_data: Optional[Dict] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """Make authenticated request to bridge API.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API path (e.g., '/resource/light')
            json_data: Optional JSON payload
            headers: Optional additional headers
            timeout: Override default timeout
            
        Returns:
            Parsed JSON response
            
        Raises:
            BridgeConnectionError: If connection fails
            BridgeAuthError: If authentication fails
            BridgeError: For other API errors
        """
        if not self.bridge_ip:
            raise BridgeConnectionError("Bridge IP not configured")
            
        url = f"https://{self.bridge_ip}/clip/v2{path}"
        
        request_headers = {"hue-application-key": self.app_key}
        if headers:
            request_headers.update(headers)
            
        try:
            resp = self._session.request(
                method,
                url,
                headers=request_headers,
                json=json_data,
                timeout=timeout or self.timeout
            )
            
            # Handle specific error codes
            if resp.status_code == 401:
                raise BridgeAuthError("Invalid app key or bridge authentication required")
            elif resp.status_code == 403:
                raise BridgeAuthError("Insufficient permissions")
            elif resp.status_code == 404:
                raise BridgeError(f"Resource not found: {path}")
            elif resp.status_code >= 500:
                raise BridgeConnectionError(f"Bridge server error: {resp.status_code}")
            
            resp.raise_for_status()
            
            if resp.content:
                return resp.json()
            return {}
            
        except requests.exceptions.Timeout:
            raise BridgeConnectionError(f"Timeout connecting to bridge at {self.bridge_ip}")
        except requests.exceptions.ConnectionError as e:
            raise BridgeConnectionError(f"Cannot connect to bridge at {self.bridge_ip}: {e}")
        except requests.exceptions.RequestException as e:
            raise BridgeError(f"Request failed: {e}") from e
    
    def get_application_id(self) -> Optional[str]:
        """Get hue-application-id from /auth/v1 endpoint.
        
        This is the PSK identity for DTLS entertainment streaming.
        
        Returns:
            Application ID string or None if unavailable
        """
        if not self.bridge_ip or not self.app_key:
            return None
            
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            url = f"https://{self.bridge_ip}/auth/v1"
            req = urllib.request.Request(url, method='GET')
            req.add_header('hue-application-key', self.app_key)
            
            resp = urllib.request.urlopen(req, context=ctx, timeout=self.timeout)
            headers = dict(resp.headers)
            return headers.get('hue-application-id')
        except Exception:
            return None
    
    # === Light Operations ===
    
    def get_lights(self) -> List[Dict[str, Any]]:
        """Get all lights from bridge."""
        data = self._request('GET', '/resource/light')
        return data.get('data', [])
    
    def get_light(self, light_id: str) -> Optional[Dict[str, Any]]:
        """Get specific light by ID."""
        try:
            data = self._request('GET', f'/resource/light/{light_id}')
            items = data.get('data', [])
            return items[0] if items else None
        except BridgeError:
            return None
    
    def set_light_state(self, light_id: str, payload: Dict[str, Any]) -> bool:
        """Update light state (color, brightness, on/off).
        
        Args:
            light_id: Light resource ID
            payload: Hue v2 API payload (color, dimming, on, dynamics, etc.)
            
        Returns:
            True if successful
        """
        try:
            self._request('PUT', f'/resource/light/{light_id}', json_data=payload)
            return True
        except BridgeError:
            return False
    
    def set_light_color(
        self, 
        light_id: str, 
        xy: tuple[float, float], 
        brightness: int,
        transition_ms: Optional[int] = None
    ) -> bool:
        """Set light color and brightness.
        
        Args:
            light_id: Light resource ID
            xy: CIE XY color coordinates (0.0-1.0)
            brightness: Brightness 0-254
            transition_ms: Optional transition time in milliseconds
        """
        brightness = max(0, min(254, int(brightness)))
        
        payload = {
            'color': {'xy': {'x': xy[0], 'y': xy[1]}},
            'dimming': {'brightness': (brightness / 254.0) * 100.0},
            'on': {'on': True},
        }
        
        if transition_ms is not None:
            payload['dynamics'] = {'duration': int(max(0, transition_ms))}
        
        return self.set_light_state(light_id, payload)
    
    def set_light_gradient(
        self, 
        light_id: str, 
        points: List[Dict], 
        brightness: int,
        transition_ms: Optional[int] = None
    ) -> bool:
        """Set gradient light colors.
        
        Args:
            light_id: Light resource ID
            points: List of {'color': {'xy': {'x': x, 'y': y}}} gradient points
            brightness: Brightness 0-254
            transition_ms: Optional transition time in milliseconds
        """
        brightness = max(0, min(254, int(brightness)))
        
        # Validate and format gradient points
        formatted_points = []
        for point in points or []:
            if isinstance(point, dict):
                color = point.get('color')
                if isinstance(color, dict):
                    xy = color.get('xy')
                    if isinstance(xy, dict) and 'x' in xy and 'y' in xy:
                        formatted_points.append({'color': {'xy': {'x': xy['x'], 'y': xy['y']}}})
        
        if len(formatted_points) < 2:
            return False
        
        payload = {
            'gradient': {'points': formatted_points},
            'dimming': {'brightness': (brightness / 254.0) * 100.0},
            'on': {'on': True}
        }
        
        if transition_ms is not None:
            payload['dynamics'] = {'duration': int(max(0, transition_ms))}
        
        return self.set_light_state(light_id, payload)
    
    # === Zone Operations ===
    
    def get_zones(self) -> List[Dict[str, Any]]:
        """Get all zones from bridge."""
        data = self._request('GET', '/resource/zone')
        return data.get('data', [])
    
    def set_zone_state(self, zone_id: str, payload: Dict[str, Any]) -> bool:
        """Update zone state."""
        try:
            self._request('PUT', f'/resource/zone/{zone_id}', json_data=payload)
            return True
        except BridgeError:
            return False
    
    def set_zone_color(
        self, 
        zone_id: str, 
        xy: tuple[float, float], 
        brightness: int
    ) -> bool:
        """Set entire zone color."""
        brightness = max(0, min(254, int(brightness)))
        
        payload = {
            'color': {'xy': {'x': xy[0], 'y': xy[1]}},
            'dimming': {'brightness': (brightness / 254.0) * 100.0},
            'on': {'on': True},
        }
        
        return self.set_zone_state(zone_id, payload)
    
    # === Entertainment Operations ===
    
    def get_entertainment_configurations(self) -> List[Dict[str, Any]]:
        """Get all entertainment configurations."""
        data = self._request('GET', '/resource/entertainment_configuration')
        return data.get('data', [])
    
    def get_entertainment_configuration(self, config_id: str) -> Optional[Dict[str, Any]]:
        """Get specific entertainment configuration."""
        try:
            data = self._request('GET', f'/resource/entertainment_configuration/{config_id}')
            items = data.get('data', [])
            return items[0] if items else None
        except BridgeError:
            return None
    
    def activate_entertainment_streaming(self, config_id: str) -> bool:
        """Activate entertainment streaming for a configuration."""
        try:
            self._request(
                'PUT', 
                f'/resource/entertainment_configuration/{config_id}',
                json_data={'action': 'start'}
            )
            return True
        except BridgeError:
            return False
    
    def deactivate_entertainment_streaming(self, config_id: str) -> bool:
        """Deactivate entertainment streaming for a configuration."""
        try:
            self._request(
                'PUT',
                f'/resource/entertainment_configuration/{config_id}',
                json_data={'action': 'stop'}
            )
            return True
        except BridgeError:
            return False
    
    # === Device Operations ===
    
    def get_devices(self) -> List[Dict[str, Any]]:
        """Get all devices for spatial mapping."""
        data = self._request('GET', '/resource/device')
        return data.get('data', [])
    
    # === User Management ===
    
    @staticmethod
    def create_user(
        bridge_ip: str, 
        application_name: str = "lumux"
    ) -> Optional[Dict[str, str]]:
        """Create a new user/app key on the bridge.
        
        User must press the link button on the bridge before calling this.
        
        Args:
            bridge_ip: Bridge IP address
            application_name: Application identifier
            
        Returns:
            Dict with 'app_key' and 'client_key' on success, None on failure
        """
        try:
            url = f"https://{bridge_ip}/api"
            payload = {
                "devicetype": f"{application_name}#user", 
                "generateclientkey": True
            }
            
            resp = requests.post(
                url, 
                json=payload, 
                verify=False, 
                timeout=5
            )
            
            if resp.status_code == 200:
                result = resp.json()
                if result and len(result) > 0:
                    if 'success' in result[0]:
                        return {
                            'app_key': result[0]['success']['username'],
                            'client_key': result[0]['success'].get('clientkey', '')
                        }
                    elif 'error' in result[0]:
                        error_msg = result[0]['error'].get('description', 'Unknown error')
                        raise BridgeAuthError(f"Bridge error: {error_msg}")
                        
        except requests.exceptions.RequestException as e:
            raise BridgeConnectionError(f"Failed to create user: {e}")
            
        return None
    
    def test_connection(self) -> bool:
        """Test if bridge is accessible and credentials work."""
        try:
            self.get_lights()
            return True
        except BridgeError:
            return False


# Backward compatibility aliases
HueBridgeClient = BridgeClient
