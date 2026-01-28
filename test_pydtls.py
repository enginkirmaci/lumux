#!/usr/bin/env python
"""Test HueStream v2 using PyDTLS library."""

import socket
import time
import struct
import json
import urllib.request
import ssl as ssl_module
import uuid

# Try to import pydtls
try:
    from dtls import do_patch
    from dtls.sslconnection import SSLConnection
    do_patch()
    HAVE_DTLS = True
except ImportError as e:
    print(f"PyDTLS import error: {e}")
    HAVE_DTLS = False

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
    msg += bytes([0x02, 0x00])  # Version 2.0
    msg += bytes([sequence])  # Sequence number
    msg += bytes([0x00, 0x00])  # Reserved
    msg += bytes([0x00])  # Color mode: RGB
    msg += bytes([0x00])  # Linear filter
    
    # Entertainment config UUID (16 bytes)
    ent_uuid = uuid.UUID(ENTERTAINMENT_CONFIG_ID)
    msg += ent_uuid.bytes
    
    # Channel states
    for channel_id, (r, g, b) in sorted(channel_colors.items()):
        msg += bytes([channel_id])
        msg += bytes([r, r, g, g, b, b])
    
    return msg


def main():
    print("=== HueStream v2 Test with PyDTLS ===\n")
    
    if not HAVE_DTLS:
        print("PyDTLS not available, cannot continue")
        return
    
    # Stop first
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "stop"})
    time.sleep(0.5)
    
    # Start streaming
    print("Activating streaming...")
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "start"})
    time.sleep(1)
    
    # Check status
    result = api_call('GET', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}')
    if result:
        status = result['data'][0].get('status')
        print(f"Status: {status}")
        if status != 'active':
            print("ERROR: Streaming not active!")
            return
    
    # Create DTLS socket
    print("\nCreating DTLS connection...")
    
    try:
        # Create UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(10)
        
        # Convert client key to bytes
        psk = bytes.fromhex(CLIENT_KEY)
        
        # Create SSL context for DTLS
        # Note: PyDTLS might not support PSK directly
        # Let's see what happens
        print(f"Connecting to {BRIDGE_IP}:{PORT}...")
        sock.connect((BRIDGE_IP, PORT))
        
        print("Socket connected, trying DTLS handshake...")
        
        # This is experimental - pydtls API
        from dtls.sslconnection import SSLConnection
        
        ssl_sock = SSLConnection(
            sock, 
            keyfile=None, 
            certfile=None,
            server_side=False,
            do_handshake_on_connect=False
        )
        
        ssl_sock.connect((BRIDGE_IP, PORT))
        print("DTLS handshake...")
        ssl_sock.do_handshake()
        print("DTLS connected!")
        
    except Exception as e:
        print(f"DTLS connection failed: {e}")
        import traceback
        traceback.print_exc()
        
        # Cleanup
        api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
                 {"action": "stop"})
        return
    
    # Send colors
    print("\nSending colors...")
    fps = 25
    seq = 0
    
    colors = [
        ("RED", {i: (255, 0, 0) for i in range(11)}),
        ("GREEN", {i: (0, 255, 0) for i in range(11)}),
        ("BLUE", {i: (0, 0, 255) for i in range(11)}),
    ]
    
    for name, color_map in colors:
        print(f"Sending {name}...")
        for _ in range(fps * 3):
            try:
                msg = build_v2_message(color_map, seq)
                ssl_sock.send(msg)
                seq = (seq + 1) % 256
                time.sleep(1.0 / fps)
            except Exception as e:
                print(f"Send error: {e}")
                break
    
    print("\nDone!")
    
    # Cleanup
    try:
        ssl_sock.shutdown()
        ssl_sock.close()
    except:
        pass
    
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "stop"})


if __name__ == "__main__":
    main()
