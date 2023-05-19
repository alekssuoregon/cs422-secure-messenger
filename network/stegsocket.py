import os
import socket
import select
import tempfile
import threading
from stego import StegoTranscoder

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import dh
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

HEADER_SIZE = 4
BYTE_ORDER = 'little'
BUFFER_SIZE = 4096
POLL_TIME_MS = 5000

class StegoSocket:
    def __init__(self, image_repo: str, sock: socket.socket, is_server: bool = False):
        self.sock = sock 
        self.poller = select.poll() 
        self.poller.register(self.sock, select.POLLIN)

        self.image_repo = [os.path.join(image_repo, f) for f in os.listdir(image_repo) if os.path.isfile(os.path.join(image_repo, f))]
        self.img_idx = 0

        self.transcoder = StegoTranscoder()
        self.__key_exchange(is_server)

    def send(self, message: bytes) -> bool:
        medium_in_file = self.image_repo[self.img_idx]
        self.img_idx = (self.img_idx + 1) % len(self.image_repo)
        medium_out_file = tempfile.NamedTemporaryFile().name + ".png"

        if not self.transcoder.encode(message, medium_in_file, medium_out_file):
            return False
        
        img_size = os.path.getsize(medium_out_file)
        header = img_size.to_bytes(HEADER_SIZE, BYTE_ORDER, signed=False)

        self.sock.sendall(header)
        with open(medium_out_file, "rb") as f:
            while True:
                bytes_read = f.read(BUFFER_SIZE)
                if not bytes_read:
                    break
                self.sock.sendall(bytes_read)
        os.remove(medium_out_file)

        return True

    def recv(self) -> bytes | None:
        # Check if any data is on the pipe 
        header = None
        events = self.poller.poll(POLL_TIME_MS)
        for sock, event in events:
            if event and select.POLLIN:
                if sock == self.sock.fileno():
                    header = self.sock.recv(HEADER_SIZE)
        
        if header is None:
            return None 

        # Receive image
        img_size = int.from_bytes(header, BYTE_ORDER, signed=False)
        read_bytes = 0
        medium_out_file = tempfile.NamedTemporaryFile().name + ".png" 
        with open(medium_out_file, "wb") as f:
            while read_bytes < img_size:
                buf_size = BUFFER_SIZE
                if buf_size > img_size - read_bytes:
                    buf_size = img_size - read_bytes

                bytes_read = self.sock.recv(BUFFER_SIZE)
                if not bytes_read:
                    break
                read_bytes += len(bytes_read)
                f.write(bytes_read)
        
        try:
            msg = self.transcoder.decode(medium_out_file)
        except:
            raise socket.error

        os.remove(medium_out_file)
        return msg
    
    def __key_exchange(self, server):
        # Generate/receive DH parameters
        if server:
            parameters = dh.generate_parameters(generator=2, key_size=2048)
            parameter_bytes = parameters.parameter_bytes(
                                            serialization.Encoding.PEM,
                                            serialization.ParameterFormat.PKCS3,
                                        )
            parameter_header_size = len(parameter_bytes).to_bytes(HEADER_SIZE, BYTE_ORDER, signed=False)
            self.sock.sendall(parameter_header_size)
            self.sock.sendall(parameter_bytes)
        else:
            parameter_header_size = self.sock.recv(HEADER_SIZE)
            parameter_header_size = int.from_bytes(parameter_header_size, BYTE_ORDER, signed=False)
            parameter_bytes = self.__recv_n_bytes(parameter_header_size)
            parameters = serialization.load_pem_parameters(parameter_bytes)

        # Generate private key
        priv_key = parameters.generate_private_key()

        # Send public key
        my_pkey_bytes = priv_key.public_key().public_bytes(
                                                serialization.Encoding.PEM, 
                                                serialization.PublicFormat.SubjectPublicKeyInfo
                                            )
        send_size_header = len(my_pkey_bytes).to_bytes(HEADER_SIZE, BYTE_ORDER, signed=False)
        self.sock.sendall(send_size_header)
        self.sock.sendall(my_pkey_bytes)

        # Receive peer public key
        recv_header_raw = self.sock.recv(HEADER_SIZE)
        recv_size_header = int.from_bytes(recv_header_raw, BYTE_ORDER, signed=False)
        peer_pub_key_raw = self.__recv_n_bytes(recv_size_header) 
        peer_pub_key = serialization.load_pem_public_key(bytes(peer_pub_key_raw)) 

        # Derive symmetric key
        self._shared_key = priv_key.exchange(peer_pub_key) 
        self._derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b'handshake data'
        )
        print("Derived Key! ", self._derived_key)
    
    def __recv_n_bytes(self, n):
        byte_buf = bytearray()
        while len(byte_buf) < n:
            to_read = BUFFER_SIZE
            if to_read > n - len(byte_buf):
                to_read = n - len(byte_buf)
            data = self.sock.recv(to_read)
            byte_buf.extend(data)
        return bytes(byte_buf)

    
    def close(self):
        self.sock.close()