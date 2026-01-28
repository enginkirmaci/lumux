#!/usr/bin/env python
"""Test HueStream using gnutls-cli for DTLS-PSK."""

import os
import pty
import select
import time
import json
import urllib.request
import ssl as ssl_module
import uuid
import termios

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
    print("=== HueStream test with gnutls-cli ===\n")
    
    # Stop any existing streaming
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
    
    # Create pty and fork gnutls-cli
    print("\nCreating PTY for gnutls-cli...")
    
    master_fd, slave_fd = pty.openpty()
    
    # Disable echo
    attrs = termios.tcgetattr(master_fd)
    attrs[3] = attrs[3] & ~termios.ECHO
    termios.tcsetattr(master_fd, termios.TCSANOW, attrs)
    
    pid = os.fork()
    
    if pid == 0:
        # Child process
        os.close(master_fd)
        os.setsid()
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        os.close(slave_fd)
        
        # gnutls-cli for DTLS-PSK
        # --pskusername and --pskkey
        os.execvp("gnutls-cli", [
            "gnutls-cli",
            "--udp",
            "--pskusername", APP_KEY,
            "--pskkey", CLIENT_KEY,
            "-p", str(PORT),
            "--insecure",  # Don't verify certs
            BRIDGE_IP,
        ])
    
    # Parent process
    os.close(slave_fd)
    
    # Wait for handshake
    print("Waiting for DTLS handshake...")
    time.sleep(3)
    
    # Check if child is still running
    result, status = os.waitpid(pid, os.WNOHANG)
    if result != 0:
        print(f"gnutls-cli exited with status {status}")
        os.close(master_fd)
        api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
                 {"action": "stop"})
        return
    
    print("gnutls-cli running!")
    
    # Read any initial output
    readable, _, _ = select.select([master_fd], [], [], 0.5)
    if readable:
        data = os.read(master_fd, 4096)
        print(f"Initial output ({len(data)} bytes):\n{data.decode('utf-8', errors='replace')}")
    
    # Send colors
    colors = {i: (255, 0, 0) for i in range(11)}
    
    print("\nSending 100 RED messages...")
    for seq in range(100):
        msg = build_v2_message(colors, seq)
        try:
            os.write(master_fd, msg)
            time.sleep(0.04)
        except Exception as e:
            print(f"Write error: {e}")
            break
    
    print("Sent 100 messages, waiting 3 seconds...")
    time.sleep(3)
    
    # Check for output
    readable, _, _ = select.select([master_fd], [], [], 0.1)
    if readable:
        data = os.read(master_fd, 4096)
        print(f"Output: {data}")
    
    # Cleanup
    os.close(master_fd)
    os.kill(pid, 9)
    os.waitpid(pid, 0)
    
    api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
             {"action": "stop"})
    
    print("\n=== Did lights turn RED? ===")


if __name__ == "__main__":
    main()
