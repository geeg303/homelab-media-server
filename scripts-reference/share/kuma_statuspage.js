// INSIDE uptime-kuma: create status page "box" (slug: box) listing every check by group, for the Homepage uptimekuma widget. Idempotent.
const sqlite3 = require("@louislam/sqlite3");
const crypto = require("crypto");
const jwt = require("jsonwebtoken");
const { io } = require("socket.io-client");
const db = new sqlite3.Database("/app/data/kuma.db", sqlite3.OPEN_READONLY);
const q = (s, p = []) => new Promise((res, rej) => db.get(s, p, (e, r) => (e ? rej(e) : res(r))));
const all = (s, p = []) => new Promise((res, rej) => db.all(s, p, (e, r) => (e ? rej(e) : res(r))));
const shake = (d) => crypto.createHash("shake256", { outputLength: 16 }).update(d).digest("hex");
(async () => {
  const u = await q("SELECT username, password FROM user WHERE active = 1 ORDER BY id LIMIT 1");
  const raw = (await q("SELECT value FROM setting WHERE key = 'jwtSecret'")).value;
  let sec; try { sec = JSON.parse(raw); } catch { sec = raw; }
  const groups = await all("SELECT id, name FROM monitor WHERE type = 'group' ORDER BY id");
  const order = ["Media apps", "Background containers", "Infrastructure", "Host health", "Storage & jobs"];
  groups.sort((a, b) => order.indexOf(a.name) - order.indexOf(b.name));
  const publicGroupList = [];
  for (const g of groups) {
    const kids = await all("SELECT id FROM monitor WHERE parent = ? AND active = 1 ORDER BY id", [g.id]);
    if (kids.length) publicGroupList.push({ name: g.name, monitorList: kids.map((k) => ({ id: k.id })) });
  }
  const s = io("http://127.0.0.1:3001", { transports: ["websocket"], reconnection: false });
  const emit = (ev, ...a) => new Promise((res) => s.emit(ev, ...a, res));
  await new Promise((r) => s.on("connect", r));
  if (!(await emit("loginByToken", jwt.sign({ username: u.username, h: shake(u.password) }, sec))).ok) { console.log("LOGIN FAILED"); process.exit(1); }
  if (!(await q("SELECT id FROM status_page WHERE slug = 'box'"))) {
    const r = await emit("addStatusPage", "box media server", "box");
    console.log("addStatusPage:", r.ok ? "ok" : r.msg);
  } else console.log("status page exists, updating its monitor list");
  const config = { slug: "box", title: "box media server", description: "All Uptime Kuma checks for the media server (LAN only).",
    icon: "/icon.svg", theme: "dark", published: true, showTags: false, domainNameList: [], customCSS: "", footerText: null,
    showPoweredBy: false, googleAnalyticsId: null, showCertificateExpiry: false, autoRefreshInterval: 60, analyticsType: null, analyticsId: null,
    analyticsScriptUrl: null, rssTitle: null };
  const r2 = await emit("saveStatusPage", "box", config, "/icon.svg", publicGroupList);
  console.log("saveStatusPage:", r2.ok ? "ok" : r2.msg, "| groups:", publicGroupList.map((g) => g.name + " " + g.monitorList.length).join(", "));
  s.close(); process.exit(0);
})().catch((e) => { console.log("ERROR", e.message.slice(0, 120)); process.exit(1); });
