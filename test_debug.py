#!/usr/bin/env python
"""Debug DTLS connection with stderr capture."""

import subprocess
import time
import struct
import json
import urllib.request
import ssl
import threading

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


def read_stderr(proc, output_list):
    """Read stderr in background thread."""
    while True:
        line = proc.stderr.readline()
        if not line:
            break
        output_list.append(line.decode().strip())


def main():
    print("=== DTLS Debug Test ===\n")
    
    # Stop first
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "stop"})
    time.sleep(0.5)
    
    # Start streaming
    print("Activating streaming...")
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "start"})
    time.sleep(1)
    
    # Connect DTLS with verbose output
    print("Connecting DTLS (with debug)...")
    proc = subprocess.Popen(
        ["openssl", "s_client", "-dtls1_2",
         "-psk_identity", APP_KEY,
         "-psk", CLIENT_KEY,
         "-connect", f"{BRIDGE_IP}:{PORT}",
         "-msg"],  # -msg shows protocol messages
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    stderr_output = []
    stderr_thread = threading.Thread(target=read_stderr, args=(proc, stderr_output))
    stderr_thread.daemon = True
    stderr_thread.start()
    
    time.sleep(2)
    
    # Print captured stderr
    print("\n=== OpenSSL stderr output: ===")
    for line in stderr_output[:30]:
        print(f"  {line}")
    if len(stderr_output) > 30:
        print(f"  ... and {len(stderr_output)-30} more lines")
    
    print("\n=== Process status ===")
    print(f"  Return code: {proc.poll()}")
    
    if proc.poll() is None:
        print("  Process still running - sending test message...")
        msg = b"HueStream" + b"\x01\x00\x00\x00\x00\x00\x00"
        msg += bytes([0x00])  # channel type
        msg += struct.pack(">H", 0)  # channel 0
        msg += struct.pack(">HHH", 65535, 0, 0)  # RED
        
        try:
            proc.stdin.write(msg)
            proc.stdin.flush()
            print(f"  Wrote {len(msg)} bytes")
            time.sleep(0.5)
            
            # Check if still alive
            print(f"  Process still running: {proc.poll() is None}")
        except Exception as e:
            print(f"  Write error: {e}")
    
    # More stderr
    time.sleep(0.5)
    print("\n=== Additional stderr: ===")
    for line in stderr_output[30:50]:
        print(f"  {line}")
    
    # Cleanup
    proc.terminate()
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "stop"})
    
    print("\nDone!")


if __name__ == "__main__":
    main()
