#!/usr/bin/env python
"""Test if openssl subprocess is actually sending data."""

import subprocess
import time
import json
import urllib.request
import ssl
import uuid
import threading
import select

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


def build_v2_message(channel_colors, sequence=0):
    """Build HueStream v2 message."""
    msg = b"HueStream"
    msg += bytes([0x02, 0x00])
    msg += bytes([sequence])
    msg += bytes([0x00, 0x00])
    msg += bytes([0x00])
    msg += bytes([0x00])
    
    ent_uuid = uuid.UUID(ENTERTAINMENT_CONFIG_ID)
    msg += ent_uuid.bytes
    
    for channel_id, (r, g, b) in sorted(channel_colors.items()):
        msg += bytes([channel_id])
        msg += bytes([r, r, g, g, b, b])
    
    return msg


def monitor_stderr(proc):
    """Monitor stderr in background."""
    while True:
        line = proc.stderr.readline()
        if not line:
            break
        text = line.decode().strip()
        if text:
            print(f"[STDERR] {text}")


def main():
    print("=== OpenSSL subprocess test with verbose monitoring ===\n")
    
    # Stop first
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "stop"})
    time.sleep(0.5)
    
    # Start streaming
    print("Activating streaming...")
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "start"})
    time.sleep(1)
    
    # Connect DTLS with -msg flag to see what's sent
    print("\nConnecting DTLS with message tracing...")
    proc = subprocess.Popen(
        ["openssl", "s_client", "-dtls1_2",
         "-psk_identity", APP_KEY,
         "-psk", CLIENT_KEY,
         "-connect", f"{BRIDGE_IP}:{PORT}",
         "-msg"],  # Show protocol messages
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    # Start stderr monitor
    stderr_thread = threading.Thread(target=monitor_stderr, args=(proc,), daemon=True)
    stderr_thread.start()
    
    time.sleep(2)
    
    if proc.poll() is not None:
        print("DTLS failed!")
        return
    
    print("\nDTLS appears connected. Sending test message...")
    
    # Build a simple test message
    colors = {i: (255, 0, 0) for i in range(11)}
    msg = build_v2_message(colors, 0)
    
    print(f"Message length: {len(msg)} bytes")
    print(f"Message hex: {msg.hex()}")
    
    # Send via stdin
    try:
        bytes_written = proc.stdin.write(msg)
        print(f"stdin.write returned: {bytes_written}")
        proc.stdin.flush()
        print("stdin.flush completed")
    except Exception as e:
        print(f"Write error: {e}")
    
    # Wait a bit
    time.sleep(1)
    
    # Check process status
    print(f"\nProcess still running: {proc.poll() is None}")
    
    # Send more messages
    print("\nSending 50 RED messages...")
    for i in range(50):
        try:
            msg = build_v2_message(colors, i)
            proc.stdin.write(msg)
            proc.stdin.flush()
            time.sleep(0.04)
        except Exception as e:
            print(f"Write error at {i}: {e}")
            break
    
    print("Sent 50 messages")
    time.sleep(2)
    
    print(f"Process still running: {proc.poll() is None}")
    
    # Cleanup
    proc.terminate()
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "stop"})
    
    print("\n=== Did the lights turn RED? ===")


if __name__ == "__main__":
    main()
