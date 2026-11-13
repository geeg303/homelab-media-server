/* ==========================================================================
 *  user's Homepage: "Pro" (engineering / observability) custom.js
 *  Loaded by Homepage (gethomepage v2.8.x) from /app/config/custom.js, which is
 *  served at /api/config/custom.js and injected after hydration. Safe to load twice.
 *
 *  Injects:  #pro-strip     sticky KPI strip above the tab bar
 *              .pro-kpis > .pro-kpi[data-kpi] (.pro-kpi-label, .pro-kpi-value)
 *              state: .is-ok | .is-warn | .is-crit | .is-stale (+ .is-loading before 1st data)
 *              .pro-updated "Updated 12:04:31"
 *              #pro-switch  "Retro view ↗" (also keyboard shortcut "v")
 *            .pro-age       "4m" data-age label on customapi tiles whose JSON has `updated`
 *  All data is same-origin through Homepage's own proxy (/api/services/proxy), so
 *  no secrets ever reach the browser beyond what Homepage widgets already expose.
 *  Styling here is zero-specificity (:where) fallback; parts/design CSS wins.
 * ========================================================================== */
(function () {
  "use strict";

  /* =============================== CONFIG ================================ */
  var CONFIG = {
    refreshMs: 30000,               // KPI + age refresh
    fetchTimeoutMs: 12000,
    staleAfterFailures: 2,          // chip gets .is-stale after N consecutive failed refreshes
    clock24h: true,                 // "Updated 12:04:31"
    boxUtcOffsetMin: null,          // null = box clock == browser clock. e.g. -420 for MST
                                    // (used only for status JSON times without a TZ)

    /* ---- KPI order + thresholds (value >= warn -> .is-warn, >= crit -> .is-crit) ---- */
    kpis: ["health", "migration", "cpu", "ram", "temp", "storage", "backup", "updates", "plex", "downloads", "tdarr", "eng"],
    labels: {
      health: "Health", migration: "Migration", cpu: "CPU", ram: "RAM", temp: "Max temp", storage: "Storage",
      backup: "Backup", updates: "Updates", plex: "Plex", downloads: "Downloads", tdarr: "Tdarr", eng: "Systemd",
    },
    // Optional per-chip link (e.g. a Pro tab hash "#infrastructure"); null = plain chip.
    links: { health: null, migration: null, cpu: null, ram: null, temp: null, storage: null, backup: null,
             updates: null, plex: null, downloads: null, tdarr: null, eng: null },
    thresholds: {
      health:   { pendingIsWarn: true, failedUnitsIsWarn: true },     // any monitor down -> crit
      cpu:      { warn: 75, crit: 90 },                               // %
      ram:      { warn: 80, crit: 92 },                               // %
      temp:     { warn: 85, crit: 95,                                 // °C, CPU/board sensors (Glances)
                  diskWarn: 50, diskCrit: 58,                         // °C, HDD (selftest bays / eng SMART)
                  ignore: /^(Video|dell_smm|Sensor \d)|fan/i },       // sensor labels to skip
      storage:  { warn: 85, crit: 95,                                 // % used, tightest disk
                  include: /^(root|scratch|disk\d+|parity\d*|cache\w*|pool\w*)$/i,
                  exclude: /^(mig_|array_total|updated)/i },
      backup:   { warnHours: 26, critHours: 50 },
      updates:  { warn: 5, crit: 15 },                                // # images with updates
      plex:     { transcodeWarn: 4 },
      downloads:{ pausedIsWarn: true },
      tdarr:    { errorPattern: /error|fail|stuck|crash/i },
      eng:      { rebootIsWarn: false, usbErrorsWarn: 10 },          // eng.json extras
      migration:{ maxAgeMin: 20 },                                    // status JSON older -> stale
      dataMaxAgeMin: 20,                                              // host/disks/tdarr JSON older -> stale
    },

    /* ---- data sources ----
     * Resolved at runtime from GET /api/services: an explicit {group, service, index}
     * wins if that service exists; otherwise the first widget of `type` whose service
     * name matches `match` OR whose customapi mappings contain one of `fields`. */
    services: {
      kuma:      { type: "uptimekuma", match: /kuma|uptime/i },
      glances:   { type: "glances", match: /vitals|cpu|glances|host|system/i, version: 4 },
      wud:       { type: "whatsupdocker" },
      tautulli:  { type: "tautulli" },
      sabnzbd:   { type: "sabnzbd" },
      host:      { type: "customapi", match: /\(host\)|host status|^host$/i, fields: ["backup_last", "failed_units", "tailscale_ip"] },
      migration: { type: "customapi", match: /migrat/i, fields: ["round", "overall_bar", "verify_bar"] },
      disks:     { type: "customapi", match: /storage at a glance|^storage$|data disks/i, fields: ["array_total", "disk1", "scratch"] },
      tdarr:     { type: "customapi", match: /tdarr conv/i, fields: ["totals", "saved", "swap"] },
      selftest:  { type: "customapi", match: /self.?test/i, fields: ["bay1"] },
      // Engineering telemetry (/opt/media/status/eng.json via a customapi tile).
      // Lead: set the exact service name the Pro services.yaml uses, e.g.
      //   eng: { type: "customapi", group: "Platform", service: "Engineering status", index: 0 }
      eng:       { type: "customapi", group: "Service Health", service: "Engineering status", index: 0, enabled: true },
    },

    /* ---- view switch ---- */
    retroUrl: "http://192.0.2.242:3000/",
    switchLabel: "Retro view \u2197",
    switchKey: "v",                         // null disables the shortcut
    // Pro tab slug -> 90s tab slug (90s slugs verified in its DOM: home-page, media-mania,
    // download-o-rama, server-room, net-%26-home, jobs, cool-links). Exact entries win;
    // otherwise `tabRules` (regex on the Pro slug) apply; otherwise retroDefault.
    tabMap: {
      // real Pro tabs (settings.yaml): overview compute storage network pipelines applications runbook
      "compute": "server-room", "pipelines": "jobs", "applications": "media-mania", "runbook": "cool-links",
      "overview": "home-page", "home": "home-page", "summary": "home-page",
      "media": "media-mania", "downloads": "download-o-rama", "automation": "download-o-rama",
      "infrastructure": "server-room", "system": "server-room", "hardware": "server-room", "storage": "server-room",
      "network": "net-%26-home", "network-%26-home": "net-%26-home", "home-%26-network": "net-%26-home",
      "jobs": "jobs", "operations": "jobs", "ops": "jobs", "links": "cool-links", "bookmarks": "cool-links",
    },
    tabRules: [
      [/media|plex|stream|tv/i, "media-mania"],
      [/download|arr|automat|queue|calendar/i, "download-o-rama"],
      [/net|wifi|smart|home-?assist/i, "net-%26-home"],
      [/server|system|infra|host|hardware|compute|storage|disk|contain|observ|metric/i, "server-room"],
      [/job|task|pipeline|migrat|update|ops|backup/i, "jobs"],
      [/link|bookmark/i, "cool-links"],
    ],
    retroDefault: "home-page",
    // Landing self-heal: Homepage shows an EMPTY page for an unknown #hash. If the page is
    // opened with a hash that is not one of our tabs (e.g. a 90s slug from the retro
    // "Switch to Pro view" button), pick the first Pro tab whose slug matches the rule
    // for that hash, else the first tab.
    landingFix: true,
    landRules: {
      "home-page": /overview|home|summary|dash|status/i,
      "media-mania": /application|media|plex|stream|watch/i,
      "download-o-rama": /pipeline|download|automat|queue|acquisition/i,
      "server-room": /compute|infra|system|server|host|hardware|metric|observ/i,
      "net-%26-home": /network/i,
      "jobs": /pipeline|job|ops|operation|task|migrat/i,
      "cool-links": /runbook|link|bookmark/i,
    },

    /* ---- freshness labels ---- */
    freshness: { enabled: true, oldMin: 30, field: "updated" },
  };
  /* ======================================================================= */

  if (window.__hpPro) return;   // never run twice
  window.__hpPro = true;

  var doc = document, T = CONFIG.thresholds;

  /* ---------------------------- fallback CSS ----------------------------- */
  var STYLE = [
    // structural (not cosmetic): Homepage's page container is `h-full` and its content
    // overflows it, which would un-stick the strip after one screen. Let it grow instead.
    "#inner_wrapper > div:has(> #pro-strip){height:auto}",
    ":where(#pro-strip){position:sticky;top:0;z-index:40;display:flex;flex-wrap:wrap;align-items:center;gap:6px 8px;box-sizing:border-box;",
    "  margin:0 1.25rem .5rem;padding:6px 8px;border-radius:6px;background:rgba(17,20,26,.92);border:1px solid rgba(255,255,255,.08);",
    "  font:12px/1.3 ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif;color:#d8dee9;backdrop-filter:blur(6px)}",
    ":where(#pro-strip) :where(.pro-kpis){display:flex;flex-wrap:wrap;gap:6px;flex:1 1 0;min-width:0}",
    ":where(.pro-kpi){display:inline-flex;align-items:baseline;gap:6px;padding:3px 8px;border-radius:4px;white-space:nowrap;",
    "  background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-left:3px solid #6b7280;color:inherit;text-decoration:none;cursor:default}",
    ":where(a.pro-kpi){cursor:pointer}",
    ":where(.pro-kpi-label){font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:#8b95a7}",
    ":where(.pro-kpi-value){font-weight:600;font-variant-numeric:tabular-nums}",
    ":where(.pro-kpi.is-ok){border-left-color:#3fb950}",
    ":where(.pro-kpi.is-warn){border-left-color:#d29922}:where(.pro-kpi.is-warn .pro-kpi-value){color:#e3b341}",
    ":where(.pro-kpi.is-crit){border-left-color:#f85149;background:rgba(248,81,73,.10)}:where(.pro-kpi.is-crit .pro-kpi-value){color:#ff7b72}",
    ":where(.pro-kpi.is-stale){opacity:.55;border-left-style:dashed}",
    ":where(.pro-kpi.is-loading .pro-kpi-value){color:#6b7280}",
    ":where(.pro-updated){font-size:11px;color:#8b95a7;font-variant-numeric:tabular-nums;white-space:nowrap}",
    ":where(#pro-switch){display:inline-flex;align-items:center;padding:3px 10px;border-radius:4px;border:1px solid rgba(255,255,255,.18);",
    "  color:inherit;text-decoration:none;font-size:12px;white-space:nowrap}",
    ":where(#pro-switch):hover,:where(#pro-switch):focus-visible{background:rgba(255,255,255,.08)}",
    ":where(.pro-kpi):focus-visible,:where(#pro-switch):focus-visible{outline:2px solid #58a6ff;outline-offset:1px}",
    ":where(.pro-age){margin-left:auto;align-self:flex-start;padding:0 5px;border-radius:3px;font:10px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;",
    "  color:#8b95a7;background:rgba(255,255,255,.05);white-space:nowrap;pointer-events:auto}",
    ":where(.pro-age.is-old){color:#e3b341}",
    "@media (prefers-reduced-motion: reduce){:where(#pro-strip),:where(#pro-strip) *{transition:none!important;animation:none!important}}",
  ].join("\n");
  function addStyle() {
    if (doc.getElementById("pro-js-style")) return;
    var s = doc.createElement("style");
    s.id = "pro-js-style";
    s.textContent = STYLE;
    var h = doc.head || doc.documentElement;
    h.insertBefore(s, h.firstChild);   // first, so custom.css wins ties
  }

  /* ------------------------------- helpers ------------------------------- */
  function el(tag, attrs, kids) {
    var e = doc.createElement(tag);
    if (attrs) for (var k in attrs) { if (k === "text") e.textContent = attrs[k]; else e.setAttribute(k, attrs[k]); }
    (kids || []).forEach(function (c) { if (c) e.appendChild(typeof c === "string" ? doc.createTextNode(c) : c); });
    return e;
  }
  function clean(s) {
    if (s == null) return "";
    return String(s).replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}\u{200D}\u{2500}-\u{259F}]/gu, "")
      .replace(/\s+/g, " ").trim();
  }
  function num(v) { var n = typeof v === "number" ? v : parseFloat(String(v == null ? "" : v).replace(/[^\d.\-]/g, "")); return isFinite(n) ? n : null; }
  function pctOf(s) { var m = /(\d+(?:\.\d+)?)\s*%/.exec(s || ""); return m ? parseFloat(m[1]) : null; }
  function level(v, th) { return v == null ? null : v >= th.crit ? "crit" : v >= th.warn ? "warn" : "ok"; }
  function worst(a, b) { var r = { ok: 1, warn: 2, crit: 3 }; return (r[b] || 0) > (r[a] || 0) ? b : a; }
  function dur(ms) {
    var s = Math.max(0, Math.round(ms / 1000));
    if (s < 60) return s + "s";
    var m = Math.round(s / 60); if (m < 60) return m + "m";
    var h = Math.floor(m / 60); if (h < 48) return h + "h" + (h < 10 && m % 60 ? " " + (m % 60) + "m" : "");
    return Math.round(h / 24) + "d";
  }
  function hhmmss(d) {
    try { return d.toLocaleTimeString(CONFIG.clock24h ? "en-GB" : undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: !CONFIG.clock24h }); }
    catch (e) { return d.toTimeString().slice(0, 8); }
  }

  // Parse the timestamp styles the box's status JSONs use:
  //   "Fri 12:14 PM", "Fri 12:15:33 PM", "05:25", "Fri 2026-11-13 04:31:39 MST", ISO, epoch s/ms
  var TZ = { UTC: 0, GMT: 0, Z: 0, MST: -420, MDT: -360, PST: -480, PDT: -420, CST: -360, CDT: -300, EST: -300, EDT: -240 };
  var WD = { sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6 };
  function parseWhen(v, nowMs) {
    nowMs = nowMs || Date.now();
    if (v == null || v === "") return null;
    if (typeof v === "number") return v > 1e12 ? v : v > 1e9 ? v * 1000 : null;
    var s = clean(v), m;
    if (/^\d{10,13}$/.test(s)) return parseWhen(+s, nowMs);
    var off = CONFIG.boxUtcOffsetMin;
    // Date.UTC from wall-clock parts in a given offset (null = browser local time)
    function at(y, mo, d, h, mi, se, o) {
      return o == null ? new Date(y, mo, d, h, mi, se).getTime() : Date.UTC(y, mo, d, h, mi, se) - o * 60000;
    }
    m = /(\d{4})-(\d{2})-(\d{2})[T ](\d{1,2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?\s*(Z|[+-]\d{2}:?\d{2}|[A-Z]{3})?/.exec(s);
    if (m) {
      var o = off;
      if (m[7]) {
        if (TZ[m[7]] != null) o = TZ[m[7]];
        else if (/^[+-]/.test(m[7])) { var z = m[7].replace(":", ""); o = (z[0] === "-" ? -1 : 1) * (parseInt(z.slice(1, 3), 10) * 60 + parseInt(z.slice(3), 10)); }
      }
      return at(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0), o);
    }
    m = /^(?:(sun|mon|tue|wed|thu|fri|sat)\w*\.?,?\s+)?(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AP]M)?$/i.exec(s);
    if (m) {
      var h = +m[2];
      if (m[5]) { h = h % 12; if (/p/i.test(m[5])) h += 12; }
      // "today" on the box's clock
      var nb = off == null ? new Date(nowMs) : new Date(nowMs + off * 60000);
      var Y = off == null ? nb.getFullYear() : nb.getUTCFullYear(), Mo = off == null ? nb.getMonth() : nb.getUTCMonth(),
          D = off == null ? nb.getDate() : nb.getUTCDate(), dow = off == null ? nb.getDay() : nb.getUTCDay();
      var back = 0;
      if (m[1]) back = (dow - WD[m[1].toLowerCase().slice(0, 3)] + 7) % 7;
      var t = at(Y, Mo, D - back, h, +m[3], +(m[4] || 0), off);
      if (t > nowMs + 5 * 60000) t -= (m[1] ? 7 : 1) * 86400000;   // future -> last week / yesterday
      return t;
    }
    var p = Date.parse(s);
    return isNaN(p) ? null : p;
  }

  /* -------------------------------- fetch -------------------------------- */
  var cycleCache = {};   // url -> Promise, cleared each refresh so tiles + chips share requests
  function fetchJSON(url) {
    if (cycleCache[url]) return cycleCache[url];
    var ctl = window.AbortController ? new AbortController() : null;
    var t = ctl ? setTimeout(function () { ctl.abort(); }, CONFIG.fetchTimeoutMs) : null;
    return (cycleCache[url] = fetch(url, { cache: "no-store", credentials: "same-origin", signal: ctl ? ctl.signal : undefined })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { return j && !(j.error && Object.keys(j).length <= 2) ? j : null; })
      .catch(function () { return null; })
      .then(function (j) { if (t) clearTimeout(t); return j; }));
  }
  function proxyURL(s, endpoint) {
    var u = "/api/services/proxy?group=" + encodeURIComponent(s.group) + "&service=" + encodeURIComponent(s.service) + "&index=" + (s.index || 0);
    if (endpoint) u += "&endpoint=" + encodeURIComponent(endpoint);
    return u;
  }

  /* ----------------------- resolve services at runtime -------------------- */
  var resolved = null, customapis = [];   // customapis: [{group, service, index}] for freshness labels
  function resolveServices() {
    if (resolved) return Promise.resolve(resolved);
    return fetchJSON("/api/services").then(function (groups) {
      if (!Array.isArray(groups)) return null;          // retry next cycle
      var flat = [];
      (function walk(gs) {
        (gs || []).forEach(function (g) {
          (g.services || []).forEach(function (s) {
            var ws = s.widgets || (s.widget ? [s.widget] : []);
            ws.forEach(function (w, wi) {
              if (!w || typeof w !== "object") return;
              // mappings may be a list [{field,..}] or an object {label: {field,..} | "field"}
              var mp = w.mappings || [], fields = [];
              (Array.isArray(mp) ? mp : Object.keys(mp).map(function (k) { return mp[k]; })).forEach(function (m) {
                var f = m && typeof m === "object" ? m.field : m;
                if (f && typeof f === "object") f = Object.keys(f)[0];   // nested {field: {a: b}} form
                if (typeof f === "string") fields.push(f);
              });
              flat.push({ group: g.name, service: s.name, index: w.index != null ? w.index : wi, type: w.type, version: w.version, fields: fields });
            });
          });
          walk(g.groups);
        });
      })(groups);
      var map = {};
      Object.keys(CONFIG.services).forEach(function (key) {
        var want = CONFIG.services[key], hit = null, i;
        if (want.enabled === false) return;
        if (want.service) for (i = 0; i < flat.length && !hit; i++) {
          var f = flat[i];
          if (f.service === want.service && (!want.group || f.group === want.group) && (want.index == null || f.index === want.index)) hit = f;
        }
        for (i = 0; i < flat.length && !hit; i++) if (flat[i].type === want.type && want.match && want.match.test(flat[i].service)) hit = flat[i];
        if (want.fields) for (i = 0; i < flat.length && !hit; i++) {
          if (flat[i].type !== want.type) continue;
          for (var k = 0; k < want.fields.length; k++) if (flat[i].fields.indexOf(want.fields[k]) !== -1) { hit = flat[i]; break; }
        }
        // non-customapi widget types are unambiguous enough: fall back to the first of that type
        if (want.type !== "customapi") for (i = 0; i < flat.length && !hit; i++) if (flat[i].type === want.type) hit = flat[i];
        if (hit) map[key] = { group: hit.group, service: hit.service, index: hit.index, version: hit.version || want.version };
      });
      var seen = {};
      customapis = flat.filter(function (f) {
        if (f.type !== "customapi" || seen[f.service]) return false;
        return (seen[f.service] = true);
      });
      return (resolved = map);
    });
  }

  /* ----------------------------- data fetch ------------------------------ */
  // Returns D: key -> data | null (failed) ; key absent = not configured on this page.
  function loadData(S) {
    var jobs = {};
    function add(key, svc, ep) { if (svc) jobs[key] = fetchJSON(proxyURL(svc, ep)); }
    add("kumaSP", S.kuma, "status_page");
    add("kumaHB", S.kuma, "heartbeat");
    var gv = S.glances && (S.glances.version || 4);
    add("quick", S.glances, gv + "/quicklook");
    add("sensors", S.glances, gv + "/sensors");
    add("wud", S.wud, "containers");
    add("tautulli", S.tautulli, "get_activity");
    add("sab", S.sabnzbd, "queue");
    ["host", "migration", "disks", "tdarr", "selftest", "eng"].forEach(function (k) { add(k, S[k]); });
    var keys = Object.keys(jobs);
    return Promise.all(keys.map(function (k) { return jobs[k]; })).then(function (vals) {
      var D = {};
      keys.forEach(function (k, i) { D[k] = vals[i]; });
      return D;
    });
  }
  function ageOf(j) { var t = j && parseWhen(j[CONFIG.freshness.field]); return t == null ? null : Date.now() - t; }
  function staleByAge(j, maxMin) { var a = ageOf(j); return a != null && a > maxMin * 60000; }

  /* ------------------------------ KPI logic ------------------------------ */
  // Each: needs (any-of D keys; chip hidden if none configured), compute(D) -> {value, state, title} | null
  var KPI = {
    health: { needs: ["kumaHB"], compute: function (D) {
      var hb = D.kumaHB, sp = D.kumaSP;
      if (!hb || !hb.heartbeatList) return null;
      var mons = [];
      if (sp && sp.publicGroupList) sp.publicGroupList.forEach(function (g) { (g.monitorList || []).forEach(function (m) { mons.push({ id: String(m.id), name: m.name }); }); });
      if (!mons.length) mons = Object.keys(hb.heartbeatList).map(function (id) { return { id: id, name: "#" + id }; });
      var up = 0, down = [], other = [];
      mons.forEach(function (m) {
        var b = hb.heartbeatList[m.id] || [], last = b[b.length - 1];
        if (last && last.status === 1) up++; else if (last && last.status === 0) down.push(m.name); else other.push(m.name);
      });
      var state = down.length ? "crit" : other.length && T.health.pendingIsWarn ? "warn" : "ok";
      var tip = ["Uptime Kuma: " + up + "/" + mons.length + " monitors up"];
      if (down.length) tip.push("Down: " + down.join(", "));
      if (other.length) tip.push("Pending/maintenance: " + other.join(", "));
      if (hb.uptimeList) {
        var v = mons.map(function (m) { return hb.uptimeList[m.id + "_24"]; }).filter(function (x) { return typeof x === "number"; });
        if (v.length) tip.push("24 h mean uptime: " + (v.reduce(function (a, b) { return a + b; }, 0) / v.length * 100).toFixed(2) + "%");
      }
      var e = D.eng || {}, unh = [].concat(e.containers_unhealthy || [], e.containers_stopped || []);
      if (unh.length) { tip.push("Unhealthy/stopped containers: " + unh.map(function (c) { return typeof c === "string" ? c : c && (c.name || c.id); }).join(", ")); state = worst(state, "warn"); }
      var fu = failedUnits(D);
      if (fu && fu.count > 0) {
        tip.push("Failed systemd units: " + (fu.names.length ? fu.names.join(", ") : fu.count));
        if (T.health.failedUnitsIsWarn) state = worst(state, "warn");
      }
      return { value: up + "/" + mons.length + " up" + (down.length ? " \u00b7 " + down.length + " down" : ""), state: state, title: tip.join("\n") };
    } },

    migration: { needs: ["migration"], compute: function (D) {
      var j = D.migration;
      if (!j || !(j.round || j.overall_bar)) return null;
      var round = clean(j.round).split("\u00b7")[0].trim(), stage = clean(j.stage);
      var verify = pctOf(j.verify_bar), copy = pctOf(j.copy_bar), overall = pctOf(j.overall_bar);
      var checksum = /checksum|verif/i.test(stage);
      var phase = checksum ? "checksum" : /copy/i.test(stage) || copy != null ? "copy" : clean(stage).split(/[\u00b7:]/)[0].trim().toLowerCase();
      var p = checksum ? verify : copy != null && copy < 100 ? copy : overall;
      var eta = clean(j.eta).replace(/^[^:]*:\s*/, "").replace(/\s*\(.*\)\s*$/, "");
      var done = overall != null && overall >= 100 && !/\d+h|\d+m/.test(eta);
      var m = /errors[^:]*:\s*(\d+)/i.exec(j.health || ""), errs = m ? +m[1] : 0;
      var dm = /differences[^:]*:\s*(\d+)/i.exec(j.health || ""), diffs = dm ? +dm[1] : 0;
      var r = /(\d+)\s*of\s*(\d+)/.exec(round);
      var value = done ? "complete" : (r ? "R" + r[1] + "/" + r[2] + " " : "") + phase + (p != null ? " " + Math.round(p) + "%" : "") + (eta ? " \u00b7 " + eta : "");
      return {
        value: value, state: errs > 0 ? "crit" : diffs > 0 ? "warn" : "ok", stale: staleByAge(j, T.migration.maxAgeMin),
        title: ["Round " + clean(j.round), stage, overall != null ? "Overall " + overall + "%" : "", clean(j.eta) ? "ETA " + clean(j.eta) : "",
                clean(j.rounds), clean(j.health), j.updated ? "Status as of " + clean(j.updated) : ""].filter(Boolean).join("\n"),
      };
    } },

    cpu: { needs: ["quick"], compute: function (D) {
      var q = D.quick; if (!q || typeof q.cpu !== "number") return null;
      return { value: q.cpu.toFixed(0) + "%", state: level(q.cpu, T.cpu),
               title: "CPU " + q.cpu.toFixed(1) + "% (Glances quicklook)" + (q.load != null ? "\nLoad " + q.load + "% of cores" : "") +
                      (D.host && D.host.load ? "\nLoad avg " + clean(D.host.load) : "") + "\nwarn \u2265 " + T.cpu.warn + "%, crit \u2265 " + T.cpu.crit + "%" };
    } },

    ram: { needs: ["quick", "host", "eng"], compute: function (D) {
      var q = D.quick, v = q && typeof q.mem === "number" ? q.mem : null, src = "Glances";
      if (v == null && D.host && D.host.memory) {        // "6.6 GB used / 32.8 GB"
        var m = /([\d.]+)\s*([GMT])B?\s*used\s*\/\s*([\d.]+)\s*([GMT])/i.exec(D.host.memory);
        if (m) { var u = { M: 1 / 1024, G: 1, T: 1024 }; v = (+m[1] * u[m[2].toUpperCase()]) / (+m[3] * u[m[4].toUpperCase()]) * 100; src = "host.json"; }
      }
      if (v == null && D.eng && typeof D.eng.mem_used_pct === "number") { v = D.eng.mem_used_pct; src = "eng.json"; }
      if (v == null) return null;
      return { value: v.toFixed(0) + "%", state: level(v, T.ram),
               title: "Memory " + v.toFixed(1) + "% used (" + src + ")" + (D.host && D.host.memory ? "\n" + clean(D.host.memory) : "") +
                      (q && q.swap != null ? "\nSwap " + q.swap + "%" : "") + "\nwarn \u2265 " + T.ram.warn + "%, crit \u2265 " + T.ram.crit + "%" };
    } },

    temp: { needs: ["sensors", "host", "selftest", "eng"], compute: function (D) {
      var hot = [], best = null, state = null;
      if (Array.isArray(D.sensors)) D.sensors.forEach(function (s) {
        if (!s || !/temp/i.test(s.type || "") || typeof s.value !== "number" || T.temp.ignore.test(s.label || "")) return;
        hot.push({ label: s.label, v: s.value, disk: false });
      });
      var h = D.host || {};
      ["cpu_temp", "temp", "max_temp"].forEach(function (k) { var v = num(h[k]); if (v != null) hot.push({ label: "host " + k, v: v, disk: false }); });
      // HDD temps: selftest bays ("... · 48°C") and eng.json SMART
      var st = D.selftest || {};
      Object.keys(st).forEach(function (k) { var m = /^bay\d/i.test(k) && /(\d+)\s*\u00b0C/.exec(st[k] || ""); if (m) hot.push({ label: k, v: +m[1], disk: true }); });
      engSmart(D.eng).forEach(function (d) { if (d.temp != null) hot.push({ label: d.name, v: d.temp, disk: !d.nvme }); });
      if (!hot.length) return null;
      hot.forEach(function (x) {
        var lv = level(x.v, x.disk ? { warn: T.temp.diskWarn, crit: T.temp.diskCrit } : T.temp);
        state = worst(state, lv);
      });
      hot.sort(function (a, b) { return b.v - a.v; });
      var cpu = hot.filter(function (x) { return !x.disk; }), disk = hot.filter(function (x) { return x.disk; });
      best = cpu[0] || disk[0];
      var tip = [];
      if (cpu.length) tip.push("Hottest sensors: " + cpu.slice(0, 4).map(function (x) { return x.label + " " + x.v + "\u00b0C"; }).join(", "));
      if (disk.length) tip.push("Hottest disks: " + disk.slice(0, 4).map(function (x) { return x.label + " " + x.v + "\u00b0C"; }).join(", "));
      tip.push("CPU warn \u2265 " + T.temp.warn + "\u00b0C / crit \u2265 " + T.temp.crit + "\u00b0C; disks warn \u2265 " + T.temp.diskWarn + " / crit \u2265 " + T.temp.diskCrit + "\u00b0C");
      return { value: best.v.toFixed(0) + "\u00b0C" + (disk.length && cpu.length ? " \u00b7 disk " + disk[0].v + "\u00b0C" : ""), state: state, title: tip.join("\n") };
    } },

    storage: { needs: ["disks"], compute: function (D) {
      var j = D.disks; if (!j || typeof j !== "object") return null;
      var list = [];
      Object.keys(j).forEach(function (k) {
        if (T.storage.exclude.test(k) || !T.storage.include.test(k)) return;
        var p = pctOf(j[k]); if (p != null) list.push({ k: k, p: p, txt: clean(j[k]).replace(/^[^\d]*/, "") });
      });
      if (!list.length) return null;
      list.sort(function (a, b) { return b.p - a.p; });
      var top = list[0], state = level(top.p, T.storage);
      var bad = engSmart(D.eng).filter(function (d) { return d.failed; });
      if (bad.length) state = "crit";
      var tip = list.slice(0, 5).map(function (x) { return x.k + ": " + x.txt; });
      if (j.array_total) tip.push("Array: " + clean(j.array_total).replace(/^[^\d]*/, ""));
      if (bad.length) tip.push("SMART failing: " + bad.map(function (d) { return d.name; }).join(", "));
      tip.push("warn \u2265 " + T.storage.warn + "%, crit \u2265 " + T.storage.crit + "%");
      return { value: Math.round(top.p) + "% " + top.k, state: state, stale: staleByAge(j, T.dataMaxAgeMin), title: tip.join("\n") };
    } },

    backup: { needs: ["host", "eng"], compute: function (D) {
      var h = D.host || {}, e = D.eng || {};
      var raw = h.backup_last || e.backup_last || (e.backup && (e.backup.last || e.backup.last_run));
      if (!raw) return null;
      var t = parseWhen(raw), failed = /\u274c|fail|error/i.test(String(raw));
      if (t == null && !failed) return null;
      var age = t == null ? null : Date.now() - t, hrs = age == null ? null : age / 3600000;
      var state = failed ? "crit" : hrs >= T.backup.critHours ? "crit" : hrs >= T.backup.warnHours ? "warn" : "ok";
      return { value: failed ? "failed" : dur(age) + " ago", state: state, stale: staleByAge(D.host, T.dataMaxAgeMin),
               title: "Last config backup: " + clean(raw) + (h.backup_next ? "\nNext: " + clean(h.backup_next) : "") +
                      "\nwarn > " + T.backup.warnHours + " h, crit > " + T.backup.critHours + " h" };
    } },

    updates: { needs: ["wud"], compute: function (D) {
      var w = D.wud; if (!Array.isArray(w)) return null;
      var up = w.filter(function (c) { return c && c.updateAvailable; });
      var names = up.map(function (c) { return c.displayName || c.name; }).filter(Boolean);
      return { value: up.length ? up.length + " pending" : "none", state: up.length >= T.updates.crit ? "crit" : up.length >= T.updates.warn ? "warn" : "ok",
               title: "What's Up Docker: " + up.length + " of " + w.length + " images have updates" + (names.length ? "\n" + names.slice(0, 12).join(", ") + (names.length > 12 ? ", \u2026" : "") : "") };
    } },

    plex: { needs: ["tautulli"], compute: function (D) {
      var d = D.tautulli && D.tautulli.response && D.tautulli.response.data; if (!d) return null;
      var n = parseInt(d.stream_count, 10) || 0, tc = parseInt(d.stream_count_transcode, 10) || 0, dp = parseInt(d.stream_count_direct_play, 10) || 0;
      var bw = parseInt(d.total_bandwidth, 10) || 0;
      return { value: n ? n + " stream" + (n === 1 ? "" : "s") + (tc ? " \u00b7 " + tc + " TC" : "") : "idle", state: tc >= T.plex.transcodeWarn ? "warn" : "ok",
               title: "Tautulli: " + n + " active stream(s), " + tc + " transcoding, " + dp + " direct play" + (bw ? "\nBandwidth " + (bw / 1000).toFixed(1) + " Mbps" : "") };
    } },

    downloads: { needs: ["sab"], compute: function (D) {
      var q = D.sab && D.sab.queue; if (!q) return null;
      var n = q.noofslots_total != null ? q.noofslots_total : (q.noofslots || 0), kb = num(q.kbpersec) || 0;
      var rate = kb >= 1024 ? (kb / 1024).toFixed(1) + " MB/s" : kb.toFixed(0) + " KB/s";
      var value = q.paused ? "paused" + (n ? " \u00b7 " + n + " queued" : "") : n ? rate + " \u00b7 " + n + " queued" : "idle";
      return { value: value, state: q.paused && T.downloads.pausedIsWarn ? "warn" : "ok",
               title: "SABnzbd: " + (q.status || "?") + "\nQueue " + n + " item(s)" + (q.sizeleft ? ", " + q.sizeleft + " left" : "") +
                      (n && q.timeleft ? ", ETA " + q.timeleft : "") + "\nSpeed " + rate + (q.speedlimit ? " (limit " + q.speedlimit + "%)" : "") };
    } },

    tdarr: { needs: ["tdarr"], compute: function (D) {
      var j = D.tdarr; if (!j || !(j.now || j.totals)) return null;
      var now = clean(j.now), tot = clean(j.totals);
      var q = /queue\s+(\d+)/i.exec(tot), state = T.tdarr.errorPattern.test(now) ? "warn" : "ok";
      var word = now.split(/[\u00b7,]/)[0].trim() || "unknown";
      return { value: word + (q ? " \u00b7 q " + q[1] : ""), state: state, stale: staleByAge(j, T.dataMaxAgeMin),
               title: ["Tdarr: " + now, tot, clean(j.workers), clean(j.saved), clean(j.swap), j.updated ? "Status as of " + clean(j.updated) : ""].filter(Boolean).join("\n") };
    } },

    eng: { needs: ["eng"], compute: function (D) {
      var e = D.eng; if (!e || typeof e !== "object") return null;
      var fu = failedUnits(D, true), timers = engTimers(e);
      var badT = timers.filter(function (t) { return t.bad; });
      var state = fu && fu.count > 0 ? "crit" : badT.length || e.overall_ok === false ? "warn" : "ok";
      if (e.reboot_required && T.eng.rebootIsWarn) state = worst(state, "warn");
      if (num(e.usb_errors_24h) >= T.eng.usbErrorsWarn) state = worst(state, "warn");
      var tip = [];
      if (e.overall) tip.push(clean(e.overall));
      if (fu) tip.push("Failed units: " + (fu.count ? (fu.names.join(", ") || fu.count) : "none"));
      if (timers.length) tip.push("Jobs/timers: " + timers.length + (badT.length ? ", failing: " + badT.map(function (t) { return t.name; }).join(", ") : ", all OK"));
      timers.slice(0, 8).forEach(function (t) { tip.push("  " + t.name + (t.last ? " \u2014 last " + t.last : "") + (t.bad ? " \u2716" : "")); });
      ["reboot", "apt", "usb", "pressure", "docker_health", "smart_summary"].forEach(function (k) { if (e[k]) tip.push(k.replace(/_/g, " ") + ": " + clean(e[k])); });
      if (e.updated) tip.push("Status as of " + clean(e.updated));
      return { value: (fu ? fu.count + " failed" : "ok") + (timers.length ? " \u00b7 " + (timers.length - badT.length) + "/" + timers.length + " jobs" : ""),
               state: state, stale: staleByAge(e, T.dataMaxAgeMin), title: tip.join("\n") || "Engineering status" };
    } },
  };

  // eng.json is optional and its schema loose: accept several shapes, fail soft.
  function failedUnits(D, engOnly) {
    var e = D.eng || {}, h = engOnly ? {} : (D.host || {});
    if (typeof e.failed_count === "number") return { count: e.failed_count, names: Array.isArray(e.failed_names) ? e.failed_names.map(String) : [] };
    var v = e.failed_units != null ? e.failed_units : e.systemd && e.systemd.failed != null ? e.systemd.failed :
            e.units && e.units.failed != null ? e.units.failed : h.failed_units;
    if (v == null) return null;
    if (Array.isArray(v)) return { count: v.length, names: v.map(function (u) { return typeof u === "string" ? u : (u && (u.unit || u.name)) || "?"; }) };
    if (typeof v === "number") return { count: v, names: [] };
    var s = clean(v);
    if (!s || /^(none|0|ok|no failed.*)$/i.test(s)) return { count: 0, names: [] };
    var n = /^(\d+)\b/.exec(s);
    var names = s.replace(/^\d+\s*(failed)?\s*[:\-\u00b7]?\s*/i, "").split(/[,\s]+/).filter(function (x) { return /\.\w+$|\w/.test(x); });
    return { count: n ? +n[1] : names.length || 1, names: names };
  }
  function engTimers(e) {
    var t = e && (e.timers || (e.systemd && e.systemd.timers) || (e.units && typeof e.units === "object" && !Array.isArray(e.units) && e.units.failed == null ? e.units : null));
    if (!t || typeof t !== "object") return [];
    var arr = Array.isArray(t) ? t : Object.keys(t).map(function (k) { var x = t[k]; return typeof x === "object" && x ? Object.assign({ name: k }, x) : { name: k, result: x }; });
    return arr.filter(function (x) { return x && typeof x === "object"; }).map(function (x) {
      var res = String(x.result != null ? x.result : x.status != null ? x.status : x.ok === false ? "failed" : "success");
      var last = x.last_ago && x.last_ago !== "never" ? x.last_ago : clean(x.last_run || x.last || x.last_trigger || "");
      return { name: String(x.unit || x.name || x.timer || "?").replace(/\.service$/, ""), last: last === "\u2014" ? "" : last,
               state: clean(x.state || ""),
               bad: x.ok === false || /fail/i.test(x.state || "") || /fail|error|timeout|exit|core|signal|\u274c/i.test(res) && !/^success$/i.test(res) };
    });
  }
  function engSmart(e) {
    var s = e && (e.smart || e.smart_temps || e.disks);
    if (!s || typeof s !== "object") return [];
    var arr = Array.isArray(s) ? s : Object.keys(s).map(function (k) { var x = s[k]; return typeof x === "object" && x ? Object.assign({ name: k }, x) : { name: k, temp: x }; });
    return arr.filter(function (x) { return x && typeof x === "object"; }).map(function (x) {
      var health = x.health != null ? String(x.health) : x.passed === false ? "FAILED" : "";
      return { name: x.label || x.dev || x.device || x.disk || x.name || "?", temp: num(x.temp != null ? x.temp : x.temperature != null ? x.temperature : x.temp_c),
               nvme: /nvme/i.test(String(x.bus || x.dev || "")), failed: x.passed === false || /fail/i.test(health) };
    });
  }

  /* ------------------------------- strip --------------------------------- */
  var chipState = {};   // key -> {fails, last:{value,state,title}, ok:boolean}
  var lastUpdated = null;

  function buildStrip() {
    var kp = el("div", { class: "pro-kpis" });
    CONFIG.kpis.forEach(function (k) {
      if (!KPI[k]) return;
      var href = CONFIG.links[k];
      var c = el(href ? "a" : "div", { class: "pro-kpi is-loading", "data-kpi": k, tabindex: "0", hidden: "" },
        [el("span", { class: "pro-kpi-label", text: CONFIG.labels[k] || k }), el("span", { class: "pro-kpi-value", text: "\u2026" })]);
      if (href) c.setAttribute("href", href);
      kp.appendChild(c);
    });
    var strip = el("div", { id: "pro-strip", role: "region", "aria-label": "System status" }, [
      kp,
      el("span", { class: "pro-updated", "aria-live": "off", text: "Updating\u2026" }),
      el("a", { id: "pro-switch", href: retroHref(), title: "Open the retro (90s) dashboard on the closest tab" + (CONFIG.switchKey ? " \u2014 shortcut: " + CONFIG.switchKey.toUpperCase() : ""),
                "aria-keyshortcuts": CONFIG.switchKey || "", text: CONFIG.switchLabel }),
    ]);
    return strip;
  }
  function paintChip(k) {
    var c = doc.querySelector('#pro-strip .pro-kpi[data-kpi="' + k + '"]');
    var s = chipState[k];
    if (!c || !s) return;
    if (s.hidden) { c.setAttribute("hidden", ""); return; }
    c.removeAttribute("hidden");
    var r = s.last, stale = s.fails >= CONFIG.staleAfterFailures || (r && r.stale);
    var cls = "pro-kpi";
    if (!r) cls += stale ? " is-stale" : " is-loading";
    else { cls += " is-" + (r.state || "ok"); if (stale) cls += " is-stale"; }
    if (c.className !== cls) c.className = cls;
    var v = c.querySelector(".pro-kpi-value");
    var txt = r ? r.value : stale ? "no data" : "\u2026";
    if (v && v.textContent !== txt) v.textContent = txt;
    var title = (r ? r.title : "") + (stale ? (r ? "\n\n" : "") + (s.fails >= CONFIG.staleAfterFailures ? "Source unavailable (" + s.fails + " failed refreshes) \u2014 showing last known value" : "Source data is old") : "") +
                (s.at ? "\nLast good: " + hhmmss(s.at) : "");
    if (c.title !== title) c.title = title;
    c.setAttribute("aria-label", (CONFIG.labels[k] || k) + ": " + txt + (r && r.state ? " (" + (stale ? "stale" : r.state) + ")" : ""));
  }
  function paintAll() {
    Object.keys(chipState).forEach(paintChip);
    var u = doc.querySelector("#pro-strip .pro-updated");
    if (u) {
      var t = lastUpdated ? "Updated " + hhmmss(lastUpdated) : "Updating\u2026";
      if (u.textContent !== t) u.textContent = t;
      u.title = "KPI refresh every " + Math.round(CONFIG.refreshMs / 1000) + " s";
    }
  }

  /* --------------------------- view switch ------------------------------- */
  function currentSlug() {
    var h = (location.hash || "").replace(/^#/, "");
    if (!h) {
      var b = doc.querySelector('#myTab [aria-selected="true"], #myTab button[class*="bg-theme-300"]');
      if (b) h = encodeURIComponent(b.textContent.trim().toLowerCase().replace(/\s+/g, "-"));
    }
    return h.toLowerCase();
  }
  function retroSlug(slug) {
    if (!slug) return CONFIG.retroDefault;
    if (CONFIG.tabMap[slug]) return CONFIG.tabMap[slug];
    var dec = slug; try { dec = decodeURIComponent(slug); } catch (e) {}
    if (CONFIG.tabMap[dec]) return CONFIG.tabMap[dec];
    for (var i = 0; i < CONFIG.tabRules.length; i++) if (CONFIG.tabRules[i][0].test(dec)) return CONFIG.tabRules[i][1];
    return CONFIG.retroDefault;
  }
  function retroHref() { var s = retroSlug(currentSlug()); return CONFIG.retroUrl + (s ? "#" + s : ""); }
  function updateSwitch() { var a = doc.getElementById("pro-switch"); if (a) { var h = retroHref(); if (a.getAttribute("href") !== h) a.setAttribute("href", h); } }
  function slugify(t) { return encodeURIComponent(String(t).trim().toLowerCase().replace(/\s+/g, "-")); }
  var landed = !CONFIG.landingFix;
  function fixLanding() {
    if (landed) return;
    var btns = doc.querySelectorAll("#myTab button");
    if (!btns.length) return;                     // tabs not rendered yet (or none configured)
    landed = true;
    var h = (location.hash || "").replace(/^#/, "").toLowerCase();
    if (!h) return;
    var slugs = [].map.call(btns, function (b) { return slugify(b.textContent); });
    if (slugs.indexOf(h) !== -1) return;
    var dec = h; try { dec = decodeURIComponent(h); } catch (e) {}
    var rule = CONFIG.landRules[h];
    var idx = -1, i;
    if (rule) for (i = 0; i < slugs.length && idx < 0; i++) if (rule.test(decodeURIComponent(slugs[i]))) idx = i;
    for (i = 0; i < slugs.length && idx < 0; i++) if (decodeURIComponent(slugs[i]).indexOf(dec) !== -1 || dec.indexOf(decodeURIComponent(slugs[i])) !== -1) idx = i;
    btns[idx < 0 ? 0 : idx].click();             // Homepage sets location.hash itself
  }
  function onKey(e) {
    if (!CONFIG.switchKey || e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || e.repeat) return;
    if ((e.key || "").toLowerCase() !== CONFIG.switchKey) return;
    var t = e.target, tag = t && t.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (t && t.isContentEditable)) return;
    // Homepage keeps its quick-launch [role=dialog] mounted but invisible; only bail if one is shown
    var dlg = doc.querySelectorAll("dialog[open], [role=dialog]");
    for (var i = 0; i < dlg.length; i++) {
      var cs = getComputedStyle(dlg[i]);
      if (cs.visibility !== "hidden" && cs.display !== "none" && parseFloat(cs.opacity) > 0) return;
    }
    e.preventDefault(); e.stopImmediatePropagation();   // keep Homepage quick-launch from opening on "v"
    location.href = retroHref();
  }

  /* ---------------------------- freshness -------------------------------- */
  var ages = {};   // service name -> {t: ms, raw}
  function cssEsc(s) { return window.CSS && CSS.escape ? CSS.escape(s) : String(s).replace(/["\\]/g, "\\$&"); }
  function refreshAges() {
    if (!CONFIG.freshness.enabled || !customapis.length) return Promise.resolve();
    // only tiles currently rendered (active tab) -> few requests
    var visible = customapis.filter(function (f) { return doc.querySelector('li.service[data-name="' + cssEsc(f.service) + '"]'); });
    return Promise.all(visible.map(function (f) {
      return fetchJSON(proxyURL(f)).then(function (j) {
        var raw = j && !Array.isArray(j) && j[CONFIG.freshness.field];
        var t = raw ? parseWhen(raw) : null;
        if (t != null) ages[f.service] = { t: t, raw: clean(raw) };
        else if (j) delete ages[f.service];
      });
    })).then(paintAges);
  }
  function paintAges() {
    if (!CONFIG.freshness.enabled) return;
    Object.keys(ages).forEach(function (name) {
      var li = doc.querySelector('li.service[data-name="' + cssEsc(name) + '"]');
      if (!li) return;
      var host = li.querySelector(".service-title") || li.querySelector(".service-card") || li;
      var tag = host.querySelector(":scope > .pro-age");
      if (!tag) { tag = el("span", { class: "pro-age" }); host.appendChild(tag); }
      var a = Date.now() - ages[name].t, txt = dur(a), old = a > CONFIG.freshness.oldMin * 60000;
      if (tag.textContent !== txt) tag.textContent = txt;
      var cls = "pro-age" + (old ? " is-old" : "");
      if (tag.className !== cls) tag.className = cls;
      var title = "Data as of " + ages[name].raw + " (" + txt + " ago)";
      if (tag.title !== title) { tag.title = title; tag.setAttribute("aria-label", "data age " + txt); }
    });
  }

  /* ------------------------------ refresh -------------------------------- */
  var refreshing = false;
  function refresh() {
    if (refreshing) return;
    refreshing = true;
    cycleCache = {};
    resolveServices().then(function (S) {
      if (!S) { CONFIG.kpis.forEach(function (k) { var s = chipState[k] || (chipState[k] = { fails: 0 }); s.fails++; }); return; }
      return loadData(S).then(function (D) {
        var anyGood = false;
        CONFIG.kpis.forEach(function (k) {
          var def = KPI[k]; if (!def) return;
          var s = chipState[k] || (chipState[k] = { fails: 0, last: null });
          s.hidden = !def.needs.some(function (n) { return n in D; });
          if (s.hidden) return;
          var r = null;
          try { r = def.compute(D); } catch (e) { r = null; }
          if (r) { s.last = r; s.fails = 0; s.at = new Date(); anyGood = true; } else s.fails++;
        });
        if (anyGood) lastUpdated = new Date();
        return refreshAges();
      });
    }).catch(function () {}).then(function () { refreshing = false; ensureAll(); paintAll(); paintAges(); });
  }

  /* --------------------------- DOM injection ----------------------------- */
  function pageContainer() {
    var iw = doc.getElementById("inner_wrapper");
    if (iw) for (var i = 0; i < iw.children.length; i++) if (iw.children[i].tagName === "DIV") return iw.children[i];
    return null;
  }
  function topLevelChild(container, node) { while (node && node.parentNode !== container) node = node.parentNode; return node; }
  function ensureStrip(c) {
    var tabs = doc.getElementById("myTab");
    var anchor = tabs ? topLevelChild(c, tabs) : null;
    if (!anchor) { var g = doc.getElementById("layout-groups") || doc.querySelector(".services-group"); anchor = g ? topLevelChild(c, g) : null; }
    var s = doc.getElementById("pro-strip");
    if (s && s.parentNode === c && (anchor ? s.nextElementSibling === anchor : true)) return;
    if (!s) s = buildStrip();
    c.insertBefore(s, anchor || c.firstChild);
    paintAll();
  }
  var observer = null;
  function ensureAll() {
    var c = pageContainer();
    if (!c) return;
    if (observer) observer.disconnect();
    try { addStyle(); ensureStrip(c); fixLanding(); updateSwitch(); paintAges(); } catch (e) { /* fail silently */ }
    observe();
  }
  var scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    (window.requestAnimationFrame || setTimeout)(function () { scheduled = false; ensureAll(); });
  }
  function observe() {
    var t = doc.getElementById("__next") || doc.body;
    if (!t || !window.MutationObserver) return;
    if (!observer) observer = new MutationObserver(schedule);
    observer.observe(t, { childList: true, subtree: true });
  }

  /* -------------------------------- boot --------------------------------- */
  function boot() {
    ensureAll();
    refresh();
    setInterval(function () { if (!doc.hidden) refresh(); }, CONFIG.refreshMs);
    doc.addEventListener("visibilitychange", function () {
      if (!doc.hidden && (!lastUpdated || Date.now() - lastUpdated > CONFIG.refreshMs)) refresh();
    });
    window.addEventListener("hashchange", function () {
      schedule(); updateSwitch();
      setTimeout(function () { refreshAges(); updateSwitch(); }, 400);   // new tab -> new tiles
    });
    window.addEventListener("keydown", onKey, true);
    var n = 0, t = setInterval(function () { ensureAll(); if (++n > 10) clearInterval(t); }, 1000);
  }
  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", boot); else boot();

  // tiny debug hook for the lead / tests (no data, just state)
  window.__hpPro = { config: CONFIG, refresh: refresh, parseWhen: parseWhen, retroSlug: retroSlug,
                     state: function () { return JSON.parse(JSON.stringify(chipState)); } };
})();
