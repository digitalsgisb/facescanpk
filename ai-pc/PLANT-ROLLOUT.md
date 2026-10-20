# Testing reset, employee updates and plant rollout

This update supports Port Klang and Sendayan on a shared AI PC, and repeatable rollout to another plant. It does not change `face.py`, biometric processing or biometric files. The supplied workbook is treated only as employee data.

## What is ready

- Clock in / out → unlock → **Clock out everyone — testing reset**. This closes open sessions at the current server time, including stale and archived employee sessions. History is retained, marked `testing_reset` and audited with your reason. A consistent private database/photo backup must succeed first. The reset runs atomically and retries are safe.
- Employee imports match by immutable ID. Name, company, plant, source department, Job Type and Position are updated. **Position uses the exact Job Type text from the workbook**, including abbreviations. No job title is guessed or expanded.
- Existing photos, active status, nicknames, teams, production lines, individual hours and attendance history are preserved. Existing employees absent from the file are retained. New employees are active with no assigned team/line/hours; configure these before attendance use. No photo or biometric file is in the employee update JSON.
- Existing Office board placement stays Office; its represented office department is refreshed. Research & Development uses the existing R&D board label. The original source department is retained separately. Other board departments follow the source department.
- Employees and live-board groups are labeled by location. The directory offers a location filter. Records without a location remain explicitly unassigned and visible to the all-plants administrator until reviewed.

The workbook contains 248 unique employees: 168 PORT KLANG and 80 SENDAYAN. The transfer package contains separate files for each location plus a combined file. Import is previewed against the **actual AI PC database** before any data update, rather than replacing that database with a development copy.

## Account setup

Sign in as the existing administrator. Open System settings → Staff permissions and photo retention. Use the three setup shortcuts and choose a different private password for each account:

| Username | Role | Plant access | Intended access |
| --- | --- | --- | --- |
| `pk-admin` | Administrator | `PORT KLANG` | PK employees, profile photos, ordinary consent, imports and attendance |
| `sendayan-admin` | Administrator | `SENDAYAN` | Sendayan employees, profile photos, ordinary consent, imports and attendance |
| `developer` | Administrator | blank (all plants) | Oversee both plants, staff, connections, backups and global settings |

The shortcuts prefill these settings; accounts are saved only after entering a password and pressing Create or update staff on the AI PC. No default passwords or user sessions are shipped. Staff accounts use separate server-side sessions expiring after eight hours. Unlock clock controls with that named account's own password. Updating role/location/password or disabling an account revokes its existing sessions. The original administrator remains available for recovery.

Plant limits are checked on the server for employee lists, photo access, consent, attendance, clock actions, resets and imports. A plant user cannot move a record to another plant, import another plant's file, use its employee IDs, inspect global backups/audit or change system settings. An employee ID is unique across the system. The developer account must review cross-plant employee transfers.

Site admins share the existing centrally managed schedule/rule system on a shared server. The developer account manages global team schedules and settings. Separate installations have independent databases/settings. This update does not create isolated server instances or alter network/proxy configuration automatically.

## Connect each plant's kiosk

As developer, open System settings → Connection plant access. Assign the PK kiosk to `PORT KLANG` and the Sendayan kiosk to `SENDAYAN`, then save each. The same option applies to read-only integrations. Existing tokens keep working. A blank location preserves legacy all-plant access, so assign the plant before using a shared server with both sites.

The server returns only that kiosk's ordinary employee metadata and accepts scans only for employees assigned there. Photos and consent never enter kiosk payloads. Sync confirmations are checked against the kiosk's own plant snapshot. Keep each physical kiosk assigned to one plant; let its pending scan queue finish before reassigning its location. Reassignment does not delete its local biometric files or queued events.

## Existing AI PC: safe code transfer

The outer transfer ZIP is **private** because it contains names/IDs and HR details. Transfer it over your existing private SSH/SFTP channel or a protected USB drive. Do not put it in GitHub or a public share. Its inner `AI-PC-Code-Update.zip` contains code and generic UI assets only. The package contains SHA-256 checksums for transfer verification; checksums do not authenticate an untrusted sender.

1. Pause scanning at both kiosks and allow pending scans to finish. Choose a maintenance window and retain your current code.
2. Copy the private transfer ZIP to a new staging directory on the AI PC. Extract there, never directly into the live app. Open START-HERE.md. Run `sha256sum -c SHA256SUMS.txt` inside the extracted folder on Linux. Windows: compare `Get-FileHash -Algorithm SHA256` with the listed checksum for a file.
3. Set `APP` to the existing AI PC application folder containing `server.py` and `compose.yaml`. Existing deployments may use `/srv/apps/facescan_pk/ai-pc` or the checkout root. Verify the path; do not create a second live database.

Example commands, from the extracted staging directory in Bash. Replace the APP value with the verified application path and keep STAGE pointing at this extracted directory:

```bash
APP=/srv/apps/facescan_pk/ai-pc
STAGE="$PWD"
test -f "$APP/server.py" && test -f "$APP/compose.yaml"
python3 "$STAGE/install_code_update.py" "$STAGE/AI-PC-Code-Update.zip" --target "$APP"
cd "$APP"
sudo docker compose exec attendance python manage.py backup --output "runtime/backups/pre-plant-rollout-$(date +%Y%m%d-%H%M%S).zip"
sudo docker compose stop attendance
sudo python3 "$STAGE/install_code_update.py" "$STAGE/AI-PC-Code-Update.zip" --target "$APP" --apply
sudo docker compose up -d --build
sudo docker compose ps
curl --fail http://127.0.0.1:3800/api/health
```

Run each command only after the previous command succeeds. Native Python installations use the same installer preview/apply, but stop/restart their existing service and use their configured port. The compiled dashboard is included, so no Node installation is needed for native code transfer. Keep your existing Python environment and install requirements only if needed by that installation.

The installer verifies every inner file checksum and allows only source, generic public/dist assets and named application files. It rejects live `runtime/`, `uploads/`, biometric folders, `data/employees.json`, `.env` and `compose.yaml` paths. Existing `.dockerignore` and example employee data are preserved. The new Compose example has a different filename. Existing code is backed up into `runtime/backups/code-before-update-*.zip` before replacement. Files are replaced atomically; a write failure attempts restoration of files already written. No service is stopped or started by the installer itself.

4. Refresh the dashboard. As the original administrator, open Employees → Import employee details. Select `employee-files-PRIVATE/employees-ALL-PLANTS.json` for a shared server, or the correct per-plant file for separate servers. Review the new/update/unchanged/preserved counts and individual field changes. Press **Back up and apply reviewed changes**. A failed backup or stale preview prevents the import. A database error rolls it back. Network retries reuse the same request and do not repeat the update.
5. Create `pk-admin`, `sendayan-admin` and `developer` with the account shortcuts above. Assign kiosks to their plants. Verify each account's view, imported position/location and preserved working hours/photos. Existing employees not in the spreadsheet remain; review unassigned locations with the developer account instead of silently archiving them.
6. After testing, unlock Clock in / out and use Testing reset. A plant account resets its own plant only. Developer resets **all plants**; directory/search filters do not narrow that button. Type `CLOCK OUT EVERYONE` and a reason. The result includes the number closed and backup filename. Resume scanners only when ready to begin; subsequent scans can clock employees in again.

Stale test sessions will show long elapsed periods after closing; their `testing_reset` flag identifies them. This resets current IN/OUT state, not historical payroll totals. Future-dated clock-ins must be corrected first. There is no attendance-history wipe in this update.

## New plant: repeatable Yokoten

Use the same code update package for every plant. For an independent AI PC, follow the existing Docker/network/TLS setup with a new empty application/runtime directory, apply the code package, and use `compose.new-plant.example.yaml` as a starting template only if no production Compose file exists. Create its first administrator using the existing local/SSH `manage.py init-admin` procedure. Import only that plant's employee JSON and create its plant account. Keep credentials and kiosk tokens unique to the installation; do not copy another plant's live database, biometric directory or `.env`.

For another plant on a shared AI PC, developer creates a new staff account with Administrator role and its new uppercase Plant access name. Prepare a workbook with the same six headers, including its location in Base. Import that plant's rows and assign its kiosk. No code change or hardcoded plant list is required. Full administrators can import combined files; plant accounts can import only their own location.

Prepare future private imports using Python's standard library; Excel and additional Python packages are not required:

```bash
python3 prepare_employee_update.py "Employment Details.xlsx" --output NEW-PRIVATE-EMPLOYEE-FOLDER
```

Expected single-sheet headers: `Employee#`, `Name`, `Company`, `Base`, `Department`, `Job Type`. IDs are treated as text. Use existing IDs, uppercase location names, and actual values. Formulas, duplicates, missing required fields and unsupported layouts are rejected. The tool creates separate plant files and one combined file, never modifies the workbook and refuses to replace an existing output folder.

## Verification and rollback

Automated checks use temporary data only. From the repository root:

```bash
python -m unittest discover -s ai-pc -p 'test*.py' -v
python -m unittest discover -s raspberry-pi -p test_kiosk_transport.py -v
python -m unittest discover -s tools -p test_plant_rollout.py -v
cd ai-pc
node --test src/*.test.js
npm run build
```

On staging, verify exact Job Type/Position, location filters, old photos/team/line/hours, each account's blocked cross-plant actions, per-plant kiosk sync, test-reset closure and backup availability. Check the developer view across both sites. Physical kiosk and phone acceptance remains necessary.

Code rollback: stop the service, restore only the old application files from `runtime/backups/code-before-update-*.zip` to their original paths, then rebuild/restart the previous version. Ignore the backup's `code-backup-manifest.json`; it lists newly introduced files, which older code does not import. Keep the current database, uploads and configuration. Old code ignores additive tables/columns, but it does not provide plant-scoped accounts; keep the old service restricted to the original administrator and use pre-update per-plant device deployments until the new code is restored. Do not continue a multi-plant deployment on an old server assuming location isolation still applies.

Imports and resets cannot be undone by code rollback. Their private `before-employee-import-*.zip` or `before-reset-*.zip` backups contain the pre-operation database/photos. A full data restore is a separate stopped-service recovery: first back up current data and reconcile all attendance after that backup. Do not overwrite a live database with a development database or stale backup. Audit entries retain the original per-session times and per-field import changes for targeted corrections.

## Local delivery verification

70 backend tests, 7 Pi transport tests, 4 transfer-tool tests and 28 frontend tests passed (109 total). The production frontend build succeeded. A disposable import against the local 173-employee snapshot updated 160 IDs, added 88, and preserved 13 employees missing from the supplied workbook. All 248 imported names, exact positions and locations matched the workbook; original photos, teams, lines and schedule IDs stayed unchanged. These counts describe that local snapshot; the actual AI PC preview is authoritative.

No live AI PC deployment, production data import, real attendance reset or account creation was performed during preparation. The package includes setup shortcuts for `pk-admin`, `sendayan-admin` and `developer`, with passwords to be chosen on the AI PC. Physical phone/Pi and Linux/Docker deployment acceptance remains required. Existing production configuration and biometric files were untouched.
