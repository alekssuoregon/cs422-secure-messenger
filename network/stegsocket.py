import os
import socket
import select
import tempfile
from stego import StegoTranscoder

from cryptography.hazmat.primitives import hashes, serialization, padding
from cryptography.hazmat.primitives.asymmetric import dh
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

IV_SIZE = 16
HEADER_SIZE = 4
AES_BLOCK_SIZE = 128
AES_KEY_LENGTH = 32
BYTE_ORDER = 'little'
BUFFER_SIZE = 4096
POLL_TIME_MS = 5000

class StegoSocket:
    def __init__(self, image_repo: str, sock: socket.socket, encryption: bool = False, is_server: bool = False):
        self._sock = sock 
        self._poller = select.poll() 
        self._poller.register(self._sock, select.POLLIN)

        self._image_repo = [os.path.join(image_repo, f) for f in os.listdir(image_repo) if os.path.isfile(os.path.join(image_repo, f))]
        self._img_idx = 0

        self._transcoder = StegoTranscoder()
        self._use_encryption = encryption
        if self._use_encryption:
            self._key_exchange(is_server)

    def send(self, message: bytes) -> bool:
        # Encrypt message if encryption mode is enabled 
        if self._use_encryption:
            # Generate IV and create cipher
            iv = os.urandom(IV_SIZE)
            cipher = Cipher(algorithms.AES(self._derived_key), modes.CBC(iv))

            # Pad data to standard AES block size
            padder = padding.PKCS7(AES_BLOCK_SIZE).padder()
            message = padder.update(message) + padder.finalize()

            # Encrypt data
            encryptor = cipher.encryptor()
            message = iv + encryptor.update(message) + encryptor.finalize()

        # Pick appropriate image medium file 
        medium_in_file = self._image_repo[self._img_idx]
        self._img_idx = (self._img_idx + 1) % len(self._image_repo)
        medium_out_file = tempfile.NamedTemporaryFile().name + ".png"

        # Perform steganographic encoding
        if not self._transcoder.encode(message, medium_in_file, medium_out_file):
            return False
        
        # Send fixed-length size header to peer
        img_size = os.path.getsize(medium_out_file)
        header = img_size.to_bytes(HEADER_SIZE, BYTE_ORDER, signed=False)
        self._sock.sendall(header)

        # Send encoded image file to peer
        with open(medium_out_file, "rb") as f:
            while True:
                bytes_read = f.read(BUFFER_SIZE)
                if not bytes_read:
                    break
                self._sock.sendall(bytes_read)
        os.remove(medium_out_file)

        return True

    def recv(self) -> bytes | None:
        # Check if any data is on the pipe 
        header = None
        events = self._poller.poll(POLL_TIME_MS)
        for sock, event in events:
            if event and select.POLLIN:
                if sock == self._sock.fileno():
                    header = self._sock.recv(HEADER_SIZE)
        
        if header is None:
            return None 

        # Receive encoded image
        img_size = int.from_bytes(header, BYTE_ORDER, signed=False)
        read_bytes = 0
        medium_out_file = tempfile.NamedTemporaryFile().name + ".png" 
        with open(medium_out_file, "wb") as f:
            while read_bytes < img_size:
                buf_size = BUFFER_SIZE
                if buf_size > img_size - read_bytes:
                    buf_size = img_size - read_bytes

                bytes_read = self._sock.recv(BUFFER_SIZE)
                if not bytes_read:
                    break
                read_bytes += len(bytes_read)
                f.write(bytes_read)
        
        # Attempt steganographic decoding
        try:
            message = self._transcoder.decode(medium_out_file)
        except:
            raise socket.error

        # Cleanup intermediary image file
        os.remove(medium_out_file)
        
        # Decrypt if encryption mode is enabled
        if self._use_encryption:
            # Extract IV
            iv = message[:IV_SIZE] 
            message = message[IV_SIZE:]

            # Create cipher for decoding
            cipher = Cipher(algorithms.AES(self._derived_key), modes.CBC(iv))
            decryptor = cipher.decryptor()

            # Decrypt and unpad
            unpadder = padding.PKCS7(AES_BLOCK_SIZE).unpadder()
            message = decryptor.update(message) + decryptor.finalize()
            message = unpadder.update(message) + unpadder.finalize() 

        return message
    
    def _key_exchange(self, server: bool):
        # Generate/receive DH parameters
        if server:
            parameters = dh.generate_parameters(generator=2, key_size=2048)
            parameter_bytes = parameters.parameter_bytes(
                                            serialization.Encoding.PEM,
                                            serialization.ParameterFormat.PKCS3,
                                        )
            parameter_header_size = len(parameter_bytes).to_bytes(HEADER_SIZE, BYTE_ORDER, signed=False)
            self._sock.sendall(parameter_header_size)
            self._sock.sendall(parameter_bytes)
        else:
            parameter_header_size = self._sock.recv(HEADER_SIZE)
            parameter_header_size = int.from_bytes(parameter_header_size, BYTE_ORDER, signed=False)
            parameter_bytes = self._recv_n_bytes(parameter_header_size)
            parameters = serialization.load_pem_parameters(parameter_bytes)

        # Generate private key
        priv_key = parameters.generate_private_key()

        # Send public key
        my_pkey_bytes = priv_key.public_key().public_bytes(
                                                serialization.Encoding.PEM, 
                                                serialization.PublicFormat.SubjectPublicKeyInfo
                                            )
        send_size_header = len(my_pkey_bytes).to_bytes(HEADER_SIZE, BYTE_ORDER, signed=False)
        self._sock.sendall(send_size_header)
        self._sock.sendall(my_pkey_bytes)

        # Receive peer public key
        recv_header_raw = self._sock.recv(HEADER_SIZE)
        recv_size_header = int.from_bytes(recv_header_raw, BYTE_ORDER, signed=False)
        peer_pub_key_raw = self._recv_n_bytes(recv_size_header) 
        peer_pub_key = serialization.load_pem_public_key(bytes(peer_pub_key_raw)) 

        # Derive symmetric key
        self._shared_key = priv_key.exchange(peer_pub_key) 
        self._derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=AES_KEY_LENGTH,
            salt=None,
            info=b'handshake'
        ).derive(self._shared_key)
    
    def _recv_n_bytes(self, n: int):
        byte_buf = bytearray()
        while len(byte_buf) < n:
            to_read = BUFFER_SIZE
            if to_read > n - len(byte_buf):
                to_read = n - len(byte_buf)
            data = self._sock.recv(to_read)
            byte_buf.extend(data)
        return bytes(byte_buf)

    
    def close(self):
        self._sock.close()