#!/usr/bin/env python
"""Test entertainment streaming with simple colors."""

import subprocess
import time
import struct
import json
import urllib.request
import ssl

BRIDGE_IP = "192.168.2.107"
PORT = 2100
APP_KEY = "X7Lyq8FJ8ha1h7DGVmNeCqYTAJxXw2wKa-rg0XjS"
CLIENT_KEY = "9B2AEF6437497AAFA703214009E8EFB1"
ENTERTAINMENT_CONFIG_ID = "192d98c5-7adc-4dd5-ac13-fd9d010cf04a"


def api_call(method, endpoint, data=None):
    """Make API call to bridge."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    url = f"https://{BRIDGE_IP}/clip/v2/resource/{endpoint}"
    req = urllib.request.Request(url, method=method)
    req.add_header('hue-application-key', APP_KEY)
    req.add_header('Content-Type', 'application/json')
    
    if data:
        req.data = json.dumps(data).encode('utf-8')
    
    try:
        resp = urllib.request.urlopen(req, context=ctx, timeout=5)
        return json.loads(resp.read().decode())
    except Exception as e:
        print(f"API error: {e}")
        return None


def build_message_v1(channel_colors):
    """Build HueStream v1 message (simpler format).
    
    Format based on Philips Hue Entertainment API documentation:
    Header (16 bytes):
    - "HueStream" (9 bytes)
    - Version: 0x01 0x00 (2 bytes) - API version 1.0
    - Sequence: 0x00 (1 byte)
    - Reserved: 0x00 0x00 (2 bytes)
    - Color space: 0x00=RGB, 0x01=XY (1 byte)
    - Reserved: 0x00 (1 byte)
    
    Per light (7 bytes each):
    - Light type: 0x00=Light (1 byte)  
    - Light ID: 16-bit big-endian (2 bytes) - NOT channel_id, but device_id from members
    - R/X: 16-bit big-endian (2 bytes)
    - G/Y: 16-bit big-endian (2 bytes)
    - B/Bri: 16-bit big-endian (2 bytes) - wait, that's 9 bytes total per light
    """
    # Let's try the exact format from official examples
    header = b"HueStream"
    header += bytes([0x01, 0x00])  # Version 1.0
    header += bytes([0x00])  # Sequence
    header += bytes([0x00, 0x00])  # Reserved
    header += bytes([0x00])  # Color space: RGB
    header += bytes([0x00])  # Reserved
    
    # Per-channel: type (1) + id (2) + R (2) + G (2) + B (2) = 9 bytes
    data = b""
    for channel_id, (r, g, b) in sorted(channel_colors.items()):
        data += bytes([0x00])  # Type: light
        data += struct.pack(">H", channel_id)  # Channel ID (2 bytes big-endian)
        data += struct.pack(">HHH", r, g, b)  # R, G, B (16-bit each)
    
    return header + data


def build_message_simple(channel_colors):
    """Build simplest possible HueStream message."""
    # Minimal header
    msg = b"HueStream"  # 9 bytes
    msg += bytes([0x01, 0x00])  # API version 1.0
    msg += bytes([0x00])  # Sequence number
    msg += bytes([0x00, 0x00])  # Reserved
    msg += bytes([0x00])  # Colorspace: RGB
    msg += bytes([0x00])  # Reserved (or entertainment area byte)
    
    # Channel data
    for channel_id, (r, g, b) in sorted(channel_colors.items()):
        msg += bytes([0x00])  # Device type: Light
        msg += struct.pack(">H", channel_id)  # Channel ID
        msg += struct.pack(">HHH", r, g, b)  # R, G, B
    
    return msg


def build_message_with_v1_lights(light_colors):
    """Build HueStream message using v1 API light IDs."""
    # Header
    msg = b"HueStream"  # 9 bytes
    msg += bytes([0x01, 0x00])  # API version 1.0
    msg += bytes([0x00])  # Sequence number
    msg += bytes([0x00, 0x00])  # Reserved
    msg += bytes([0x00])  # Colorspace: RGB
    msg += bytes([0x00])  # Reserved
    
    # Per-light data using v1 light IDs
    for light_v1_id, (r, g, b) in sorted(light_colors.items()):
        msg += bytes([0x00])  # Device type: Light
        msg += struct.pack(">H", light_v1_id)  # v1 Light ID (e.g., 1, 4, etc)
        msg += struct.pack(">HHH", r, g, b)  # R, G, B
    
    return msg


def build_message_v2(channel_colors, entertainment_id):
    """Build HueStream v2 message."""
    # Header for API v2
    header = b"HueStream"
    header += struct.pack(">BB", 2, 0)  # API version 2.0
    header += struct.pack(">B", 0)  # Sequence
    header += struct.pack(">BB", 0, 0)  # Reserved
    header += struct.pack(">B", 0)  # Color space: 0=RGB
    header += struct.pack(">B", 0)  # Reserved
    
    # In v2, we need the entertainment group ID bytes (first 16 chars of UUID without dashes)
    # The entertainment_id is like "192d98c5-7adc-4dd5-ac13-fd9d010cf04a"
    # We need the first 8 bytes as a 64-bit value
    uuid_clean = entertainment_id.replace('-', '')
    group_bytes = bytes.fromhex(uuid_clean[:16])  # First 8 bytes
    header += group_bytes
    
    # Per-channel: 1 byte type + 1 byte id + 6 bytes RGB (16-bit each)
    data = b""
    for channel_id, (r, g, b) in sorted(channel_colors.items()):
        data += struct.pack(">B", 0)  # Device type: light
        data += struct.pack(">B", channel_id)  # Channel ID (1 byte in v2)
        data += struct.pack(">HHH", r, g, b)  # R, G, B (16-bit)
    
    return header + data


def test_stream():
    """Test entertainment streaming."""
    print("=" * 60)
    print("Testing Entertainment Streaming")
    print("=" * 60)
    
    # Get entertainment config
    print("\n1. Getting entertainment config...")
    result = api_call('GET', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}')
    channel_ids = []
    if result:
        config = result.get('data', [{}])[0]
        channels = config.get('channels', [])
        print(f"   Found {len(channels)} channels")
        for ch in channels:
            ch_id = ch.get('channel_id')
            members = ch.get('members', [])
            channel_ids.append(ch_id)
            print(f"   Channel {ch_id}: pos={ch.get('position')}, members={len(members)}")
            for m in members:
                svc = m.get('service', {})
                print(f"      - {svc.get('rtype')}: {svc.get('rid')}")
    
    if not channel_ids:
        channel_ids = list(range(11))
    
    # Activate streaming
    print("\n2. Activating streaming...")
    result = api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
                      {"action": "start"})
    print(f"   Result: {result}")
    
    time.sleep(0.5)
    
    # Start DTLS connection
    print("\n3. Starting DTLS connection...")
    cmd = [
        "openssl", "s_client",
        "-dtls1_2",
        "-psk_identity", APP_KEY,
        "-psk", CLIENT_KEY,
        "-connect", f"{BRIDGE_IP}:{PORT}",
    ]
    
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    time.sleep(1)
    
    if proc.poll() is not None:
        print("   DTLS connection failed!")
        stdout, stderr = proc.communicate()
        print(f"   stderr: {stderr.decode()}")
        api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
                 {"action": "stop"})
        return
    
    print("   DTLS connected!")
    
    # Test with v1 light IDs (from id_v1 field: /lights/1, /lights/4, etc)
    print("\n4. Testing with v1 light IDs...")
    
    # v1 light IDs from the entertainment services
    v1_light_ids = [1, 4]  # /lights/1 and /lights/4 based on API response
    print(f"   Testing v1 light IDs: {v1_light_ids}")
    
    # Bright RED
    print("\n   === RED (v1 light IDs) ===")
    colors = {lid: (65535, 0, 0) for lid in v1_light_ids}
    msg = build_message_with_v1_lights(colors)
    print(f"   Message ({len(msg)} bytes): {msg.hex()}")
    for _ in range(50):
        proc.stdin.write(msg)
        proc.stdin.flush()
        time.sleep(0.033)  # ~30 fps
    print("   Sent 50 packets - check if lights are RED")
    time.sleep(3)
    
    # Also try with channel IDs
    print("\n   === GREEN (channel IDs 0,1,2) ===")
    colors = {0: (0, 65535, 0), 1: (0, 65535, 0), 2: (0, 65535, 0)}
    msg = build_message_simple(colors)
    print(f"   Message ({len(msg)} bytes): {msg.hex()}")
    for _ in range(50):
        proc.stdin.write(msg)
        proc.stdin.flush()
        time.sleep(0.033)
    print("   Sent 50 packets - check if lights are GREEN")
    time.sleep(3)
    
    # Bright BLUE - try all channels 0-10
    print("\n   === BLUE (all channels 0-10) ===")
    colors = {i: (0, 0, 65535) for i in range(11)}
    msg = build_message_simple(colors)
    print(f"   Message ({len(msg)} bytes): {msg[:40].hex()}...")
    for _ in range(50):
        proc.stdin.write(msg)
        proc.stdin.flush()
        time.sleep(0.033)
    print("   Sent 50 packets - check if lights are BLUE")
    time.sleep(3)
    
    # Clean up
    print("\n5. Cleaning up...")
    try:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=2)
    except:
        proc.kill()
    
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "stop"})
    
    print("\nDone! Did you see the lights change to red, then green, then blue?")


if __name__ == "__main__":
    test_stream()
