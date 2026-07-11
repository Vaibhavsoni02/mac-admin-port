"""
Mac Admin Analytics — Streamlit
Open from any browser on this machine or your LAN.
"""

from __future__ import annotations

from datetime import timedelta

import streamlit as st

from admin_core import collect_all, collect_network, primary_lan_ip

st.set_page_config(
    page_title="Mac Admin Analytics",
    page_icon="▣",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
  .block-container { padding-top: 1.2rem; max-width: 1200px; }
  div[data-testid="stMetricValue"] { font-size: 1.55rem; }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=20, show_spinner=False)
def load_snapshot():
    return collect_all()


@st.cache_data(ttl=20, show_spinner=False)
def load_network():
    return collect_network()


def priority_label(p: str) -> str:
    return {"high": "HIGH", "medium": "MEDIUM", "low": "LOW"}.get(p, (p or "").upper())


with st.sidebar:
    st.markdown("### Mac Admin Analytics")
    st.caption("Ports · Docker · deps · network · cloud move plan")
    auto = st.toggle("Auto-refresh (30s)", value=True)
    if st.button("Refresh now", use_container_width=True):
        load_snapshot.clear()
        load_network.clear()
        st.rerun()

    lan = primary_lan_ip()
    st.divider()
    st.markdown("**Open from another device**")
    if lan:
        st.code(f"http://{lan}:8501", language=None)
        st.caption("Same Wi‑Fi/LAN. Host machine must allow inbound TCP 8501.")
    else:
        st.caption("Could not detect LAN IP.")
    st.caption("This computer: http://127.0.0.1:8501")
    st.caption("Node UI still available at http://127.0.0.1:4040 if you prefer.")


@st.fragment(run_every=timedelta(seconds=30) if auto else None)
def dashboard():
    if auto:
        load_snapshot.clear()
        load_network.clear()

    with st.spinner("Scanning this machine…"):
        data = load_snapshot()
        network = load_network()

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
    m1.metric(
        "Memory",
        f"{host.get('memPressurePct')}%",
        f"{host.get('usedMemGb')}/{host.get('totalMemGb')} GB",
    )
    disk = host.get("disk") or {}
    m2.metric(
        "Disk",
        disk.get("capacity") or "—",
        f"{disk.get('used', '')} / {disk.get('size', '')}".strip(" /"),
    )
    m3.metric("Load 1m", str((host.get("load") or ["—"])[0]))
    m4.metric("Ports", counts.get("ports", 0))
    m5.metric("Docker up", counts.get("dockerRunning", 0), f"{counts.get('dockerTotal', 0)} total")
    m6.metric("Cloud score", cloud.get("score", 0), f"{counts.get('cloudItems', 0)} items")

    tab_cloud, tab_net, tab_ports, tab_docker, tab_proc, tab_deps, tab_apps = st.tabs(
        [
            "Cloud move",
            "Network & browser",
            "Ports",
            "Docker",
            "Processes",
            "Dependencies",
            "Apps",
        ]
    )

    with tab_cloud:
        st.subheader("What to move first")
        st.write(cloud.get("summary") or "")
        for item in cloud.get("items") or []:
            with st.container(border=True):
                st.markdown(
                    f"**{priority_label(item.get('priority'))}** — {item.get('title')}"
                )
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
                        "IPv4",
                        "IPv6",
                        "Country",
                        "Region",
                        "City",
                        "ZIP",
                        "Timezone",
                        "ISP",
                        "Organization",
                        "ASN",
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
            st.write(f"**LAN IP of host:** `{network.get('lanIp') or '—'}`")
            st.write(f"**Timezone (lookup):** `{pub.get('timezone') or '—'}`")
            st.markdown("**User-Agent (from your browser)**")
            st.code(ua, language=None)

        st.markdown("#### Local network interfaces")
        ifaces = network.get("localInterfaces") or []
        if ifaces:
            st.dataframe(ifaces, hide_index=True, use_container_width=True)
        else:
            st.caption("No non-loopback interfaces detected.")

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
            st.info("Docker CLI not found on PATH.")
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
            st.markdown("#### Brew services")
            st.dataframe(
                (data.get("brew") or {}).get("services") or [],
                hide_index=True,
                use_container_width=True,
            )
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

    st.divider()
    st.caption(
        "Streamlit host · public IP/geo uses outbound HTTPS · "
        "listening on 0.0.0.0:8501 so any LAN browser can connect."
    )


dashboard()
