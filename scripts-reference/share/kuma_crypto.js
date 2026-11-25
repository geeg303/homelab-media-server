// INSIDE uptime-kuma: "Crypto bots" group + dashboard HTTP check + 4 docker checks, ntfy attached,
// NOT in any maintenance window, then appended to status page "box" keeping every existing group. Idempotent.
// Never prints a secret.
const sqlite3 = require("@louislam/sqlite3");
const crypto = require("crypto");
const jwt = require("jsonwebtoken"); const { io } = require("socket.io-client");
const db = new sqlite3.Database("/app/data/kuma.db", sqlite3.OPEN_READONLY);
const q = (s, p = []) => new Promise((res, rej) => db.get(s, p, (e, r) => (e ? rej(e) : res(r))));
const shake = (d) => crypto.createHash("shake256", { outputLength: 16 }).update(d).digest("hex");
const STRIP = ["id", "path", "pathName", "childrenIDs", "tags", "maintenance", "screenshot", "includeSensitiveData", "forceInactive", "active", "parent"];
const GROUP = "Crypto bots";
(async () => {
  const raw = (await q("SELECT value FROM setting WHERE key = 'jwtSecret'")).value;
  let sec; try { sec = JSON.parse(raw); } catch { sec = raw; }
  const u = await q("SELECT username, password FROM user WHERE active = 1 ORDER BY id LIMIT 1");
  const notif = (await q("SELECT id FROM notification WHERE name = 'ntfy (box alerts)'")).id;
  const dh = (await q("SELECT id FROM docker_host WHERE docker_daemon = 'tcp://socket-proxy:2375'")).id;
  const s = io("http://127.0.0.1:3001", { transports: ["websocket"], reconnection: false });
  const emit = (ev, ...a) => new Promise((res) => s.emit(ev, ...a, res));
  await new Promise((r) => s.on("connect", r));
  if (!(await emit("loginByToken", jwt.sign({ username: u.username, h: shake(u.password) }, sec))).ok) { console.log("LOGIN FAILED"); process.exit(1); }
  const ids = {};
  const clone = async (tplName, name, extra) => {
    const have = await q("SELECT id FROM monitor WHERE name = ?", [name]);
    if (have) { console.log("exists", name, have.id); return have.id; }
    const tplRow = await q("SELECT id FROM monitor WHERE name = ?", [tplName]);
    const tpl = (await emit("getMonitor", tplRow.id)).monitor;
    const m = { ...tpl, ...extra, name, notificationIDList: { [notif]: true } };
    for (const k of STRIP) if (!(k in extra)) delete m[k];
    const r = await emit("add", m);
    console.log("add", name + ":", r.ok ? "ok id " + r.monitorID : r.msg); if (!r.ok) process.exit(1);
    return r.monitorID;
  };
  // group (clone of an existing group monitor so all defaults match)
  ids.group = await clone("Background containers", GROUP, { description: "Fake-money crypto trading simulators (docker stack crypto). Not in the backup window." });
  ids.dash = await clone("Homepage Pro (3010)", "Crypto dashboard", { parent: ids.group, url: "http://192.0.2.242:8050/",
    description: "Read-only web dashboard of the crypto simulator bots (served by crypto-futures)" });
  const bots = [["crypto-futures", "Crypto futures bot (long/short)"], ["crypto-alt", "Crypto alt breakout bot"],
                ["crypto-trend", "Crypto BTC trend bot"], ["crypto-pair", "Crypto ETH/BTC pair bot"]];
  for (const [c, n] of bots) ids[c] = await clone("Recyclarr", n, { parent: ids.group, docker_container: c, docker_host: dh,
    description: `Container ${c}: fake-money simulator using Coinbase public data` });
  // safety: none of these may sit in a maintenance window
  for (const id of Object.values(ids)) {
    const mm = await q("SELECT count(*) c FROM monitor_maintenance WHERE monitor_id = ?", [id]);
    if (mm.c) console.log("WARNING monitor", id, "is in a maintenance window");
  }
  // status page: keep existing groups as-is, append/refresh the Crypto bots group
  const cur = await (await fetch("http://127.0.0.1:3001/api/status-page/box")).json();
  const cfgRes = await emit("getStatusPage", "box"); if (!cfgRes.ok) { console.log("getStatusPage failed"); process.exit(1); }
  const config = cfgRes.config;
  const kids = [ids.dash, ids["crypto-futures"], ids["crypto-alt"], ids["crypto-trend"], ids["crypto-pair"]];
  const groups = cur.publicGroupList.map((g) => ({ id: g.id, name: g.name, monitorList: g.monitorList.map((m) => ({ id: m.id })) }));
  let g = groups.find((x) => x.name === GROUP);
  if (!g) { g = { name: GROUP, monitorList: [] }; groups.push(g); }
  for (const id of kids) if (!g.monitorList.some((m) => m.id === id)) g.monitorList.push({ id });
  const before = cur.publicGroupList.reduce((a, x) => a + x.monitorList.length, 0);
  const r2 = await emit("saveStatusPage", "box", config, config.icon || "/icon.svg", groups);
  console.log("saveStatusPage:", r2.ok ? "ok" : r2.msg, "| before", before, "after", groups.reduce((a, x) => a + x.monitorList.length, 0),
    "|", groups.map((x) => x.name + " " + x.monitorList.length).join(", "));
  console.log("IDS", JSON.stringify(ids));
  s.close(); process.exit(0);
})().catch((e) => { console.log("ERROR", String(e.message).slice(0, 120)); process.exit(1); });
