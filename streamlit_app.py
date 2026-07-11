"""
Mac Admin Analytics — Streamlit

On a fresh system: automated checklist → in-process scanner → analytics.
Run on the machine you want inventoried (recommended):

  ./run.sh
  # or: python3 -m streamlit run streamlit_app.py
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import streamlit as st

from admin_core.checklist import ensure_pip_packages, run_checklist
from admin_core.network import primary_lan_ip

st.set_page_config(
    page_title="Mac Admin Analytics",
    page_icon="▣",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
  .block-container { padding-top: 1.1rem; max-width: 1200px; }
  div[data-testid="stMetricValue"] { font-size: 1.55rem; }
</style>
""",
    unsafe_allow_html=True,
)

if "setup_done" not in st.session_state:
    st.session_state.setup_done = False
if "checklist" not in st.session_state:
    st.session_state.checklist = None
if "auto_ran" not in st.session_state:
    st.session_state.auto_ran = False


def priority_label(p: str) -> str:
    return {"high": "HIGH", "medium": "MEDIUM", "low": "LOW"}.get(p, (p or "").upper())


def render_checklist_page() -> None:
    st.title("Setup checklist")
    st.caption(
        "Everything runs on **this computer** (the one hosting Streamlit). "
        "On a fresh machine the app installs deps, verifies tools, runs the scanner, then unlocks analytics."
    )

    col_a, col_b, col_c = st.columns([1, 1, 1])
    with col_a:
        auto_install = st.checkbox("Auto-install missing pip packages", value=True)
    with col_b:
        if st.button("Run checklist", type="primary", use_container_width=True):
            with st.spinner("Checking this system and running scanner…"):
                st.session_state.checklist = run_checklist(auto_install=auto_install)
                st.session_state.auto_ran = True
    with col_c:
        if st.button("Install requirements.txt", use_container_width=True):
            with st.spinner("pip install -r requirements.txt…"):
                ok, log = ensure_pip_packages()
            if ok:
                st.success("Dependencies installed. Run checklist again.")
            else:
                st.error(log or "pip install failed")

    # First visit: auto-run once
    if not st.session_state.auto_ran:
        with st.spinner("First-run: verifying this system…"):
            st.session_state.checklist = run_checklist(auto_install=True)
            st.session_state.auto_ran = True

    result = st.session_state.checklist
    if not result:
        st.info("Click **Run checklist** to begin.")
        return

    st.progress(
        result["required_passed"] / max(result["required_total"], 1),
        text=f"Required checks: {result['required_passed']} / {result['required_total']}",
    )

    if result["cloud"]:
        st.warning(
            "This session is on **Streamlit Community Cloud**. "
            "Analytics describe the cloud server, not your laptop. "
            "For real Mac analytics, clone the repo and run `./run.sh` on the Mac."
        )

    for item in result["items"]:
        icon = "PASS" if item["ok"] else ("NEED" if item["required"] else "SKIP")
        with st.container(border=True):
            left, right = st.columns([4, 1])
            with left:
                req = "required" if item["required"] else "optional"
                st.markdown(f"**{item['title']}** · `{req}`")
                st.caption(item.get("detail") or "")
                if not item["ok"] and item.get("fix"):
                    st.markdown(f"Fix: {item['fix']}")
            with right:
                if item["ok"]:
                    st.success(icon)
                elif item["required"]:
                    st.error(icon)
                else:
                    st.warning(icon)

    st.divider()
    if result["ready"]:
        st.success(
            f"Ready — scanner inventoried **{result.get('hostname')}**. "
            "Continue to live analytics."
        )
        if st.button("Continue to analytics", type="primary"):
            st.session_state.setup_done = True
            st.rerun()
    else:
        st.error("Required checks failed. Fix the items marked NEED, then run checklist again.")
        if st.button("Skip and show analytics anyway (may be incomplete)"):
            st.session_state.setup_done = True
            st.rerun()


def render_analytics(data: dict[str, Any], network: dict[str, Any]) -> None:
    host = data["host"]
    counts = data["counts"]
    cloud = data["cloud"]
    pub = network.get("public") or {}

    st.title(host.get("hostname") or "Machine Admin")
    meta_bits = [
        f"macOS {host['macos']}" if host.get("macos") else host.get("platform"),
        host.get("cpuModel"),
        f"{host.get('cpuCount')} cores",
        f"{host.get('totalMemGb')} GB RAM",
        host.get("arch"),
    ]
    st.caption(" · ".join(str(x) for x in meta_bits if x))
    st.caption(f"Scanned {data.get('collectedAt')} · public IP source: {pub.get('source') or '—'}")

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Memory", f"{host.get('memPressurePct')}%", f"{host.get('usedMemGb')}/{host.get('totalMemGb')} GB")
    disk = host.get("disk") or {}
    m2.metric("Disk", disk.get("capacity") or "—", f"{disk.get('used', '')} / {disk.get('size', '')}".strip(" /"))
    m3.metric("Load 1m", str((host.get("load") or ["—"])[0]))
    m4.metric("Ports", counts.get("ports", 0))
    m5.metric("Docker up", counts.get("dockerRunning", 0), f"{counts.get('dockerTotal', 0)} total")
    m6.metric("Cloud score", cloud.get("score", 0), f"{counts.get('cloudItems', 0)} items")

    tab_cloud, tab_net, tab_ports, tab_docker, tab_proc, tab_deps, tab_apps = st.tabs(
        ["Cloud move", "Network & browser", "Ports", "Docker", "Processes", "Dependencies", "Apps"]
    )

    with tab_cloud:
        st.subheader("What to move first")
        st.write(cloud.get("summary") or "")
        for item in cloud.get("items") or []:
            with st.container(border=True):
                st.markdown(f"**{priority_label(item.get('priority'))}** — {item.get('title')}")
                st.caption(item.get("detail"))
                st.write(item.get("action"))

    with tab_net:
        if pub.get("error"):
            st.warning(f"Public IP lookup issue: {pub['error']}")
        if pub.get("proxyNote"):
            st.info(pub["proxyNote"])
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### Public IP & location")
            st.dataframe(
                {
                    "Field": [
                        "IPv4", "IPv6", "Country", "Region", "City", "ZIP",
                        "Timezone", "ISP", "Organization", "ASN",
                    ],
                    "Value": [
                        pub.get("ipv4") or "—",
                        pub.get("ipv6") or "—",
                        pub.get("country") or "—",
                        pub.get("region") or "—",
                        pub.get("city") or "—",
                        pub.get("zip") or "—",
                        pub.get("timezone") or "—",
                        pub.get("isp") or "—",
                        pub.get("organization") or "—",
                        " · ".join(x for x in [pub.get("asn"), pub.get("asName")] if x) or "—",
                    ],
                },
                hide_index=True,
                use_container_width=True,
            )
        with c2:
            st.markdown("#### This browser session")
            headers = {}
            try:
                headers = dict(st.context.headers)
            except Exception:
                headers = {}
            ua = headers.get("User-Agent") or headers.get("user-agent") or "—"
            st.write(f"**LAN IP of this host:** `{network.get('lanIp') or primary_lan_ip() or '—'}`")
            st.write(f"**Timezone (lookup):** `{pub.get('timezone') or '—'}`")
            st.markdown("**User-Agent**")
            st.code(ua, language=None)
        st.markdown("#### Local network interfaces")
        ifaces = network.get("localInterfaces") or []
        if ifaces:
            st.dataframe(ifaces, hide_index=True, use_container_width=True)

    with tab_ports:
        st.dataframe(
            [
                {
                    "Port": p["port"],
                    "Bind": p.get("address"),
                    "Process": p.get("command"),
                    "PID": p.get("pid"),
                    "User": p.get("user"),
                    "Cloud note": p.get("cloudHint"),
                }
                for p in data.get("ports") or []
            ],
            hide_index=True,
            use_container_width=True,
        )

    with tab_docker:
        d = data.get("docker") or {}
        if not d.get("available"):
            st.info("Docker CLI not found — optional.")
        else:
            st.dataframe(
                [
                    {
                        "Name": c["name"],
                        "Image": c["image"],
                        "Status": "running" if c.get("running") else "stopped",
                        "Ports": c.get("ports") or "—",
                        "Note": c.get("note"),
                    }
                    for c in d.get("containers") or []
                ],
                hide_index=True,
                use_container_width=True,
            )

    with tab_proc:
        st.dataframe(
            [
                {
                    "CPU %": p["cpu"],
                    "RSS MB": p["rssMb"],
                    "PID": p["pid"],
                    "User": p["user"],
                    "Command": p["command"],
                }
                for p in data.get("processes") or []
            ],
            hide_index=True,
            use_container_width=True,
        )

    with tab_deps:
        st.markdown("#### Runtimes on PATH")
        st.dataframe(data.get("runtimes") or [], hide_index=True, use_container_width=True)
        left, right = st.columns(2)
        with left:
            st.markdown(f"#### Homebrew formulae ({counts.get('brewFormulae', 0)})")
            formulae = (data.get("brew") or {}).get("formulae") or []
            st.write(", ".join(formulae) if formulae else "_None_")
            st.dataframe((data.get("brew") or {}).get("services") or [], hide_index=True, use_container_width=True)
        with right:
            st.markdown(f"#### npm global ({counts.get('npmGlobal', 0)})")
            st.dataframe(data.get("npmGlobal") or [], hide_index=True, use_container_width=True)
            st.markdown(f"#### pip ({counts.get('pip', 0)})")
            st.dataframe(data.get("pip") or [], hide_index=True, use_container_width=True)
        agents = data.get("launchAgents") or []
        if agents:
            st.markdown("#### LaunchAgents")
            st.dataframe(agents, hide_index=True, use_container_width=True)

    with tab_apps:
        st.dataframe(data.get("apps") or [], hide_index=True, use_container_width=True)


with st.sidebar:
    st.markdown("### Mac Admin Analytics")
    st.caption("Fresh system → checklist → analytics on **this** host")
    page = st.radio(
        "View",
        ["Setup checklist", "Analytics"],
        index=0 if not st.session_state.setup_done else 1,
    )
    if st.button("Re-run setup", use_container_width=True):
        st.session_state.setup_done = False
        st.session_state.auto_ran = False
        st.session_state.checklist = None
        st.rerun()

    lan = primary_lan_ip()
    st.divider()
    st.markdown("**Open elsewhere on LAN**")
    if lan:
        st.code(f"http://{lan}:8501", language=None)
    st.caption("Local: http://127.0.0.1:8501")
    st.caption("Fresh Mac: `./run.sh`")


if page == "Setup checklist" or not st.session_state.setup_done:
    if page == "Analytics" and not st.session_state.setup_done:
        st.info("Finish the setup checklist first (or skip from that page).")
    render_checklist_page()
else:

    @st.fragment(run_every=timedelta(seconds=30))
    def live_dashboard() -> None:
        cached = st.session_state.checklist or {}
        # Prefer fresh scan each fragment tick
        try:
            from admin_core.collect import collect_all
            from admin_core.network import collect_network

            with st.spinner("Scanning this machine…"):
                data = collect_all()
                network = collect_network()
        except Exception as e:
            # Fallback to checklist snapshot
            data = cached.get("snapshot")
            network = cached.get("network")
            if not data or not network:
                st.error(f"Scan failed: {e}")
                return
            st.warning(f"Live scan issue ({e}); showing last checklist snapshot.")

        top = st.columns([4, 1])
        with top[1]:
            if st.button("Refresh", use_container_width=True):
                st.rerun()
        render_analytics(data, network)

    live_dashboard()
