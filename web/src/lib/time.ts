// The API sends naive UTC timestamps ("2026-11-06T03:00:00.123456", no
// offset). Date() would read those as local time - 9 hours off in Korea -
// so mark them as UTC first.
export function parseUtc(ts: string): Date {
  const hasZone = /(?:[zZ]|[+-]\d{2}:?\d{2})$/.test(ts);
  return new Date(hasZone ? ts : `${ts}Z`);
}

// withSeconds: for lists where two entries can land in the same minute
// (saved team runs), so they stay distinguishable.
export function formatUtc(ts: string, withSeconds = false): string {
  return parseUtc(ts).toLocaleString("ko-KR", {
    month: "numeric",
    day: "numeric",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    ...(withSeconds ? { second: "2-digit" } : {}),
  });
}
