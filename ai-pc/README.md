# AI PC · React dashboard and attendance API

This entire folder goes on the **AI PC**. It includes the React source and build, Python API, SQLite storage code, schedules, employee management and audited attendance corrections. The backend must run alongside the dashboard; copying React alone does not provide attendance storage or Pi connectivity.

**Ubuntu AI PC accessible only through SSH?** Use the [Docker + SSH step-by-step guide](DOCKER-SSH.md). It includes Docker installation, private data transfer, terminal-only admin/token setup, persistent storage, updates and the exact Pi service commands. The Windows instructions below are for a non-Docker installation.

## Live attendance notifications

Confirmed kiosk clock-ins and clock-outs show an employee notification at the right of the screen for 3 seconds, including TV fullscreen. A soft bell plays once when each notification appears. Rapid scans queue in order. Opening the dashboard does not replay existing records; duplicate scans and scans awaiting review stay silent.

Bell sound is on by default. Click anywhere in the app once after opening it to let the browser enable audio (entering TV fullscreen also does this). Use **Bell on / Bell off** in the header or live board to mute it; the preference is saved in this browser. The TV/device must also have its audio output enabled.

## Step-by-step: first setup on the AI PC

1. **Download the correct ZIP.** Download [Smart-Attendance-AI-PC.zip](https://github.com/digitalsgisb/facescanpk/raw/refs/heads/main/downloads/Smart-Attendance-AI-PC.zip). Extract it to a permanent location, for example `C:\SmartAttendance\ai-pc`. The folder containing `server.py` is the app folder. The ready-made ZIP includes `dist/`, so you do not need Node.js just to run it.
2. **Open PowerShell in the app folder.** In File Explorer, open that folder and choose Open in Terminal. Alternatively, using the example location:

   ```powershell
   Set-Location -LiteralPath 'C:\SmartAttendance\ai-pc'
   python --version
   python -m pip install -r requirements.txt
   ```

   Use Python 3.10 or newer. If the existing attendance installation uses a particular Python executable or environment, keep using it; replace `python` in these commands with that interpreter.
3. **Choose whether this is a blank installation or a transfer.** For a blank installation continue below. To keep the existing company employees, photos, attendance and device registrations on a replacement PC, follow [private data transfer](#step-by-step-transfer-existing-company-data) **before starting the new service**. Public GitHub downloads intentionally contain no company database.
4. **Start locally for initial setup.** Run:

   ```powershell
   python server.py
   ```

   Leave the terminal open. Open `http://127.0.0.1:8765` in the PC's browser. A new blank installation asks you to create an administrator password of at least 12 characters. A restored installation uses its existing login. First-time administrator creation must happen locally on this PC.
5. **Prepare employee information and schedules.** Add employees/photos in Employees, or check the restored records. In Schedules & roster, assign the normal/day/night hours, OT and team rotation that actually apply. Missing schedules do not erase scans; they cause review flags. A/B are teams, not permanently fixed day/night assignments.
6. **Enable access from the Pi.** Stop the terminal service with Ctrl+C, then restart for company-network access:

   ```powershell
   python server.py --host 0.0.0.0
   ```

   If you already have company HTTPS configured, keep its certificates and use the existing HTTPS launcher instead. The equivalent PowerShell launcher is `./start.ps1 -Lan`; direct Python commands above also work when script execution is restricted. Do not run both launchers at once.
7. **Find the PC address.** Open another PowerShell terminal and run:

   ```powershell
   ipconfig
   ```

   Note the IPv4 address of the active company Ethernet/Wi-Fi adapter. For example, if it is `192.168.1.100`, the Pi uses `http://192.168.1.100:8765`. This is an example, not an address already configured for your company. Use the configured HTTPS address if applicable. Keep the PC address stable through the company's normal network configuration.
8. **Check network reachability.** From the Pi browser, try that PC address. If it cannot open, check the service is still running, the PC/Pi can reach each other and Windows Firewall permits the attendance service/port on the appropriate company private network. The app does not create firewall rules.
9. **Create the Pi token.** In the app open System settings → Add connection → Raspberry Pi attendance kiosk. Copy the token shown once and enter it on the Pi during connection setup. Do not paste it into GitHub, a README or browser source code.
10. **Connect the Pi and HDMI board.** Continue with the [Pi connection guide](../raspberry-pi/README.md#step-by-step-connect-your-existing-pi) and [two-screen guide](../raspberry-pi/README.md#step-by-step-two-screen-setup). Keep the PC service awake and running while attendance is in use. Closing its terminal stops a manually launched service.

## Step-by-step: update the AI PC

1. Download and extract the latest AI PC ZIP into a temporary folder. Do not extract it directly over the running service.
2. Stop the attendance service normally. For a terminal launch, use Ctrl+C in that terminal. For an existing Windows service/startup launcher, use its existing stop procedure. Do not start a second server on the same port.
3. Back up the existing app folder to a separate private location. Preserve all of `runtime/` (database, uploads and any WAL files), `data/employees.json` if present, certificates and local settings. With PowerShell already inside the existing app folder, an example full-folder backup is:

   ```powershell
   $attendanceSource = (Get-Location).Path
   $attendanceBackup = Join-Path (Split-Path -Parent $attendanceSource) ('attendance-pc-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
   Copy-Item -LiteralPath $attendanceSource -Destination $attendanceBackup -Recurse
   ```

   Verify the backup folder exists and contains `runtime/attendance.sqlite3` before proceeding. Keep this backup private.
4. Open the extracted `ai-pc/` folder. Copy its **contents** into the existing app folder (`attendance-app/` in the original installation), replacing matching code files. Do not delete the old app folder. Do not overwrite its database with the separate private restore ZIP during a routine update.
5. In the existing Python environment, run `python -m pip install -r requirements.txt` if dependencies need installing. Restart the service using the same network/TLS options as before; for a manually launched LAN service use `python server.py --host 0.0.0.0`.
6. Refresh the PC dashboard. Check employee counts, photos, schedules and recent attendance are still present. If the browser shows the old design, reload while bypassing its cache.
7. On the Pi, run `python3 configure_kiosk.py --check` from its attendance folder. Then apply any [Pi code update](../raspberry-pi/README.md#step-by-step-update-the-pi) and restart the kiosk. Existing device tokens should keep working when the existing PC database is preserved.
8. Verify one approved test employee's scan reaches the PC and appears on the live board. If the PC update must be rolled back, stop the API first, restore the previous code and retain the current database. Only restore an older database intentionally after accounting for attendance recorded since the backup.

## Step-by-step: transfer existing company data

Use this only for moving/restoring the existing installation. A code update on the same PC does not need this archive.

1. Obtain the separately supplied local `Smart-Attendance-Company-Data-PRIVATE.zip`. It is not on GitHub. Keep it private; it includes employee records, photos, attendance, settings, admin login and registered device-token hashes.
2. Prepare the destination PC's code folder from the AI PC ZIP, but leave its API stopped. If the destination already has data, back up its whole app folder first as described above.
3. Extract the private archive into a temporary private folder. Open its `ai-pc/` subfolder. It contains `runtime/attendance.sqlite3`, `runtime/uploads/` and `data/employees.json`.
4. Copy those `runtime/` and `data/` contents into the destination app folder **while the API is stopped**. Confirm that `server.py` and `runtime/` are now in the same app folder. Replacing an existing destination database is an intentional restore, so keep its backup. Do not combine a snapshot with WAL/SHM files from another database: restore into a clean new app folder when moving PCs, or preserve the old complete `runtime/` separately before restoring into an empty `runtime/`.
5. Start locally with `python server.py` and log in using the existing administrator password. Check the employee count, photos and attendance from the archive. The archive reflects the time it was created; it does not contain later attendance automatically.
6. Stop and restart using the PC's normal LAN/HTTPS settings. If its address changed, run `python3 configure_kiosk.py` on the Pi with the new address and an appropriate kiosk token. Open the new PC address in the Pi's HDMI browser too.
7. Keep the old PC service stopped once the replacement is in use. A transfer should have one active attendance API/database serving the kiosks.

The archive does not contain the Raspberry Pi's face enrollments or offline queue. Preserve those on the Pi during this procedure.

## If you update from Git source instead of the ZIP

1. Stop the relevant attendance program and back up its private data as above.
2. From your repository checkout, run `git pull --ff-only`. If Git reports local source changes/conflicts, preserve and resolve those changes before proceeding; do not discard them just to update.
3. On the AI PC, enter `ai-pc/` and run `npm ci`, then `npm run build`. The source repository does not track `dist/`; every React source update needs a fresh build. Restart the PC API with its existing settings.
4. On the Pi, run the code in `raspberry-pi/` using its existing Python environment. For the first change to a cloned folder, stop the kiosk and privately transfer its existing `database/`, `kiosk-runtime/` and `kiosk.env` there; do not start an empty replacement outbox while old queued scans remain elsewhere.
5. Run the Pi connection check and verify the live board before returning the system to normal use.

## Public repository exclusions

Live database, employee names/IDs/photos, face embeddings, private tokens, certificates, original Node-RED credentials and local preview screenshots are not included. The company logo and generic UI assets are included. `data/employees.json` and `runtime/` are intentionally ignored by Git.
