#!/usr/bin/env python
"""Test HueStream with all channels in one message."""

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


def build_complete_message(channel_colors, sequence=0):
    """Build complete HueStream message with all channels."""
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
    print("Testing HueStream with complete multi-channel messages\n")
    
    # Activate streaming
    print("Activating streaming...")
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "start"})
    time.sleep(0.5)
    
    # Start DTLS
    print("Starting DTLS connection...")
    proc = subprocess.Popen(
        ["openssl", "s_client", "-dtls1_2",
         "-psk_identity", APP_KEY,
         "-psk", CLIENT_KEY,
         "-connect", f"{BRIDGE_IP}:{PORT}"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    time.sleep(1)
    
    if proc.poll() is not None:
        print("DTLS failed!")
        api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
                 {"action": "stop"})
        return
    
    print("DTLS connected!\n")
    
    # All channels bright RED
    print("=== Setting ALL channels to BRIGHT RED ===")
    colors = {i: (65535, 0, 0) for i in range(11)}
    msg = build_complete_message(colors)
    print(f"Message ({len(msg)} bytes)")
    print(f"Hex: {msg.hex()}\n")
    
    # Send many times
    seq = 0
    for _ in range(60):  # 3 seconds at 20fps
        msg = build_complete_message(colors, seq)
        proc.stdin.write(msg)
        proc.stdin.flush()
        seq = (seq + 1) % 256
        time.sleep(0.05)
    
    print("Sent 60 packets, waiting 2s... ARE LIGHTS RED?\n")
    time.sleep(2)
    
    # All channels bright GREEN
    print("=== Setting ALL channels to BRIGHT GREEN ===")
    colors = {i: (0, 65535, 0) for i in range(11)}
    
    for _ in range(60):
        msg = build_complete_message(colors, seq)
        proc.stdin.write(msg)
        proc.stdin.flush()
        seq = (seq + 1) % 256
        time.sleep(0.05)
    
    print("Sent 60 packets, waiting 2s... ARE LIGHTS GREEN?\n")
    time.sleep(2)
    
    # All channels bright BLUE
    print("=== Setting ALL channels to BRIGHT BLUE ===")
    colors = {i: (0, 0, 65535) for i in range(11)}
    
    for _ in range(60):
        msg = build_complete_message(colors, seq)
        proc.stdin.write(msg)
        proc.stdin.flush()
        seq = (seq + 1) % 256
        time.sleep(0.05)
    
    print("Sent 60 packets, waiting 2s... ARE LIGHTS BLUE?\n")
    time.sleep(2)
    
    # Cleanup
    print("Cleaning up...")
    proc.stdin.close()
    proc.terminate()
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "stop"})
    
    print("\nDone! Did you see the lights change color?")


if __name__ == "__main__":
    main()
