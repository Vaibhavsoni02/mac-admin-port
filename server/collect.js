import os from "node:os";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import fs from "node:fs/promises";
import path from "node:path";

const execFileAsync = promisify(execFile);

async function run(cmd, args = [], opts = {}) {
  try {
    const { stdout, stderr } = await execFileAsync(cmd, args, {
      timeout: opts.timeout ?? 12000,
      maxBuffer: 8 * 1024 * 1024,
      env: { ...process.env, PATH: process.env.PATH },
    });
    return { ok: true, out: String(stdout || ""), err: String(stderr || "") };
  } catch (e) {
    return {
      ok: false,
      out: String(e.stdout || ""),
      err: String(e.stderr || e.message || e),
    };
  }
}

async function which(bin) {
  const r = await run("which", [bin]);
  return r.ok ? r.out.trim() : null;
}

async function versionOf(bin, args = ["--version"]) {
  const loc = await which(bin);
  if (!loc) return null;
  const r = await run(bin, args);
  const text = (r.out || r.err || "").trim().split("\n")[0];
  return { bin, path: loc, version: text || "installed" };
}

async function memoryStats() {
  const totalGb = Math.round(os.totalmem() / (1024 ** 3));
  const vm = await run("vm_stat");
  const pageSizeMatch = vm.out.match(/page size of (\d+) bytes/i);
  const pageSize = pageSizeMatch ? Number(pageSizeMatch[1]) : 16384;
  const grab = (label) => {
    const m = vm.out.match(new RegExp(`${label}:\\s+(\\d+)`, "i"));
    return m ? Number(m[1]) : 0;
  };
  const free = grab("Pages free");
  const speculative = grab("Pages speculative");
  const inactive = grab("Pages inactive");
  const purgeable = grab("Pages purgeable");
  const availablePages = free + speculative + inactive + purgeable;
  const availableGb = Math.round(((availablePages * pageSize) / 1024 ** 3) * 10) / 10;
  const usedGb = Math.max(0, Math.round((totalGb - availableGb) * 10) / 10);
  const usedPct = Math.min(100, Math.round((usedGb / totalGb) * 100));
  return { totalGb, availableGb, usedGb, usedPct };
}

async function collectHost() {
  const hostname = os.hostname();
  const platform = `${os.type()} ${os.release()}`;
  const arch = os.arch();
  const cpus = os.cpus();
  const cpuModel = cpus[0]?.model?.trim() || "Unknown CPU";
  const cpuCount = cpus.length;
  const mem = await memoryStats();
  const load = os.loadavg().map((n) => Math.round(n * 100) / 100);
  const uptimeSec = Math.round(os.uptime());

  const df = await run("df", ["-h", "/System/Volumes/Data"]);
  let disk = null;
  const lines = df.out.trim().split("\n");
  if (lines.length >= 2) {
    const parts = lines[1].split(/\s+/);
    disk = {
      size: parts[1],
      used: parts[2],
      avail: parts[3],
      capacity: parts[4],
      mount: parts[8] || parts[parts.length - 1],
    };
  }

  const sw = await run("sw_vers");
  const product = {};
  for (const line of sw.out.split("\n")) {
    const [k, ...rest] = line.split(":");
    if (k && rest.length) product[k.trim()] = rest.join(":").trim();
  }

  return {
    hostname,
    platform,
    arch,
    cpuModel,
    cpuCount,
    totalMemGb: mem.totalGb,
    freeMemGb: mem.availableGb,
    usedMemGb: mem.usedGb,
    memPressurePct: mem.usedPct,
    load,
    uptimeSec,
    disk,
    macos: product.ProductVersion || null,
    build: product.BuildVersion || null,
  };
}

async function collectPorts() {
  const r = await run("lsof", ["-nP", "-iTCP", "-sTCP:LISTEN"]);
  if (!r.ok && !r.out) return [];

  const rows = [];
  const seen = new Set();
  for (const line of r.out.split("\n").slice(1)) {
    if (!line.trim()) continue;
    const parts = line.trim().split(/\s+/);
    if (parts.length < 9) continue;
    const command = parts[0];
    const pid = Number(parts[1]);
    const user = parts[2];
    const name = parts[parts.length - 2] === "(LISTEN)" ? parts[parts.length - 3] : parts[8];
    const m = String(name).match(/:(\d+)$/);
    if (!m) continue;
    const port = Number(m[1]);
    const address = String(name).replace(/:\d+$/, "");
    const key = `${port}|${pid}|${address}`;
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push({
      port,
      address,
      command,
      pid,
      user,
      bind: name,
      cloudHint: cloudHintForPort(port, command),
    });
  }
  rows.sort((a, b) => a.port - b.port || a.pid - b.pid);
  return rows;
}

function cloudHintForPort(port, command) {
  const map = {
    3000: "Web app / Metabase — easy container or PaaS move",
    3001: "App server — containerize with Docker Compose",
    5432: "PostgreSQL — managed DB (RDS, Neon, Supabase, Cloud SQL)",
    6379: "Redis — managed Redis / ElastiCache / Upstash",
    27017: "MongoDB — Atlas or managed Mongo",
    3306: "MySQL — managed MySQL / PlanetScale / RDS",
    8080: "HTTP service — container or reverse-proxy PaaS",
    8000: "Dev API — containerize",
    5173: "Vite/dev UI — static host or container",
    4200: "Angular/dev — static host",
    9200: "Elasticsearch — Elastic Cloud",
  };
  if (map[port]) return map[port];
  if (/docker|com\.docke/i.test(command)) return "Docker-published port — already container-ready";
  if (/postgres/i.test(command)) return "Postgres — prefer managed DB in cloud";
  if (/node/i.test(command)) return "Node process — deploy to Fly/Render/Railway/ECS";
  return "Review before cloud move";
}

async function collectProcesses() {
  const r = await run("ps", ["-axo", "%cpu=,rss=,pid=,user=,comm="]);
  if (!r.ok && !r.out) return [];
  const rows = [];
  for (const line of r.out.split("\n")) {
    if (!line.trim()) continue;
    const m = line.match(/^\s*([\d.]+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(.+)$/);
    if (!m) continue;
    const cpu = Number(m[1]);
    const rssKb = Number(m[2]);
    const pid = Number(m[3]);
    const user = m[4];
    let command = m[5].trim();
    // Prefer short app name when path is long
    const appMatch = command.match(/\/Applications\/([^/]+)\.app\//);
    if (appMatch) command = appMatch[1] + (command.includes("Helper") ? " Helper" : "");
    if (cpu < 0.3 && rssKb < 80_000) continue;
    rows.push({
      cpu,
      rssMb: Math.round((rssKb / 1024) * 10) / 10,
      pid,
      user,
      command,
    });
  }
  rows.sort((a, b) => b.cpu - a.cpu || b.rssMb - a.rssMb);
  return rows.slice(0, 60);
}

async function collectDocker() {
  const dockerPath = await which("docker");
  if (!dockerPath) return { available: false, containers: [], images: [] };

  const ps = await run("docker", [
    "ps",
    "-a",
    "--format",
    "{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}\t{{.ID}}",
  ]);
  const containers = [];
  for (const line of ps.out.split("\n")) {
    if (!line.trim()) continue;
    const [name, image, status, ports, id] = line.split("\t");
    containers.push({
      name,
      image,
      status,
      ports: ports || "",
      id,
      running: /^Up /i.test(status || ""),
      cloudReady: true,
      note: "Already containerized — strongest cloud migration candidate",
    });
  }

  return { available: true, containers };
}

async function collectRuntimes() {
  const checks = [
    ["node", ["-v"]],
    ["npm", ["-v"]],
    ["python3", ["--version"]],
    ["docker", ["--version"]],
    ["brew", ["--version"]],
    ["go", ["version"]],
    ["uv", ["--version"]],
    ["psql", ["--version"]],
    ["redis-server", ["--version"]],
    ["mysql", ["--version"]],
    ["mongod", ["--version"]],
    ["nginx", ["-v"]],
    ["ruby", ["-v"]],
    ["php", ["-v"]],
    ["bun", ["-v"]],
    ["pnpm", ["-v"]],
    ["yarn", ["-v"]],
    ["cargo", ["--version"]],
    ["java", ["-version"]],
    ["gh", ["--version"]],
  ];
  const found = [];
  for (const [bin, args] of checks) {
    const v = await versionOf(bin, args);
    if (!v) continue;
    if (/unable to locate|not found|no such file/i.test(v.version)) continue;
    found.push(v);
  }
  return found;
}

async function collectBrew() {
  const brew = await which("brew");
  if (!brew) return { available: false, formulae: [], casks: [], services: [] };

  const [formulaeR, casksR, servicesR] = await Promise.all([
    run("brew", ["list", "--formula"]),
    run("brew", ["list", "--cask"]),
    run("brew", ["services", "list"]),
  ]);

  const formulae = formulaeR.out
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
  const casks = casksR.out
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

  const services = [];
  for (const line of servicesR.out.split("\n").slice(1)) {
    if (!line.trim()) continue;
    const parts = line.trim().split(/\s+/);
    services.push({
      name: parts[0],
      status: parts[1] || "unknown",
      user: parts[2] || "",
    });
  }

  return { available: true, formulae, casks, services };
}

async function collectNpmGlobal() {
  const npm = await which("npm");
  if (!npm) return [];
  const r = await run("npm", ["list", "-g", "--depth=0", "--json"]);
  try {
    const json = JSON.parse(r.out || "{}");
    const deps = json.dependencies || {};
    return Object.entries(deps).map(([name, meta]) => ({
      name,
      version: meta.version || (meta.resolved ? "link" : "unknown"),
      link: Boolean(meta.resolved || meta.link),
    }));
  } catch {
    return [];
  }
}

async function collectPip() {
  const r = await run("python3", ["-m", "pip", "list", "--format=json"]);
  if (!r.ok) return [];
  try {
    return JSON.parse(r.out || "[]").map((p) => ({
      name: p.name,
      version: p.version,
    }));
  } catch {
    return [];
  }
}

async function collectApps() {
  const dirs = ["/Applications", path.join(os.homedir(), "Applications")];
  const apps = [];
  for (const dir of dirs) {
    try {
      const entries = await fs.readdir(dir);
      for (const name of entries) {
        if (!name.endsWith(".app")) continue;
        apps.push({
          name: name.replace(/\.app$/, ""),
          path: path.join(dir, name),
          scope: dir.startsWith(os.homedir()) ? "user" : "system",
        });
      }
    } catch {
      /* missing dir */
    }
  }
  apps.sort((a, b) => a.name.localeCompare(b.name));
  return apps;
}

async function collectLaunchAgents() {
  const dir = path.join(os.homedir(), "Library", "LaunchAgents");
  try {
    const entries = await fs.readdir(dir);
    return entries.filter((e) => e.endsWith(".plist")).map((e) => ({ name: e, path: path.join(dir, e) }));
  } catch {
    return [];
  }
}

function buildCloudPlan({ ports, docker, runtimes, brew }) {
  const items = [];

  for (const c of docker.containers || []) {
    if (!c.running) continue;
    items.push({
      priority: "high",
      title: `Docker: ${c.name}`,
      detail: `${c.image} · ${c.ports || "no published ports"}`,
      action: "Lift-and-shift with the same image to ECS/Fly/Railway/Cloud Run. Attach managed Postgres/Redis instead of container DBs when possible.",
      category: "container",
    });
  }

  const interestingPorts = (ports || []).filter((p) => {
    if (p.address === "*" || p.address === "0.0.0.0") return true;
    return [3000, 3001, 5432, 6379, 8080, 8000, 5173, 4200, 27017, 3306].includes(p.port);
  });

  const byPort = new Map();
  for (const p of interestingPorts) {
    if (!byPort.has(p.port)) byPort.set(p.port, p);
  }
  for (const p of byPort.values()) {
    if (/com\.docke|docker/i.test(p.command)) continue;
    items.push({
      priority: p.port === 5432 ? "high" : "medium",
      title: `Port ${p.port} · ${p.command}`,
      detail: `Listening on ${p.bind} (pid ${p.pid})`,
      action: p.cloudHint,
      category: "port",
    });
  }

  const runtimeNames = new Set((runtimes || []).map((r) => r.bin));
  if (runtimeNames.has("psql") || (ports || []).some((p) => p.port === 5432)) {
    items.push({
      priority: "high",
      title: "Local PostgreSQL dependency",
      detail: "Postgres is present locally (app and/or Docker).",
      action: "Move to Neon, Supabase, RDS, or Cloud SQL before shipping. Keep connection strings in env vars.",
      category: "data",
    });
  }
  if ((docker.containers || []).some((c) => /redis/i.test(c.image) && c.running)) {
    items.push({
      priority: "medium",
      title: "Local Redis",
      detail: "Redis is running in Docker.",
      action: "Use Upstash, ElastiCache, or Memorystore in cloud.",
      category: "data",
    });
  }

  const brewCritical = (brew.formulae || []).filter((f) =>
    /^(node|python|go|ffmpeg|postgresql|redis|nginx|cloudflared)/.test(f)
  );
  if (brewCritical.length) {
    items.push({
      priority: "low",
      title: "Homebrew runtime stack",
      detail: brewCritical.slice(0, 12).join(", "),
      action: "Bake these into Dockerfiles or use cloud buildpacks so deploys do not rely on your Mac brew cellar.",
      category: "deps",
    });
  }

  const score = Math.min(
    100,
    (docker.containers || []).filter((c) => c.running).length * 18 +
      byPort.size * 8 +
      (runtimeNames.has("docker") ? 10 : 0)
  );

  return {
    score,
    summary:
      score >= 60
        ? "Several local services look cloud-movable soon — Docker workloads first."
        : score >= 30
          ? "Some local services can move; start with databases and published ports."
          : "Light local footprint — still inventory ports before each project deploy.",
    items,
  };
}

export async function collectAll() {
  const [host, ports, processes, docker, runtimes, brew, npmGlobal, pip, apps, launchAgents] =
    await Promise.all([
      collectHost(),
      collectPorts(),
      collectProcesses(),
      collectDocker(),
      collectRuntimes(),
      collectBrew(),
      collectNpmGlobal(),
      collectPip(),
      collectApps(),
      collectLaunchAgents(),
    ]);

  const cloud = buildCloudPlan({ ports, docker, runtimes, brew });

  return {
    collectedAt: new Date().toISOString(),
    host,
    ports,
    processes,
    docker,
    runtimes,
    brew,
    npmGlobal,
    pip,
    apps,
    launchAgents,
    cloud,
    counts: {
      ports: ports.length,
      processes: processes.length,
      dockerRunning: (docker.containers || []).filter((c) => c.running).length,
      dockerTotal: (docker.containers || []).length,
      runtimes: runtimes.length,
      brewFormulae: (brew.formulae || []).length,
      brewCasks: (brew.casks || []).length,
      npmGlobal: npmGlobal.length,
      pip: pip.length,
      apps: apps.length,
      launchAgents: launchAgents.length,
      cloudItems: cloud.items.length,
    },
  };
}
