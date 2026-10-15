# Raspberry Pi · Python kiosk

This folder goes on the **Raspberry Pi**, not the AI PC. It includes `face.py`, camera/inference workers, the complete 800×480 registration keyboard, durable offline delivery and connection setup.

## Update an existing Pi

1. Stop the attendance kiosk using its normal launcher/service. Do not switch launch methods or Python environments during the update.
2. Back up the current installation, especially `database/`, `kiosk-runtime/` and `kiosk.env`.
3. Extract `Smart-Attendance-Pi.zip`. Copy the **contents** of its `raspberry-pi/` folder into the existing Pi attendance folder. Preserve the three local data/configuration folders/files above and any existing logo. No update file replaces them.
4. Use the existing camera/AI Python environment. This update does not require replacing its installed packages.
5. From that folder, run `python3 configure_kiosk.py --check`. If this is the first connection, run `python3 configure_kiosk.py` instead. Enter the AI PC's address and a Raspberry Pi kiosk token created in the app's System settings.
6. Start the kiosk again with `bash run_kiosk.sh` or the existing service pointing to this folder.

The connection check requires the updated PC API to be running. Start/restart the AI PC service first. It checks the kiosk token without recording attendance. Never enter the React admin password as the kiosk token.

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
