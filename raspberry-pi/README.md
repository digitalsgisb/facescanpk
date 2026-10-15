# Raspberry Pi · Python kiosk

This folder goes on the **Raspberry Pi**, not the AI PC. It includes `face.py`, camera/inference workers, the complete 800×480 registration keyboard, durable offline delivery and connection setup.

## Step-by-step: connect your existing Pi

These steps use your already-working Raspberry Pi camera/face-recognition environment. Keep using the same Python environment or virtual environment as the old kiosk.

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

The Pi's DSI touchscreen is 800×480 at (0,0). Python maps there before requesting fullscreen. The HDMI screen at (800,0) displays a browser connected to the PC. Final placement is controlled by the Pi's window manager.

Use the already-working Raspberry Pi environment with Tkinter, Picamera2, OpenCV, NumPy, Pillow, InsightFace and ONNX Runtime. Camera and AI run in separate restartable processes. The setup/check tools use Python's standard library. Preserve the existing face model files as well as face enrollments.
