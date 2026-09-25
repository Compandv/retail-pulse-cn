import calendar from "../config/trading-calendar.json" with { type: "json" };

export const TRADING_CALENDAR = calendar;
const holidays = new Set(calendar.holidays);
const [hour, minute] = calendar.availableAfter.split(":").map(Number);

/** Existing collection convention: wait until 15:30 Beijing time. */
export function latestSession(now = new Date()): string {
  if (!Number.isFinite(now.getTime())) return "";
  const local = new Date(now.getTime() + calendar.utcOffsetHours * 3600000);
  if (local.getUTCHours() * 60 + local.getUTCMinutes() < hour * 60 + minute) local.setUTCDate(local.getUTCDate() - 1);
  while ([0, 6].includes(local.getUTCDay()) || holidays.has(local.toISOString().slice(0, 10))) local.setUTCDate(local.getUTCDate() - 1);
  return local.toISOString().slice(0, 10);
}

export function isSupportedSession(day: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return false;
  const parsed = new Date(`${day}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === day &&
    calendar.supportedYears.includes(parsed.getUTCFullYear()) &&
    ![0, 6].includes(parsed.getUTCDay()) && !holidays.has(day);
}

/** Do not claim freshness when this build has no calendar for the current year. */
export function latestSupportedSession(now = new Date()): string | null {
  const local = new Date(now.getTime() + calendar.utcOffsetHours * 3600000);
  if (!Number.isFinite(local.getTime()) || !calendar.supportedYears.includes(local.getUTCFullYear())) return null;
  const day = latestSession(now);
  return isSupportedSession(day) ? day : null;
}

export function validSession(day: string, now = new Date()): boolean {
  return isSupportedSession(day) && day <= latestSession(now);
}
