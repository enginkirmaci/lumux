#!/usr/bin/env python
"""
Test DTLS with streaming activated first.
"""

import ctypes
import ctypes.util
import socket
import time
import json
import urllib.request
import ssl as ssl_module
import uuid
import select

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


def build_v2_message(channel_colors, ent_config_id, sequence=0):
    """Build HueStream v2 message."""
    msg = b"HueStream"
    msg += bytes([0x02, 0x00])  # Version 2.0
    msg += bytes([sequence])
    msg += bytes([0x00, 0x00])  # Reserved
    msg += bytes([0x00])  # Color mode: RGB
    msg += bytes([0x00])  # Linear filter
    
    # Entertainment config UUID (16 bytes)
    ent_uuid = uuid.UUID(ent_config_id)
    msg += ent_uuid.bytes
    
    # Channel states
    for channel_id, (r, g, b) in sorted(channel_colors.items()):
        msg += bytes([channel_id])
        msg += bytes([r, r, g, g, b, b])
    
    return msg


# Load OpenSSL
_ssl_lib_name = ctypes.util.find_library('ssl')
_crypto_lib_name = ctypes.util.find_library('crypto')

if _ssl_lib_name:
    _ssl = ctypes.CDLL(_ssl_lib_name)
else:
    _ssl = ctypes.CDLL('libssl.so.3')

if _crypto_lib_name:
    _crypto = ctypes.CDLL(_crypto_lib_name)
else:
    _crypto = ctypes.CDLL('libcrypto.so.3')

# Types
SSL_CTX_p = ctypes.c_void_p
SSL_p = ctypes.c_void_p
SSL_METHOD_p = ctypes.c_void_p
BIO_p = ctypes.c_void_p

# PSK callback
PSK_CLIENT_CALLBACK = ctypes.CFUNCTYPE(
    ctypes.c_uint, SSL_p, ctypes.c_char_p, ctypes.c_char_p,
    ctypes.c_uint, ctypes.c_char_p, ctypes.c_uint,
)

# SSL error codes
SSL_ERROR_NONE = 0
SSL_ERROR_WANT_READ = 2
SSL_ERROR_WANT_WRITE = 3

# Define functions
_ssl.DTLS_client_method.restype = SSL_METHOD_p
_ssl.SSL_CTX_new.argtypes = [SSL_METHOD_p]
_ssl.SSL_CTX_new.restype = SSL_CTX_p
_ssl.SSL_CTX_free.argtypes = [SSL_CTX_p]
_ssl.SSL_new.argtypes = [SSL_CTX_p]
_ssl.SSL_new.restype = SSL_p
_ssl.SSL_free.argtypes = [SSL_p]
_ssl.SSL_set_fd.argtypes = [SSL_p, ctypes.c_int]
_ssl.SSL_set_fd.restype = ctypes.c_int
_ssl.SSL_connect.argtypes = [SSL_p]
_ssl.SSL_connect.restype = ctypes.c_int
_ssl.SSL_write.argtypes = [SSL_p, ctypes.c_void_p, ctypes.c_int]
_ssl.SSL_write.restype = ctypes.c_int
_ssl.SSL_get_error.argtypes = [SSL_p, ctypes.c_int]
_ssl.SSL_get_error.restype = ctypes.c_int
_ssl.SSL_CTX_set_psk_client_callback.argtypes = [SSL_CTX_p, PSK_CLIENT_CALLBACK]
_ssl.SSL_CTX_set_cipher_list.argtypes = [SSL_CTX_p, ctypes.c_char_p]
_ssl.SSL_CTX_set_cipher_list.restype = ctypes.c_int
_ssl.SSL_shutdown.argtypes = [SSL_p]

# BIO
_crypto.BIO_new_dgram.argtypes = [ctypes.c_int, ctypes.c_int]
_crypto.BIO_new_dgram.restype = BIO_p
_ssl.SSL_set_bio.argtypes = [SSL_p, BIO_p, BIO_p]

# DTLS timeout functions - may not exist in all OpenSSL versions
try:
    _ssl.DTLSv1_get_timeout.argtypes = [SSL_p, ctypes.c_void_p]
    _ssl.DTLSv1_get_timeout.restype = ctypes.c_int
    _ssl.DTLSv1_handle_timeout.argtypes = [SSL_p]
    _ssl.DTLSv1_handle_timeout.restype = ctypes.c_int
    HAS_DTLS_TIMEOUT = True
except AttributeError:
    HAS_DTLS_TIMEOUT = False


def main():
    print("=== DTLS ctypes test with streaming ===\n")
    
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
    
    # Store PSK data for callback
    psk_identity = APP_KEY.encode()
    psk_key = bytes.fromhex(CLIENT_KEY)
    
    # Create callback that captures the PSK
    @PSK_CLIENT_CALLBACK
    def psk_callback(ssl, hint, identity, max_id_len, psk_out, max_psk_len):
        print(f"PSK callback called! hint={hint}, max_id={max_id_len}, max_psk={max_psk_len}")
        # Copy identity
        ctypes.memmove(identity, psk_identity, len(psk_identity))
        # Copy PSK
        ctypes.memmove(psk_out, psk_key, len(psk_key))
        print(f"PSK callback returning {len(psk_key)}")
        return len(psk_key)
    
    try:
        # Create UDP socket
        print(f"\nCreating UDP socket to {BRIDGE_IP}:{PORT}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        sock.connect((BRIDGE_IP, PORT))
        
        # Create SSL context
        print("Creating SSL context...")
        method = _ssl.DTLS_client_method()
        ctx = _ssl.SSL_CTX_new(method)
        if not ctx:
            print("Failed to create SSL context")
            return
        
        # Set ciphers
        ciphers = b"PSK-CHACHA20-POLY1305:PSK-AES128-GCM-SHA256"
        _ssl.SSL_CTX_set_cipher_list(ctx, ciphers)
        
        # Set PSK callback
        _ssl.SSL_CTX_set_psk_client_callback(ctx, psk_callback)
        
        # Create SSL object
        ssl = _ssl.SSL_new(ctx)
        if not ssl:
            print("Failed to create SSL object")
            return
        
        # Create BIO
        bio = _crypto.BIO_new_dgram(sock.fileno(), 0)
        _ssl.SSL_set_bio(ssl, bio, bio)
        
        # Try handshake with retries
        print("Starting DTLS handshake...")
        max_retries = 50
        for i in range(max_retries):
            result = _ssl.SSL_connect(ssl)
            
            if result == 1:
                print("DTLS handshake successful!")
                break
            
            err = _ssl.SSL_get_error(ssl, result)
            if err == SSL_ERROR_WANT_READ:
                # Wait for data with select
                readable, _, _ = select.select([sock], [], [], 0.5)
                if not readable and HAS_DTLS_TIMEOUT:
                    # Handle timeout
                    _ssl.DTLSv1_handle_timeout(ssl)
                continue
            elif err == SSL_ERROR_WANT_WRITE:
                time.sleep(0.01)
                continue
            else:
                print(f"Handshake error: {err}")
                break
        else:
            print("Handshake timed out")
            _ssl.SSL_free(ssl)
            _ssl.SSL_CTX_free(ctx)
            sock.close()
            api_call('PUT', f'entertainment_configuration/{ENTERTAINMENT_CONFIG_ID}', 
                     {"action": "stop"})
            return
        
        # Send colors!
        print("\nSending colors...")
        colors = {i: (255, 0, 0) for i in range(11)}  # RED
        
        for seq in range(100):
            msg = build_v2_message(colors, ENTERTAINMENT_CONFIG_ID, seq)
            result = _ssl.SSL_write(ssl, msg, len(msg))
            if result <= 0:
                err = _ssl.SSL_get_error(ssl, result)
                print(f"Write error: {err}")
                break
            time.sleep(0.04)
        
        print("Sent 100 RED messages!")
        time.sleep(2)
        
        # Cleanup
        _ssl.SSL_shutdown(ssl)
        _ssl.SSL_free(ssl)
        _ssl.SSL_CTX_free(ctx)
        sock.close()
        
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
