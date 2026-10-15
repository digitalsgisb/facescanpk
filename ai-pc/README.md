# AI PC · React dashboard and attendance API

This entire folder goes on the **AI PC**. It includes the React source and build, Python API, SQLite storage code, schedules, employee management and audited attendance corrections. The backend must run alongside the dashboard; copying React alone does not provide attendance storage or Pi connectivity.

## Update an existing PC

1. Stop the attendance service normally.
2. Back up the existing installation. At minimum preserve **all of `runtime/`**, including `attendance.sqlite3`, its WAL files if present and `uploads/`. Preserve private `data/employees.json` if present.
3. Extract `Smart-Attendance-AI-PC.zip`. Copy the **contents** of `ai-pc/` over the existing app directory (`attendance-app/` in the original installation). Do not delete the old directory first. The update contains no `runtime/` folder or private employee seed.
4. Run `python -m pip install -r requirements.txt` in the same environment if required, then restart with the existing service or `./start.ps1 -Lan`.
5. Refresh the dashboard. Run `python3 configure_kiosk.py --check` on the Pi to verify the updated API connection.

The ZIP contains `dist/`, so Node.js is not needed to deploy that ZIP. The source checkout omits compiled files; build it using `npm ci` followed by `npm run build` before starting, or let `start.ps1` build when `dist/` is missing. Rebuild after changing React source; an existing `dist/` is not rebuilt automatically by the launcher.

## First installation / moving to another PC

Install Python 3.10+ and the dependencies in `requirements.txt`. Without company data, the API starts with an empty employee list using `data/employees.example.json`. Create the initial administrator account by opening `http://127.0.0.1:8765` on the PC itself.

To transfer the existing company installation, keep the service stopped and copy the `ai-pc/` contents from the separately supplied **private company-data ZIP** into this app folder. This is an intentional restore: its database carries existing employees, attendance, admin login and device-token registrations. Restart using that PC's normal network/TLS configuration. Back up any destination database first; never apply the private archive over a newer working database as a routine code update.

## Run

```powershell
python -m pip install -r requirements.txt
.\start.ps1
```

Use `./start.ps1 -Lan` for the company network; use `-CertFile` and `-KeyFile` for your trusted HTTPS configuration. Keep existing certificates and local environment settings outside GitHub. The API defaults to port 8765. The Pi connects to this PC's actual LAN address, not its own localhost.

Out-of-hours scans are recorded and flagged. Night shifts retain their start date across midnight. Manual entries and corrections require reasons and retain an audit trail. IN/OUT reflects confirmed attendance records. The kiosk queues scans locally during an outage and reuses stable event IDs on retry.

## Public repository exclusions

Live database, employee names/IDs/photos, face embeddings, private tokens, certificates, original Node-RED credentials and local preview screenshots are not included. The company logo and generic UI assets are included. `data/employees.json` and `runtime/` are intentionally ignored by Git.
