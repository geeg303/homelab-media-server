# Headless Edge + raw CDP: log into HA with the long-lived token (read from file, never printed), screenshot a dashboard view,
# count error cards. Usage: python ha_shot.py <path> <out.png> [width] [height]
import base64, json, os, socket, struct, subprocess, sys, time, urllib.request, shutil
SCR = r"C:\Users\user\AppData\Local\hermes\cache\scratch"
path, out = sys.argv[1], sys.argv[2]; W = int(sys.argv[3]) if len(sys.argv) > 3 else 1400; H = int(sys.argv[4]) if len(sys.argv) > 4 else 1700
prof = os.path.join(SCR, "edge-ha-prof")
p = subprocess.Popen([r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "--headless=new", "--remote-debugging-port=9333",
                      f"--user-data-dir={prof}", "--no-first-run", "--disable-gpu", f"--window-size={W},{H}", "about:blank"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(40):
        try: tg = json.loads(urllib.request.urlopen("http://127.0.0.1:9333/json", timeout=2).read()); break
        except Exception: time.sleep(0.5)
    wsurl = next(t["webSocketDebuggerUrl"] for t in tg if t["type"] == "page")
    hostport, rpath = wsurl[5:].split("/", 1); host, port = hostport.split(":")
    s = socket.create_connection((host, int(port)), timeout=60)
    s.sendall((f"GET /{rpath} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {base64.b64encode(os.urandom(16)).decode()}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    buf = b""
    while b"\r\n\r\n" not in buf: buf += s.recv(4096)
    rest = buf.split(b"\r\n\r\n", 1)[1]
    def rx(n):
        global rest
        while len(rest) < n: rest += s.recv(1 << 20)
        o, rest = rest[:n], rest[n:]; return o
    def recv():
        m = b""
        while True:
            b1, b2 = rx(2); n = b2 & 127
            if n == 126: n = struct.unpack(">H", rx(2))[0]
            elif n == 127: n = struct.unpack(">Q", rx(8))[0]
            m += rx(n)
            if b1 & 128: return json.loads(m)
    mid = [0]
    def call(method, **params):
        mid[0] += 1; d = json.dumps({"id": mid[0], "method": method, "params": params}).encode(); k = os.urandom(4); n = len(d)
        hdr = bytes([129]) + (bytes([128 | n]) if n < 126 else bytes([254]) + struct.pack(">H", n) if n < 65536 else bytes([255]) + struct.pack(">Q", n))
        s.sendall(hdr + k + bytes(b ^ k[i % 4] for i, b in enumerate(d)))
        while True:
            r = recv()
            if r.get("id") == mid[0]: return r.get("result", r)
    call("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1, mobile=W < 600)
    tok = open(os.path.join(SCR, ".hat")).read().strip()
    call("Page.enable")
    call("Page.addScriptToEvaluateOnNewDocument", source="window.externalApp = { getExternalAuth: (p) => { const o = JSON.parse(p); setTimeout(() => window[o.callback](true, {access_token: " + json.dumps(tok) + ", expires_in: 86400}), 0); }, revokeExternalAuth: (p) => {}, externalBus: (m) => { const o = JSON.parse(m); if (o.type === \"config/get\") setTimeout(() => window.externalBus({id: o.id, type: \"result\", success: true, result: {hasSettingsScreen: false, canWriteTag: false, hasExoPlayer: false, canCommissionMatter: false, canImportThreadCredentials: false, hasAssist: false, hasBarCodeScanner: 0, canSetupImprov: false}}), 0); } };")
    del tok
    call("Page.navigate", url="http://192.0.2.150" + path + ("&" if "?" in path else "?") + "external_auth=1")
    probe = "(() => { const ha = document.querySelector('home-assistant'); const m = ha?.shadowRoot?.querySelector('home-assistant-main'); return m ? 'main' : (document.body.innerText||'').slice(0,60); })()"
    for _ in range(40):
        time.sleep(1)
        st_ = call("Runtime.evaluate", expression=probe, returnByValue=True)["result"].get("value")
        if st_ == "main": break
    print("app state:", st_); time.sleep(6)
    js = r"""(() => { const out = []; const walk = (n) => { if (!n) return; if (n.tagName && /hui-error-card|hui-warning/i.test(n.tagName)) out.push((n.innerText||n.shadowRoot?.textContent||'').trim().slice(0,160));
      (n.shadowRoot ? [...n.shadowRoot.children] : []).concat([...(n.children||[])]).forEach(walk); }; walk(document.body); return JSON.stringify({title: document.title, errors: out}); })()"""
    print(call("Runtime.evaluate", expression=js, returnByValue=True)["result"].get("value"))
    img = call("Page.captureScreenshot", format="png")["data"]
    open(out, "wb").write(base64.b64decode(img)); print("saved", out)
finally:
    p.kill(); p.wait(); time.sleep(1); shutil.rmtree(prof, ignore_errors=True)
