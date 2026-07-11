"""Cross-platform system collectors for Mac Admin Analytics (Streamlit)."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any


def run(cmd: list[str], timeout: int = 12) -> tuple[bool, str, str]:
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ},
        )
        return p.returncode == 0, p.stdout or "", p.stderr or ""
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        return False, "", str(e)


def which(bin_name: str) -> str | None:
    return shutil.which(bin_name)


def version_of(bin_name: str, args: list[str] | None = None) -> dict[str, str] | None:
    loc = which(bin_name)
    if not loc:
        return None
    ok, out, err = run([bin_name, *(args or ["--version"])])
    text = (out or err or "").strip().splitlines()
    version = text[0] if text else "installed"
    if re.search(r"unable to locate|not found|no such file", version, re.I):
        return None
    return {"bin": bin_name, "path": loc, "version": version}


def _memory_stats() -> dict[str, float | int]:
    total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") if hasattr(os, "sysconf") else 0
    # Fallback via platform
    try:
        import psutil  # optional

        vm = psutil.virtual_memory()
        total_gb = round(vm.total / (1024**3))
        avail_gb = round(vm.available / (1024**3), 1)
        used_gb = round((vm.total - vm.available) / (1024**3), 1)
        return {
            "totalGb": total_gb,
            "availableGb": avail_gb,
            "usedGb": used_gb,
            "usedPct": int(vm.percent),
        }
    except Exception:
        pass

    system = platform.system()
    if system == "Darwin":
        ok, out, _ = run(["sysctl", "-n", "hw.memsize"])
        total_b = int(out.strip()) if ok and out.strip().isdigit() else 0
        total_gb = round(total_b / (1024**3)) if total_b else 0
        ok, vm_out, _ = run(["vm_stat"])
        page_size = 16384
        m = re.search(r"page size of (\d+) bytes", vm_out, re.I)
        if m:
            page_size = int(m.group(1))

        def grab(label: str) -> int:
            mm = re.search(rf"{label}:\s+(\d+)", vm_out, re.I)
            return int(mm.group(1)) if mm else 0

        available_pages = (
            grab("Pages free")
            + grab("Pages speculative")
            + grab("Pages inactive")
            + grab("Pages purgeable")
        )
        available_gb = round((available_pages * page_size) / (1024**3), 1)
        used_gb = max(0.0, round(total_gb - available_gb, 1))
        used_pct = min(100, round((used_gb / total_gb) * 100)) if total_gb else 0
        return {
            "totalGb": total_gb,
            "availableGb": available_gb,
            "usedGb": used_gb,
            "usedPct": used_pct,
        }

    # Linux /proc/meminfo
    try:
        info = Path("/proc/meminfo").read_text()
        def kb(name: str) -> int:
            mm = re.search(rf"{name}:\s+(\d+)", info)
            return int(mm.group(1)) if mm else 0

        total_kb = kb("MemTotal")
        avail_kb = kb("MemAvailable") or (kb("MemFree") + kb("Buffers") + kb("Cached"))
        total_gb = round(total_kb / (1024**2))
        available_gb = round(avail_kb / (1024**2), 1)
        used_gb = max(0.0, round(total_gb - available_gb, 1))
        used_pct = min(100, round((used_gb / total_gb) * 100)) if total_gb else 0
        return {
            "totalGb": total_gb,
            "availableGb": available_gb,
            "usedGb": used_gb,
            "usedPct": used_pct,
        }
    except Exception:
        return {"totalGb": 0, "availableGb": 0, "usedGb": 0, "usedPct": 0}


def collect_host() -> dict[str, Any]:
    mem = _memory_stats()
    cpus = os.cpu_count() or 1
    cpu_model = platform.processor() or platform.machine()
    if platform.system() == "Darwin":
        ok, out, _ = run(["sysctl", "-n", "machdep.cpu.brand_string"])
        if ok and out.strip():
            cpu_model = out.strip()
    elif Path("/proc/cpuinfo").exists():
        try:
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith("model name"):
                    cpu_model = line.split(":", 1)[1].strip()
                    break
        except Exception:
            pass

    load = [0.0, 0.0, 0.0]
    try:
        load = [round(x, 2) for x in os.getloadavg()]
    except OSError:
        pass

    disk = None
    disk_path = "/System/Volumes/Data" if platform.system() == "Darwin" else "/"
    ok, out, _ = run(["df", "-h", disk_path])
    lines = [ln for ln in out.splitlines() if ln.strip()]
    if len(lines) >= 2:
        parts = lines[1].split()
        if len(parts) >= 5:
            disk = {
                "size": parts[1],
                "used": parts[2],
                "avail": parts[3],
                "capacity": parts[4],
                "mount": parts[-1],
            }

    macos = None
    build = None
    if platform.system() == "Darwin":
        ok, out, _ = run(["sw_vers"])
        for line in out.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            if k == "ProductVersion":
                macos = v
            elif k == "BuildVersion":
                build = v

    return {
        "hostname": socket.gethostname(),
        "platform": f"{platform.system()} {platform.release()}",
        "arch": platform.machine(),
        "cpuModel": cpu_model,
        "cpuCount": cpus,
        "totalMemGb": mem["totalGb"],
        "freeMemGb": mem["availableGb"],
        "usedMemGb": mem["usedGb"],
        "memPressurePct": mem["usedPct"],
        "load": load,
        "uptimeSec": int(time.time() - _boot_time()),
        "disk": disk,
        "macos": macos,
        "build": build,
        "system": platform.system(),
    }


def _boot_time() -> float:
    try:
        import psutil

        return float(psutil.boot_time())
    except Exception:
        pass
    if platform.system() == "Darwin":
        ok, out, _ = run(["sysctl", "-n", "kern.boottime"])
        m = re.search(r"sec\s*=\s*(\d+)", out)
        if m:
            return float(m.group(1))
    try:
        # Linux: uptime seconds in /proc/uptime
        up = float(Path("/proc/uptime").read_text().split()[0])
        return time.time() - up
    except Exception:
        return time.time()


def cloud_hint_for_port(port: int, command: str) -> str:
    hints = {
        3000: "Web app / Metabase — easy container or PaaS move",
        3001: "App server — containerize with Docker Compose",
        5432: "PostgreSQL — managed DB (RDS, Neon, Supabase, Cloud SQL)",
        6379: "Redis — managed Redis / ElastiCache / Upstash",
        27017: "MongoDB — Atlas or managed Mongo",
        3306: "MySQL — managed MySQL / PlanetScale / RDS",
        8080: "HTTP service — container or reverse-proxy PaaS",
        8000: "Dev API — containerize",
        8501: "Streamlit — deploy to Streamlit Community Cloud / container",
        5173: "Vite/dev UI — static host or container",
    }
    if port in hints:
        return hints[port]
    if re.search(r"docker|com\.docke", command, re.I):
        return "Docker-published port — already container-ready"
    if re.search(r"postgres", command, re.I):
        return "Postgres — prefer managed DB in cloud"
    if re.search(r"node|python|streamlit", command, re.I):
        return "App process — deploy to Fly/Render/Railway/ECS"
    return "Review before cloud move"


def collect_ports() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    ok, out, _ = run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"])
    if ok and out.strip():
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 9:
                continue
            command, pid, user = parts[0], parts[1], parts[2]
            name = parts[-2] if parts[-1] == "(LISTEN)" else parts[8]
            m = re.search(r":(\d+)$", name)
            if not m:
                continue
            port = int(m.group(1))
            address = re.sub(r":\d+$", "", name)
            key = f"{port}|{pid}|{address}"
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "port": port,
                    "address": address,
                    "command": command,
                    "pid": int(pid) if pid.isdigit() else pid,
                    "user": user,
                    "bind": name,
                    "cloudHint": cloud_hint_for_port(port, command),
                }
            )
    else:
        # Linux fallback: ss
        ok, out, _ = run(["ss", "-lptn"])
        if ok:
            for line in out.splitlines()[1:]:
                m = re.search(r":(\d+)\s+", line)
                if not m:
                    continue
                port = int(m.group(1))
                proc = "unknown"
                pm = re.search(r'users:\(\("([^"]+)"', line)
                if pm:
                    proc = pm.group(1)
                key = f"{port}|{proc}"
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "port": port,
                        "address": "*",
                        "command": proc,
                        "pid": "—",
                        "user": "—",
                        "bind": f"*:{port}",
                        "cloudHint": cloud_hint_for_port(port, proc),
                    }
                )

    rows.sort(key=lambda r: (r["port"], str(r["pid"])))
    return rows


def collect_processes() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ok, out, _ = run(["ps", "-axo", "%cpu=,rss=,pid=,user=,comm="])
    if not ok:
        ok, out, _ = run(["ps", "axo", "%cpu,rss,pid,user,comm"])
    for line in out.splitlines():
        m = re.match(r"^\s*([\d.]+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(.+)$", line)
        if not m:
            continue
        cpu = float(m.group(1))
        rss_kb = int(m.group(2))
        pid = int(m.group(3))
        user = m.group(4)
        command = m.group(5).strip()
        app = re.search(r"/Applications/([^/]+)\.app/", command)
        if app:
            command = app.group(1) + (" Helper" if "Helper" in command else "")
        if cpu < 0.3 and rss_kb < 80_000:
            continue
        rows.append(
            {
                "cpu": cpu,
                "rssMb": round(rss_kb / 1024, 1),
                "pid": pid,
                "user": user,
                "command": command,
            }
        )
    rows.sort(key=lambda r: (-r["cpu"], -r["rssMb"]))
    return rows[:60]


def collect_docker() -> dict[str, Any]:
    if not which("docker"):
        return {"available": False, "containers": []}
    ok, out, _ = run(
        [
            "docker",
            "ps",
            "-a",
            "--format",
            "{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}\t{{.ID}}",
        ]
    )
    containers = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        while len(parts) < 5:
            parts.append("")
        name, image, status, ports, cid = parts[:5]
        containers.append(
            {
                "name": name,
                "image": image,
                "status": status,
                "ports": ports,
                "id": cid,
                "running": status.startswith("Up "),
                "note": "Already containerized — strongest cloud migration candidate",
            }
        )
    return {"available": True, "containers": containers}


def collect_runtimes() -> list[dict[str, str]]:
    checks = [
        ("node", ["-v"]),
        ("npm", ["-v"]),
        ("python3", ["--version"]),
        ("docker", ["--version"]),
        ("brew", ["--version"]),
        ("go", ["version"]),
        ("uv", ["--version"]),
        ("psql", ["--version"]),
        ("redis-server", ["--version"]),
        ("streamlit", ["--version"]),
        ("gh", ["--version"]),
        ("ruby", ["-v"]),
        ("java", ["-version"]),
        ("bun", ["-v"]),
        ("pnpm", ["-v"]),
    ]
    found = []
    for bin_name, args in checks:
        v = version_of(bin_name, args)
        if v:
            found.append(v)
    return found


def collect_brew() -> dict[str, Any]:
    if not which("brew"):
        return {"available": False, "formulae": [], "casks": [], "services": []}
    _, formulae_out, _ = run(["brew", "list", "--formula"], timeout=30)
    _, casks_out, _ = run(["brew", "list", "--cask"], timeout=30)
    _, services_out, _ = run(["brew", "services", "list"], timeout=20)
    formulae = [x for x in formulae_out.splitlines() if x.strip()]
    casks = [x for x in casks_out.splitlines() if x.strip()]
    services = []
    for line in services_out.splitlines()[1:]:
        parts = line.split()
        if not parts:
            continue
        services.append(
            {
                "name": parts[0],
                "status": parts[1] if len(parts) > 1 else "unknown",
                "user": parts[2] if len(parts) > 2 else "",
            }
        )
    return {"available": True, "formulae": formulae, "casks": casks, "services": services}


def collect_npm_global() -> list[dict[str, Any]]:
    if not which("npm"):
        return []
    ok, out, _ = run(["npm", "list", "-g", "--depth=0", "--json"], timeout=25)
    try:
        data = json.loads(out or "{}")
    except json.JSONDecodeError:
        return []
    deps = data.get("dependencies") or {}
    rows = []
    for name, meta in deps.items():
        if not isinstance(meta, dict):
            meta = {}
        rows.append(
            {
                "name": name,
                "version": meta.get("version") or ("link" if meta.get("resolved") or meta.get("link") else "unknown"),
                "link": bool(meta.get("resolved") or meta.get("link")),
            }
        )
    return rows


def collect_pip() -> list[dict[str, str]]:
    ok, out, _ = run(["python3", "-m", "pip", "list", "--format=json"], timeout=25)
    if not ok:
        return []
    try:
        return [{"name": p["name"], "version": p["version"]} for p in json.loads(out or "[]")]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []


def collect_apps() -> list[dict[str, str]]:
    apps: list[dict[str, str]] = []
    home = Path.home()
    dirs = []
    if platform.system() == "Darwin":
        dirs = [Path("/Applications"), home / "Applications"]
    elif platform.system() == "Linux":
        dirs = [
            Path("/usr/share/applications"),
            home / ".local/share/applications",
        ]
    for d in dirs:
        if not d.exists():
            continue
        try:
            for entry in d.iterdir():
                name = entry.name
                if platform.system() == "Darwin":
                    if not name.endswith(".app"):
                        continue
                    apps.append(
                        {
                            "name": name.replace(".app", ""),
                            "path": str(entry),
                            "scope": "user" if str(entry).startswith(str(home)) else "system",
                        }
                    )
                else:
                    if not name.endswith(".desktop"):
                        continue
                    apps.append(
                        {
                            "name": name.replace(".desktop", ""),
                            "path": str(entry),
                            "scope": "user" if str(entry).startswith(str(home)) else "system",
                        }
                    )
        except OSError:
            continue
    apps.sort(key=lambda a: a["name"].lower())
    return apps


def collect_launch_agents() -> list[dict[str, str]]:
    if platform.system() != "Darwin":
        return []
    d = Path.home() / "Library" / "LaunchAgents"
    if not d.exists():
        return []
    return [{"name": p.name, "path": str(p)} for p in sorted(d.glob("*.plist"))]


def build_cloud_plan(ports: list, docker: dict, runtimes: list, brew: dict) -> dict[str, Any]:
    items: list[dict[str, str]] = []
    for c in docker.get("containers") or []:
        if not c.get("running"):
            continue
        items.append(
            {
                "priority": "high",
                "title": f"Docker: {c['name']}",
                "detail": f"{c['image']} · {c.get('ports') or 'no published ports'}",
                "action": "Lift-and-shift with the same image to ECS/Fly/Railway/Cloud Run. Prefer managed Postgres/Redis.",
                "category": "container",
            }
        )

    interesting = {3000, 3001, 5432, 6379, 8080, 8000, 5173, 8501, 27017, 3306}
    by_port: dict[int, dict] = {}
    for p in ports:
        if p.get("address") in ("*", "0.0.0.0", "::") or p["port"] in interesting:
            by_port.setdefault(p["port"], p)
    for p in by_port.values():
        if re.search(r"com\.docke|docker", str(p.get("command", "")), re.I):
            continue
        items.append(
            {
                "priority": "high" if p["port"] == 5432 else "medium",
                "title": f"Port {p['port']} · {p['command']}",
                "detail": f"Listening on {p.get('bind')} (pid {p.get('pid')})",
                "action": p.get("cloudHint", "Review"),
                "category": "port",
            }
        )

    runtime_names = {r["bin"] for r in runtimes}
    if "psql" in runtime_names or any(p["port"] == 5432 for p in ports):
        items.append(
            {
                "priority": "high",
                "title": "Local PostgreSQL dependency",
                "detail": "Postgres is present locally (app and/or Docker).",
                "action": "Move to Neon, Supabase, RDS, or Cloud SQL. Keep connection strings in env vars.",
                "category": "data",
            }
        )
    if any(re.search(r"redis", c.get("image", ""), re.I) and c.get("running") for c in docker.get("containers") or []):
        items.append(
            {
                "priority": "medium",
                "title": "Local Redis",
                "detail": "Redis is running in Docker.",
                "action": "Use Upstash, ElastiCache, or Memorystore in cloud.",
                "category": "data",
            }
        )

    brew_critical = [
        f
        for f in (brew.get("formulae") or [])
        if re.match(r"^(node|python|go|ffmpeg|postgresql|redis|nginx|cloudflared)", f)
    ]
    if brew_critical:
        items.append(
            {
                "priority": "low",
                "title": "Homebrew runtime stack",
                "detail": ", ".join(brew_critical[:12]),
                "action": "Bake these into Dockerfiles or cloud buildpacks — don't rely on this machine's brew cellar.",
                "category": "deps",
            }
        )

    score = min(
        100,
        len([c for c in docker.get("containers") or [] if c.get("running")]) * 18
        + len(by_port) * 8
        + (10 if "docker" in runtime_names else 0),
    )
    if score >= 60:
        summary = "Several local services look cloud-movable soon — Docker workloads first."
    elif score >= 30:
        summary = "Some local services can move; start with databases and published ports."
    else:
        summary = "Light local footprint — still inventory ports before each project deploy."

    return {"score": score, "summary": summary, "items": items}


def collect_all() -> dict[str, Any]:
    host = collect_host()
    ports = collect_ports()
    processes = collect_processes()
    docker = collect_docker()
    runtimes = collect_runtimes()
    brew = collect_brew()
    npm_global = collect_npm_global()
    pip = collect_pip()
    apps = collect_apps()
    launch_agents = collect_launch_agents()
    cloud = build_cloud_plan(ports, docker, runtimes, brew)

    return {
        "collectedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": host,
        "ports": ports,
        "processes": processes,
        "docker": docker,
        "runtimes": runtimes,
        "brew": brew,
        "npmGlobal": npm_global,
        "pip": pip,
        "apps": apps,
        "launchAgents": launch_agents,
        "cloud": cloud,
        "counts": {
            "ports": len(ports),
            "processes": len(processes),
            "dockerRunning": len([c for c in docker.get("containers") or [] if c.get("running")]),
            "dockerTotal": len(docker.get("containers") or []),
            "runtimes": len(runtimes),
            "brewFormulae": len(brew.get("formulae") or []),
            "brewCasks": len(brew.get("casks") or []),
            "npmGlobal": len(npm_global),
            "pip": len(pip),
            "apps": len(apps),
            "launchAgents": len(launch_agents),
            "cloudItems": len(cloud["items"]),
        },
    }
