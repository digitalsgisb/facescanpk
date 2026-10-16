# Smart Checksheet attendance connection

The attendance API already supports read-only app connections. The new employee field `checksheet_group` separates the FC tablets without splitting the attendance TV board or FC working-hour settings.

1. Deploy this updated backend and React build on the AI PC, then restart Attendance. Startup adds the new field automatically with existing employees unassigned.
2. Open **Employees > Profile** for each FC employee. Keep Department **PRODUCTION**, Production line **FC**, and choose **Checksheet tablet assignment**: FC Line 1, FC Line 2, or FC Line 3. Employees remain together under FC on the TV board. Do not guess assignments from team A/B/N; teams describe shifts.
3. **System settings > Connected devices > Add connection**: choose **Production app / checksheet (read only)**. Keep the once-shown token private and put it in the Checksheet backend's `ATTENDANCE_TOKEN` environment setting.
4. Deploy the Smart Checksheet integration. Its `ATTENDANCE-INTEGRATION.md` explains the five group configurations and its `Connect-Attendance.ps1` can verify and save the configuration on Windows. Both apps on a native installation of the same AI PC can use `ATTENDANCE_API_URL=http://127.0.0.1:8765`. Docker requires a reachable internal network address.
5. Open **Attendance** in the Checksheet menu. Check one employee for each FC assignment, Mini Forming and the whole Roll Making section. Verify a clock-in changes the count after the next refresh and that losing the connection displays an error.

`GET /api/employees` with an integration bearer token includes the saved `checksheet_group`; it remains read-only. The Checksheet backend filters employees and sends only names, teams, lines and clock status to signed-in tablets. Mini Forming uses existing line `MF`. Roll Making includes the entire `ROLL MAKING` production section. Unassigned FC employees do not appear on an FC tablet until assigned.

OUT means currently clocked out, not shift absence. Old unclosed clock-ins appear as Needs review. No real employee assignments or connection tokens are created by deploying these source files.
