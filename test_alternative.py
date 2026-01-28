#!/usr/bin/env python
"""Test using raw UDP after handshake via cryptography library."""

import socket
import time
import json
import urllib.request
import ssl as ssl_module
import uuid
import os

# Try using cryptography for DTLS-PSK
try:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    HAVE_CRYPTO = True
except ImportError:
    HAVE_CRYPTO = False

BRIDGE_IP = "192.168.2.107"
PORT = 2100
APP_KEY = "X7Lyq8FJ8ha1h7DGVmNeCqYTAJxXw2wKa-rg0XjS"
CLIENT_KEY = "9B2AEF6437497AAFA703214009E8EFB1"
ENTERTAINMENT_CONFIG_ID = "192d98c5-7adc-4dd5-ac13-fd9d010cf04a"


def api_call(method, endpoint, data=None):
    ctx = ssl_module.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl_module.CERT_NONE
    
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


def main():
    print("=== Testing with raw UDP ===\n")
    
    # First check if maybe the bridge accepts unencrypted UDP
    # (Unlikely, but worth testing)
    
    # Stop any streaming
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "stop"})
    time.sleep(0.5)
    
    # Start streaming
    print("Activating streaming...")
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "start"})
    time.sleep(1)
    
    # Create raw UDP socket
    print(f"Creating UDP socket to {BRIDGE_IP}:{PORT}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5)
    
    # Build message
    colors = {i: (255, 0, 0) for i in range(11)}
    msg = build_v2_message(colors, 0)
    
    print(f"Sending {len(msg)} bytes raw UDP...")
    print(f"Hex: {msg.hex()}")
    
    try:
        sock.sendto(msg, (BRIDGE_IP, PORT))
        print("Sent successfully (raw UDP)")
        
        # Try to receive response
        try:
            data, addr = sock.recvfrom(1024)
            print(f"Response: {data.hex()}")
        except socket.timeout:
            print("No response (expected for raw UDP)")
    except Exception as e:
        print(f"Send error: {e}")
    
    sock.close()
    
    # Try using netcat with openssl piping
    print("\n=== Alternative: Using fifo for openssl ===\n")
    
    import subprocess
    import tempfile
    
    # Create named pipes
    fifo_in = "/tmp/hue_dtls_in"
    fifo_out = "/tmp/hue_dtls_out"
    
    # Remove if exists
    for f in [fifo_in, fifo_out]:
        try:
            os.unlink(f)
        except:
            pass
    
    os.mkfifo(fifo_in)
    print(f"Created fifo: {fifo_in}")
    
    # Start openssl in background with fifo
    print("Starting openssl with fifo...")
    
    # This approach: use openssl with -ign_eof to keep reading
    cmd = f"openssl s_client -dtls1_2 -psk_identity {APP_KEY} -psk {CLIENT_KEY} -connect {BRIDGE_IP}:{PORT} -ign_eof < {fifo_in}"
    
    proc = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    time.sleep(0.5)
    
    # Open fifo for writing (this will block until reader is ready)
    print("Opening fifo for writing...")
    
    import threading
    
    def write_to_fifo():
        try:
            with open(fifo_in, 'wb', buffering=0) as f:
                print("Fifo opened, waiting for DTLS handshake...")
                time.sleep(2)  # Wait for handshake
                
                colors = {i: (255, 0, 0) for i in range(11)}
                
                print("Sending 100 RED messages via fifo...")
                for i in range(100):
                    msg = build_v2_message(colors, i)
                    f.write(msg)
                    f.flush()
                    time.sleep(0.04)
                
                print("Sent via fifo!")
        except Exception as e:
            print(f"Fifo write error: {e}")
    
    writer_thread = threading.Thread(target=write_to_fifo, daemon=True)
    writer_thread.start()
    
    # Wait for completion
    time.sleep(8)
    
    # Check process
    print(f"Process running: {proc.poll() is None}")
    
    # Cleanup
    proc.terminate()
    try:
        os.unlink(fifo_in)
    except:
        pass
    
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "stop"})
    
    print("\n=== Did lights turn RED? ===")


if __name__ == "__main__":
    main()
