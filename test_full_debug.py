#!/usr/bin/env python
"""Debug DTLS connection fully."""

import subprocess
import time
import struct
import json
import urllib.request
import ssl
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


def main():
    print("=== Full DTLS Debug ===\n")
    
    # Stop first
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "stop"})
    time.sleep(0.5)
    
    # Start streaming
    print("Activating streaming...")
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "start"})
    time.sleep(1)
    
    # Connect DTLS - capture stdout too
    print("Connecting DTLS...")
    proc = subprocess.Popen(
        ["openssl", "s_client", "-dtls1_2",
         "-psk_identity", APP_KEY,
         "-psk", CLIENT_KEY,
         "-connect", f"{BRIDGE_IP}:{PORT}"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    # Wait for handshake
    time.sleep(2)
    
    # Check if data available on stdout
    import os
    import fcntl
    
    # Make stdout non-blocking
    flags = fcntl.fcntl(proc.stdout, fcntl.F_GETFL)
    fcntl.fcntl(proc.stdout, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    
    try:
        stdout_data = proc.stdout.read()
        if stdout_data:
            print(f"\n=== STDOUT ({len(stdout_data)} bytes): ===")
            print(stdout_data.decode('utf-8', errors='replace'))
    except:
        print("No stdout data yet")
    
    # Check stderr
    flags = fcntl.fcntl(proc.stderr, fcntl.F_GETFL)
    fcntl.fcntl(proc.stderr, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    
    try:
        stderr_data = proc.stderr.read()
        if stderr_data:
            print(f"\n=== STDERR ({len(stderr_data)} bytes): ===")
            print(stderr_data.decode('utf-8', errors='replace'))
    except:
        print("No stderr data yet")
    
    print(f"\nProcess running: {proc.poll() is None}")
    
    if proc.poll() is None:
        print("\nSending RED color command...")
        msg = b"HueStream"
        msg += bytes([0x01, 0x00])  # Version
        msg += bytes([0x00])  # Sequence
        msg += bytes([0x00, 0x00])  # Reserved
        msg += bytes([0x00])  # RGB mode
        msg += bytes([0x00])  # Reserved
        
        # Add all 11 channels as RED
        for ch in range(11):
            msg += bytes([0x00])  # Light type
            msg += struct.pack(">H", ch)  # Channel ID
            msg += struct.pack(">HHH", 65535, 0, 0)  # RED
        
        print(f"Message: {len(msg)} bytes")
        print(f"Hex (first 50 chars): {msg.hex()[:50]}...")
        
        proc.stdin.write(msg)
        proc.stdin.flush()
        print("Sent!")
        
        time.sleep(2)
        print("Still running:", proc.poll() is None)
    
    # Cleanup
    proc.terminate()
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "stop"})
    
    print("\nDone!")


if __name__ == "__main__":
    main()
