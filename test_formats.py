#!/usr/bin/env python
"""Test HueStream format variants."""

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


# Different message format variations
def build_v1_rgb(channel_id, r, g, b):
    """HueStream v1 with RGB."""
    msg = b"HueStream"
    msg += bytes([0x01, 0x00])  # API v1.0
    msg += bytes([0x00])  # Sequence
    msg += bytes([0x00, 0x00])  # Reserved
    msg += bytes([0x00])  # RGB color space
    msg += bytes([0x00])  # Reserved
    
    msg += bytes([0x00])  # Type: Light
    msg += struct.pack(">H", channel_id)
    msg += struct.pack(">HHH", r, g, b)
    
    return msg


def build_v2_rgb(channel_id, r, g, b, entertainment_id):
    """HueStream v2 with RGB (includes entertainment group ID)."""
    msg = b"HueStream"
    msg += bytes([0x02, 0x00])  # API v2.0
    msg += bytes([0x00])  # Sequence
    msg += bytes([0x00, 0x00])  # Reserved
    msg += bytes([0x00])  # RGB color space
    msg += bytes([0x00])  # Reserved
    
    # Entertainment config ID (first 8 bytes of UUID)
    uuid_clean = entertainment_id.replace('-', '')
    msg += bytes.fromhex(uuid_clean[:16])
    
    msg += bytes([0x00])  # Type: Light
    msg += bytes([channel_id])  # Channel ID (1 byte in v2!)
    msg += struct.pack(">HHH", r, g, b)
    
    return msg


def test_format(name, msg_func):
    """Test a specific message format."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"{'='*60}")
    
    # Activate streaming
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "start"})
    time.sleep(0.5)
    
    # Start DTLS
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
    
    print("DTLS connected, sending colors...")
    
    # Send RED
    for ch in range(11):
        msg = msg_func(ch, 65535, 0, 0)
        print(f"  Channel {ch}: {msg.hex()[:60]}...")
        for _ in range(20):
            proc.stdin.write(msg)
            proc.stdin.flush()
            time.sleep(0.05)
    
    print("Sent RED to all channels, waiting 3s...")
    time.sleep(3)
    
    # Cleanup
    proc.stdin.close()
    proc.terminate()
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "stop"})


def main():
    print("Testing different HueStream message formats\n")
    
    # Test v1 with 2-byte channel ID
    test_format("v1 RGB (2-byte channel)", 
                lambda ch, r, g, b: build_v1_rgb(ch, r, g, b))
    
    # Test v2 with 1-byte channel ID
    test_format("v2 RGB (1-byte channel, with group ID)", 
                lambda ch, r, g, b: build_v2_rgb(ch, r, g, b, ENTERTAINMENT_CONFIG_ID))
    
    print("\n" + "="*60)
    print("Done! Did you see lights turn red in either test?")


if __name__ == "__main__":
    main()
