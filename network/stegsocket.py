import os
import socket
import select
import tempfile
from stego import StegoTranscoder

HEADER_SIZE = 4
BYTE_ORDER = 'little'
BUFFER_SIZE = 4096
POLL_TIME_MS = 5000

class StegoSocket:
    def __init__(self, image_repo, sock):
        self.sock = sock 
        self.poller = select.poll() 
        self.poller.register(self.sock, select.POLLIN)

        self.image_repo = [os.path.join(image_repo, f) for f in os.listdir(image_repo) if os.path.isfile(os.path.join(image_repo, f))]
        self.img_idx = 0

        self.transcoder = StegoTranscoder()
        None

    def send(self, message):
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

    def recv(self):
        # Check if any data is on the pipe 
        header = None
        events = self.poller.poll(POLL_TIME_MS)
        for sock, event in events:
            if event and select.POLLIN:
                if sock == self.sock.fileno():
                    header = self.sock.recv(HEADER_SIZE)
        
        if header is None:
            return []

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
        
        msg = self.transcoder.decode(medium_out_file)
        os.remove(medium_out_file)
        return msg