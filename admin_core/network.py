"""Public IP / geo and local interface collectors."""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any


def _fetch_json(url: str, timeout: float = 8.0) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "mac-admin-analytics-streamlit/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def local_interfaces() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        import psutil

        for name, addrs in psutil.net_if_addrs().items():
            for a in addrs:
                family = str(a.family).replace("AddressFamily.", "")
                if "AF_INET" not in family and "AF_PACKET" not in family and "AF_LINK" not in family:
                    # Keep IPv4 / IPv6
                    if a.family not in (socket.AF_INET, socket.AF_INET6):
                        continue
                if a.family not in (socket.AF_INET, socket.AF_INET6):
                    continue
                addr = a.address
                if not addr or addr.startswith("127.") or addr == "::1":
                    continue
                rows.append(
                    {
                        "iface": name,
                        "family": "IPv4" if a.family == socket.AF_INET else "IPv6",
                        "address": addr.split("%")[0],
                        "mac": "—",
                        "cidr": a.netmask or "—",
                    }
                )
    except Exception:
        # Fallback: hostname resolution is weak; still return empty gracefully
        pass

    # Always try socket.getaddrinfo for primary LAN guess
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan = s.getsockname()[0]
        s.close()
        if lan and not any(r["address"] == lan for r in rows):
            rows.insert(0, {"iface": "primary", "family": "IPv4", "address": lan, "mac": "—", "cidr": "—"})
    except OSError:
        pass

    rows.sort(key=lambda r: (r["iface"], r["family"]))
    return rows


def primary_lan_ip() -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def _public_ip_geo() -> dict[str, Any]:
    try:
        j = _fetch_json("https://ipwho.is/")
        if j.get("success") is False:
            raise RuntimeError(j.get("message") or "ipwho failed")
        ip = j.get("ip")
        return {
            "source": "ipwho.is",
            "ipv4": ip if ip and ":" not in ip else j.get("ipv4"),
            "ipv6": ip if ip and ":" in ip else j.get("ipv6"),
            "ip": ip,
            "country": j.get("country"),
            "countryCode": j.get("country_code"),
            "region": j.get("region"),
            "city": j.get("city"),
            "zip": j.get("postal"),
            "timezone": (j.get("timezone") or {}).get("id") if isinstance(j.get("timezone"), dict) else j.get("timezone"),
            "isp": (j.get("connection") or {}).get("isp") or j.get("isp"),
            "org": (j.get("connection") or {}).get("org") or j.get("org"),
            "asn": f"AS{(j.get('connection') or {}).get('asn')}" if (j.get("connection") or {}).get("asn") else j.get("asn"),
            "asName": (j.get("connection") or {}).get("org"),
            "lat": j.get("latitude"),
            "lon": j.get("longitude"),
        }
    except Exception as primary_err:
        try:
            j = _fetch_json("https://ipapi.co/json/")
            ip = j.get("ip")
            return {
                "source": "ipapi.co",
                "ipv4": ip if ip and ":" not in str(ip) else None,
                "ipv6": ip if ip and ":" in str(ip) else None,
                "ip": ip,
                "country": j.get("country_name"),
                "countryCode": j.get("country_code"),
                "region": j.get("region"),
                "city": j.get("city"),
                "zip": j.get("postal"),
                "timezone": j.get("timezone"),
                "isp": j.get("org"),
                "org": j.get("org"),
                "asn": j.get("asn"),
                "asName": j.get("org"),
                "lat": j.get("latitude"),
                "lon": j.get("longitude"),
                "note": f"fallback after {primary_err}",
            }
        except Exception as secondary_err:
            return {
                "source": None,
                "error": f"{primary_err}; {secondary_err}",
                "ipv4": None,
                "ipv6": None,
                "ip": None,
            }


def _dual_stack() -> dict[str, str | None]:
    out: dict[str, str | None] = {"ipv4": None, "ipv6": None}
    try:
        j = _fetch_json("https://api.ipify.org?format=json")
        out["ipv4"] = j.get("ip")
    except Exception:
        pass
    try:
        j = _fetch_json("https://api64.ipify.org?format=json")
        ip = j.get("ip")
        if ip and ":" in ip:
            out["ipv6"] = ip
        elif ip and not out["ipv4"]:
            out["ipv4"] = ip
    except Exception:
        pass
    return out


def collect_network() -> dict[str, Any]:
    geo = _public_ip_geo()
    dual = _dual_stack()
    ifaces = local_interfaces()

    ipv4 = dual.get("ipv4") or geo.get("ipv4")
    ipv6 = dual.get("ipv6") or geo.get("ipv6")
    if geo.get("ip") and ":" not in str(geo["ip"]) and not ipv4:
        ipv4 = geo["ip"]
    if geo.get("ip") and ":" in str(geo["ip"]) and not ipv6:
        ipv6 = geo["ip"]

    isp_blob = f"{geo.get('isp') or ''} {geo.get('org') or ''}"
    proxy_note = None
    if any(x in isp_blob.lower() for x in ("prefetch", "proxy")) and any(
        x in isp_blob.lower() for x in ("google", "cloudflare", "privacy")
    ):
        proxy_note = (
            "ISP looks like a browser privacy/prefetch proxy — public IP may not be your home ISP."
        )

    return {
        "collectedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hostname": socket.gethostname(),
        "lanIp": primary_lan_ip(),
        "public": {
            "ipv4": ipv4,
            "ipv6": ipv6,
            "country": geo.get("country"),
            "countryCode": geo.get("countryCode"),
            "region": geo.get("region"),
            "city": geo.get("city"),
            "zip": geo.get("zip"),
            "timezone": geo.get("timezone"),
            "isp": geo.get("isp"),
            "organization": geo.get("org"),
            "asn": geo.get("asn"),
            "asName": geo.get("asName"),
            "lat": geo.get("lat"),
            "lon": geo.get("lon"),
            "source": geo.get("source"),
            "error": geo.get("error"),
            "proxyNote": proxy_note,
        },
        "localInterfaces": ifaces,
    }
