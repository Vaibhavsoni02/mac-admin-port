const $ = (sel) => document.querySelector(sel);

let snapshot = null;
let timer = null;

function fmtUptime(sec) {
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderMetrics(data) {
  const h = data.host;
  const c = data.counts;
  $("#hostname").textContent = h.hostname;
  $("#host-meta").textContent = [
    h.macos ? `macOS ${h.macos}` : h.platform,
    h.cpuModel,
    `${h.cpuCount} cores`,
    `${h.totalMemGb} GB RAM`,
    h.arch,
  ].join(" · ");
  $("#collected-at").textContent = new Date(data.collectedAt).toLocaleString();

  const items = [
    { label: "Memory", value: `${h.memPressurePct}%`, hint: `${h.usedMemGb}/${h.totalMemGb} GB used` },
    { label: "Disk", value: h.disk?.capacity || "—", hint: h.disk ? `${h.disk.used} / ${h.disk.size}` : "" },
    { label: "Load", value: String(h.load?.[0] ?? "—"), hint: `1m · up ${fmtUptime(h.uptimeSec)}` },
    { label: "Ports", value: String(c.ports), hint: "TCP listen" },
    { label: "Docker up", value: String(c.dockerRunning), hint: `${c.dockerTotal} total` },
    { label: "Cloud items", value: String(c.cloudItems), hint: `score ${data.cloud.score}` },
  ];

  $("#metrics").innerHTML = items
    .map(
      (m) => `<article class="metric">
        <div class="label">${esc(m.label)}</div>
        <div class="value">${esc(m.value)}</div>
        <div class="hint">${esc(m.hint)}</div>
      </article>`
    )
    .join("");
}

function renderCloud(data) {
  const cloud = data.cloud;
  const items = cloud.items
    .map(
      (it) => `<article class="plan-item">
        <div class="prio ${esc(it.priority)}">${esc(it.priority)}</div>
        <div>
          <h4>${esc(it.title)}</h4>
          <p class="detail">${esc(it.detail)}</p>
          <p class="action">${esc(it.action)}</p>
        </div>
      </article>`
    )
    .join("");

  $("#panel-cloud").innerHTML = `
    <div class="score-row">
      <div class="score-box">
        <div class="label">Cloud readiness</div>
        <div class="value">${esc(cloud.score)}</div>
        <div class="hint">/ 100 · higher = more movable now</div>
      </div>
      <div class="score-copy">
        <h3>What to move first</h3>
        <p>${esc(cloud.summary)}</p>
      </div>
    </div>
    <div class="section-head">
      <h2>Migration checklist</h2>
      <p>${cloud.items.length} actionable items from live scan</p>
    </div>
    <div class="plan-list">${items || "<p class='sub'>No high-signal local services detected.</p>"}</div>
  `;
}

function renderPorts(data) {
  const rows = data.ports
    .map(
      (p) => `<tr>
        <td class="mono">${esc(p.port)}</td>
        <td class="mono">${esc(p.address)}</td>
        <td>${esc(p.command)}</td>
        <td class="mono">${esc(p.pid)}</td>
        <td>${esc(p.user)}</td>
        <td>${esc(p.cloudHint)}</td>
      </tr>`
    )
    .join("");

  $("#panel-ports").innerHTML = `
    <div class="section-head">
      <h2>Listening TCP ports</h2>
      <p>${data.ports.length} unique bindings · via lsof</p>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Port</th><th>Bind</th><th>Process</th><th>PID</th><th>User</th><th>Cloud note</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function renderDocker(data) {
  const d = data.docker;
  if (!d.available) {
    $("#panel-docker").innerHTML = `<p class="sub">Docker CLI not found on PATH.</p>`;
    return;
  }
  const rows = (d.containers || [])
    .map(
      (c) => `<tr>
        <td>${esc(c.name)}</td>
        <td class="mono">${esc(c.image)}</td>
        <td><span class="badge ${c.running ? "" : "off"}">${c.running ? "running" : "stopped"}</span></td>
        <td class="mono">${esc(c.ports || "—")}</td>
        <td>${esc(c.note)}</td>
      </tr>`
    )
    .join("");

  $("#panel-docker").innerHTML = `
    <div class="section-head">
      <h2>Docker containers</h2>
      <p>Best lift-and-shift candidates for cloud</p>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Name</th><th>Image</th><th>Status</th><th>Ports</th><th>Move note</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function renderProcesses(data) {
  const rows = data.processes
    .map(
      (p) => `<tr>
        <td class="mono">${esc(p.cpu)}%</td>
        <td class="mono">${esc(p.rssMb)} MB</td>
        <td class="mono">${esc(p.pid)}</td>
        <td>${esc(p.user)}</td>
        <td class="mono">${esc(p.command)}</td>
      </tr>`
    )
    .join("");

  $("#panel-processes").innerHTML = `
    <div class="section-head">
      <h2>Active processes</h2>
      <p>Filtered to meaningful CPU/memory users</p>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>CPU</th><th>RSS</th><th>PID</th><th>User</th><th>Command</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function chipList(items, mapFn) {
  return `<div class="chips">${items.map(mapFn).join("")}</div>`;
}

function renderDeps(data) {
  const runtimes = chipList(
    data.runtimes,
    (r) => `<span class="chip"><strong>${esc(r.bin)}</strong> ${esc(r.version)}</span>`
  );
  const brew = chipList(
    data.brew.formulae || [],
    (f) => `<span class="chip">${esc(f)}</span>`
  );
  const casks = chipList(
    data.brew.casks || [],
    (f) => `<span class="chip">${esc(f)}</span>`
  );
  const npm = chipList(
    data.npmGlobal,
    (p) => `<span class="chip"><strong>${esc(p.name)}</strong> ${esc(p.version)}</span>`
  );
  const pip = chipList(
    data.pip.slice(0, 80),
    (p) => `<span class="chip"><strong>${esc(p.name)}</strong> ${esc(p.version)}</span>`
  );
  const services = (data.brew.services || [])
    .map(
      (s) => `<tr><td>${esc(s.name)}</td><td class="mono">${esc(s.status)}</td><td>${esc(s.user)}</td></tr>`
    )
    .join("");
  const agents = (data.launchAgents || [])
    .map((a) => `<span class="chip">${esc(a.name)}</span>`)
    .join("");

  $("#panel-deps").innerHTML = `
    <div class="section-head">
      <h2>Installed dependencies</h2>
      <p>Runtimes, Homebrew, npm globals, pip, launch agents</p>
    </div>
    <div class="grid-2">
      <div class="block">
        <h3>Runtimes on PATH (${data.runtimes.length})</h3>
        <div class="scroll">${runtimes}</div>
      </div>
      <div class="block">
        <h3>Brew services</h3>
        <div class="table-wrap scroll">
          <table>
            <thead><tr><th>Name</th><th>Status</th><th>User</th></tr></thead>
            <tbody>${services || "<tr><td colspan='3'>None</td></tr>"}</tbody>
          </table>
        </div>
      </div>
      <div class="block">
        <h3>Homebrew formulae (${data.counts.brewFormulae})</h3>
        <div class="scroll">${brew}</div>
      </div>
      <div class="block">
        <h3>Homebrew casks (${data.counts.brewCasks})</h3>
        <div class="scroll">${casks || "<span class='sub'>None</span>"}</div>
      </div>
      <div class="block">
        <h3>npm global (${data.counts.npmGlobal})</h3>
        <div class="scroll">${npm || "<span class='sub'>None</span>"}</div>
      </div>
      <div class="block">
        <h3>pip packages (${data.counts.pip})</h3>
        <div class="scroll">${pip}</div>
      </div>
    </div>
    <div class="block" style="margin-top:16px">
      <h3>LaunchAgents (${data.counts.launchAgents})</h3>
      <div class="chips">${agents || "<span class='sub'>None</span>"}</div>
    </div>
  `;
}

function renderApps(data) {
  const rows = data.apps
    .map(
      (a) => `<tr>
        <td>${esc(a.name)}</td>
        <td class="mono">${esc(a.scope)}</td>
        <td class="mono">${esc(a.path)}</td>
      </tr>`
    )
    .join("");

  $("#panel-apps").innerHTML = `
    <div class="section-head">
      <h2>Installed applications</h2>
      <p>${data.apps.length} apps in /Applications and ~/Applications</p>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Name</th><th>Scope</th><th>Path</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function browserDetails() {
  const nav = navigator;
  const conn = nav.connection || nav.mozConnection || nav.webkitConnection;
  let timezone = "—";
  try {
    timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "—";
  } catch {
    /* ignore */
  }
  return {
    userAgent: nav.userAgent || "—",
    platform: nav.platform || "—",
    language: nav.language || "—",
    languages: Array.isArray(nav.languages) ? nav.languages.join(", ") : "—",
    cookiesEnabled: Boolean(nav.cookieEnabled),
    online: Boolean(nav.onLine),
    hardwareConcurrency: nav.hardwareConcurrency ?? "—",
    deviceMemoryGb: nav.deviceMemory ?? "—",
    timezone,
    timezoneOffsetMin: new Date().getTimezoneOffset(),
    screen: `${screen.width}×${screen.height}`,
    availScreen: `${screen.availWidth}×${screen.availHeight}`,
    colorDepth: screen.colorDepth,
    devicePixelRatio: window.devicePixelRatio || 1,
    viewport: `${window.innerWidth}×${window.innerHeight}`,
    connectionType: conn?.effectiveType || conn?.type || "—",
    downlinkMbps: conn?.downlink ?? "—",
    rttMs: conn?.rtt ?? "—",
    vendor: nav.vendor || "—",
  };
}

function kv(label, value, mono = false) {
  return `<div class="kv"><div class="k">${esc(label)}</div><div class="v${mono ? " mono" : ""}">${esc(value ?? "—")}</div></div>`;
}

function renderNetwork(network) {
  const p = network?.public || {};
  const b = browserDetails();
  const note = p.proxyNote ? `<p class="note">${esc(p.proxyNote)}</p>` : "";
  const err = p.error ? `<p class="note">Public IP lookup issue: ${esc(p.error)}</p>` : "";

  const ifaceRows = (network?.localInterfaces || [])
    .map(
      (i) => `<tr>
        <td>${esc(i.iface)}</td>
        <td class="mono">${esc(i.family)}</td>
        <td class="mono">${esc(i.address)}</td>
        <td class="mono">${esc(i.cidr || "—")}</td>
        <td class="mono">${esc(i.mac)}</td>
      </tr>`
    )
    .join("");

  $("#panel-network").innerHTML = `
    <div class="section-head">
      <h2>Public IP &amp; location</h2>
      <p>Live egress lookup · ${esc(p.source || "—")} · ${esc(network?.collectedAt ? new Date(network.collectedAt).toLocaleString() : "—")}</p>
    </div>
    ${err}${note}
    <div class="kv-grid" style="margin-bottom:18px">
      ${kv("IPv4", p.ipv4, true)}
      ${kv("IPv6", p.ipv6, true)}
      ${kv("Country", p.country)}
      ${kv("Region", p.region)}
      ${kv("City", p.city)}
      ${kv("ZIP", p.zip)}
      ${kv("Timezone", p.timezone)}
      ${kv("ISP", p.isp)}
      ${kv("Organization", p.organization)}
      ${kv("AS number / name", [p.asn, p.asName].filter(Boolean).join(" · ") || "—")}
    </div>

    <div class="section-head">
      <h2>This browser (realtime)</h2>
      <p>Read from the page you have open right now</p>
    </div>
    <div class="kv-grid" style="margin-bottom:12px">
      ${kv("Timezone", b.timezone)}
      ${kv("Languages", b.languages)}
      ${kv("Platform", b.platform, true)}
      ${kv("Online", b.online ? "yes" : "no")}
      ${kv("Screen", b.screen, true)}
      ${kv("Viewport", b.viewport, true)}
      ${kv("Pixel ratio", b.devicePixelRatio, true)}
      ${kv("Connection", `${b.connectionType} · ↓${b.downlinkMbps} Mbps · RTT ${b.rttMs} ms`)}
      ${kv("Vendor", b.vendor)}
      ${kv("Cookies", b.cookiesEnabled ? "enabled" : "disabled")}
    </div>
    <div class="section-head" style="margin-top:4px">
      <h2>User agent</h2>
      <p></p>
    </div>
    <div class="ua-box">${esc(b.userAgent)}</div>

    <div class="section-head" style="margin-top:18px">
      <h2>Local network interfaces</h2>
      <p>Non-loopback addresses on this Mac</p>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Interface</th><th>Family</th><th>Address</th><th>CIDR</th><th>MAC</th></tr></thead>
        <tbody>${ifaceRows || "<tr><td colspan='5'>None</td></tr>"}</tbody>
      </table>
    </div>
  `;
}

function renderAll(data) {
  snapshot = data;
  renderMetrics(data);
  renderCloud(data);
  renderPorts(data);
  renderDocker(data);
  renderProcesses(data);
  renderDeps(data);
  renderApps(data);
}

async function load() {
  const btn = $("#refresh-btn");
  btn.disabled = true;
  btn.textContent = "Scanning…";
  try {
    const [snapRes, netRes] = await Promise.all([
      fetch("/api/snapshot", { cache: "no-store" }),
      fetch("/api/network", { cache: "no-store" }),
    ]);
    if (!snapRes.ok) throw new Error(`Snapshot HTTP ${snapRes.status}`);
    const data = await snapRes.json();
    if (data.error) throw new Error(data.error);
    renderAll(data);

    if (netRes.ok) {
      const network = await netRes.json();
      if (!network.error) renderNetwork(network);
      else renderNetwork({ public: { error: network.error }, localInterfaces: [] });
    } else {
      renderNetwork({ public: { error: `Network HTTP ${netRes.status}` }, localInterfaces: [] });
    }
  } catch (err) {
    const msg = esc(err.message || err);
    $("#panel-cloud").innerHTML = `<div class="error">Failed to scan this Mac: ${msg}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Refresh";
  }
}

function setupTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      $(`#panel-${tab.dataset.tab}`).classList.add("active");
    });
  });
}

setupTabs();
$("#refresh-btn").addEventListener("click", load);
load();
timer = setInterval(load, 30000);
