# Smart Checksheet attendance connection

The attendance API already supports read-only app connections. The new employee field `checksheet_group` separates the FC tablets without splitting the attendance TV board or FC working-hour settings.

1. Deploy this updated backend and React build on the AI PC, then restart Attendance. Startup adds the new field automatically with existing employees unassigned.
2. Open **Employees > Profile** for each FC employee. Keep Department **PRODUCTION**, Production line **FC**, and choose **Checksheet tablet assignment**: FC Line 1, FC Line 2, or FC Line 3. Employees remain together under FC on the TV board. Do not guess assignments from team A/B/N; teams describe shifts.
3. **System settings > Connected devices > Add connection**: choose **Production app / checksheet (read only)**. Keep the once-shown token private and put it in the Checksheet backend's `ATTENDANCE_TOKEN` environment setting.
4. Deploy the Smart Checksheet integration. Its `ATTENDANCE-INTEGRATION.md` explains the five group configurations and its `Connect-Attendance.ps1` can verify and save the configuration on Windows. Both apps on a native installation of the same AI PC can use `ATTENDANCE_API_URL=http://127.0.0.1:8765`. Docker requires a reachable internal network address.
5. Open **Attendance** in the Checksheet menu. Check one employee for each FC assignment, Mini Forming and the whole Roll Making section. Verify a clock-in changes the count after the next refresh and that losing the connection displays an error.

`GET /api/employees` with an integration bearer token includes the saved `checksheet_group`; it remains read-only. The Checksheet backend filters employees and sends only names, teams, lines and clock status to signed-in tablets. Mini Forming uses existing line `MF`. Roll Making includes the entire `ROLL MAKING` production section. Unassigned FC employees do not appear on an FC tablet until assigned.

OUT means currently clocked out, not shift absence. Old unclosed clock-ins appear as Needs review. No real employee assignments or connection tokens are created by deploying these source files.

## Production staff managed from Smart Checksheet

The Checksheet's **Employees** screen adds, edits, deactivates and reactivates **Production** employees through the same integration token:

- `POST /api/integrations/production-employees` creates one employee; `PUT /api/integrations/production-employees/<id>` edits one (send the `updated_at` you read, or the change is refused with 409).
- Allowed fields: name, nickname, position, plant (`base`), section, line, team, FC group, active, `checksheet_role` (SUPERVISOR, LEADER, OPERATOR, QUALITY; older FORMING, WATERJET and ASSEMBLY values are still accepted and read as OPERATOR) and `covers_lines` (supervisors and leaders only; the home line is always included). Department is always PRODUCTION. Office staff cannot be changed.
- A plant-limited token manages its own plant only. Someone still clocked in cannot be deactivated. Every change is audited as `<connection>:<Checksheet user>`.

The first Checksheet save turns on **Production staff managed in Smart Checksheet** (Setup > attendance rules). While it is on, Production names, lines, teams, positions, plant and status are read-only in Attendance: the profile form, Archive, and spreadsheet import all refuse them. Photos, consent, working hours and face enrollment stay in Attendance. Turn the setting off to hand Production staff back to Attendance.
