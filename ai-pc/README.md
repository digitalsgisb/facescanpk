# AI PC · React dashboard and attendance API

This entire folder goes on the **AI PC**. It includes the React source and build, Python API, SQLite storage code, schedules, employee management and audited attendance corrections. The backend must run alongside the dashboard; copying React alone does not provide attendance storage or Pi connectivity.

**Ubuntu AI PC accessible only through SSH?** Use the [Docker + SSH step-by-step guide](DOCKER-SSH.md). It includes Docker installation, private data transfer, terminal-only admin/token setup, persistent storage, updates and the exact Pi service commands. The Windows instructions below are for a non-Docker installation.

## Live attendance notifications

Confirmed kiosk and dashboard clock-ins and clock-outs show an employee notification at the right of the screen for 3 seconds, including TV fullscreen. A soft bell plays once when each notification appears. Rapid scans queue in order. Opening the dashboard does not replay existing records; duplicate scans and scans awaiting review stay silent.

Bell sound is on by default. Click anywhere in the app once after opening it to let the browser enable audio (entering TV fullscreen also does this). Use **Bell on / Bell off** in the header or live board to mute it; the preference is saved in this browser. The TV/device must also have its audio output enabled.

### Admin clock in / out, including batches

Open **Clock in / out** in the sidebar, or press **Admin controls** on the TV header. The header button leaves fullscreen and opens the admin panel; the TV cards remain view only.

1. Enter the administrator password and press **Unlock admin controls**. This unlock lasts 30 minutes, independently of the persistent login. Use **Lock controls** when finished.
2. Find an employee by name/ID or filter by department and team. Use the green **Clock in** or red **Clock out** button on their row. **Edit attendance** opens the existing correction form.
3. For a batch, tick employee checkboxes or **Select shown**, then press **Clock in selected** or **Clock out selected**. Changing a filter clears the selection. The result lists how many were saved, skipped or need attention.

The server enforces the password unlock on both individual and batch clock endpoints. Kiosk and read-only integration tokens cannot use them. Current-time actions are audited. Batches apply a fixed IN or OUT action, skip people already in that state, and preserve event IDs on retries; they never blindly toggle a selection. Individual stale actions are rejected. Old open sessions needing review still require **Edit attendance** and a correction reason. The kiosk repeat-scan cooldown remains unchanged.

### Larger photos and sharper TV text

**TV fullscreen** now opens **Large photos**: native 190×68 pixel cards with 44×44 photos and 14-pixel names. It rotates through grouped employee pages every 15 seconds. Use **Previous / Next** or **Pause rotation**; opening employee details pauses rotation too. The details popup has a larger portrait. All active employees remain available across the pages.

Use **Compact overview** if you need the full workforce on one screen. Large photos renders text and photos at native CSS sizes. Compact overview automatically scales the board to fit everyone without scrolling and necessarily uses smaller cards; large photos need more than one page on a 1366×768 TV.

A photo of a TV can also show camera focus and screen-pattern interference. App changes cannot recover detail missing from an original photo or compensate for the display scaling its input. Keep the browser zoom at 100% and use the TV panel's actual native output resolution; the existing 1366×768 example is only correct for a panel using that resolution. If it remains blurry, collect the Pi's `wlr-randr` output before changing its display mode.

## Control centre: team shifts and OT

Open **Control centre** from the sidebar. It brings team hours, overtime, schedule templates and links to the other admin tools together.

- **Fixed teams:** choose **Day**, **Night** or **Normal** for each team. The separate **Overtime** switch selects the matching Day + OT or Night + OT hours. The time preview shows exactly what will apply.
- **Automatic A/B swap:** choose A and B's starting shifts, a start date and the number of days between swaps. Each team's OT setting stays with that team when the shifts swap. Team N keeps its own fixed hours.
- Press **Save team working hours** to apply the setup. Until saved, the controls are a preview. **Individual employee defaults** leaves a team's existing personal schedules in use.
- In **Employees → Profile**, changing the Team immediately updates **Working hours today** in the editor. Individual fallback hours are used only when no higher-priority setting applies.
- Use **Working-hour templates** to edit exact start/end times, or **Date override** for an employee/team exception.

Schedule priority is: employee date override → team date override → A/B rotation → team default → individual fallback. Team OT affects rotation/default hours; explicit date overrides retain their chosen schedule. Existing attendance sessions keep their saved planned times.

The workspace stays white with black animated headers and flat green/red attendance cards. **Compact overview** automatically scales the full workforce into its screen area without scrolling. **Large photos** keeps readable native-size cards on rotating pages.

## Stay signed in

Login sessions have no server-side expiry and survive API/container restarts until you press Log out. Valid sessions from the previous eight-hour setup are upgraded automatically. If your old browser cookie already expired, sign in once after updating.

The browser stores a persistent HttpOnly cookie for 400 days and renews it on authenticated API requests. Browser cookie limits, clearing site data, private-browsing cleanup, or changing browsers can still require another login. Log out deletes the server session and clears its cookie immediately.

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

For the Ubuntu Docker installation, use [these SSH pull/rebuild commands](DOCKER-SSH.md#10-update-later). Docker builds React inside the image; a restart alone does not apply new source code. For the Pi, use its [Git update commands](../raspberry-pi/README.md#git-pull-update--existing-pi-installation).

### Git pull update — native Python installation

These commands assume the live installation is `ai-pc/` inside an existing Git checkout. If you installed from a ZIP, use the ZIP update steps above instead. Stop the existing Python server/service first and make a private backup of `runtime/` and `data/` as described above. Keep the same Python environment and LAN/HTTPS settings.

On **Windows PowerShell**, replace the example checkout path if needed. Run each command only after the previous one succeeds:

```powershell
Set-Location -LiteralPath 'C:\SmartAttendance\facescanpk'
git status --short
git pull --ff-only origin main
Set-Location ai-pc
python -m pip install -r requirements.txt
npm ci
npm run build
python server.py --host 0.0.0.0
```

On **Linux**, after stopping and backing up the native service, this block stops at the first failed command:

```bash
(
set -e
cd ~/facescanpk
git status --short
git pull --ff-only origin main
cd ai-pc
python3 -m pip install -r requirements.txt
npm ci
npm run build
python3 server.py --host 0.0.0.0
)
```

Use your existing service launcher instead of the final `python server.py` command if the API normally runs as a service. Retain existing certificate arguments for HTTPS. The native examples use port **8765**; verify `http://127.0.0.1:8765/api/health` and refresh the Pi's HDMI browser after the restart. The repository does not track `dist/`, so every React update needs a build.

To upload AI PC source changes, follow the repository's [Git push commands](../README.md#push-code-changes-to-github), staging only the intended `ai-pc/` files.

## Public repository exclusions

Live database, employee names/IDs/photos, face embeddings, private tokens, certificates, original Node-RED credentials and local preview screenshots are not included. The company logo and generic UI assets are included. `data/employees.json` and `runtime/` are intentionally ignored by Git.
