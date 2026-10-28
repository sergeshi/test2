"""Send a sample level snapshot to a running Level Archaeologist bridge."""
import json
import socket

snapshot = {
    "name": "Runtime demo — old corridor",
    "source": "demo adapter",
    "units": "cm",
    "objects": [
        {"name": "Floor", "type": "collision", "position": [0, 0, -20], "size": [1200, 800, 40]},
        {"name": "North wall", "type": "collision", "position": [0, 390, 140], "size": [1200, 20, 280]},
        {"name": "South wall", "type": "collision", "position": [0, -390, 140], "size": [1200, 20, 280]},
        {"name": "West wall", "type": "collision", "position": [-590, 0, 140], "size": [20, 800, 280]},
        {"name": "East doorway left", "type": "collision", "position": [590, -230, 140], "size": [20, 340, 280]},
        {"name": "East doorway right", "type": "collision", "position": [590, 300, 140], "size": [20, 200, 280]},
        {"name": "Crate", "type": "static_mesh", "position": [100, 60, 45], "size": [100, 100, 90]},
    ],
}

with socket.create_connection(("127.0.0.1", 47831), timeout=3) as connection:
    connection.sendall((json.dumps(snapshot, ensure_ascii=False) + "\n").encode("utf-8"))
    print("Bridge reply:", connection.recv(4096).decode("utf-8").strip())
