#!/usr/bin/env python
"""Test HueStream with proper timing."""

import subprocess
import time
import struct
import json
import urllib.request
import ssl
import sys

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


def build_message(channel_colors, sequence=0):
    """Build HueStream message."""
    msg = b"HueStream"
    msg += bytes([0x01, 0x00])  # API v1.0
    msg += bytes([sequence])  # Sequence
    msg += bytes([0x00, 0x00])  # Reserved
    msg += bytes([0x00])  # RGB color space
    msg += bytes([0x00])  # Reserved
    
    for channel_id, (r, g, b) in sorted(channel_colors.items()):
        msg += bytes([0x00])  # Type: Light
        msg += struct.pack(">H", channel_id)
        msg += struct.pack(">HHH", r, g, b)
    
    return msg


def main():
    print("=== HueStream Test with Proper Sequence ===\n")
    
    # Step 1: Ensure streaming is stopped first
    print("Step 1: Stopping any active streaming...")
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "stop"})
    time.sleep(1)
    status, streamer = check_status()
    print(f"   Status: {status}, Streamer: {streamer}\n")
    
    # Step 2: Start streaming
    print("Step 2: Activating streaming mode...")
    result = api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "start"})
    print(f"   Result: {result}")
    time.sleep(1)
    
    status, streamer = check_status()
    print(f"   Status: {status}, Streamer: {streamer}")
    
    if status != 'active':
        print("   ERROR: Streaming not active! Cannot proceed.")
        return
    
    print("   Streaming is ACTIVE!\n")
    
    # Step 3: Connect DTLS
    print("Step 3: Establishing DTLS connection...")
    proc = subprocess.Popen(
        ["openssl", "s_client", "-dtls1_2",
         "-psk_identity", APP_KEY,
         "-psk", CLIENT_KEY,
         "-connect", f"{BRIDGE_IP}:{PORT}",
         "-quiet"],  # -quiet suppresses certificate output
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    # Wait for connection
    time.sleep(1.5)
    
    if proc.poll() is not None:
        stderr = proc.stderr.read().decode() if proc.stderr else ""
        print(f"   DTLS connection FAILED!")
        print(f"   stderr: {stderr}")
        api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
                 {"action": "stop"})
        return
    
    # Check streaming is still active
    status, streamer = check_status()
    print(f"   Status after DTLS: {status}")
    
    if status != 'active':
        print("   Streaming became inactive! DTLS may have failed.")
        proc.terminate()
        return
        
    print("   DTLS connected!\n")
    
    # Step 4: Send colors
    print("Step 4: Sending color commands...")
    
    colors_red = {i: (65535, 0, 0) for i in range(11)}
    colors_green = {i: (0, 65535, 0) for i in range(11)}
    colors_blue = {i: (0, 0, 65535) for i in range(11)}
    
    seq = 0
    fps = 25  # Higher frame rate
    
    print("   Sending RED for 4 seconds...")
    for _ in range(fps * 4):
        try:
            msg = build_message(colors_red, seq)
            proc.stdin.write(msg)
            proc.stdin.flush()
            seq = (seq + 1) % 256
            time.sleep(1.0 / fps)
        except Exception as e:
            print(f"   Write error: {e}")
            break
    
    # Check process is still running
    if proc.poll() is not None:
        print("   Process died!")
        stderr = proc.stderr.read().decode()
        print(f"   stderr: {stderr}")
    else:
        print("   Still connected!")
    
    print("   Sending GREEN for 4 seconds...")
    for _ in range(fps * 4):
        try:
            msg = build_message(colors_green, seq)
            proc.stdin.write(msg)
            proc.stdin.flush()
            seq = (seq + 1) % 256
            time.sleep(1.0 / fps)
        except Exception as e:
            print(f"   Write error: {e}")
            break
    
    print("   Sending BLUE for 4 seconds...")
    for _ in range(fps * 4):
        try:
            msg = build_message(colors_blue, seq)
            proc.stdin.write(msg)
            proc.stdin.flush()
            seq = (seq + 1) % 256
            time.sleep(1.0 / fps)
        except Exception as e:
            print(f"   Write error: {e}")
            break
    
    print("\n   Done sending!\n")
    
    # Cleanup
    print("Step 5: Cleanup...")
    try:
        proc.stdin.close()
    except:
        pass
    proc.terminate()
    time.sleep(0.5)
    
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "stop"})
    
    status, _ = check_status()
    print(f"   Final status: {status}\n")
    
    print("=== TEST COMPLETE ===")
    print("Did you see the lights change: RED -> GREEN -> BLUE?")


if __name__ == "__main__":
    main()
