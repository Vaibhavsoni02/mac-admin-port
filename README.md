# Mac Admin Analytics

Central admin for the machine running it: listening ports, Docker, processes, apps, dependencies, public IP/network, and a cloud-migration checklist.

Works best on **macOS**; Linux is supported for ports/processes/Docker. Open from **any browser** on the same computer or LAN.

## Streamlit (recommended)

```bash
cd "/Users/fs/Downloads/mac admin analytics"
python3 -m pip install -r requirements.txt
python3 -m streamlit run streamlit_app.py
```

Then open:

| Where | URL |
|---|---|
| This computer | http://127.0.0.1:8501 |
| Phone / other PC (same Wi‑Fi) | `http://<this-machine-LAN-IP>:8501` (shown in the sidebar) |

Streamlit listens on **0.0.0.0:8501** (see `.streamlit/config.toml`).

## Node UI (optional)

```bash
npm start
```

Open http://127.0.0.1:4040 (localhost only).

## Tabs

| Tab | What you get |
|---|---|
| Cloud move | Migration checklist from live ports + Docker |
| Network & browser | Public IPv4/IPv6, geo, ISP, LAN interfaces, browser User-Agent |
| Ports | TCP listen table |
| Docker | Containers and published ports |
| Processes | Top CPU/memory |
| Dependencies | brew / npm -g / pip / runtimes |
| Apps | Installed applications |

## Notes

- Public IP/geo uses outbound HTTPS (`ipwho.is` / fallbacks).
- Binding to `0.0.0.0` means anyone on your LAN can open the dashboard — use only on trusted networks.
- Copy this folder to another Mac, install requirements, run Streamlit the same way.
