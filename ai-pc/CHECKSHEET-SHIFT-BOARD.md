# Checksheet shifts, OT and the Attendance board

Actual **Smart Checksheet → Shift details** controls the linked employee cards in Attendance. This uses confirmed production shifts, not the separate Executive Workspace planner. A 30-minute grace period is the default; select 15 minutes for a particular shift when needed.

| Day shift choice | Scheduled end | Grey with 15-minute grace | Grey with 30-minute grace |
| --- | --- | --- | --- |
| NO OT | 16:15 | 16:30 | 16:45 |
| WITH OT | 20:00 | 20:15 | 20:30 |

Times use Asia/Kuala_Lumpur. Night shifts work across midnight. Confirmed manual early endings use the earlier end plus grace. A newly started shift takes precedence over an employee’s older completed shift. Changing OT before the current shift ends updates its confirmed end and grey cutoff. An already-ended production shift cannot be reopened through this feature.

Grey cards show **Shift finished** alongside the actual IN/OUT status. Before the grey cutoff they show **Shift ending** during the grace period. This changes presentation only: it does not clock people out, alter face recognition, rewrite saved attendance times/payroll schedule snapshots, or change daily clock-out settings. The separate Attendance roster/template controls remain available. Employee Details shows the linked Checksheet timing separately from the Attendance template hours.

## Deploy both sides

Use the existing source directories on the AI PC. Keep all existing database volumes, employee data, private configuration, machine settings and Attendance tokens. Do not use `docker compose down -v`.

1. Update the **smartchecksheet** checkout:

   ```bash
   cd /srv/apps/smartchecksheet
   git pull --ff-only origin main
   ```

2. Generate one new dedicated feed token on the AI PC:

   ```bash
   openssl rand -hex 32
   ```

   Save the same value privately in both configurations below. This is a separate token from `ATTENDANCE_TOKEN`. Do not paste it into chat, screenshots, browser code or a URL.

3. In Checksheet’s existing `.env.docker`, add:

   ```dotenv
   CHECKSHEET_SHIFT_FEED_TOKEN=PASTE_THE_NEW_SHARED_FEED_TOKEN
   ```

   Keep the existing `ATTENDANCE_API_URL`, `ATTENDANCE_TOKEN` and `ATTENDANCE_GROUPS`: Checksheet still reads employees through Attendance’s read-only integration. Preserve the current production `APP_MODE`; `attendance` and `live` support this feed, while `demo` deliberately does not.

4. Update the **facescanpk** checkout and enter its `ai-pc` directory. If Attendance was installed from a code-only package instead of Git, apply the updated Attendance code package using its existing backed-up update procedure.

   In Attendance’s existing `.env` (beside its `compose.yaml`), add:

   ```dotenv
   CHECKSHEET_API_URL=http://host.docker.internal:3700
   CHECKSHEET_SHIFT_FEED_TOKEN=PASTE_THE_SAME_NEW_SHARED_FEED_TOKEN
   ```

   The URL is the Checksheet server origin as reachable **from the Attendance container**, not a browser URL with `/#...`. Use the actual published Checksheet port if it differs from 3700. The updated compose file supplies Linux `host-gateway`. If Checksheet is bound only to host loopback, use a shared private Docker network and Checksheet’s service hostname instead. For native installations, set equivalent environment variables and use a reachable native origin such as `http://127.0.0.1:3700`.

   If a code-only update preserved your existing Attendance Compose file, merge these entries into its existing `attendance` service as well (do not replace its volumes or ports):

   ```yaml
   environment:
     CHECKSHEET_API_URL: ${CHECKSHEET_API_URL:-}
     CHECKSHEET_SHIFT_FEED_TOKEN: ${CHECKSHEET_SHIFT_FEED_TOKEN:-}
   extra_hosts:
     - host.docker.internal:host-gateway
   ```

5. Rebuild Checksheet from its deployment folder:

   ```bash
   docker compose --env-file .env.docker config --quiet
   docker compose --env-file .env.docker up -d --build checksheet
   docker compose --env-file .env.docker logs --tail=50 checksheet
   ```

6. Rebuild Attendance from its own deployment folder containing `compose.yaml`:

   ```bash
   docker compose config --quiet
   docker compose up -d --build attendance
   docker compose logs --tail=50 attendance
   ```

   Do not share expanded Compose output, which can include the secret. Refresh both browser apps and apply their app update when offered.

## Link lines and employees

7. In Checksheet, sign in as Developer or Management. Open **Executive Workspace → Production group setup** and map each actual line to one of:

   - Conversion · Port Klang
   - Conversion · Sendayan
   - Roll Making · Port Klang

   In Attendance, employee profiles must have the correct **plant/location**, production section, line and FC tablet assignment. The integration checks both employee ID and permanent plant/section; missing plant labels are not guessed. Port Klang and Sendayan employees sharing the source line name FC are filtered by their explicit plant and division. Attendance groups with several `accountLines` must still map those account lines to one production group; create separate group definitions when necessary.

8. In **Smart Checksheet → Start shift**, or **Shift details → Edit shift details** for an active shift:

   - Set the actual production date, Day/Night, NO OT/WITH OT and production roles.
   - Under **Attendance shift board**, choose 30 or 15 minutes.
   - Select the actual Attendance employees working this shift. The picker shows names, employee IDs and permanent group labels. Names alone are never used to link people.
   - Save. Set these links for each new production shift. Older shifts without selected employee IDs do not control board cards.

   Operators, Management, Developer and scoped Executive accounts can manage actual shift details. Executives do not gain production count, reject, machine setup, verification or account-administration permissions. In live mode edits use the existing same-shift Python update path and wait for machine confirmation before changed OT timing reaches the board; counts are preserved. Use an up-to-date commissioned Python checksheet service supporting same-shift updates.

## Verify

9. Open Attendance’s **Live board**. The header should say **Checksheet shifts linked**. Open one selected employee’s details and verify the Checksheet line, OT, start, end and grey cutoff. Confirm an employee in another plant/section is unaffected.

10. Test with a controlled real shift or a disposable test environment: for a Day NO OT shift ending at 16:15 with 30-minute grace, **Shift ending** applies at 16:15 and **Shift finished**/grey at 16:45. A 15-minute setting gives 16:30. With OT, the corresponding cutoffs are 20:30/20:15. The server refresh is approximately every 15 seconds, so display changes can follow by one refresh interval. Actual clock status stays separate.

11. Before an active shift ends, change its OT or grace setting, save, and verify the linked timing updates. In live mode wait for Python confirmation. Two simultaneous stale shift edits require refreshing rather than overwriting the newer details.

## Failure and recovery

Attendance’s backend polls the dedicated authenticated `GET /api/integrations/shifts` endpoint every 15 seconds; a browser does not need to remain open. It validates timestamps, groups, employee IDs and grace intervals, and persists the last accepted snapshot. Tokens never reach the React application. Redirects are not followed.

A failed poll or a snapshot older than 90 seconds marks the connection unavailable and suppresses the Checksheet grey overlay, falling back to actual attendance display. The header warns **Checksheet shift sync unavailable**. Successful polling restores the linked view. Source history survives rollover/restart and includes the last 14 days; no linked shift means ordinary attendance display. Removing employee links or moving a line out of its production group removes its old board effects on the next successful poll.

If the picker is empty, check the employee’s active state, PRODUCTION department, exact plant/location, production section and source Attendance mapping. If the board header is unavailable, check both token values match, the port is reachable from the Attendance container, and both apps were rebuilt. Keep the existing read-only Attendance integration enabled as well.

For an intentional disconnect, clear both `CHECKSHEET_API_URL` and `CHECKSHEET_SHIFT_FEED_TOKEN` in Attendance’s environment and recreate its container. This clears its cached board control without changing clock records.

## Development verification

Checksheet: `npm test` and `npm run build`.

Attendance: `python -m unittest discover`, `node --test src/*.test.js` and `npm run build` from `ai-pc`. The optional two-app contract test additionally runs when `CHECKSHEET_TEST_DIR` points to a Checksheet checkout with dependencies installed and Node is on PATH. It uses temporary databases and synthetic employees, and does not access production records.
