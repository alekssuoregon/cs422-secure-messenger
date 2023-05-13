from stegsocket import StegoSocket 
import socket

if __name__ == "__main__":
    image_repo = "images/"
    working_dir = "working/"
    host = "127.0.0.1"
    port = 55527
    s = socket.socket()
    s.bind((host, port))

    while True:
        s.listen(5)
        client_socket, address = s.accept()
        steg_sock = StegoSocket(image_repo, working_dir, client_socket) 
        message = steg_sock.recv()
        while True:
            if message == []:
                message = steg_sock.recv()
            else:
                print(message)
                steg_sock.send("This is my return message")
                message = []
