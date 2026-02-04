"""Hue Entertainment API streaming via DTLS-PSK.

This module implements the Hue Entertainment streaming protocol which allows
low-latency color updates to lights in an entertainment zone using DTLS over UDP.
"""

import struct
import subprocess
import threading
import time
from datetime import datetime
from typing import Dict, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from lumux.bridge import HueBridge


def _timed_print(*args, **kwargs):
    prefix = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    print(prefix, *args, **kwargs)


# HueStream protocol constants
HUESTREAM_HEADER = b"HueStream"
HUESTREAM_VERSION_MAJOR = 0x02  # API version 2.0
HUESTREAM_VERSION_MINOR = 0x00
HUESTREAM_COLORSPACE_RGB = 0x00
HUESTREAM_COLORSPACE_XY = 0x01
ENTERTAINMENT_PORT = 2100


class EntertainmentStream:
    """Manages DTLS connection and streaming to a Hue Entertainment zone."""

    def __init__(self, bridge_ip: str, app_key: str, client_key: str,
                 entertainment_config_id: str):
        """Initialize entertainment stream.

        Args:
            bridge_ip: IP address of the Hue bridge
            app_key: Application key (username) - used to get hue-application-id
            client_key: Client key - used as PSK (32-byte hex string)
            entertainment_config_id: ID of the entertainment configuration to stream to
        """
        self.bridge_ip = bridge_ip
        self.app_key = app_key
        self.client_key = client_key
        self.entertainment_config_id = entertainment_config_id
        self._application_id = None  # Retrieved from /auth/v1

        self._dtls_socket = None
        self._openssl_proc = None  # OpenSSL subprocess for DTLS
        self._connected = False
        self._sequence = 0
        self._lock = threading.Lock()

        # Channel mapping: channel_id -> position info
        self.channels: Dict[int, dict] = {}
        # Reverse mapping: light_id -> channel_id (for convenience)
        self.light_to_channel: Dict[str, int] = {}

    def connect(self, bridge: 'HueBridge') -> bool:
        """Establish DTLS connection to the bridge.

        Args:
            bridge: HueBridge instance to use for API calls

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # First, get entertainment configuration details
            config = bridge.get_entertainment_configuration(self.entertainment_config_id)
            if not config:
                print(f"Entertainment configuration {self.entertainment_config_id} not found")
                return False

            # Parse channels from the configuration
            self._parse_channels(config)

            # Get hue-application-id for PSK identity
            self._application_id = self._get_application_id(bridge)
            if not self._application_id:
                _timed_print("Warning: Could not get hue-application-id, falling back to app_key")
                self._application_id = self.app_key
            else:
                _timed_print(f"Got hue-application-id: {self._application_id}")

            # Activate streaming via REST API
            if not bridge.activate_entertainment_streaming(self.entertainment_config_id):
                print("Failed to activate entertainment streaming")
                return False

            # Give the bridge a moment to prepare for DTLS connections
            import time
            time.sleep(0.5)

            # Establish DTLS connection
            if not self._connect_dtls():
                bridge.deactivate_entertainment_streaming(self.entertainment_config_id)
                return False

            self._connected = True
            _timed_print(f"Entertainment stream connected with {len(self.channels)} channels")
            return True

        except Exception as e:
            print(f"Error connecting entertainment stream: {e}")
            return False

    def _get_application_id(self, bridge: 'HueBridge') -> Optional[str]:
        """Get hue-application-id from /auth/v1 endpoint.
        
        This is the correct PSK identity for DTLS connection per official API docs.
        """
        try:
            return bridge.get_application_id()
        except Exception as e:
            _timed_print(f"Error getting application ID: {e}")
            return None

    def _parse_channels(self, config: dict):
        """Parse channel information from entertainment configuration."""
        self.channels.clear()
        self.light_to_channel.clear()

        channels = config.get('channels', [])
        _timed_print(f"Entertainment config has {len(channels)} channel entries")
        
        for channel in channels:
            channel_id = channel.get('channel_id')
            if channel_id is None:
                _timed_print(f"  Skipping channel without ID: {channel}")
                continue

            position = channel.get('position', {})
            members = channel.get('members', [])

            self.channels[channel_id] = {
                'channel_id': channel_id,
                'position': position,
                'members': members
            }
            
            _timed_print(f"  Channel {channel_id}: pos=({position.get('x', 0):.2f}, {position.get('y', 0):.2f}, {position.get('z', 0):.2f}), {len(members)} members")

            # Map member light IDs to channel
            for member in members:
                service = member.get('service', {})
                light_rid = service.get('rid')
                if light_rid:
                    self.light_to_channel[light_rid] = channel_id

        _timed_print(f"Parsed {len(self.channels)} channels from entertainment config")

    def _connect_dtls(self) -> bool:
        """Establish DTLS-PSK connection to bridge port 2100.
        
        Uses openssl s_client subprocess for DTLS-PSK connection.
        """
        import subprocess
        
        try:
            # Start openssl s_client for DTLS-PSK
            # PSK identity must be hue-application-id (from /auth/v1), not app_key
            psk_identity = self._application_id or self.app_key
            cmd = [
                "openssl", "s_client",
                "-dtls1_2",
                "-psk_identity", psk_identity,
                "-psk", self.client_key,
                "-cipher", "PSK-AES128-GCM-SHA256:PSK-CHACHA20-POLY1305",
                "-connect", f"{self.bridge_ip}:{ENTERTAINMENT_PORT}",
                "-quiet",
            ]
            
            _timed_print(f"Starting DTLS connection: openssl s_client -dtls1_2 -connect {self.bridge_ip}:{ENTERTAINMENT_PORT}")
            
            self._openssl_proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            # Wait for connection to establish
            time.sleep(0.5)
            
            # Check if process is still running
            if self._openssl_proc.poll() is not None:
                stdout, stderr = self._openssl_proc.communicate()
                print(f"DTLS connection failed (exit code {self._openssl_proc.returncode})")
                print(f"stderr: {stderr.decode()}")
                return False
            
            # Verify handshake succeeded by checking if process is ready for input
            # A successful handshake means the process stays alive and accepts data
            import select
            # Give it a bit more time for handshake to complete
            time.sleep(0.3)
            
            # Check again if process is still running after handshake period
            if self._openssl_proc.poll() is not None:
                stdout, stderr = self._openssl_proc.communicate()
                print(f"DTLS handshake failed (exit code {self._openssl_proc.returncode})")
                print(f"stderr: {stderr.decode()}")
                return False
            
            _timed_print(f"DTLS connection established to {self.bridge_ip}:{ENTERTAINMENT_PORT}")
            return True

        except FileNotFoundError:
            print("DTLS connection failed: openssl command not found")
            return False
        except Exception as e:
            print(f"DTLS connection failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def disconnect(self, bridge: 'HueBridge'):
        """Close DTLS connection and deactivate streaming."""
        self._connected = False

        # Clean up subprocess-based DTLS connection
        if self._openssl_proc:
            try:
                self._openssl_proc.stdin.close()
                self._openssl_proc.terminate()
                self._openssl_proc.wait(timeout=2)
            except Exception:
                try:
                    self._openssl_proc.kill()
                except:
                    pass
            self._openssl_proc = None

        if self._dtls_socket:
            try:
                self._dtls_socket.shutdown()
                self._dtls_socket.close()
            except Exception:
                pass
            self._dtls_socket = None

        # Deactivate streaming via REST API
        try:
            bridge.deactivate_entertainment_streaming(self.entertainment_config_id)
        except Exception as e:
            print(f"Error deactivating streaming: {e}")

        _timed_print("Entertainment stream disconnected")

    def is_connected(self) -> bool:
        """Check if DTLS connection is active."""
        if self._openssl_proc:
            return self._connected and self._openssl_proc.poll() is None
        return self._connected and self._dtls_socket is not None

    def send_colors(self, colors: Dict[int, Tuple[float, float, float, float]]):
        """Send color update to all channels.

        Args:
            colors: Dict mapping channel_id to (x, y, brightness, _) tuple
                   where x, y are CIE color coordinates (0.0-1.0)
                   and brightness is 0.0-1.0
        """
        if not self.is_connected():
            return

        with self._lock:
            try:
                message = self._build_message(colors)
                self._send_dtls_message(message)
                self._sequence = (self._sequence + 1) % 256
            except Exception as e:
                print(f"Error sending colors: {e}")
                self._connected = False

    def send_colors_xy(self, channel_colors: Dict[int, Tuple[Tuple[float, float], int]]):
        """Send color update using XY + brightness format.

        Args:
            channel_colors: Dict mapping channel_id to ((x, y), brightness) tuple
                           where x, y are CIE color coordinates and brightness is 0-254
        """
        if not self.is_connected():
            return

        with self._lock:
            try:
                message = self._build_message_xy(channel_colors)
                self._send_dtls_message(message)
                self._sequence = (self._sequence + 1) % 256
            except Exception as e:
                print(f"Error sending colors: {e}")
                self._connected = False

    def _send_dtls_message(self, message: bytes):
        """Send a message over the DTLS connection."""
        if self._openssl_proc:
            try:
                self._openssl_proc.stdin.write(message)
                self._openssl_proc.stdin.flush()
            except (BrokenPipeError, OSError) as e:
                # Connection lost, mark as disconnected
                print(f"DTLS connection lost: {e}")
                self._connected = False
                raise
        elif self._dtls_socket:
            try:
                self._dtls_socket.send(message)
            except OSError as e:
                print(f"DTLS socket error: {e}")
                self._connected = False
                raise
        else:
            raise Exception("No DTLS connection available")

    def _build_message(self, colors: Dict[int, Tuple[float, float, float, float]]) -> bytes:
        """Build HueStream v2 message with RGB color space.

        Official HueStream API format (per Hue Entertainment API docs):
        - Header: "HueStream" (9 bytes)
        - Version: 0x02 0x00 (2 bytes) - API v2.0
        - Sequence: 1 byte - increments with each message
        - Reserved: 0x00 0x00 (2 bytes)
        - Color space: 0x00=RGB, 0x01=XY+Bri (1 byte)
        - Reserved: 0x00 (1 byte)
        - Entertainment config ID: 36 bytes ASCII UUID string
        
        Per-channel (7 bytes each):
        - Channel ID: 1 byte
        - R: 2 bytes (16-bit big-endian)
        - G: 2 bytes (16-bit big-endian)
        - B: 2 bytes (16-bit big-endian)
        """
        # Build header
        header = bytearray()
        header.extend(HUESTREAM_HEADER)  # "HueStream"
        header.append(HUESTREAM_VERSION_MAJOR)  # Version 0x02
        header.append(HUESTREAM_VERSION_MINOR)  # Version 0x00
        header.append(self._sequence)  # Sequence
        header.extend([0x00, 0x00])  # Reserved
        header.append(HUESTREAM_COLORSPACE_RGB)  # Color space: RGB
        header.append(0x00)  # Reserved
        
        # Entertainment config ID (36 bytes ASCII string, NOT binary UUID)
        header.extend(self.entertainment_config_id.encode('ascii'))

        # Build channel data
        data = bytearray()
        for channel_id in sorted(self.channels.keys()):
            if channel_id in colors:
                r, g, b, _ = colors[channel_id]
            else:
                r, g, b = 0.0, 0.0, 0.0

            # Convert 0-1 float to 16-bit integer (0x0000 - 0xFFFF)
            r16 = int(max(0, min(1, r)) * 65535)
            g16 = int(max(0, min(1, g)) * 65535)
            b16 = int(max(0, min(1, b)) * 65535)

            # Channel ID (1 byte) + RGB (2 bytes each, big-endian)
            data.append(channel_id)
            data.extend([(r16 >> 8) & 0xFF, r16 & 0xFF])
            data.extend([(g16 >> 8) & 0xFF, g16 & 0xFF])
            data.extend([(b16 >> 8) & 0xFF, b16 & 0xFF])

        return bytes(header + data)

    def _build_message_xy(self, colors: Dict[int, Tuple[Tuple[float, float], int]]) -> bytes:
        """Build HueStream v2 message with XY+Brightness color space.

        Official HueStream API format:
        - Header: "HueStream" (9 bytes)
        - Version: 0x02 0x00 (2 bytes) - API v2.0
        - Sequence: 1 byte
        - Reserved: 0x00 0x00 (2 bytes)
        - Color space: 0x01 (XY+Bri) (1 byte)
        - Reserved: 0x00 (1 byte)
        - Entertainment config ID: 36 bytes ASCII UUID string
        
        Per-channel (7 bytes each):
        - Channel ID: 1 byte
        - X: 2 bytes (16-bit big-endian, 0x0000=0.0, 0xFFFF=1.0)
        - Y: 2 bytes (16-bit big-endian, 0x0000=0.0, 0xFFFF=1.0)
        - Brightness: 2 bytes (16-bit big-endian)
        """
        # Build header
        header = bytearray()
        header.extend(HUESTREAM_HEADER)  # "HueStream"
        header.append(HUESTREAM_VERSION_MAJOR)  # Version 0x02
        header.append(HUESTREAM_VERSION_MINOR)  # Version 0x00
        header.append(self._sequence)  # Sequence
        header.extend([0x00, 0x00])  # Reserved
        header.append(HUESTREAM_COLORSPACE_XY)  # Color space: XY+Bri
        header.append(0x00)  # Reserved
        
        # Entertainment config ID (36 bytes ASCII string)
        header.extend(self.entertainment_config_id.encode('ascii'))

        # Build channel data
        data = bytearray()
        for channel_id in sorted(self.channels.keys()):
            if channel_id in colors:
                (x, y), brightness = colors[channel_id]
            else:
                x, y, brightness = 0.0, 0.0, 0

            # X and Y are 0-1, scale to 16-bit (0x0000 to 0xFFFF)
            x16 = int(max(0, min(1, x)) * 65535)
            y16 = int(max(0, min(1, y)) * 65535)
            # Brightness 0-254 scaled to 16-bit
            bri16 = int(max(0, min(254, brightness)) * 257)  # 254 * 257 ≈ 65278

            # Channel ID (1 byte) + XY+Bri (2 bytes each, big-endian)
            data.append(channel_id)
            data.extend([(x16 >> 8) & 0xFF, x16 & 0xFF])
            data.extend([(y16 >> 8) & 0xFF, y16 & 0xFF])
            data.extend([(bri16 >> 8) & 0xFF, bri16 & 0xFF])

        return bytes(header + data)

    def get_channel_positions(self) -> Dict[int, dict]:
        """Get mapping of channel IDs to their 3D positions.

        Returns dict of channel_id -> {'x': float, 'y': float, 'z': float}
        Positions are normalized: x=-1 to 1 (left to right),
        y=-1 to 1 (front to back), z=0 to 1 (bottom to top)
        """
        positions = {}
        for channel_id, info in self.channels.items():
            pos = info.get('position', {})
            positions[channel_id] = {
                'x': pos.get('x', 0),
                'y': pos.get('y', 0),
                'z': pos.get('z', 0)
            }
        return positions

    def map_zone_to_channel(self, zone_id: str) -> Optional[int]:
        """Map a screen zone ID to an entertainment channel ID based on position.

        Args:
            zone_id: Zone identifier like 'top_0', 'left_1', 'right_2', 'bottom_3'

        Returns:
            Best matching channel_id or None
        """
        if not self.channels:
            return None

        # Parse zone position
        try:
            edge, idx_str = zone_id.split('_')
            idx = int(idx_str)
        except ValueError:
            return None

        # Map edge to expected x/y ranges
        # Entertainment positions: x is left-right (-1 to 1), y is front-back
        # For PC monitor setup: we'll use x and z (z is height)
        edge_positions = {
            'top': {'z_min': 0.5, 'z_max': 1.0},
            'bottom': {'z_min': -1.0, 'z_max': -0.5},
            'left': {'x_min': -1.0, 'x_max': -0.5},
            'right': {'x_min': 0.5, 'x_max': 1.0}
        }

        if edge not in edge_positions:
            return None

        # Find channels that match this edge
        matching_channels = []
        edge_range = edge_positions[edge]

        for channel_id, info in self.channels.items():
            pos = info.get('position', {})
            x = pos.get('x', 0)
            z = pos.get('z', 0)

            matches = False
            if edge in ('left', 'right'):
                if edge_range['x_min'] <= x <= edge_range['x_max']:
                    matches = True
                    sort_key = z  # Sort by height for left/right
            else:  # top/bottom
                if edge_range['z_min'] <= z <= edge_range['z_max']:
                    matches = True
                    sort_key = x  # Sort by x position for top/bottom

            if matches:
                matching_channels.append((channel_id, sort_key))

        if not matching_channels:
            # Fallback: just return any channel
            return list(self.channels.keys())[0] if self.channels else None

        # Sort channels and pick the one matching the index
        matching_channels.sort(key=lambda c: c[1])
        idx = min(idx, len(matching_channels) - 1)
        return matching_channels[idx][0]
