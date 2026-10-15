// The first snapshot establishes a baseline; opening the app never replays history.
export function createAttendanceTracker() {
  let seen = new Map(), watermark = null;
  return snapshot => {
    const events = snapshot.recent_events || [];
    if (watermark === null) {
      seen = new Map(events.map(event => [event.id, event.received_at]));
      watermark = snapshot.time;
      return [];
    }
    const fresh = events.filter(event => !seen.has(event.id) && event.received_at >= watermark)
      .sort((a, b) => a.received_at.localeCompare(b.received_at) || a.occurred_at.localeCompare(b.occurred_at));
    for (const event of fresh) seen.set(event.id, event.received_at);
    // Keep IDs at the watermark too: multiple scans can arrive in the same second.
    if (fresh.length) watermark = fresh.at(-1).received_at;
    for (const [id, received] of seen) if (received < watermark) seen.delete(id);
    return fresh.flatMap(event => {
      let result;
      try { result = JSON.parse(event.result); } catch { return []; }
      if (!result.accepted || !['IN', 'OUT'].includes(result.action)) return [];
      const employee = snapshot.employees.find(employee => employee.id === event.employee_id);
      return [{...event, action: result.action, employee: employee || {id: event.employee_id, name: event.name, nickname: event.nickname}}];
    });
  };
}
