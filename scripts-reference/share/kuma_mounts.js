// INSIDE uptime-kuma: ensure a "Mount <mp>" push monitor exists for every mountpoint in MOUNTS (cloned from "Mount /mnt/disk2"),
// give EVERY listed mount monitor a fresh push token (rotation), add new ones to the status page group of the template,
// and write "<mp> http://127.0.0.1:3001/api/push/<token>" lines to /app/data/.mountpush (600). Never prints a token.
const sqlite3 = require("@louislam/sqlite3");
const crypto = require("crypto"); const fs = require("fs");
const jwt = require("jsonwebtoken"); const { io } = require("socket.io-client");
const MOUNTS = (process.env.MOUNTS || "").split(/\s+/).filter(Boolean);
const db = new sqlite3.Database("/app/data/kuma.db", sqlite3.OPEN_READONLY);
const q = (s, p = []) => new Promise((res, rej) => db.get(s, p, (e, r) => (e ? rej(e) : res(r))));
const all = (s, p = []) => new Promise((res, rej) => db.all(s, p, (e, r) => (e ? rej(e) : res(r))));
const shake = (d) => crypto.createHash("shake256", { outputLength: 16 }).update(d).digest("hex");
const tok = () => crypto.randomBytes(24).toString("base64url").slice(0, 32);
(async () => {
  const u = await q("SELECT username, password FROM user WHERE active = 1 ORDER BY id LIMIT 1");
  const raw = (await q("SELECT value FROM setting WHERE key = 'jwtSecret'")).value;
  let sec; try { sec = JSON.parse(raw); } catch { sec = raw; }
  const s = io("http://127.0.0.1:3001", { transports: ["websocket"], reconnection: false });
  const emit = (ev, ...a) => new Promise((res) => s.emit(ev, ...a, res));
  await new Promise((r) => s.on("connect", r));
  if (!(await emit("loginByToken", jwt.sign({ username: u.username, h: shake(u.password) }, sec))).ok) { console.log("LOGIN FAILED"); process.exit(1); }
  const tplRow = await q("SELECT id FROM monitor WHERE name = 'Mount /mnt/disk2'");
  const tpl = (await emit("getMonitor", tplRow.id)).monitor;
  const lines = [];
  for (const mp of MOUNTS) {
    const name = "Mount " + mp; const t = tok();
    const row = await q("SELECT id FROM monitor WHERE name = ?", [name]);
    if (row) {
      const m = (await emit("getMonitor", row.id)).monitor; m.pushToken = t;
      const r = await emit("editMonitor", m); console.log("rotate", name + ":", r.ok ? "ok" : r.msg); if (!r.ok) process.exit(1);
    } else {
      const m = { ...tpl, id: undefined, name, pushToken: t, description: `${mp} mounted (pushed by mount-push every minute)` };
      for (const k of ["id", "path", "pathName", "childrenIDs", "tags", "maintenance", "screenshot", "includeSensitiveData", "forceInactive", "active"]) delete m[k];
      const r = await emit("add", m); console.log("add", name + ":", r.ok ? "ok" : r.msg); if (!r.ok) process.exit(1);
      const maint = await all("SELECT maintenance_id FROM monitor_maintenance WHERE monitor_id = ?", [tplRow.id]);
      for (const x of maint) {
        const linked = await all("SELECT monitor_id FROM monitor_maintenance WHERE maintenance_id = ?", [x.maintenance_id]);
        await emit("addMonitorMaintenance", x.maintenance_id, [...linked.map((y) => ({ id: y.monitor_id })), { id: r.monitorID }]);
      }
    }
    lines.push(`${mp} http://127.0.0.1:3001/api/push/${t}`);
  }
  fs.writeFileSync("/app/data/.mountpush", "# <mountpoint> <uptime-kuma push url>\n" + lines.join("\n") + "\n", { mode: 0o600 });
  console.log("mount push lines:", lines.length);
  s.close(); process.exit(0);
})().catch((e) => { console.log("ERROR", e.message.slice(0, 120)); process.exit(1); });
