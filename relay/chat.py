import sys
sys.path.append("../network")
sys.path.append("..")

import time
import json
import socket
import select
import constants
import threading
from network.stegsocket import StegoSocket

host = sys.argv[1]
port = int(sys.argv[2])
channel = sys.argv[3]

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((host, port))
stego_sock = StegoSocket("../images/", sock)

mutex = threading.Lock()
messages = [] 

def receive_messages():
    global messages

    while True:
        msg = stego_sock.recv()
        if msg is not None:
            mutex.acquire()
            messages.append(msg)
            mutex.release()
        time.sleep(1)
    


stego_sock.send(json.dumps({constants.CHANNEL_PARAM: channel}))
receiver = threading.Thread(target=receive_messages, daemon=True)
receiver.start()

while True:
    message = str(input("Message> "))
    if not stego_sock.send(message):
        print("Failed to send message")

    mutex.acquire()
    if len(messages) != 0: 
        for msg in messages:
            print("Received> ", msg)
        messages = []
    mutex.release()




