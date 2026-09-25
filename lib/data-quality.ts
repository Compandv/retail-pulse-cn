import { FOLLOWING_METHOD } from "./following-method.ts";
import { isSupportedSession, latestSupportedSession, TRADING_CALENDAR } from "./trading-calendar.ts";
import type { DailyReport, ReportSector } from "../app/report-types.ts";

export type SnapshotHealthInput = {
  tradeDate: string;
  methodVersion?: string;
  expectedMethodVersion?: string;
  historical?: boolean;
  now?: Date | null;
};
export type SnapshotHealthState = {
  state: "checking" | "historical" | "current" | "stale" | "invalid" | "calendar-unknown";
  title: string;
  detail: string;
  methodMismatch: boolean;
  expectedDate: string | null;
};

/** Time and method validity are independent of sampling quality. No freshness guesses. */
export function snapshotHealth(input: SnapshotHealthInput): SnapshotHealthState {
  const { tradeDate, methodVersion, expectedMethodVersion, historical, now } = input;
  const methodMismatch = Boolean(expectedMethodVersion && methodVersion !== expectedMethodVersion);
  const expectedDate = now ? latestSupportedSession(now) : null;
  const result = (state: SnapshotHealthState["state"], title: string, detail: string): SnapshotHealthState =>
    ({ state, title, detail, methodMismatch, expectedDate });
  const parsed = new Date(`${tradeDate}T00:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(tradeDate) || !Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== tradeDate) {
    return result("invalid", "快照日期异常", "不能将此数据认定为有效交易日数据。");
  }
  if (TRADING_CALENDAR.supportedYears.includes(parsed.getUTCFullYear()) && !isSupportedSession(tradeDate)) {
    return result("invalid", "快照不是已支持的交易日", "请核对采集日期，未替换原始记录。");
  }
  if (expectedDate && tradeDate > expectedDate) return result("invalid", "快照日期晚于可用收盘日", `当前可用收盘日为 ${expectedDate}，请核对日期。`);
  if (historical) return result("historical", "正在查看历史快照", `本区域只展示 ${tradeDate} 保存的数据；独立即时资金榜不随此日期回放。`);
  if (!now) return result("checking", "保存快照 · 正在核对时效", "日期按北京时间及收盘后数据可用窗口核对；采集时间不等于行情日期。");
  if (!expectedDate) return result("calendar-unknown", "当前年份交易日历尚未配置", "未据周末规则猜测最新交易日，日期新旧暂不自动判定。");
  if (tradeDate < expectedDate) return result("stale", "快照尚未更新到最近收盘日", `当前保存 ${tradeDate}，按已有交易日历最近可用收盘日为 ${expectedDate}。查看页面不会更新日报；更新请运行 run_daily.cmd。`);
  return result("current", "日期已对齐最近可用收盘日", "这只表示日期一致，不代表来源完整或情绪分类准确。");
}

export function displayBeijingTime(value?: string): string {
  if (!value) return "未记录";
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime()) ? parsed.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false }) : "时间格式异常";
}

export function knownCount(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : null;
}

export function coveragePercent(observed: unknown, expected: unknown): number | null {
  const n = knownCount(observed), total = knownCount(expected);
  return n != null && total != null && total > 0 && n <= total ? 100 * n / total : null;
}

/** Counts in different sectors overlap. Never sum them into market-wide people. */
export function reportQuality(report: DailyReport) {
  const sectors = report.sectors;
  const feedObserved = knownCount(report.meta.feedObserved), feedExpected = knownCount(report.meta.feedExpected);
  const feedComplete = knownCount(report.meta.feedComplete);
  return {
    sectors: sectors.length, feedObserved, feedExpected, feedComplete,
    sourceCoverage: coveragePercent(feedObserved, feedExpected),
    completeCoverage: coveragePercent(feedComplete, feedExpected),
    completeSectors: sectors.filter(s => s.observation.memberTotal > 0 && s.observation.complete).length,
    publishedScores: sectors.filter(s => typeof s.leekScore?.score === "number" && Number.isFinite(s.leekScore.score)).length,
    highUnknownSectors: sectors.filter(s => (s.expressionProfile?.unknownRate ?? -1) > FOLLOWING_METHOD.maximumUnknownRate).length,
    errors: report.meta.errors.length,
  };
}

/** Missing fields on historical captures stay unknown rather than silently becoming zero. */
export function sectorQuality(sector: ReportSector) {
  const p = sector.expressionProfile, o = sector.observation;
  const unmatched = knownCount(p?.unmatchedAccounts), unsampled = knownCount(p?.unsampledAccounts);
  const unknown = knownCount(p?.unknownAccounts);
  const content = o.contentCoverage;
  const counts = content ? [content.bodyTexts, content.titleOnlyTexts, content.unspecifiedTexts, content.total].map(knownCount) : [];
  const contentValid = counts.length === 4 && counts.every(n => n != null) &&
    counts.slice(0, 3).reduce<number>((sum, n) => sum + (n ?? 0), 0) === counts[3] && counts[3] === o.sampleCount;
  return {
    unmatched: unmatched != null && unsampled != null && unknown === unmatched + unsampled ? unmatched : null,
    unsampled: unmatched != null && unsampled != null && unknown === unmatched + unsampled ? unsampled : null,
    identityMissingPosts: knownCount(o.unknownAuthorPosts),
    bodyTexts: contentValid ? content!.bodyTexts : null,
    titleOnlyTexts: contentValid ? content!.titleOnlyTexts : null,
    unspecifiedTexts: contentValid ? content!.unspecifiedTexts : null,
    enrichedBodies: knownCount(o.bodyObserved),
  };
}

/** Legacy snapshots expose valid aggregate breadth, but not a fabricated distribution. */
export function netAdvanceShare(market: { up: number; down: number; flat: number; quoted: number }): number | null {
  const values = [market.up, market.down, market.flat, market.quoted].map(knownCount);
  if (values.some(n => n == null) || market.quoted <= 0 || market.up + market.down + market.flat !== market.quoted) return null;
  return 100 * (market.up - market.down) / market.quoted;
}
