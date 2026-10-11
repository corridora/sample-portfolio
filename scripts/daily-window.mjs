// A schedule period begins at the configured UTC time and ends at the next day's start.
export function dailyWindow(now = new Date(), time = '14:20') {
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(time)) throw new Error('Daily time must be HH:MM UTC');
  const [hour, minute] = time.split(':').map(Number);
  let start = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), hour, minute);
  if (start > now.getTime()) start -= 86400000;
  return { start, end: start + 86400000, day: new Date(start).toISOString().slice(0, 10) };
}

export function heartbeatCovers(heartbeat, window) {
  return heartbeat?.result === 'passed' && Number.isFinite(heartbeat.at)
    && heartbeat.at * 1000 >= window.start && heartbeat.at * 1000 < window.end;
}
