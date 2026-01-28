#!/usr/bin/env python
"""Test HueStream with CORRECT format per official API docs."""

import subprocess
import time
import json
import urllib.request
import ssl

BRIDGE_IP = "192.168.2.107"
PORT = 2100
APP_KEY = "X7Lyq8FJ8ha1h7DGVmNeCqYTAJxXw2wKa-rg0XjS"
CLIENT_KEY = "9B2AEF6437497AAFA703214009E8EFB1"
ENTERTAINMENT_CONFIG_ID = "192d98c5-7adc-4dd5-ac13-fd9d010cf04a"


def api_call(method, endpoint, data=None, return_headers=False):
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
        if return_headers:
            return json.loads(resp.read().decode()), dict(resp.headers)
        return json.loads(resp.read().decode())
    except Exception as e:
        print(f"API error: {e}")
        return None


def get_application_id():
    """Get hue-application-id from /auth/v1 endpoint."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    url = f"https://{BRIDGE_IP}/auth/v1"
    req = urllib.request.Request(url, method='GET')
    req.add_header('hue-application-key', APP_KEY)
    
    try:
        resp = urllib.request.urlopen(req, context=ctx, timeout=5)
        headers = dict(resp.headers)
        app_id = headers.get('hue-application-id')
        print(f"Got hue-application-id: {app_id}")
        return app_id
    except Exception as e:
        print(f"Error getting application ID: {e}")
        return None


def build_message(channel_colors, ent_config_id, sequence=0):
    """
    Build HueStream message per official API docs.
    
    Format (from docs):
    - Protocol name: 9 bytes "HueStream"
    - Version: 2 bytes (0x02, 0x00)
    - Sequence ID: 1 byte
    - Reserved: 2 bytes (zeros)
    - Color space: 1 byte (0x00 = RGB)
    - Reserved: 1 byte (zero)
    - Entertainment config ID: 36 bytes ASCII UUID string
    - Channel data: 7 bytes per channel (1 byte ID + 6 bytes RGB16)
    """
    msg = bytearray()
    
    # Protocol name (9 bytes)
    msg.extend(b"HueStream")
    
    # Version 2.0 (2 bytes)
    msg.extend([0x02, 0x00])
    
    # Sequence ID (1 byte)
    msg.append(sequence % 256)
    
    # Reserved (2 bytes)
    msg.extend([0x00, 0x00])
    
    # Color space: RGB (1 byte)
    msg.append(0x00)
    
    # Reserved (1 byte)
    msg.append(0x00)
    
    # Entertainment configuration ID (36 bytes ASCII)
    msg.extend(ent_config_id.encode('ascii'))
    
    # Channel data (7 bytes each)
    for channel_id, (r, g, b) in sorted(channel_colors.items()):
        # Channel ID (1 byte)
        msg.append(channel_id)
        
        # RGB 16-bit values (2 bytes each, big-endian)
        msg.extend([(r >> 8) & 0xFF, r & 0xFF])  # R high, R low
        msg.extend([(g >> 8) & 0xFF, g & 0xFF])  # G high, G low
        msg.extend([(b >> 8) & 0xFF, b & 0xFF])  # B high, B low
    
    return bytes(msg)


def main():
    print("=== HueStream Test with CORRECT API Format ===\n")
    
    # Step 1: Get the application ID
    print("Step 1: Getting hue-application-id...")
    app_id = get_application_id()
    if not app_id:
        print("Failed to get application ID, falling back to APP_KEY")
        app_id = APP_KEY
    
    # Step 2: Stop any existing streaming
    print("\nStep 2: Stopping any active streaming...")
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "stop"})
    time.sleep(0.5)
    
    # Step 3: Start streaming
    print("\nStep 3: Activating streaming mode...")
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "start"})
    time.sleep(1)
    
    # Check status
    result = api_call('GET', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}')
    if result:
        status = result['data'][0].get('status')
        streamer = result['data'][0].get('active_streamer')
        print(f"Status: {status}, Streamer: {streamer}")
        if status != 'active':
            print("ERROR: Streaming not active!")
            return
    
    # Step 4: Build and show message format
    print("\n=== Message Format ===")
    colors_red = {i: (0xFFFF, 0, 0) for i in range(11)}  # 16-bit max red
    test_msg = build_message(colors_red, ENTERTAINMENT_CONFIG_ID, 0)
    
    print(f"Total length: {len(test_msg)} bytes")
    print(f"  Header (HueStream): {test_msg[0:9]}")
    print(f"  Version: {test_msg[9]:02x} {test_msg[10]:02x}")
    print(f"  Sequence: {test_msg[11]:02x}")
    print(f"  Reserved: {test_msg[12]:02x} {test_msg[13]:02x}")
    print(f"  Color space: {test_msg[14]:02x}")
    print(f"  Reserved: {test_msg[15]:02x}")
    print(f"  Ent Config ID (36 bytes ASCII): {test_msg[16:52].decode()}")
    print(f"  First channel (7 bytes): {test_msg[52:59].hex()}")
    print(f"  Full hex:\n  {test_msg.hex()}")
    
    # Step 5: Connect DTLS with correct PSK identity
    print(f"\nStep 5: Connecting DTLS...")
    print(f"  PSK Identity: {app_id}")
    print(f"  PSK (client key): {CLIENT_KEY}")
    
    proc = subprocess.Popen(
        ["openssl", "s_client", "-dtls1_2",
         "-psk_identity", app_id,
         "-psk", CLIENT_KEY,
         "-cipher", "PSK-AES128-GCM-SHA256:PSK-CHACHA20-POLY1305",
         "-connect", f"{BRIDGE_IP}:{PORT}",
         "-quiet"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    time.sleep(1.5)
    
    if proc.poll() is not None:
        stderr = proc.stderr.read().decode()
        print(f"DTLS connection FAILED!")
        print(f"stderr: {stderr}")
        api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
                 {"action": "stop"})
        return
    
    print("DTLS connected!")
    
    # Step 6: Send colors
    print("\n=== Sending Colors ===")
    fps = 50  # 50-60 Hz recommended
    
    colors = [
        ("RED", {i: (0xFFFF, 0, 0) for i in range(11)}),
        ("GREEN", {i: (0, 0xFFFF, 0) for i in range(11)}),
        ("BLUE", {i: (0, 0, 0xFFFF) for i in range(11)}),
        ("WHITE", {i: (0xFFFF, 0xFFFF, 0xFFFF) for i in range(11)}),
    ]
    
    seq = 0
    for name, color_map in colors:
        print(f"Sending {name} for 3 seconds...")
        for _ in range(fps * 3):
            try:
                msg = build_message(color_map, ENTERTAINMENT_CONFIG_ID, seq)
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
    
    print("\n========================================")
    print("Did you see RED -> GREEN -> BLUE -> WHITE?")
    print("========================================")


if __name__ == "__main__":
    main()
