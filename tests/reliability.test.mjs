import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { snapshotHealth, coveragePercent, reportQuality, sectorQuality, netAdvanceShare } from "../lib/data-quality.ts";
import { FOLLOWING_METHOD, FOLLOWING_FORMULA, FOLLOWING_EXPLANATION, MEASUREMENT_ANSWER, expectedReportMethod, savedFollowingFormula } from "../lib/following-method.ts";
import { latestSupportedSession } from "../lib/trading-calendar.ts";

const now = new Date("2026-09-15T20:00:00+08:00");
const health = (overrides = {}) => snapshotHealth({ tradeDate: "2026-09-15", methodVersion: FOLLOWING_METHOD.topicAnalysisVersion, expectedMethodVersion: FOLLOWING_METHOD.topicAnalysisVersion, now, ...overrides });
const sector = () => ({
  id: "one", name: "测试", observation: { authors: 20, sampleCount: 20, memberTotal: 2, memberObserved: 2, memberComplete: 1, complete: false },
  expressionProfile: { observedAccounts: 20, unknownAccounts: 12, unknownRate: 60 },
  leekScore: { score: null },
});

test("historical weights are displayed as saved rather than replaced with the current formula", () => {
  assert.equal(savedFollowingFormula({ following: 1 }), "跟随决策 100%");
  assert.equal(savedFollowingFormula({ chase: .25, hype: .75 }), "明确追涨 25% + 无依据喊涨 75%");
  assert.equal(savedFollowingFormula(), "未记录或权重无效");
  assert.equal(savedFollowingFormula({ chase: NaN }), "未记录或权重无效");
  assert.equal(savedFollowingFormula({ chase: .2 }), "未记录或权重无效");
});

// Tests only use local fixtures. No model API or remote market data is requested.
test("shared following definitions agree with Python and retire the active old formula", () => {
  assert.deepEqual(FOLLOWING_METHOD.weights, { following: .3, chase: .4, question: .2, hype: .1 });
  for (const [key, weight] of Object.entries(FOLLOWING_METHOD.weights)) assert.ok(FOLLOWING_FORMULA.includes(`${FOLLOWING_METHOD.labels[key]} ${weight * 100}%`));
  assert.ok(FOLLOWING_EXPLANATION.includes("未知账户"));
  assert.doesNotMatch(MEASUREMENT_ANSWER, /L1\+L2|35%/);
  assert.equal(expectedReportMethod({ discovery: {} }), FOLLOWING_METHOD.topicAnalysisVersion);
  assert.equal(expectedReportMethod({}), FOLLOWING_METHOD.version);
  const source = readFileSync(new URL("../app/MeasurementDashboard.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(source, /L1\+L2占35%|L1\+L2 35%|韭菜分使用 L1/);
  assert.ok(source.includes("setAnswer(MEASUREMENT_ANSWER)"));
  const result = spawnSync(process.env.PYTHON_BIN || "python", ["-c", "import json; from sentiment.following import METHOD; print(json.dumps(METHOD))"], { encoding: "utf8", env: { ...process.env, PYTHONUTF8: "1" } });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), FOLLOWING_METHOD);
});

test("freshness and method mismatch are independent", () => {
  assert.equal(health().state, "current");
  const stale = health({ tradeDate: "2026-09-07", methodVersion: "following-topic-2.0" });
  assert.equal(stale.state, "stale");
  assert.equal(stale.expectedDate, "2026-09-15");
  assert.equal(stale.methodMismatch, true);
  assert.equal(health({ methodVersion: undefined }).methodMismatch, true);
  assert.equal(health({ tradeDate: "2026-09-07", historical: true }).state, "historical");
});

test("historical browsing does not suppress invalid or future date checks", () => {
  for (const date of ["2026-02-30", "2026-05-01", "2026-09-12", "2026-09-16", "oops"]) assert.equal(health({ tradeDate: date, historical: true }).state, "invalid", date);
});

test("SSR has a stable checking state and unsupported calendars remain unknown", () => {
  assert.equal(health({ now: null }).state, "checking");
  assert.equal(health({ now: new Date("2027-01-05T12:00:00Z") }).state, "calendar-unknown");
  assert.equal(latestSupportedSession(new Date("2027-01-05T12:00:00Z")), null);
  assert.equal(latestSupportedSession(new Date("invalid")), null);
});

test("freshness follows the existing Beijing 15:30 availability window", () => {
  assert.equal(latestSupportedSession(new Date("2026-09-15T15:29:59+08:00")), "2026-09-14");
  assert.equal(latestSupportedSession(new Date("2026-09-15T15:30:00+08:00")), "2026-09-15");
  assert.equal(latestSupportedSession(new Date("2026-09-13T20:00:00+08:00")), "2026-09-11");
  assert.equal(latestSupportedSession(new Date("2026-09-25T20:00:00+08:00")), "2026-09-24");
});

test("coverage distinguishes unknown, empty, zero and corrupt denominators", () => {
  for (const [a,b] of [[null,10],[0,0],[11,10],[-1,10],[1,NaN],[true,10],["1",10],[.5,10]]) assert.equal(coveragePercent(a,b), null);
  assert.equal(coveragePercent(0,10), 0);
  assert.equal(coveragePercent(8,10), 80);
});

test("legacy reports do not manufacture complete-source or body coverage", () => {
  const old = { meta: { feedObserved: 2, feedExpected: 2, errors: [] }, sectors: [sector()] };
  const q = reportQuality(old);
  assert.equal(q.sourceCoverage, 100);
  assert.equal(q.completeCoverage, null);
  assert.equal(q.feedComplete, null);
  assert.equal(q.publishedScores, 0);
  assert.equal(q.highUnknownSectors, 1);
  const details = sectorQuality(old.sectors[0]);
  assert.equal(details.unmatched, null);
  assert.equal(details.unsampled, null);
  assert.equal(details.bodyTexts, null);
  assert.equal(details.enrichedBodies, null);
  assert.equal(details.identityMissingPosts, null);
});

test("quality audits enforce count identities without reclassifying unknowns", () => {
  const s = sector();
  Object.assign(s.expressionProfile, { unmatchedAccounts: 10, unsampledAccounts: 2 });
  Object.assign(s.observation, { contentCoverage: { total: 20, bodyTexts: 4, titleOnlyTexts: 6, unspecifiedTexts: 10 }, bodyObserved: 0, unknownAuthorPosts: 0 });
  const before = structuredClone(s);
  const q = sectorQuality(s);
  assert.equal(q.unmatched, 10);
  assert.equal(q.unsampled, 2);
  assert.equal(q.bodyTexts, 4);
  assert.equal(q.enrichedBodies, 0);
  assert.equal(q.identityMissingPosts, 0);
  assert.deepEqual(s, before);
  s.expressionProfile.unsampledAccounts = 3;
  s.observation.contentCoverage.total = 21;
  assert.equal(sectorQuality(s).unmatched, null);
  assert.equal(sectorQuality(s).bodyTexts, null);
});

test("legacy breadth uses only consistent saved stock counts", () => {
  assert.equal(netAdvanceShare({ up: 6, down: 3, flat: 1, quoted: 10 }), 30);
  assert.equal(netAdvanceShare({ up: 0, down: 0, flat: 10, quoted: 10 }), 0);
  assert.equal(netAdvanceShare({ up: 0, down: 0, flat: 0, quoted: 0 }), null);
  assert.equal(netAdvanceShare({ up: 6, down: 3, flat: 0, quoted: 10 }), null);
  assert.equal(netAdvanceShare({ up: NaN, down: 0, flat: 0, quoted: 10 }), null);
});
