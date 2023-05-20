import sys
sys.path.append("../network")
sys.path.append("..")

import os
import json
import select
import socket
import constants
import threading
from network.stegsocket import StegoSocket
from configparser import ConfigParser

# Constants
QUEUED_SOCKETS_LIMIT = 10 
POLL_PERIOD_MS = 5000

# Shared Memory
sockets_mutex = threading.Lock()
pollers_mutex = threading.Lock()
sockets = {}
pollers = {}

# Handle initial connections being placed in the right resource stores
def client_ingestion_daemon(host, port, image_repo):
    sock = socket.socket() 
    sock.bind((host, port))
    sock.listen(QUEUED_SOCKETS_LIMIT)

    while True:
        client_sock, _ = sock.accept()
        client_sock.settimeout(constants.SOCK_TIMEOUT)
        stego_sock = StegoSocket(image_repo, client_sock, encryption=True, is_server=True)

        raw_message = stego_sock.recv().decode(constants.CHAR_ENCODING) 
        message = json.loads(raw_message)
        channel = message[constants.CHANNEL_PARAM]

        pollers_mutex.acquire()
        sockets_mutex.acquire()
        if channel not in pollers:
            print("Creating Channel: " + channel)
            pollers[channel] = select.poll()
            sockets[channel] = {} 
        pollers[channel].register(stego_sock.__sock, select.POLLIN)
        sockets[channel][stego_sock.__sock.fileno()] = stego_sock
        sockets_mutex.release()
        pollers_mutex.release()

# Handle removal of dead connections and resources
def cleanup_resource(channel_id, sock_id):
    pollers[channel_id].unregister(sock_id)
    del sockets[channel_id][sock_id]

    if len(sockets[channel_id]) == 0:
        print("deleteing channel: " + channel_id)
        del pollers[channel_id]
        del sockets[channel_id]

# Handle routing of messages between connections in channels
def routing_daemon():
    while True:
        for channel in list(pollers.keys()):
            # Accumulate messages in channel
            pollers_mutex.acquire()
            sockets_mutex.acquire()
            messages = []
            events = pollers[channel].poll(POLL_PERIOD_MS)
            for sock_id, event in events:
                if event and select.POLLIN:
                    stego_sock = sockets[channel][sock_id]
                    try:
                        message = stego_sock.recv().decode(constants.CHAR_ENCODING)
                        messages.append(message)
                    except:
                        cleanup_resource(channel, sock_id)
            sockets_mutex.release()
            pollers_mutex.release()
            
            # Relay messages
            sockets_mutex.acquire()
            if len(messages) != 0:
                master_message = json.dumps({constants.MESSAGES_PARAM: messages}).encode(constants.CHAR_ENCODING)
                for sock_id in list(sockets[channel].keys()):
                    stego_sock = sockets[channel][sock_id]
                    try:
                        stego_sock.send(master_message)
                    except:
                        print("Problem. Cleaning up")
                        cleanup_resource(channel, sock_id)
            sockets_mutex.release()


if __name__ == "__main__":
    # Read configuration file
    if len(sys.argv) < 2:
        print("[Error] No Configuration File Passed")
        os.exit(1)

    parser = ConfigParser()
    parser.read(sys.argv[1])

    host = parser.get('network', 'host')
    port = int(parser.get('network', 'port'))
    image_repo = parser.get('security', 'image_repository')

    # Start threads
    ingestion_thread = threading.Thread(target=client_ingestion_daemon, args=(host, port, image_repo), daemon=True)
    routing_thread = threading.Thread(target=routing_daemon, daemon=True)

    ingestion_thread.start()
    routing_thread.start()

    # Hang indefinitely
    ingestion_thread.join()
    routing_thread.join()
