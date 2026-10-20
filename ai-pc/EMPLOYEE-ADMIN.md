# Mobile employee administration

For testing resets, the latest plant-scoped account rules, exact spreadsheet position imports and transfer packages, see [Plant rollout](PLANT-ROLLOUT.md). It extends the original administration features documented below.

## Architecture and existing features

The Git repository is `facescanpk/`. Other workspace copies (`attendance-app/` and the top-level Pi scripts) are separate installations and were not updated. A pre-existing local server change enabling integration photo access was preserved.

The AI PC serves the React dashboard and a Python HTTP API backed by SQLite. It already had employee create/edit, archive/restore, schedule validation, administrator cookies, kiosk/integration token scopes, audit history, protected photo serving, JPEG conversion, phone image resizing and separate camera/gallery inputs. The PWA worker excludes APIs and employee photos from its cache. These features are reused.

The Pi transport polls employees approximately every 20 seconds, persists an offline JSON cache and delivers attendance scans through its durable SQLite outbox. `face.py` consumes ordinary employee metadata alongside the existing local recognition data. This change does not modify `face.py`, embeddings, enrollment, matching or biometric files. Profile photos never enter the kiosk response or cache.

## File-by-file changes

| File | Change |
| --- | --- |
| `server.py` | Staff authentication/permissions, metadata-only kiosk payload, acknowledgements, consent/photo endpoints, upload validation, stale-edit detection and additive migration integration |
| `employee_admin.py` | New staff, consent, photo lifecycle and receipt tables; canonical metadata hashes; sync statuses; explicit photo retention |
| `src/main.jsx` | Staff login, restricted navigation, consent form integration, immediate photo deletion and staff settings |
| `src/employee-privacy.jsx`, `.css` | Consent decisions with evidence, current consent, per-kiosk statuses, touch sizing and single-column phone forms |
| `src/employee-sync.js` | Explicit sync status descriptions |
| `src/staff-administration.jsx` | Create/update/disable staff; select and execute unused-photo retention |
| `src/workforce.jsx` | Directory sync status; attendance actions hidden for employee administrators |
| `raspberry-pi/kiosk_transport.py` | Fsync and replace metadata cache before sending version receipt |
| `test_employee_admin.py`, `src/employee-sync.test.js`, Pi transport tests | Permission, consent, photo lifecycle, concurrency and durable-sync regression coverage |
| `Dockerfile`, `tools/package.py` | Include new backend module and administration documentation in deployment |

## Phone workflow

1. Open the existing trusted HTTPS attendance address on the workplace network. Sign in with a named staff username/password, or leave username blank for the existing administrator.
2. Open Employees, search for a person, and choose Profile; use Add employee for registration. IDs remain immutable after registration.
3. Use Choose photo or Take photo. Camera/gallery availability depends on the phone browser. Browser-decodable images are resized before upload; unsupported HEIC files show an actionable format error. JPEG, PNG and WebP are supported by the server.
4. Optionally record an actual consent decision. Select employee data administration or profile photo, grant/withdraw, the notice version and a reference to the evidence. Save commits the employee and consent atomically. Previously recorded consent is not invented for existing employees.
5. Save changes. A stale form receives a conflict rather than overwriting another administrator's edit. Reopen the profile to refresh it. Legacy clients that omit `updated_at` retain their previous update behavior.
6. Delete saved profile photo now immediately clears that saved reference and revokes access when its last employee reference is removed. Cancel does not undo this button. Clear selected photo clears the unsaved selection; its unreferenced upload is eligible for retention cleanup.

Consent decisions are immutable history records, exposed through `GET /api/employees/{id}/consents`. Current decisions appear in the profile. Recording withdrawal records the decision; it does not silently archive employees, change attendance or delete their photos. The administrator must use photo deletion/archive where applicable. No biometric consent or biometric processing is managed here.

## Permissions and audit

| Role | Access |
| --- | --- |
| Full administrator | Existing workspace features plus staff accounts, consent history and photo retention |
| Employee administrator | Employee create/edit/archive/restore, profile photos, ordinary consent and sync status; no attendance corrections, clock controls, audit export, device management, backups or system settings |
| Kiosk token | Existing scan/heartbeat/schedule access and allowlisted ordinary metadata; no photos or consent |
| Integration token | Existing read-only employee/attendance integration and its existing protected photo access |

Create named accounts in System settings → Staff permissions and photo retention. Passwords use the existing salted PBKDF2 implementation. Staff cookies are HttpOnly and SameSite Strict; sessions expire server-side after eight hours. Changing an account password, role or active state revokes all its sessions. The existing administrator session format and password login remain compatible. Use the existing trusted HTTPS deployment for smartphone administration; this update does not alter proxy/TLS production configuration.

Employee changes, consent, uploads, deletion, staff changes and retention operations use the existing audit table with an actor identifier. Passwords and image bytes are excluded. Audit and consent tables are application-level history, not a cryptographically tamper-proof ledger; protect direct database access and backups.

## Synchronization meaning

The server hashes an allowlist of employee IDs, names, active status, nickname, department, position, line, team and ordinary grouping fields. Photos, consent and biometric data are excluded. The Pi acknowledges a version only after writing, flushing, fsyncing and replacing its offline metadata cache. Receipts are associated with authenticated kiosk tokens, persist across server restarts and are informational rather than proof of physical device integrity.

- **Confirmed:** every active registered kiosk has acknowledged the current metadata snapshot and has a heartbeat within 90 seconds.
- **Pending:** at least one online kiosk has not acknowledged the current snapshot. Older transport versions keep working but cannot confirm sync.
- **Offline:** at least one kiosk has no recent heartbeat; the last receipt time remains visible.
- **No active kiosk:** no kiosk has been registered or all have been revoked.

The snapshot is shared across employee records, so any metadata change conservatively marks all records pending until acknowledged. Schedule/status refresh and photo changes do not alter the metadata hash. This status confirms metadata cache delivery only; it does not indicate biometric enrollment or recognition readiness. New Pi transport works with older servers that omit a version.

## Photo security and retention

Uploads require an authorized browser session. The API caps JSON requests at 7 MB, decoded images at 5 MB and 20 million pixels, checks the decoded format and rejects animated/multiframe or unsupported files. It applies orientation, converts to RGB and stores a newly encoded JPEG of at most 600×600 without original EXIF metadata. Names are random, paths are constrained to the uploads directory, and responses use `no-store`. New directories/files use private Unix modes; Windows deployments inherit their existing filesystem access controls. The application does not fetch external photo URLs. Browser-origin validation compares the public Host authority (including a published Docker port), so phone writes through port 3800 work while mismatched origins are rejected.

Uploads have lifecycle records. Removal of a last shared reference marks a photo deleted in the same transaction as its audit entry. Only after commit does the server remove the file. If disk deletion fails, access stays revoked; subsequent mutations or retention runs retry it. Do not reassign a deleted URL. Deleting an external HTTPS photo clears the employee reference only; this service cannot delete that external host's file. Shared uploads remain accessible until the last reference is removed.

System settings provides an explicit cleanup action with a configurable minimum upload age (default 30 days; 1–3650 allowed). It deletes only tracked, unreferenced uploads old enough to qualify. Age is measured from upload, not from the time a reference was cleared. References on archived employees are protected. Pre-existing untracked images, employee rows, attendance, consent and audit history are not purged. No automatic cleanup runs on startup. Example API: `POST /api/retention` with `{"unreferenced_photo_days":30}` as a full administrator.

Old backups, external photo hosts and prior device caches have their own retention lifecycle. Applying a deletion does not erase historical backups. Use the facility's documented retention policy to expire private backups and historical records separately. There is deliberately no automatic attendance/history deletion or legal retention period imposed by this change.

## Deployment and tests

1. Review and preserve local code edits and save a code snapshot. Back up with `python manage.py backup --output runtime/backups/pre-employee-admin-UNIQUE.zip` from the AI PC directory (choose a new filename). Keep a protected copy off the PC. Keep `.env`, runtime, uploads and the Pi's `database/`, `kiosk-runtime/` and `kiosk.env` intact.
2. Apply reviewed code to the AI PC first. For Docker use the existing `docker compose up -d --build`; the Dockerfile now includes `employee_admin.py`. Native installations must also copy the new module and rebuild React with `npm ci` and `npm run build`. Restart the service. Existing tables/data are preserved; new tables are created additively on first startup.
3. Update only the reviewed Pi transport code and restart its kiosk through the existing documented procedure. Keep `face.py` and all biometric files unchanged. Refresh the phone dashboard. Confirm employee edits eventually show Confirmed, then test offline/pending behavior.
4. On a staging phone test camera/gallery selection, unsupported format errors, portrait/landscape layout, add/edit, archive/restore, immediate deletion, permission denial and two-phone edit conflicts. Physical phone camera and Pi hardware acceptance remains necessary.

From the repository root, using the project's Python dependencies and Node:

```sh
python -m unittest discover -s ai-pc -p 'test*.py' -v
python -m unittest discover -s raspberry-pi -p test_kiosk_transport.py -v
cd ai-pc
node --test src/*.test.js
npm run build
```

Tests create disposable databases and generated images under `ai-pc/runtime/tests`; they do not migrate or seed the production database. The GitHub delivery includes refreshed code-only device download ZIPs and their checksums. Private employee import files and transfer bundles remain local and excluded from Git.

## Rollback

Stop the affected service, restore the saved pre-update code/build, and restart. Revert only this change's source files; preserve any pre-existing local server changes. The old server ignores the additive tables and the Pi accepts the legacy employee response. Leave the live database, uploads, attendance queue and biometric files in place. Do not replace a current database with an old backup merely to roll back code: that would discard intervening attendance and employee changes.

Named staff accounts require this new code and will be unavailable under the old server; use the existing administrator login. Older code does not enforce photo tombstones, so resolve any pending physical photo deletions before rollback. An intentionally deleted photo cannot be recovered by rolling back code. If recovery is explicitly needed, retrieve only the authorized file from a protected pre-deletion backup and re-upload it using the current consent decision; do not restore an entire stale production database. Database recovery is a separate maintenance operation requiring reconciliation of all post-backup attendance.

## Local validation result

The complete backend suite passed 59 tests before the final origin correction; the new public-port origin test and the existing cross-origin regression then both passed (60 distinct backend tests covered). All 7 Pi transport tests and 26 Node tests passed, and the Vite production build succeeded. Git whitespace checks passed. Phone camera, real Pi hardware and deployment were not exercised. Existing workspace Node dependencies were reused through an ignored local junction; no production configuration or application data was changed.
