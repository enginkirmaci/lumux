#!/usr/bin/env python
"""Test HueStream using python-mbedtls for DTLS-PSK."""

import socket
import time
import json
import urllib.request
import ssl as ssl_module
import uuid

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
    print("=== HueStream test with python-mbedtls ===\n")
    
    try:
        from mbedtls import tls
        print("mbedtls imported successfully")
    except ImportError as e:
        print(f"Failed to import mbedtls: {e}")
        return
    
    # Check what's available
    print(f"tls module contents: {dir(tls)}")
    
    # Stop any existing streaming
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "stop"})
    time.sleep(0.5)
    
    # Start streaming
    print("\nActivating streaming...")
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
    
    # Try to create DTLS connection
    print("\nAttempting DTLS connection with mbedtls...")
    
    try:
        # Check for DTLSConfiguration
        if hasattr(tls, 'DTLSConfiguration'):
            print("Found DTLSConfiguration")
            
            psk = bytes.fromhex(CLIENT_KEY)
            conf = tls.DTLSConfiguration(
                pre_shared_key=(APP_KEY.encode(), psk),
                validate_certificates=False,
            )
            print(f"Created configuration: {conf}")
            
            # Create DTLS client context
            ctx = tls.ClientContext(conf)
            print(f"Created context: {ctx}")
            
            # Create socket and wrap
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(10)
            
            print(f"Connecting to {BRIDGE_IP}:{PORT}...")
            dtls_sock = ctx.wrap_socket(sock, server_hostname=BRIDGE_IP)
            dtls_sock.connect((BRIDGE_IP, PORT))
            dtls_sock.do_handshake()
            print("Handshake complete!")
            
            # Send colors
            colors = {i: (255, 0, 0) for i in range(11)}
            for seq in range(100):
                msg = build_v2_message(colors, seq)
                dtls_sock.send(msg)
                time.sleep(0.04)
            
            print("Sent 100 RED messages!")
            dtls_sock.close()
            
        else:
            print("DTLSConfiguration not found in mbedtls.tls")
            print(f"Available: {[x for x in dir(tls) if not x.startswith('_')]}")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Stop streaming
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "stop"})
    
    print("\n=== Did lights turn RED? ===")


if __name__ == "__main__":
    main()
