// INSIDE uptime-kuma: manual maintenance "Planned work" over ALL monitors + the box status page.
// ACTION=setup|on|off|status. setup is idempotent (created paused). on = resumeMaintenance, off = pauseMaintenance.
const sqlite3 = require("@louislam/sqlite3"); const crypto = require("crypto");
const jwt = require("jsonwebtoken"); const { io } = require("socket.io-client");
const db = new sqlite3.Database("/app/data/kuma.db", sqlite3.OPEN_READONLY);
const q = (s, p = []) => new Promise((res, rej) => db.get(s, p, (e, r) => (e ? rej(e) : res(r))));
const qa = (s, p = []) => new Promise((res, rej) => db.all(s, p, (e, r) => (e ? rej(e) : res(r))));
const shake = (d) => crypto.createHash("shake256", { outputLength: 16 }).update(d).digest("hex");
const ACTION = process.env.ACTION || "status"; const TITLE = "Planned work (updates / reboot)";
(async () => {
  const u = await q("SELECT username, password FROM user WHERE active = 1 ORDER BY id LIMIT 1");
  const raw = (await q("SELECT value FROM setting WHERE key = 'jwtSecret'")).value; let sec; try { sec = JSON.parse(raw); } catch { sec = raw; }
  const s = io("http://127.0.0.1:3001", { transports: ["websocket"], reconnection: false });
  const emit = (ev, ...a) => new Promise((res) => s.emit(ev, ...a, res));
  await new Promise((r) => s.on("connect", r));
  if (!(await emit("loginByToken", jwt.sign({ username: u.username, h: shake(u.password) }, sec))).ok) { console.log("LOGIN FAILED"); process.exit(1); }
  let m = await q("SELECT id, active FROM maintenance WHERE title = ?", [TITLE]);
  const allMons = async () => (await qa("SELECT id FROM monitor WHERE active = 1")).map((x) => ({ id: x.id }));
  if (ACTION === "setup") {
    if (!m) {
      const tpl = (await emit("getMaintenance", 1)).maintenance;
      const obj = { ...tpl }; delete obj.id; delete obj.status; delete obj.timeslotList;
      Object.assign(obj, { title: TITLE, description: "Turned on by box scripts around planned reboots and container updates, with an expiry; turned off automatically.", strategy: "manual", active: true });
      const r = await emit("addMaintenance", obj); if (!r.ok) { console.log("addMaintenance:", r.msg); process.exit(1); }
      m = { id: r.maintenanceID }; console.log("created maintenance", m.id);
    }
    const mons = await allMons();
    let r = await emit("addMonitorMaintenance", m.id, mons); console.log("monitors:", mons.length, r.ok ? "ok" : r.msg);
    const sp = await q("SELECT id FROM status_page WHERE slug = 'box'");
    if (sp) { r = await emit("addMaintenanceStatusPage", m.id, [{ id: sp.id }]); console.log("status page:", r.ok ? "ok" : r.msg); }
    r = await emit("pauseMaintenance", m.id); console.log("left OFF:", r.ok ? "ok" : r.msg);
  } else if (ACTION === "on" || ACTION === "off") {
    if (!m) { console.log("not set up"); process.exit(1); }
    if (ACTION === "on") await emit("addMonitorMaintenance", m.id, await allMons());   // include monitors added since setup
    const r = await emit(ACTION === "on" ? "resumeMaintenance" : "pauseMaintenance", m.id);
    console.log("maintenance", ACTION, r.ok ? "ok" : r.msg);
  } else {
    console.log(m ? `maintenance ${m.id} ${m.active ? "ON" : "off"}` : "not set up");
  }
  s.close(); process.exit(0);
})().catch((e) => { console.log("ERROR", e.message.slice(0, 160)); process.exit(1); });
