import sys
sys.path.append("../network")

import json
import select
import socket
import threading
from network.stegsocket import StegoSocket

# Constants
QUEUED_SOCKETS_LIMIT = 10 
CHANNEL_PARAM = "channel"
POLL_PERIOD_MS = 5000
SOCK_TIMEOUT = 1 

# Shared Memory
sockets_mutex = threading.Lock()
pollers_mutex = threading.Lock()
sockets = {}
pollers = {}


def client_ingestion_daemon(host, port, image_repo):
    sock = socket.socket() 
    sock.bind((host, port))
    sock.listen(QUEUED_SOCKETS_LIMIT)

    while True:
        client_sock, _ = sock.accept()
        client_sock.settimeout(SOCK_TIMEOUT)
        stego_sock = StegoSocket(image_repo, client_sock)

        raw_message = stego_sock.recv() 
        message = json.loads(raw_message)
        channel = message[CHANNEL_PARAM]

        pollers_mutex.acquire()
        sockets_mutex.acquire()
        if channel not in pollers:
            pollers[channel] = select.poll()
            sockets[channel] = {} 
        pollers[channel].register(stego_sock.sock, select.POLLIN)
        sockets[channel][stego_sock.sock.fileno()] = stego_sock
        sockets_mutex.release()
        pollers_mutex.release()

def cleanup_resource(channel_id, sock_id):
    pollers[channel_id].unregister(sock_id)
    del sockets[channel_id][sock_id]

    if len(sockets[channel_id]) == 0:
        del sockets[channel_id]

def routing_daemon():
    while True:
        for channel in pollers:
            # Accumulate messages in channel
            pollers_mutex.acquire()
            sockets_mutex.acquire()
            messages = []
            events = pollers[channel].poll(POLL_PERIOD_MS)
            for sock_id, event in events:
                if event and select.POLLIN:
                    stego_sock = sockets[channel][sock_id]
                    try:
                        message = stego_sock.recv()
                        messages.append(message)
                    except socket.timeout:
                        cleanup_resource(channel, sock_id)
            sockets_mutex.release()
            pollers_mutex.release()
            
            # Relay messages
            sockets_mutex.acquire()
            if messages != []:
                master_message = json.dumps(messages)
                for sock_id in list(sockets.keys()):
                    stego_sock = sockets[channel][sock_id]
                    try:
                        stego_sock.send(master_message)
                    except socket.timeout:
                        cleanup_resource(channel, sock_id)
            sockets_mutex.release()


if __name__ == "__main__":
    ingestion_thread = threading.Thread(target=client_ingestion_daemon, args=(host, port, image_repo), daemon=True)
    routing_thread = threading.Thread(target=routing_daemon, daemon=True)

    ingestion_thread.start()
    routing_thread.start()

    ingestion_thread.join()
    routing_thread.join()
