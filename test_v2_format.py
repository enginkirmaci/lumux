#!/usr/bin/env python
"""Test HueStream v2 with correct format from Q42.HueApi."""

import subprocess
import time
import struct
import json
import urllib.request
import ssl
import uuid

BRIDGE_IP = "192.168.2.107"
PORT = 2100
APP_KEY = "X7Lyq8FJ8ha1h7DGVmNeCqYTAJxXw2wKa-rg0XjS"
CLIENT_KEY = "9B2AEF6437497AAFA703214009E8EFB1"
ENTERTAINMENT_CONFIG_ID = "192d98c5-7adc-4dd5-ac13-fd9d010cf04a"


def api_call(method, endpoint, data=None):
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


def check_status():
    result = api_call('GET', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}')
    if result:
        cfg = result['data'][0]
        return cfg.get('status', 'unknown'), cfg.get('active_streamer')
    return 'unknown', None


def build_v2_message(channel_colors, sequence=0):
    """
    Build HueStream v2 message matching Q42.HueApi format.
    
    Format:
    - "HueStream" (9 bytes)
    - version 2.0 (0x02, 0x00)
    - sequence (1 byte)
    - reserved (0x00, 0x00)
    - color mode (0x00 = RGB)
    - linear filter (0x00)
    - entertainment config ID (16 bytes - raw UUID bytes)
    - For each channel:
      - channel_id (1 byte)
      - R, R, G, G, B, B (6 bytes - 8-bit values doubled)
    """
    msg = b"HueStream"
    
    # Version 2.0
    msg += bytes([0x02, 0x00])
    
    # Sequence number
    msg += bytes([sequence])
    
    # Reserved
    msg += bytes([0x00, 0x00])
    
    # Color mode: 0x00 = RGB
    msg += bytes([0x00])
    
    # Linear filter: 0x00 = no filter
    msg += bytes([0x00])
    
    # Entertainment configuration ID (16 bytes - raw UUID)
    ent_uuid = uuid.UUID(ENTERTAINMENT_CONFIG_ID)
    msg += ent_uuid.bytes
    
    # Add channel states
    for channel_id, (r, g, b) in sorted(channel_colors.items()):
        # Channel ID (1 byte)
        msg += bytes([channel_id])
        
        # RGB values: 8-bit doubled (R,R,G,G,B,B)
        msg += bytes([r, r, g, g, b, b])
    
    return msg


def main():
    print("=== HueStream v2 Test (Q42.HueApi format) ===\n")
    
    # Stop first
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "stop"})
    time.sleep(0.5)
    
    # Start streaming
    print("Activating streaming...")
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "start"})
    time.sleep(1)
    
    status, streamer = check_status()
    print(f"Status: {status}, Streamer: {streamer}")
    
    if status != 'active':
        print("ERROR: Streaming not active!")
        return
    
    # Connect DTLS
    print("\nConnecting DTLS...")
    proc = subprocess.Popen(
        ["openssl", "s_client", "-dtls1_2",
         "-psk_identity", APP_KEY,
         "-psk", CLIENT_KEY,
         "-connect", f"{BRIDGE_IP}:{PORT}",
         "-quiet"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    time.sleep(1.5)
    
    if proc.poll() is not None:
        print("DTLS failed!")
        api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
                 {"action": "stop"})
        return
    
    print("DTLS connected!\n")
    
    # Show message format
    print("Message format:")
    colors_red = {i: (255, 0, 0) for i in range(11)}  # 8-bit values!
    test_msg = build_v2_message(colors_red, 0)
    print(f"Length: {len(test_msg)} bytes")
    print(f"Header: {test_msg[:9].decode()}")
    print(f"Version: {test_msg[9]:02x} {test_msg[10]:02x}")
    print(f"Sequence: {test_msg[11]:02x}")
    print(f"Reserved: {test_msg[12]:02x} {test_msg[13]:02x}")
    print(f"Color mode: {test_msg[14]:02x}")
    print(f"Filter: {test_msg[15]:02x}")
    print(f"Ent Config ID: {test_msg[16:32].hex()}")
    print(f"First channel data: {test_msg[32:39].hex()}")
    print(f"Full hex: {test_msg.hex()}\n")
    
    # Test colors
    fps = 25
    seq = 0
    
    colors = [
        ("RED", {i: (255, 0, 0) for i in range(11)}),
        ("GREEN", {i: (0, 255, 0) for i in range(11)}),
        ("BLUE", {i: (0, 0, 255) for i in range(11)}),
        ("WHITE", {i: (255, 255, 255) for i in range(11)}),
    ]
    
    for name, color_map in colors:
        print(f"Sending {name} for 4 seconds...")
        for _ in range(fps * 4):
            try:
                msg = build_v2_message(color_map, seq)
                proc.stdin.write(msg)
                proc.stdin.flush()
                seq = (seq + 1) % 256
                time.sleep(1.0 / fps)
            except Exception as e:
                print(f"Write error: {e}")
                break
        
        if proc.poll() is not None:
            print("Process died!")
            break
    
    print("\nDone sending!")
    
    # Cleanup
    try:
        proc.stdin.close()
    except:
        pass
    proc.terminate()
    
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "stop"})
    
    print("\n=== Did you see RED -> GREEN -> BLUE -> WHITE? ===")


if __name__ == "__main__":
    main()
