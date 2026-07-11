import os from "node:os";
import { networkInterfaces } from "node:os";

async function fetchJson(url, timeoutMs = 8000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      signal: ctrl.signal,
      headers: { Accept: "application/json", "User-Agent": "mac-admin-analytics/1.0" },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(t);
  }
}

function localInterfaces() {
  const nets = networkInterfaces();
  const rows = [];
  for (const [name, list] of Object.entries(nets)) {
    for (const n of list || []) {
      if (n.internal) continue;
      rows.push({
        iface: name,
        family: n.family,
        address: n.address,
        mac: n.mac,
        cidr: n.cidr || null,
      });
    }
  }
  rows.sort((a, b) => a.iface.localeCompare(b.iface) || String(a.family).localeCompare(String(b.family)));
  return rows;
}

async function publicIpGeo() {
  // Prefer ipwho.is — returns v4/v6 + geo + ISP without an API key
  try {
    const j = await fetchJson("https://ipwho.is/");
    if (j?.success === false) throw new Error(j.message || "ipwho failed");
    return {
      source: "ipwho.is",
      ipv4: j.type === "IPv4" ? j.ip : j.ipv4 || (j.ip?.includes(":") ? null : j.ip) || null,
      ipv6: j.type === "IPv6" ? j.ip : j.ipv6 || (j.ip?.includes(":") ? j.ip : null) || null,
      ip: j.ip || null,
      country: j.country || null,
      countryCode: j.country_code || null,
      region: j.region || null,
      city: j.city || null,
      zip: j.postal || null,
      timezone: j.timezone?.id || j.timezone || null,
      isp: j.connection?.isp || j.isp || null,
      org: j.connection?.org || j.org || null,
      asn: j.connection?.asn ? `AS${j.connection.asn}` : j.asn || null,
      asName: j.connection?.org || null,
      lat: j.latitude ?? null,
      lon: j.longitude ?? null,
    };
  } catch (primaryErr) {
    try {
      const j = await fetchJson("https://ipapi.co/json/");
      return {
        source: "ipapi.co",
        ipv4: j.ip && !String(j.ip).includes(":") ? j.ip : null,
        ipv6: j.ip && String(j.ip).includes(":") ? j.ip : null,
        ip: j.ip || null,
        country: j.country_name || null,
        countryCode: j.country_code || null,
        region: j.region || null,
        city: j.city || null,
        zip: j.postal || null,
        timezone: j.timezone || null,
        isp: j.org || null,
        org: j.org || null,
        asn: j.asn || null,
        asName: j.org || null,
        lat: j.latitude ?? null,
        lon: j.longitude ?? null,
        note: `fallback after ${primaryErr.message}`,
      };
    } catch (secondaryErr) {
      return {
        source: null,
        error: `${primaryErr.message}; ${secondaryErr.message}`,
        ipv4: null,
        ipv6: null,
        ip: null,
      };
    }
  }
}

async function dualStackIps() {
  const out = { ipv4: null, ipv6: null };
  try {
    const res = await fetch("https://api.ipify.org?format=json");
    const j = await res.json();
    out.ipv4 = j.ip ? String(j.ip) : null;
  } catch {
    /* ignore */
  }
  try {
    const res = await fetch("https://api64.ipify.org?format=json");
    const j = await res.json();
    const ip = j.ip ? String(j.ip) : null;
    if (ip && ip.includes(":")) out.ipv6 = ip;
    else if (ip && !out.ipv4) out.ipv4 = ip;
  } catch {
    /* ignore */
  }
  return out;
}

export async function collectNetwork() {
  const [geo, dual, ifaces] = await Promise.all([publicIpGeo(), dualStackIps(), Promise.resolve(localInterfaces())]);

  const ipv4 = dual.ipv4 || geo.ipv4 || (geo.ip && !String(geo.ip).includes(":") ? geo.ip : null);
  const ipv6 = dual.ipv6 || geo.ipv6 || (geo.ip && String(geo.ip).includes(":") ? geo.ip : null);

  let proxyNote = null;
  const ispBlob = `${geo.isp || ""} ${geo.org || ""}`;
  if (/prefetch|google llc|cloudflare|privacy/i.test(ispBlob) && /proxy|prefetch|cloudflare/i.test(ispBlob)) {
    proxyNote =
      "ISP looks like a browser privacy/prefetch proxy — public IP may not be your home ISP. Compare with a normal browser tab if needed.";
  }

  return {
    collectedAt: new Date().toISOString(),
    hostname: os.hostname(),
    public: {
      ipv4,
      ipv6,
      country: geo.country,
      countryCode: geo.countryCode,
      region: geo.region,
      city: geo.city,
      zip: geo.zip,
      timezone: geo.timezone,
      isp: geo.isp,
      organization: geo.org,
      asn: geo.asn,
      asName: geo.asName,
      lat: geo.lat,
      lon: geo.lon,
      source: geo.source,
      error: geo.error || null,
      proxyNote,
    },
    localInterfaces: ifaces,
  };
}
