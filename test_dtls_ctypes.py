#!/usr/bin/env python
"""
DTLS-PSK client using ctypes and OpenSSL.
This provides native Python DTLS support without external libraries.
"""

import ctypes
import ctypes.util
import socket
import time
from typing import Optional

# Find OpenSSL library
_ssl_lib_name = ctypes.util.find_library('ssl')
_crypto_lib_name = ctypes.util.find_library('crypto')

if _ssl_lib_name:
    _ssl = ctypes.CDLL(_ssl_lib_name)
else:
    # Try common names
    try:
        _ssl = ctypes.CDLL('libssl.so.3')
    except OSError:
        try:
            _ssl = ctypes.CDLL('libssl.so.1.1')
        except OSError:
            _ssl = ctypes.CDLL('libssl.so')

if _crypto_lib_name:
    _crypto = ctypes.CDLL(_crypto_lib_name)
else:
    try:
        _crypto = ctypes.CDLL('libcrypto.so.3')
    except OSError:
        try:
            _crypto = ctypes.CDLL('libcrypto.so.1.1')
        except OSError:
            _crypto = ctypes.CDLL('libcrypto.so')


# Define types
SSL_CTX_p = ctypes.c_void_p
SSL_p = ctypes.c_void_p
SSL_METHOD_p = ctypes.c_void_p
BIO_p = ctypes.c_void_p
BIO_METHOD_p = ctypes.c_void_p

# Constants
DTLS1_2_VERSION = 0xFEFD
SSL_ERROR_WANT_READ = 2
SSL_ERROR_WANT_WRITE = 3

# PSK callback type
PSK_CLIENT_CALLBACK = ctypes.CFUNCTYPE(
    ctypes.c_uint,  # return: PSK length
    SSL_p,  # ssl
    ctypes.c_char_p,  # hint
    ctypes.c_char_p,  # identity (output)
    ctypes.c_uint,  # max_identity_len
    ctypes.c_char_p,  # psk (output)
    ctypes.c_uint,  # max_psk_len
)

# Define function signatures
_ssl.DTLS_client_method.restype = SSL_METHOD_p
_ssl.SSL_CTX_new.argtypes = [SSL_METHOD_p]
_ssl.SSL_CTX_new.restype = SSL_CTX_p
_ssl.SSL_CTX_free.argtypes = [SSL_CTX_p]
_ssl.SSL_new.argtypes = [SSL_CTX_p]
_ssl.SSL_new.restype = SSL_p
_ssl.SSL_free.argtypes = [SSL_p]
_ssl.SSL_set_bio.argtypes = [SSL_p, BIO_p, BIO_p]
_ssl.SSL_connect.argtypes = [SSL_p]
_ssl.SSL_connect.restype = ctypes.c_int
_ssl.SSL_write.argtypes = [SSL_p, ctypes.c_void_p, ctypes.c_int]
_ssl.SSL_write.restype = ctypes.c_int
_ssl.SSL_read.argtypes = [SSL_p, ctypes.c_void_p, ctypes.c_int]
_ssl.SSL_read.restype = ctypes.c_int
_ssl.SSL_get_error.argtypes = [SSL_p, ctypes.c_int]
_ssl.SSL_get_error.restype = ctypes.c_int
_ssl.SSL_CTX_set_psk_client_callback.argtypes = [SSL_CTX_p, PSK_CLIENT_CALLBACK]
_ssl.SSL_CTX_set_cipher_list.argtypes = [SSL_CTX_p, ctypes.c_char_p]
_ssl.SSL_CTX_set_cipher_list.restype = ctypes.c_int
_ssl.SSL_set_connect_state.argtypes = [SSL_p]
_ssl.SSL_do_handshake.argtypes = [SSL_p]
_ssl.SSL_do_handshake.restype = ctypes.c_int
_ssl.SSL_shutdown.argtypes = [SSL_p]
_ssl.SSL_shutdown.restype = ctypes.c_int

# BIO functions
_crypto.BIO_new_dgram.argtypes = [ctypes.c_int, ctypes.c_int]
_crypto.BIO_new_dgram.restype = BIO_p
_crypto.BIO_ctrl.argtypes = [BIO_p, ctypes.c_int, ctypes.c_long, ctypes.c_void_p]
_crypto.BIO_ctrl.restype = ctypes.c_long

# BIO_CTRL constants
BIO_CTRL_DGRAM_SET_CONNECTED = 32
BIO_CTRL_DGRAM_SET_PEER = 44


class DTLSPSKClient:
    """DTLS client using PSK authentication."""
    
    def __init__(self, host: str, port: int, psk_identity: bytes, psk: bytes):
        """
        Initialize DTLS-PSK client.
        
        Args:
            host: Server hostname/IP
            port: Server port
            psk_identity: PSK identity (app key for Hue)
            psk: Pre-shared key bytes
        """
        self.host = host
        self.port = port
        self.psk_identity = psk_identity
        self.psk = psk
        
        self._sock: Optional[socket.socket] = None
        self._ctx: Optional[SSL_CTX_p] = None
        self._ssl: Optional[SSL_p] = None
        self._bio: Optional[BIO_p] = None
        self._connected = False
        self._psk_callback = None  # Keep reference
    
    def _make_psk_callback(self):
        """Create PSK callback function."""
        psk_identity = self.psk_identity
        psk = self.psk
        
        def psk_callback(ssl, hint, identity, max_id_len, psk_out, max_psk_len):
            # Copy identity
            if len(psk_identity) + 1 > max_id_len:
                return 0
            ctypes.memmove(identity, psk_identity, len(psk_identity))
            identity[len(psk_identity)] = 0  # Null terminator
            
            # Copy PSK
            if len(psk) > max_psk_len:
                return 0
            ctypes.memmove(psk_out, psk, len(psk))
            
            return len(psk)
        
        return PSK_CLIENT_CALLBACK(psk_callback)
    
    def connect(self, timeout: float = 10.0) -> bool:
        """
        Establish DTLS connection.
        
        Args:
            timeout: Connection timeout in seconds
            
        Returns:
            True if connected successfully
        """
        try:
            # Create UDP socket
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.settimeout(timeout)
            self._sock.connect((self.host, self.port))
            
            # Create SSL context
            method = _ssl.DTLS_client_method()
            self._ctx = _ssl.SSL_CTX_new(method)
            if not self._ctx:
                raise Exception("Failed to create SSL context")
            
            # Set cipher list for PSK
            ciphers = b"PSK-CHACHA20-POLY1305:PSK-AES128-GCM-SHA256:PSK-AES256-GCM-SHA384"
            _ssl.SSL_CTX_set_cipher_list(self._ctx, ciphers)
            
            # Set PSK callback
            self._psk_callback = self._make_psk_callback()
            _ssl.SSL_CTX_set_psk_client_callback(self._ctx, self._psk_callback)
            
            # Create SSL object
            self._ssl = _ssl.SSL_new(self._ctx)
            if not self._ssl:
                raise Exception("Failed to create SSL object")
            
            # Create BIO for UDP socket
            self._bio = _crypto.BIO_new_dgram(self._sock.fileno(), 0)
            if not self._bio:
                raise Exception("Failed to create BIO")
            
            # Set peer address
            import struct as struct_mod
            addr_in = struct_mod.pack('!HH4s8s', 
                socket.AF_INET, 
                socket.htons(self.port),
                socket.inet_aton(self.host),
                b'\x00' * 8
            )
            _crypto.BIO_ctrl(self._bio, BIO_CTRL_DGRAM_SET_CONNECTED, 0, addr_in)
            
            # Attach BIO to SSL
            _ssl.SSL_set_bio(self._ssl, self._bio, self._bio)
            
            # Set connect state and do handshake
            _ssl.SSL_set_connect_state(self._ssl)
            
            result = _ssl.SSL_do_handshake(self._ssl)
            if result <= 0:
                err = _ssl.SSL_get_error(self._ssl, result)
                raise Exception(f"SSL handshake failed with error {err}")
            
            self._connected = True
            return True
            
        except Exception as e:
            print(f"DTLS connect error: {e}")
            self.close()
            return False
    
    def send(self, data: bytes) -> int:
        """Send data over DTLS connection."""
        if not self._connected or not self._ssl:
            raise Exception("Not connected")
        
        result = _ssl.SSL_write(self._ssl, data, len(data))
        if result <= 0:
            err = _ssl.SSL_get_error(self._ssl, result)
            raise Exception(f"SSL write error: {err}")
        
        return result
    
    def close(self):
        """Close DTLS connection."""
        self._connected = False
        
        if self._ssl:
            _ssl.SSL_shutdown(self._ssl)
            _ssl.SSL_free(self._ssl)
            self._ssl = None
            self._bio = None  # Freed with SSL
        
        if self._ctx:
            _ssl.SSL_CTX_free(self._ctx)
            self._ctx = None
        
        if self._sock:
            self._sock.close()
            self._sock = None


def test_dtls():
    """Test DTLS connection."""
    print("Testing DTLS-PSK client...")
    
    # Hue bridge settings
    BRIDGE_IP = "192.168.2.107"
    PORT = 2100
    APP_KEY = b"X7Lyq8FJ8ha1h7DGVmNeCqYTAJxXw2wKa-rg0XjS"
    CLIENT_KEY = bytes.fromhex("9B2AEF6437497AAFA703214009E8EFB1")
    
    client = DTLSPSKClient(BRIDGE_IP, PORT, APP_KEY, CLIENT_KEY)
    
    print(f"Connecting to {BRIDGE_IP}:{PORT}...")
    
    if client.connect(timeout=10):
        print("Connected!")
        
        # Send test message
        test_msg = b"HueStream\x02\x00\x00\x00\x00\x00\x00"
        try:
            sent = client.send(test_msg)
            print(f"Sent {sent} bytes")
        except Exception as e:
            print(f"Send error: {e}")
        
        client.close()
        print("Disconnected")
    else:
        print("Connection failed")


if __name__ == "__main__":
    test_dtls()
