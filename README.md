# Mac Admin Analytics

Inventory **the computer that runs the app**: ports, Docker, processes, apps, dependencies, public IP, cloud-move checklist.

## Fresh system (fully automated)

```bash
git clone https://github.com/Vaibhavsoni02/mac-admin-port.git
cd mac-admin-port
chmod +x run.sh
./run.sh
```

That creates a venv, installs dependencies, and starts Streamlit on **http://127.0.0.1:8501** / LAN.

Or:

```bash
python3 -m pip install -r requirements.txt
python3 -m streamlit run streamlit_app.py
```

### In the app

1. **Setup checklist** runs automatically (Python, packages, lsof/ps, Docker optional, network, first scan).  
2. Click **Auto-install** / **Install requirements** if anything is missing.  
3. When required checks pass → **Continue to analytics**.  
4. Analytics refresh about every 30s on **this** machine.

No separate agent or tunnel is required when Streamlit runs on the Mac you care about.

## Streamlit Community Cloud

[mac-app-port.streamlit.app](https://mac-app-port.streamlit.app/) inventories **Streamlit’s Linux server**, not your laptop. For Mac analytics, run `./run.sh` on the Mac (or phone on same Wi‑Fi → sidebar LAN URL).

## Optional: JSON agent / tunnel

Only if you need the cloud website to remote-scan a Mac:

```bash
python3 agent.py
cloudflared tunnel --url http://127.0.0.1:4041
```

## What you get

| Area | Source |
|---|---|
| Cloud move | Ports + Docker heuristics |
| Network | Public IP/geo + interfaces + browser UA |
| Ports / Docker / Processes | Live OS scan |
| Dependencies / Apps | brew, npm -g, pip, Applications |
