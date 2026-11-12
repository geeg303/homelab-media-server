#!/usr/bin/env python3
# Minimal Home Assistant WebSocket client (stdlib only). Usage on the box (root):
#   python3 ha_ws.py '<json command without id>' ['<json>' ...]   -> prints each result as JSON
# Token: first long line of /etc/media-server/ha-token. Never prints the token.
import base64, json, os, socket, struct, sys
HOST, PORT = "192.0.2.150", 80
TOKEN = next(l.strip() for l in open("/etc/media-server/ha-token") if len(l.strip()) > 100)
s = socket.create_connection((HOST, PORT), timeout=30)
key = base64.b64encode(os.urandom(16)).decode()
s.sendall((f"GET /api/websocket HTTP/1.1\r\nHost: {HOST}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
buf = b""
while b"\r\n\r\n" not in buf: buf += s.recv(4096)
assert b" 101 " in buf.split(b"\r\n")[0], buf[:100]
rest = buf.split(b"\r\n\r\n", 1)[1]
def recv_exact(n):
    global rest
    while len(rest) < n:
        d = s.recv(65536)
        if not d: raise EOFError
        rest += d
    out, rest = rest[:n], rest[n:]; return out
def recv():
    msg = b""
    while True:
        b1, b2 = recv_exact(2); n = b2 & 127
        if n == 126: n = struct.unpack(">H", recv_exact(2))[0]
        elif n == 127: n = struct.unpack(">Q", recv_exact(8))[0]
        data = recv_exact(n); op = b1 & 15
        if op == 9: send_frame(data, 10); continue
        msg += data
        if b1 & 128: return json.loads(msg)
def send_frame(data, op=1):
    m = os.urandom(4); n = len(data)
    hdr = bytes([128 | op]) + (bytes([128 | n]) if n < 126 else bytes([128 | 126]) + struct.pack(">H", n) if n < 65536 else bytes([128 | 127]) + struct.pack(">Q", n))
    s.sendall(hdr + m + bytes(b ^ m[i % 4] for i, b in enumerate(data)))
def send(o): send_frame(json.dumps(o).encode())
assert recv()["type"] == "auth_required"
send({"type": "auth", "access_token": TOKEN})
r = recv(); assert r["type"] == "auth_ok", r.get("type")
i = 0
for arg in sys.argv[1:]:
    i += 1; cmd = json.loads(open(arg[1:]).read() if arg.startswith("@") else arg); cmd["id"] = i; send(cmd)
    while True:
        r = recv()
        if r.get("id") == i and r.get("type") == "result": print(json.dumps(r.get("result") if r.get("success") else {"ERROR": r.get("error")})); break
