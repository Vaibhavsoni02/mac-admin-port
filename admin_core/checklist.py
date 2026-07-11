"""Fresh-system readiness checklist + light auto-setup helpers."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent.parent


@dataclass
class CheckItem:
    id: str
    title: str
    required: bool
    ok: bool
    detail: str
    fix: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _run(cmd: list[str], timeout: int = 20) -> tuple[bool, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = ((p.stdout or "") + (p.stderr or "")).strip()
        return p.returncode == 0, out
    except Exception as e:
        return False, str(e)


def ensure_pip_packages(packages: list[str] | None = None) -> tuple[bool, str]:
    """Install requirements into the current interpreter (fresh-system bootstrap)."""
    req = ROOT / "requirements.txt"
    try:
        if packages:
            cmd = [sys.executable, "-m", "pip", "install", "-q", *packages]
        elif req.exists():
            cmd = [sys.executable, "-m", "pip", "install", "-q", "-r", str(req)]
        else:
            cmd = [sys.executable, "-m", "pip", "install", "-q", "streamlit>=1.37.0", "psutil>=5.9.0"]
        ok, out = _run(cmd, timeout=180)
        return ok, out[-2000:] if out else ("installed" if ok else "pip failed")
    except Exception as e:
        return False, str(e)


def detect_streamlit_cloud() -> bool:
    return bool(
        os.environ.get("STREAMLIT_SHARING_MODE")
        or os.path.exists("/home/adminuser")
        or os.path.exists("/mount/src")
        or os.environ.get("HOSTNAME", "").startswith("streamlit")
    )


def run_checklist(auto_install: bool = False) -> dict[str, Any]:
    items: list[CheckItem] = []
    cloud = detect_streamlit_cloud()

    # 1. Python
    py_ok = sys.version_info >= (3, 9)
    items.append(
        CheckItem(
            id="python",
            title="Python 3.9+",
            required=True,
            ok=py_ok,
            detail=f"{platform.python_version()} ({sys.executable})",
            fix="Install Python 3.9+ from python.org or Homebrew (`brew install python`)",
        )
    )

    # 2. Packages
    missing: list[str] = []
    for pkg in ("streamlit", "psutil"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    install_log = ""
    if missing and auto_install:
        ok_i, install_log = ensure_pip_packages(missing)
        if ok_i:
            missing = []
            for pkg in ("streamlit", "psutil"):
                try:
                    __import__(pkg)
                except ImportError:
                    missing.append(pkg)

    items.append(
        CheckItem(
            id="packages",
            title="Python packages (streamlit, psutil)",
            required=True,
            ok=not missing,
            detail=("OK" if not missing else f"Missing: {', '.join(missing)}")
            + (f" · install: {install_log[:200]}" if install_log else ""),
            fix="Click “Auto-install dependencies” or run: python3 -m pip install -r requirements.txt",
        )
    )

    # 3. Host identity / OS
    system = platform.system()
    host = platform.node() or "unknown"
    items.append(
        CheckItem(
            id="host",
            title="Machine identity",
            required=True,
            ok=bool(host),
            detail=f"{host} · {system} {platform.release()} · {platform.machine()}",
            fix="",
        )
    )

    if cloud:
        items.append(
            CheckItem(
                id="cloud_notice",
                title="Execution target",
                required=False,
                ok=True,
                detail="Streamlit Cloud host — analytics will describe THIS cloud server, not your laptop, unless you add AGENT_URL later",
                fix="For your Mac: clone repo, run ./run.sh locally (recommended)",
            )
        )
    else:
        items.append(
            CheckItem(
                id="local_target",
                title="Execution target",
                required=True,
                ok=True,
                detail="App is running ON this computer — scanners will inventory this machine automatically",
                fix="",
            )
        )

    # 4. Port scanner
    has_lsof = bool(shutil.which("lsof"))
    has_ss = bool(shutil.which("ss"))
    port_ok = has_lsof or has_ss
    items.append(
        CheckItem(
            id="ports",
            title="Port scanner (lsof or ss)",
            required=True,
            ok=port_ok,
            detail="lsof ✓" if has_lsof else ("ss ✓" if has_ss else "neither found"),
            fix="macOS includes lsof; on Linux install iproute2 (`ss`)",
        )
    )

    # 5. Process list
    ok_ps, _ = _run(["ps", "-axo", "pid="])
    items.append(
        CheckItem(
            id="processes",
            title="Process list (ps)",
            required=True,
            ok=ok_ps,
            detail="ps available" if ok_ps else "ps failed",
            fix="Install procps (Linux) — macOS has ps built-in",
        )
    )

    # 6. Docker optional
    docker = shutil.which("docker")
    docker_ok = False
    docker_detail = "not installed (optional)"
    if docker:
        ok_d, out_d = _run([docker, "info"], timeout=12)
        docker_ok = ok_d
        docker_detail = "Docker reachable" if ok_d else f"Docker CLI present but daemon not ready: {out_d[:160]}"
    items.append(
        CheckItem(
            id="docker",
            title="Docker (optional)",
            required=False,
            ok=docker_ok or not docker,
            detail=docker_detail if docker else "not installed (optional)",
            fix="Install Docker Desktop and start it for container analytics",
        )
    )

    # 7. Memory/stats
    mem_ok = False
    mem_detail = ""
    try:
        import psutil

        vm = psutil.virtual_memory()
        mem_ok = vm.total > 0
        mem_detail = f"{round(vm.total/1024**3)} GB RAM · {vm.percent}% used"
    except Exception as e:
        mem_detail = str(e)
    items.append(
        CheckItem(
            id="memory",
            title="Memory / CPU stats",
            required=True,
            ok=mem_ok,
            detail=mem_detail,
            fix="Install psutil: python3 -m pip install psutil",
        )
    )

    # 8. Network egress for public IP
    net_ok = False
    net_detail = "skipped"
    try:
        import urllib.request

        with urllib.request.urlopen("https://api.ipify.org?format=json", timeout=8) as r:
            net_ok = r.status == 200
            net_detail = "Public IP lookup reachable"
    except Exception as e:
        net_detail = f"Offline or blocked: {e}"
    items.append(
        CheckItem(
            id="network",
            title="Outbound network (public IP geo)",
            required=False,
            ok=net_ok,
            detail=net_detail,
            fix="Allow HTTPS outbound for ipwho.is / ipify",
        )
    )

    # 9. First snapshot (scanner / “agent” in-process)
    scan_ok = False
    scan_detail = ""
    snapshot: dict[str, Any] | None = None
    network: dict[str, Any] | None = None
    try:
        from admin_core.collect import collect_all
        from admin_core.network import collect_network

        snapshot = collect_all()
        network = collect_network()
        c = snapshot.get("counts") or {}
        scan_ok = bool(snapshot.get("host"))
        scan_detail = (
            f"hostname={snapshot['host'].get('hostname')} · "
            f"ports={c.get('ports', 0)} · docker={c.get('dockerRunning', 0)} · "
            f"apps={c.get('apps', 0)}"
        )
    except Exception as e:
        scan_detail = f"Scan failed: {e}"

    items.append(
        CheckItem(
            id="scanner",
            title="In-process scanner (agent)",
            required=True,
            ok=scan_ok,
            detail=scan_detail,
            fix="Fix failed required checks above, then re-run checklist",
        )
    )

    required = [i for i in items if i.required]
    ready = all(i.ok for i in required)

    return {
        "ready": ready,
        "cloud": cloud,
        "system": system,
        "hostname": host,
        "items": [i.as_dict() for i in items],
        "required_passed": sum(1 for i in required if i.ok),
        "required_total": len(required),
        "optional_passed": sum(1 for i in items if not i.required and i.ok),
        "optional_total": sum(1 for i in items if not i.required),
        "snapshot": snapshot,
        "network": network,
    }
