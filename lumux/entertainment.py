"""Hue Entertainment API streaming via DTLS-PSK.

This module implements the Hue Entertainment streaming protocol which allows
low-latency color updates to lights in an entertainment zone using DTLS over UDP.
"""

import struct
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Dict, Optional, Tuple, TYPE_CHECKING

from lumux.utils.logging import timed_print

if TYPE_CHECKING:
    from lumux.bridge import HueBridge


# HueStream protocol constants
class HueStreamProtocol:
    """HueStream protocol constants."""
    HEADER = b"HueStream"
    VERSION_MAJOR = 0x02  # API version 2.0
    VERSION_MINOR = 0x00
    PORT = 2100
    
    # Color space constants
    COLORSPACE_RGB = 0x00
    COLORSPACE_XY = 0x01
    
    # Message structure sizes (bytes)
    HEADER_SIZE = 9
    VERSION_SIZE = 2
    SEQUENCE_SIZE = 1
    RESERVED_SIZE = 2
    COLORSPACE_SIZE = 1
    RESERVED2_SIZE = 1
    CONFIG_ID_SIZE = 36  # ASCII UUID string
    CHANNEL_DATA_SIZE = 7  # 1 byte ID + 3×2 bytes color data
    
    # Color value scaling
    MAX_16BIT = 65535
    BRIGHTNESS_SCALE = 257  # 254 * 257 ≈ 65278


class ChannelInfo:
    """Information about an entertainment channel."""
    
    def __init__(self, channel_id: int, position: Dict, members: list):
        self.channel_id = channel_id
        self.position = position
        self.members = members


class EntertainmentStream:
    """Manages DTLS connection and streaming to a Hue Entertainment zone."""

    def __init__(
        self,
        bridge_ip: str,
        app_key: str,
        client_key: str,
        entertainment_config_id: str,
        connection_timeout: float = 0.5,
        handshake_delay: float = 0.3
    ):
        """Initialize entertainment stream.

        Args:
            bridge_ip: IP address of the Hue bridge
            app_key: Application key (username) - used to get hue-application-id
            client_key: Client key - used as PSK (32-byte hex string)
            entertainment_config_id: ID of the entertainment configuration to stream to
            connection_timeout: Time to wait for DTLS connection (seconds)
            handshake_delay: Additional time for handshake completion (seconds)
        """
        self.bridge_ip = bridge_ip
        self.app_key = app_key
        self.client_key = client_key
        self.entertainment_config_id = entertainment_config_id
        self._connection_timeout = connection_timeout
        self._handshake_delay = handshake_delay
        
        self._application_id: Optional[str] = None
        self._openssl_proc: Optional[subprocess.Popen] = None
        self._dtls_socket = None  # Future: native DTLS implementation
        self._connected = False
        self._sequence = 0
        self._lock = threading.Lock()

        # Channel mappings
        self._channels: Dict[int, ChannelInfo] = {}
        self._light_to_channel: Dict[str, int] = {}

    @property
    def channels(self) -> Dict[int, ChannelInfo]:
        """Channel mapping: channel_id -> ChannelInfo."""
        return self._channels

    @property
    def light_to_channel(self) -> Dict[str, int]:
        """Reverse mapping: light_id -> channel_id."""
        return self._light_to_channel

    def connect(self, bridge: 'HueBridge') -> bool:
        """Establish DTLS connection to the bridge.

        Args:
            bridge: HueBridge instance to use for API calls

        Returns:
            True if connection successful, False otherwise
        """
        try:
            config = self._fetch_entertainment_config(bridge)
            if not config:
                return False

            self._parse_channels(config)
            self._application_id = self._fetch_application_id(bridge)

            if not self._activate_streaming(bridge):
                return False

            if not self._establish_dtls_connection():
                self._deactivate_streaming(bridge)
                return False

            self._connected = True
            timed_print(f"Entertainment stream connected with {len(self._channels)} channels")
            return True

        except Exception as e:
            print(f"Error connecting entertainment stream: {e}")
            return False

    def _fetch_entertainment_config(self, bridge: 'HueBridge') -> Optional[dict]:
        """Fetch entertainment configuration from bridge."""
        config = bridge.get_entertainment_configuration(self.entertainment_config_id)
        if not config:
            print(f"Entertainment configuration {self.entertainment_config_id} not found")
        return config

    def _fetch_application_id(self, bridge: 'HueBridge') -> str:
        """Get hue-application-id from /auth/v1 endpoint.
        
        This is the correct PSK identity for DTLS connection per official API docs.
        Falls back to app_key if unavailable.
        """
        try:
            app_id = bridge.get_application_id()
            if app_id:
                timed_print(f"Got hue-application-id: {app_id}")
                return app_id
        except Exception as e:
            timed_print(f"Error getting application ID: {e}")
        
        timed_print("Warning: Could not get hue-application-id, falling back to app_key")
        return self.app_key

    def _activate_streaming(self, bridge: 'HueBridge') -> bool:
        """Activate streaming via REST API."""
        if not bridge.activate_entertainment_streaming(self.entertainment_config_id):
            print("Failed to activate entertainment streaming")
            return False
        time.sleep(self._connection_timeout)  # Give bridge time to prepare
        return True

    def _deactivate_streaming(self, bridge: 'HueBridge') -> None:
        """Deactivate streaming via REST API."""
        try:
            bridge.deactivate_entertainment_streaming(self.entertainment_config_id)
        except Exception as e:
            print(f"Error deactivating streaming: {e}")

    def _parse_channels(self, config: dict) -> None:
        """Parse channel information from entertainment configuration."""
        self._channels.clear()
        self._light_to_channel.clear()

        channels = config.get('channels', [])
        timed_print(f"Entertainment config has {len(channels)} channel entries")
        
        for channel in channels:
            self._parse_single_channel(channel)

        timed_print(f"Parsed {len(self._channels)} channels from entertainment config")

    def _parse_single_channel(self, channel: dict) -> None:
        """Parse a single channel from config."""
        channel_id = channel.get('channel_id')
        if channel_id is None:
            timed_print(f"  Skipping channel without ID: {channel}")
            return

        position = channel.get('position', {})
        members = channel.get('members', [])

        self._channels[channel_id] = ChannelInfo(
            channel_id=channel_id,
            position=position,
            members=members
        )
        
        pos_x = position.get('x', 0)
        pos_y = position.get('y', 0)
        pos_z = position.get('z', 0)
        timed_print(
            f"  Channel {channel_id}: "
            f"pos=({pos_x:.2f}, {pos_y:.2f}, {pos_z:.2f}), "
            f"{len(members)} members"
        )

        for member in members:
            self._map_member_to_channel(member, channel_id)

    def _map_member_to_channel(self, member: dict, channel_id: int) -> None:
        """Map a member light to its channel."""
        service = member.get('service', {})
        light_rid = service.get('rid')
        if light_rid:
            self._light_to_channel[light_rid] = channel_id

    def _establish_dtls_connection(self) -> bool:
        """Establish DTLS-PSK connection to bridge port 2100."""
        try:
            cmd = self._build_openssl_command()
            timed_print(
                f"Starting DTLS connection: "
                f"openssl s_client -dtls1_2 -connect {self.bridge_ip}:{HueStreamProtocol.PORT}"
            )
            
            self._openssl_proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            return self._wait_for_handshake()

        except FileNotFoundError:
            print("DTLS connection failed: openssl command not found")
            return False
        except Exception as e:
            print(f"DTLS connection failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _build_openssl_command(self) -> list[str]:
        """Build OpenSSL command for DTLS-PSK connection."""
        psk_identity = self._application_id or self.app_key
        return [
            "openssl", "s_client",
            "-dtls1_2",
            "-psk_identity", psk_identity,
            "-psk", self.client_key,
            "-cipher", "PSK-AES128-GCM-SHA256:PSK-CHACHA20-POLY1305",
            "-connect", f"{self.bridge_ip}:{HueStreamProtocol.PORT}",
            "-quiet",
        ]

    def _wait_for_handshake(self) -> bool:
        """Wait for DTLS handshake to complete."""
        time.sleep(self._connection_timeout)
        
        if self._openssl_proc.poll() is not None:
            return self._report_handshake_failure("initial connection")
        
        time.sleep(self._handshake_delay)
        
        if self._openssl_proc.poll() is not None:
            return self._report_handshake_failure("handshake")
        
        timed_print(f"DTLS connection established to {self.bridge_ip}:{HueStreamProtocol.PORT}")
        return True

    def _report_handshake_failure(self, stage: str) -> bool:
        """Report handshake failure and cleanup."""
        if self._openssl_proc:
            stdout, stderr = self._openssl_proc.communicate()
            print(f"DTLS {stage} failed (exit code {self._openssl_proc.returncode})")
            print(f"stderr: {stderr.decode()}")
        return False

    def disconnect(self, bridge: 'HueBridge') -> None:
        """Close DTLS connection and deactivate streaming."""
        self._connected = False
        self._cleanup_openssl()
        self._deactivate_streaming(bridge)
        timed_print("Entertainment stream disconnected")

    def _cleanup_openssl(self) -> None:
        """Clean up OpenSSL subprocess."""
        if not self._openssl_proc:
            return
            
        try:
            self._openssl_proc.stdin.close()
            self._openssl_proc.terminate()
            self._openssl_proc.wait(timeout=2)
        except Exception:
            try:
                self._openssl_proc.kill()
            except Exception:
                pass
        finally:
            self._openssl_proc = None

    def is_connected(self) -> bool:
        """Check if DTLS connection is active."""
        if self._openssl_proc:
            return self._connected and self._openssl_proc.poll() is None
        return self._connected

    def send_colors(self, colors: Dict[int, Tuple[float, float, float, float]]) -> None:
        """Send color update to all channels (RGB format).

        Args:
            colors: Dict mapping channel_id to (r, g, b, _) tuple
                   where r, g, b are 0.0-1.0
        """
        if not self.is_connected():
            return

        with self._lock:
            try:
                message = self._build_rgb_message(colors)
                self._send_dtls_message(message)
                self._sequence = (self._sequence + 1) % 256
            except Exception as e:
                print(f"Error sending colors: {e}")
                self._connected = False

    def send_colors_xy(
        self,
        channel_colors: Dict[int, Tuple[Tuple[float, float], int]]
    ) -> None:
        """Send color update using XY + brightness format.

        Args:
            channel_colors: Dict mapping channel_id to ((x, y), brightness) tuple
                           where x, y are CIE color coordinates and brightness is 0-254
        """
        if not self.is_connected():
            return

        with self._lock:
            try:
                message = self._build_xy_message(channel_colors)
                self._send_dtls_message(message)
                self._sequence = (self._sequence + 1) % 256
            except Exception as e:
                print(f"Error sending colors: {e}")
                self._connected = False

    def _send_dtls_message(self, message: bytes) -> None:
        """Send a message over the DTLS connection."""
        if self._openssl_proc:
            self._send_via_openssl(message)
        elif self._dtls_socket:
            self._send_via_socket(message)
        else:
            raise ConnectionError("No DTLS connection available")

    def _send_via_openssl(self, message: bytes) -> None:
        """Send message via OpenSSL subprocess."""
        try:
            self._openssl_proc.stdin.write(message)
            self._openssl_proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            print(f"DTLS connection lost: {e}")
            self._connected = False
            raise

    def _send_via_socket(self, message: bytes) -> None:
        """Send message via native DTLS socket."""
        try:
            self._dtls_socket.send(message)
        except OSError as e:
            print(f"DTLS socket error: {e}")
            self._connected = False
            raise

    def _build_rgb_message(
        self,
        colors: Dict[int, Tuple[float, float, float, float]]
    ) -> bytes:
        """Build HueStream v2 message with RGB color space."""
        header = self._build_message_header(HueStreamProtocol.COLORSPACE_RGB)
        data = self._build_rgb_channel_data(colors)
        return bytes(header + data)

    def _build_xy_message(
        self,
        colors: Dict[int, Tuple[Tuple[float, float], int]]
    ) -> bytes:
        """Build HueStream v2 message with XY+Brightness color space."""
        header = self._build_message_header(HueStreamProtocol.COLORSPACE_XY)
        data = self._build_xy_channel_data(colors)
        return bytes(header + data)

    def _build_message_header(self, colorspace: int) -> bytearray:
        """Build HueStream message header."""
        header = bytearray()
        header.extend(HueStreamProtocol.HEADER)
        header.append(HueStreamProtocol.VERSION_MAJOR)
        header.append(HueStreamProtocol.VERSION_MINOR)
        header.append(self._sequence)
        header.extend([0x00, 0x00])  # Reserved
        header.append(colorspace)
        header.append(0x00)  # Reserved
        header.extend(self.entertainment_config_id.encode('ascii'))
        return header

    def _build_rgb_channel_data(
        self,
        colors: Dict[int, Tuple[float, float, float, float]]
    ) -> bytearray:
        """Build RGB channel data section."""
        data = bytearray()
        for channel_id in sorted(self._channels.keys()):
            r, g, b = self._extract_rgb(colors, channel_id)
            data.append(channel_id)
            data.extend(self._color_to_bytes(r))
            data.extend(self._color_to_bytes(g))
            data.extend(self._color_to_bytes(b))
        return data

    def _build_xy_channel_data(
        self,
        colors: Dict[int, Tuple[Tuple[float, float], int]]
    ) -> bytearray:
        """Build XY+Brightness channel data section."""
        data = bytearray()
        for channel_id in sorted(self._channels.keys()):
            (x, y), brightness = self._extract_xy_brightness(colors, channel_id)
            data.append(channel_id)
            data.extend(self._color_to_bytes(x))
            data.extend(self._color_to_bytes(y))
            data.extend(self._brightness_to_bytes(brightness))
        return data

    def _extract_rgb(
        self,
        colors: Dict[int, Tuple[float, float, float, float]],
        channel_id: int
    ) -> Tuple[float, float, float]:
        """Extract RGB values from colors dict."""
        if channel_id in colors:
            r, g, b, _ = colors[channel_id]
            return r, g, b
        return 0.0, 0.0, 0.0

    def _extract_xy_brightness(
        self,
        colors: Dict[int, Tuple[Tuple[float, float], int]],
        channel_id: int
    ) -> Tuple[Tuple[float, float], int]:
        """Extract XY and brightness values from colors dict."""
        if channel_id in colors:
            return colors[channel_id]
        return (0.0, 0.0), 0

    def _color_to_bytes(self, value: float) -> list[int]:
        """Convert 0-1 float to 2 big-endian bytes."""
        scaled = int(max(0, min(1, value)) * HueStreamProtocol.MAX_16BIT)
        return [(scaled >> 8) & 0xFF, scaled & 0xFF]

    def _brightness_to_bytes(self, brightness: int) -> list[int]:
        """Convert 0-254 brightness to 2 big-endian bytes."""
        scaled = int(max(0, min(254, brightness)) * HueStreamProtocol.BRIGHTNESS_SCALE)
        return [(scaled >> 8) & 0xFF, scaled & 0xFF]

    def get_channel_positions(self) -> Dict[int, dict]:
        """Get mapping of channel IDs to their 3D positions.

        Returns dict of channel_id -> {'x': float, 'y': float, 'z': float}
        Positions are normalized: x=-1 to 1 (left to right),
        y=-1 to 1 (front to back), z=0 to 1 (bottom to top)
        """
        return {
            channel_id: {
                'x': info.position.get('x', 0),
                'y': info.position.get('y', 0),
                'z': info.position.get('z', 0)
            }
            for channel_id, info in self._channels.items()
        }

    def map_zone_to_channel(self, zone_id: str) -> Optional[int]:
        """Map a screen zone ID to an entertainment channel ID based on position.

        Args:
            zone_id: Zone identifier like 'top_0', 'left_1', 'right_2', 'bottom_3'

        Returns:
            Best matching channel_id or None
        """
        if not self._channels:
            return None

        try:
            edge, idx_str = zone_id.split('_')
            idx = int(idx_str)
        except ValueError:
            return None

        edge_positions = self._get_edge_position_ranges()
        if edge not in edge_positions:
            return None

        matching_channels = self._find_channels_for_edge(edge, edge_positions[edge])
        
        if not matching_channels:
            return next(iter(self._channels.keys()), None)

        # Sort and pick by index
        matching_channels.sort(key=lambda c: c[1])
        idx = min(idx, len(matching_channels) - 1)
        return matching_channels[idx][0]

    def _get_edge_position_ranges(self) -> Dict[str, dict]:
        """Get position ranges for each screen edge."""
        return {
            'top': {'z_min': 0.5, 'z_max': 1.0},
            'bottom': {'z_min': -1.0, 'z_max': -0.5},
            'left': {'x_min': -1.0, 'x_max': -0.5},
            'right': {'x_min': 0.5, 'x_max': 1.0}
        }

    def _find_channels_for_edge(
        self,
        edge: str,
        edge_range: dict
    ) -> list[tuple[int, float]]:
        """Find channels matching the given edge."""
        matching = []
        
        for channel_id, info in self._channels.items():
            pos = info.position
            x = pos.get('x', 0)
            z = pos.get('z', 0)

            matches, sort_key = self._channel_matches_edge(edge, edge_range, x, z)
            if matches:
                matching.append((channel_id, sort_key))
        
        return matching

    def _channel_matches_edge(
        self,
        edge: str,
        edge_range: dict,
        x: float,
        z: float
    ) -> Tuple[bool, float]:
        """Check if channel position matches edge, return (matches, sort_key)."""
        if edge in ('left', 'right'):
            if edge_range['x_min'] <= x <= edge_range['x_max']:
                return True, z  # Sort by height for left/right
        else:  # top/bottom
            if edge_range['z_min'] <= z <= edge_range['z_max']:
                return True, x  # Sort by x position for top/bottom
        return False, 0.0
