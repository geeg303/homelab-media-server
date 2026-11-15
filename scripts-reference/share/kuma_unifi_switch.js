// INSIDE uptime-kuma: add the USW Flex Mini checks (idempotent). Never prints a token.
//  - "UniFi switch (ping 192.0.2.95)"  ping, Infrastructure group, cloned from "Router (192.0.2.1)"
//  - "UniFi switch (Flex Mini)"           push, Host health group, cloned from "UniFi router health"; token -> /app/data/.unifiswitch (600)
// Then the box status page is re-saved by kuma_statuspage.js (run separately).
const sqlite3 = require("@louislam/sqlite3");
const crypto = require("crypto"); const fs = require("fs");
const jwt = require("jsonwebtoken"); const { io } = require("socket.io-client");
const db = new sqlite3.Database("/app/data/kuma.db", sqlite3.OPEN_READONLY);
const q = (s, p = []) => new Promise((res, rej) => db.get(s, p, (e, r) => (e ? rej(e) : res(r))));
const all = (s, p = []) => new Promise((res, rej) => db.all(s, p, (e, r) => (e ? rej(e) : res(r))));
const shake = (d) => crypto.createHash("shake256", { outputLength: 16 }).update(d).digest("hex");
const tok = () => crypto.randomBytes(24).toString("base64url").slice(0, 32);
const STRIP = ["id", "path", "pathName", "childrenIDs", "tags", "maintenance", "screenshot", "includeSensitiveData", "forceInactive", "active"];
(async () => {
  const raw = (await q("SELECT value FROM setting WHERE key = 'jwtSecret'")).value;
  let sec; try { sec = JSON.parse(raw); } catch { sec = raw; }
  const u = await q("SELECT username, password FROM user WHERE active = 1 ORDER BY id LIMIT 1");
  const s = io("http://127.0.0.1:3001", { transports: ["websocket"], reconnection: false });
  const emit = (ev, ...a) => new Promise((res) => s.emit(ev, ...a, res));
  await new Promise((r) => s.on("connect", r));
  if (!(await emit("loginByToken", jwt.sign({ username: u.username, h: shake(u.password) }, sec))).ok) { console.log("LOGIN FAILED"); process.exit(1); }
  const clone = async (tplName, name, extra) => {
    const tplRow = await q("SELECT id FROM monitor WHERE name = ?", [tplName]);
    const have = await q("SELECT id FROM monitor WHERE name = ?", [name]);
    if (have) { console.log("exists", name, have.id); return { id: have.id, existed: true }; }
    const tpl = (await emit("getMonitor", tplRow.id)).monitor;
    const m = { ...tpl, ...extra, name };
    for (const k of STRIP) delete m[k];
    const r = await emit("add", m); console.log("add", name + ":", r.ok ? "ok id " + r.monitorID : r.msg); if (!r.ok) process.exit(1);
    const maint = await all("SELECT maintenance_id FROM monitor_maintenance WHERE monitor_id = ?", [tplRow.id]);
    for (const x of maint) {
      const linked = await all("SELECT monitor_id FROM monitor_maintenance WHERE maintenance_id = ?", [x.maintenance_id]);
      await emit("addMonitorMaintenance", x.maintenance_id, [...linked.map((y) => ({ id: y.monitor_id })), { id: r.monitorID }]);
    }
    return { id: r.monitorID, existed: false };
  };
  await clone("Router (192.0.2.1)", "UniFi switch (ping 192.0.2.95)",
    { hostname: "192.0.2.95", description: "USW Flex Mini 5-port switch (added Nov 15), answers ping" });
  const t = tok();
  const p = await clone("UniFi router health", "UniFi switch (Flex Mini)",
    { pushToken: t, description: "USW Flex Mini as UniFi sees it: online, uplink at 1 Gbps, port errors (pushed by host-health-push)" });
  if (!p.existed) fs.writeFileSync("/app/data/.unifiswitch", `UniFi switch (Flex Mini)\t${t}\n`, { mode: 0o600 });
  s.close(); process.exit(0);
})().catch((e) => { console.log("ERROR", e.message.slice(0, 120)); process.exit(1); });
