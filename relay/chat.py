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

username = str(input("Enter alias> "))
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((host, port))
stego_sock = StegoSocket("../images/", sock)

handshake_msg = json.dumps({constants.CHANNEL_PARAM: channel}).encode(constants.CHAR_ENCODING)
stego_sock.send(handshake_msg)
print("[CONNECTED TO SERVER]")

CURSOR_UP_ONE = '\x1b[1A'
ERASE_LINE = '\x1b[2K'

def receive_messages():
    while True:
        msg = stego_sock.recv()
        if msg is not None:
            messages = json.loads(msg.decode(constants.CHAR_ENCODING))
            for message in messages[constants.MESSAGES_PARAM]:
                print(CURSOR_UP_ONE + ERASE_LINE + message)
        time.sleep(1)

def write_messages():
    while True:
        message = username + "> " + str(input('> '))
        if not stego_sock.send(message.encode(constants.CHAR_ENCODING)):
            print("[ERROR] Failed to send message")
    


receiver = threading.Thread(target=receive_messages)
receiver.start()

writer = threading.Thread(target=write_messages) 
writer.start()




