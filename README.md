# Digital Attendance · Port Klang

Two device packages, one attendance system. The Raspberry Pi handles the camera, face matching and touchscreen. The AI PC runs the React dashboard and its Python/SQLite API. The Pi's HDMI browser displays the board served by the PC.

## Start here: step-by-step instructions

Choose the instructions for what you are doing:

- **Ubuntu / SSH / Docker AI PC:** use [Docker setup over SSH](ai-pc/DOCKER-SSH.md). A desktop/browser on the AI PC is not required.
- The Docker installation publishes **port 3800** on the AI PC (mapped to internal container port 8765). Use `http://AI_PC_IP:3800` from the Pi. Native Python installation commands below retain their default port 8765.

1. **First connection / setting up the AI PC:** follow [AI PC setup](ai-pc/README.md#step-by-step-first-setup-on-the-ai-pc), then [Pi connection](raspberry-pi/README.md#step-by-step-connect-your-existing-pi).
2. **Updating an existing installation:** follow [AI PC update](ai-pc/README.md#step-by-step-update-the-ai-pc), then [Pi update](raspberry-pi/README.md#step-by-step-update-the-pi). Update the PC first so the Pi can check the new API.
3. **Putting the board on the HDMI screen:** follow [two-screen setup](raspberry-pi/README.md#step-by-step-two-screen-setup).
4. **Moving existing employees and attendance to a different PC:** follow [private data transfer](ai-pc/README.md#step-by-step-transfer-existing-company-data). This replaces the destination database intentionally; it is not a normal code update.

The folder names describe the destination device. The `ai-pc/` folder includes a Python server as well as React: the Pi sends scans to that server, and the browser reads attendance from it.

| Folder | Install on | Contains |
| --- | --- | --- |
| [`raspberry-pi/`](raspberry-pi/) | Raspberry Pi | Python kiosk, registration keyboard, connection setup and durable scan delivery |
| [`ai-pc/`](ai-pc/) | AI PC | React dashboard **and** the Python API/database service |
| [`downloads/`](downloads/) | Download to the matching device | Separate ready-to-copy ZIPs |

## Download and update

- [Raspberry Pi code ZIP](https://github.com/digitalsgisb/facescanpk/raw/refs/heads/main/downloads/Smart-Attendance-Pi.zip)
- [AI PC code ZIP](https://github.com/digitalsgisb/facescanpk/raw/refs/heads/main/downloads/Smart-Attendance-AI-PC.zip)

Extract the matching ZIP and copy its folder contents over the existing installation **after stopping that device's attendance program**. Updates contain code only and do not include or delete the device's existing data folders. Do not delete the old installation folder to apply an update. See each folder's README for the complete steps.

Company data is deliberately excluded from this public repository. The local `Smart-Attendance-Company-Data-PRIVATE.zip` supplied separately is a private transfer/restore archive, not an update ZIP. It contains employee records/photos and a consistent copy of the live PC database. Keep it off GitHub. An installation without company data starts with an empty employee list.

## Raspberry Pi

Use the Pi's existing Python environment and preserve its `database/` face enrollments, `kiosk.env` connection settings and `kiosk-runtime/` offline scan queue. From the Pi installation folder:

```bash
python3 configure_kiosk.py --check
bash run_kiosk.sh
```

For the first connection, use `python3 configure_kiosk.py` and enter the PC service address and a **kiosk** token created in System settings. Tokens are entered privately and saved locally. Employee IDs come from the PC; face enrollment remains local to the Pi.

## AI PC

The ready-to-copy ZIP includes the compiled React dashboard. Install Python 3.10+ and run from `ai-pc/`:

```powershell
python -m pip install -r requirements.txt
.\start.ps1
```

Open `http://127.0.0.1:8765` on the PC for first-time administrator setup. For company-network access use `./start.ps1 -Lan`, or the existing trusted HTTPS setup. Configure a fixed PC address and the company's private-network firewall rules normally. Keep the PC running during attendance operation.

Source builds additionally need Node.js compatible with the included Vite version:

```powershell
npm ci
npm run build
```

## Displays

- DSI-1: Python touchscreen, **800×480**, desktop position **0,0**.
- HDMI-A-2: browser attendance board, **1366×768**, position **800,0**.

On the Pi browser use the **PC's LAN address**, move it to HDMI, then choose Live board → TV fullscreen. `127.0.0.1` on the Pi refers to the Pi, not the PC. The board groups departments/production lines with A/B/N strips, uniform employee cards and confirmed IN/OUT states. Unassigned teams remain marked with a dash until configured.

## Development checks and packages

```bash
python -m unittest discover -s ai-pc -p test_server.py -v
python -m unittest discover -s raspberry-pi -p test_kiosk_transport.py -v
python -m unittest discover -s raspberry-pi -p test_kiosk_keyboard.py -v
python tools/package.py
```

Keyboard checks require Tk and a desktop display. Camera/inference recovery and monitor placement still need testing on the actual Raspberry Pi. Package generation requires `ai-pc/dist/index.html`; run the React build first after changing its source. Never add employee photos, biometric embeddings, attendance databases, tokens or the old Node-RED export to this public repository.
