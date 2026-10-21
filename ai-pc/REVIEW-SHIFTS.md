# Reviews, plant shifts and daily clock-out

## Use the new controls

- **Review → Mark all reviewed:** preview the count, enter one reason, and confirm. Select a page or individual rows to review a smaller batch. The optional date limits the bulk action. Attendance times and original flags stay in the log. Stored review scans are acknowledged, not applied to attendance. Open sessions remain open. Changed records can return to the queue.
- **Review → Review prompts:** turn prompts off for the selected plant. Developer can turn them off for all plants; plant admins cannot override that global switch. Turning prompts back on restores outstanding items. Missing working hours are separate configuration tasks and remain visible until hours are assigned. Scan consistency protections continue to operate.
- **Shifts:** PK admins manage A/B/N; Sendayan admins manage C/D/N. N is the normal-hours team. Developer selects the plant to manage. Choose fixed hours or a rotating pair, set OT, and save. Department overrides and exact shift times are collapsible. Template edits apply only to the selected plant. Existing employee team assignments are preserved; choose C or D in Sendayan profiles where needed. Saved attendance retains its original planned times.
- **Developer → Shifts → Daily clock-out · All plants:** enable it, choose a Malaysia time and save. This closes eligible open sessions across every plant, including archived employee sessions. The developer/all-plants administrator controls this setting; plant admins cannot change it. It is disabled by default.
- **Live board:** developer can select Port Klang, Sendayan or all plants. The selection remains available in fullscreen and is remembered on that browser. Counts and cards follow the selection. Plant admins retain their assigned location only.
- **Employees:** imports, search filters and group shortcuts start collapsed. A group selector shows one group at a time. The sidebar connection card is removed; synchronization and live updates continue.

## Daily clock-out behavior

The AI PC checks the persisted schedule every 15 seconds. Keep its attendance service running; a browser does not need to remain open. Records use the selected cutoff time in Asia/Kuala_Lumpur. A database/photo backup must succeed before any session is closed. Per-session audit entries and OUT events record the action, and the settings card shows the last completed run. Use Refresh status to check it.

Each cutoff date runs once. Enabling a new schedule after today's cutoff begins with the next due cutoff. Changing the time after a completed run does not create a second run on that date. Saving an unchanged enabled time preserves the pending due run. If the service restarts late, it catches up to the latest due cutoff; clock-ins after that cutoff stay open. Scans arriving later are processed normally, so later attendance can change again. Backup errors leave sessions open and the worker retries; inspect service logs for `[SCHEDULED CLOCKOUT]` errors.

The existing manual testing reset remains available. Reviewing flags, turning prompts off and setting shifts do not themselves clock people out or remove attendance history.

## Implementation and update

`plant_workflows.py` adds plant preferences, review acknowledgements and persisted clock-out configuration/run receipts. Plant template overrides are stored separately from shared templates. Existing schemas and values are retained. `face.py`, biometric processing/files and production configuration are unchanged.

The Dockerfile and both packaging tools include the new module. Update the AI PC code/image first, then refresh the browser. No Pi recognition changes are needed. Use the existing [backed-up transfer and rollback procedure](PLANT-ROLLOUT.md). Before reverting to older code, disable Daily clock-out. Keep the current database and uploads; the previous server ignores the additive tables. Older versions do not provide these review/shift controls. For targeted reversal of a scheduled clock-out, use its audit records and backup through the existing stopped-service recovery process rather than replacing live data with an old snapshot.

Automated checks use disposable databases and synthetic employees, including a 250-session bulk review, C/D rotation, scoped template edits, all-plant clock-out, restart catch-up, later arrivals and backup failure. Browser checks use an isolated localhost fixture with synthetic people. Production data and accounts are not changed by development tests. Real AI PC acceptance is still required after deployment.
