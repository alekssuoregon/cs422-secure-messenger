import sys
sys.path.append("../network")
sys.path.append("..")

import json
import socket
import constants
from network.stegsocket import StegoSocket
from flask import Flask, request, jsonify

app = Flask(__name__)

#Constants
DEFAULT_RELAY_PORT = 56565

# Global Service Variables
active_connection = None
image_repo = "../images"

@app.route("/connect")
def connect():
    # Close current connection
    if active_connection is not None:
        active_connection.close()

    # Extract connection parameters
    server_url = request.args.get("server")
    channel_name = request.args.get("channel")

    host, port = "", DEFAULT_RELAY_PORT
    if server_url.find(":") != -1:
        connection_parts = server_url.split(":")
        host = connection_parts[0]
        port = int(connection_parts[1])
    else:
        host = server_url
    

    # Connect to server
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    sock.timeout(constants.SOCK_TIMEOUT)
    active_connection = StegoSocket(image_repo, sock) 

    handshake_msg = json.dumps({constants.CHANNEL_PARAM: channel_name})
    try:
        if not active_connection.send(handshake_msg):
            return {'error': 'connection failed'}, 500
    except socket.timeout:
        return {'error': 'connection timeout'}, 408


@app.route("/disconnect")
def disconnect():
    if active_connection is not None:
        active_connection.close()

@app.route("/send")
def send():
    message = request.args.get("message")
    if active_connection is not None:
        try:
            if not active_connection.send(message):
                return {'error': 'send failed'}, 500
        except socket.timeout:
            return {'error': 'connection timeout'}, 408
    else:
        return {'error': 'not connected to server'}, 500

@app.route("/recv")
def recv():
    if active_connection is not None:
        try:
            message = active_connection.recv()
            return json.loads(message) 
        except socket.timeout:
            return {'error': 'connection timeout'}, 408
    else:
        return {'error': 'not connected to server'}, 500
