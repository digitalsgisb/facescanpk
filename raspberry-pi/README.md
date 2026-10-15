# Raspberry Pi · Python kiosk

This folder goes on the **Raspberry Pi**, not the AI PC. It includes `face.py`, camera/inference workers, the complete 800×480 registration keyboard, durable offline delivery and connection setup.

## Step-by-step: connect your existing Pi

These steps use your already-working Raspberry Pi camera/face-recognition environment. Keep using the same Python environment or virtual environment as the old kiosk.

For the Ubuntu Docker installation use **port 3800** in the address, for example `http://192.168.1.100:3800`. The native Python service examples below use its default port 8765. Always use the port actually published on the AI PC.

1. **Prepare the PC first.** Follow the [AI PC setup guide](../ai-pc/README.md#step-by-step-first-setup-on-the-ai-pc). Leave its attendance service running and note its LAN IPv4 address. `192.168.1.100` below is only an example; replace it with your PC's real address.
2. **Download the Pi package.** Download [Smart-Attendance-Pi.zip](https://github.com/digitalsgisb/facescanpk/raw/refs/heads/main/downloads/Smart-Attendance-Pi.zip) onto the Pi and extract it using File Manager.
3. **Stop the old Python kiosk.** If it was started in a terminal, stop that process normally. If it runs through an existing service/autostart entry, stop that launcher first so it cannot restart during the copy. Do not change unrelated Pi services.
4. **Back up the existing attendance folder.** Copy it to a separate private backup location, preserving `database/`, `kiosk-runtime/`, `kiosk.env` if present, and existing face model files. Do not delete the original folder.
5. **Copy the code.** Open the extracted `raspberry-pi/` folder and copy its **contents** into the existing attendance folder, replacing matching code files. `face.py`, `kiosk_config.py`, `kiosk_keyboard.py`, `kiosk_transport.py`, `kiosk_vision.py`, `configure_kiosk.py`, `run_kiosk.sh` and `1.png` must be together. Keep the existing `database/` folder beside `face.py`; do not put another `raspberry-pi/` folder inside the old installation by mistake.
6. **Create a device token on the PC.** Open the app → System settings → Add connection → Raspberry Pi attendance kiosk. Copy the token shown once. This is a device token, not the administrator password.
7. **Open a Pi terminal in the attendance folder.** Activate the same Python environment used by the existing kiosk, if applicable. Run:

   ```bash
   python3 configure_kiosk.py
   ```

8. **Enter the connection details when prompted.** Enter the PC service base address, for example `http://192.168.1.100:8765`, or the company's configured HTTPS address. Paste the device token at the hidden token prompt and press Enter. The tool checks the address and kiosk scope before saving `kiosk.env`; it does not record an attendance scan.
9. **Verify the saved connection.** Run:

   ```bash
   python3 configure_kiosk.py --check
   ```

   Continue when it reports `Connected successfully` and the expected active employee count. A fresh installation without company data reports zero; add employees on the PC or restore the private company-data archive there first.
10. **Start Python on the touchscreen.** Run:

    ```bash
    bash run_kiosk.sh
    ```

    Leave this terminal/process running. If you already have a service, restart that service using its existing Python environment and the updated attendance folder instead of starting a second copy.
11. **Verify face enrollment.** Existing enrollments remain in `database/`. For a new employee, add their profile on the PC first, allow the kiosk employee list to sync, then use registration on the Pi. Enter the matching employee ID, look at the camera and save when capture is available. A profile photograph in React is not a face enrollment.
12. **Check one supervised scan.** Verify that Python receives a confirmed result and the PC board updates for the same employee. Do not deliberately clock in/out real employees merely to test; use an approved test employee. Disable the old Node-RED attendance scan flow after the replacement has been validated, to avoid recording through both systems.

## Step-by-step: update the Pi

1. Update/restart the [AI PC package](../ai-pc/README.md#step-by-step-update-the-ai-pc) first.
2. Stop the Pi kiosk. If it has pending offline scans, preserve the outbox; do not clear it to apply an update.
3. Make a private copy of the existing attendance folder outside that folder. This includes `database/`, `kiosk-runtime/` and `kiosk.env`.
4. Download and extract the latest Pi ZIP. Copy only the extracted `raspberry-pi/` **contents** over the existing attendance folder. Replace code files when asked. Keep your existing configuration, face enrollments, queued scans and Python environment.
5. In the attendance folder, run `python3 configure_kiosk.py --check`. Do not create a new token if the existing connection still works. If the PC address/token changed, run `python3 configure_kiosk.py` to update them.
6. Start the kiosk with `bash run_kiosk.sh` or restart its existing service. Confirm that the camera appears on the touchscreen and connectivity reports online. Queued scans retry automatically.
7. If the update fails, stop the kiosk and restore the previous **code files** from the backup first. Retain the newest outbox and face enrollment data; restoring an older outbox can replay or lose scan-delivery state. Keep the failed installation for troubleshooting.

## Step-by-step: two-screen setup

1. Keep **DSI-1** at **800×480**, position **0,0**, scale **1**. This is the Python touchscreen.
2. Keep **HDMI-A-2** at **1366×768**, position **800,0**, scale **1**. This is the attendance board screen. These match the supplied `wlr-randr` output; no resolution change is required.
3. Start Python as above. It maps an 800×480 window at (0,0), then requests fullscreen. Confirm its registration keyboard is fully visible on DSI. Monitor placement ultimately depends on the Pi's window manager.
4. Open the Pi's browser and enter the **PC's LAN address**, for example `http://192.168.1.100:8765`. Do not use `127.0.0.1` on the Pi: that points back to the Pi itself.
5. Move the browser window onto HDMI **before** entering fullscreen. Sign into the attendance app, open Live board, then select TV fullscreen. If browser chrome still occupies space, use the browser's own fullscreen control while that window is on HDMI.
6. Check that all 173 employees fit when the supplied company data is loaded. The count follows your actual active employees; the public code-only installation starts empty. Python remains on DSI while the browser board occupies HDMI.

## If the connection check fails

| Message or symptom | Check |
| --- | --- |
| Cannot reach the AI PC | PC service is running; correct PC IPv4/port; same reachable network; private-network firewall; trusted HTTPS certificate if used |
| Kiosk token required / connection refused | Use the token for a Raspberry Pi kiosk, not the login password or a read-only production token; restart the updated PC service |
| Connected, but zero employees | Add employees in the PC app or intentionally restore company data on the PC |
| Face not recognised after copying code | Preserve the original `database/` enrollments and existing model/environment; check that they are beside the running `face.py` |
| Python or browser is on the wrong display | Confirm the supplied screen positions and move the browser to HDMI before fullscreen; check the Pi compositor's placement |

## Files that stay only on the Pi

| File/folder | Purpose |
| --- | --- |
| `kiosk.env` | PC address and private device token |
| `database/*.npy` | Existing face enrollments; not profile photos |
| `kiosk-runtime/outbox.sqlite3` | Queued scans, retry state and confirmations |
| `kiosk-runtime/employees-cache.json` | Offline employee cache |

These are excluded from GitHub and the update ZIP. Do not delete the offline outbox during an update. An employee must exist in the PC app before registering their face on the Pi.

## Screen and dependencies

### Current setup: launch from the touchscreen terminal

The default kiosk uses **800x480 fullscreen** on the touchscreen. Launch from a terminal on the touchscreen: it first maps a small managed window, then requests fullscreen after mapping. STOP / MENU and a larger 84px logo share a reserved bottom footer. Touch handling and camera shutdown cleanup remain enabled. Keep the service stopped for this manual workflow.

```bash
sudo systemctl stop attendance-kiosk
cd /home/wblsugihara
KIOSK_DEBUG_TOUCH=1 python3 -u face.py
```

Use physical touch to test STOP, registration fields, keyboard and Cancel. Fullscreen placement still depends on Wayfire and needs physical verification. If it returns to the wrong display, `KIOSK_FULLSCREEN=0 python3 face.py` restores the working 780x400 managed window. The older automatic two-screen instructions below are optional and are not part of the current manual touchscreen setup.

### Pin the kiosk to DSI-1 under Wayfire

Python's geometry/fullscreen request cannot guarantee an output under Wayfire. Run this once as the desktop user (not with sudo), from the installed kiosk folder:

```bash
cd /home/wblsugihara
python3 configure_display.py --output DSI-1
python3 configure_display.py --output DSI-1 --apply
```

The first command previews; the second backs up `~/.config/wayfire.ini` and adds a window rule for **Smart Attendance Kiosk**. It preserves touch mappings, other rules and existing plugins. It reads Raspberry Pi OS plugin defaults from `/etc/wayfire/defaults.ini`. If your desktop uses another config file, pass `--config /actual/path/wayfire.ini`. Unknown plugin lists remain inherited; a warning explains that the rule requires the `window-rules` plugin.

Stop the service before a manual test, then launch `python3 -u face.py` from the Pi desktop terminal. Verify the kiosk stays on DSI-1 even when launched from a terminal on HDMI, and compare a VNC mouse click with a physical STOP tap. A rule being saved is not proof the compositor honored it. Some older Raspberry Pi Wayfire builds have a [reported output-placement bug](https://github.com/WayfireWM/wayfire/issues/2387). If the kiosk still opens on HDMI, report `dpkg-query -W wayfire` and the current `[window-rules]` / `[core]` sections before changing more desktop settings.

The old `force_kiosk_fullscreen.sh` service helper also moves this window; test manually first to isolate it. To undo the configuration change, restore the timestamped `wayfire.ini.attendance-*.bak` backup created by the setup command.

The Pi's DSI touchscreen is 800×480 at (0,0). Launch the fullscreen kiosk from its terminal. HDMI browser placement is independent. Final window placement is controlled by the Pi's window manager.

Use the already-working Raspberry Pi environment with Tkinter, Picamera2, OpenCV, NumPy, Pillow, InsightFace and ONNX Runtime. Camera and AI run in separate restartable processes. The setup/check tools use Python's standard library. Preserve the existing face model files as well as face enrollments.

The service starts in scanning mode. **STOP / MENU** pauses recognition and returns to the main menu; it does not exit Python or stop the systemd service. Escape also returns to the menu. The control has a reserved touch area separate from the status text and logo. Tapping it writes `[UI] Menu requested ...` to the service journal, which helps distinguish a missed input from a navigation error. To close the service completely over SSH use `sudo systemctl stop attendance-kiosk`.

### Touchscreen buttons do not respond

Kiosk buttons handle a press followed by a release inside the button without requiring a preceding mouse-hover event. Disabled buttons and releases outside the button do not invoke the action; mouse and keyboard access remain available. STOP and the company logo occupy a reserved bottom footer.

For a manual diagnostic run, keep the service stopped and run `KIOSK_DEBUG_TOUCH=1 python3 -u face.py`. Tap STOP physically. `[TOUCH] press/release` lines report widget class and coordinates without recording entry contents; a successful STOP also logs `[UI] Menu requested`. No `[TOUCH]` lines means Tk received no matching pointer events, so a button callback change alone cannot fix it. Press/release on another widget or unexpected coordinates points to window/input mapping. Window placement and physical input still require verification on the Pi.

### Camera says Device or resource busy

Stop the service and close all manual kiosk runs before starting one instance. `sudo fuser -v /dev/video* /dev/media*` identifies current holders. Inspect a Python PID with `ps -p PID -o pid,ppid,args`; stop only the identified old attendance worker with `kill -TERM PID`, using `kill -KILL PID` only if that same worker remains stuck. Do not kill all Python processes, PipeWire or WirePlumber indiscriminately.

Ctrl+C, the window close button and SIGTERM now run worker cleanup. The camera gets a stop request and an opportunity to close before forced termination; stuck native workers still have a bounded termination fallback. Camera acquisition failures are reported without repeated constructor tracebacks and retry every 10 seconds. These changes cannot release a camera already held by another running process, and SIGKILL bypasses Python cleanup.
