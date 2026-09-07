import assert from "node:assert/strict";
import test from "node:test";
import { spawnSync } from "node:child_process";
import { sortedBoards } from "../lib/market-ranking.ts";
import { collectBoardMembers } from "../lib/market-members.ts";
import { historicalPercentile, METHOD_VERSION, universeKey, classifyText } from "../lib/measurement.ts";

test("new sectors can rank first; search does not recompute relative scores", () => {
  const boards = [{ id: "new", code: "BK9999", name: "新热点", kind: "industry", changePct: 9, turnover: 2, relativeActivity: 44 }, { id: "old", code: "BK1000", name: "旧热点", kind: "industry", changePct: -1, turnover: 9, relativeActivity: 90 }, { id: "missing", code: "BK9998", name: "缺失", kind: "industry", changePct: null, turnover: null, relativeActivity: null }];
  assert.equal(sortedBoards(boards, "industry", "", "changePct")[0].id, "new");
  assert.equal(sortedBoards(boards, "industry", "", "turnover")[0].id, "old");
  assert.equal(sortedBoards(boards, "industry", "新热点", "turnover")[0].relativeActivity, 44);
  assert.equal(sortedBoards(boards, "industry", "", "turnover").at(-1).id, "missing");
});

test("discussion growth needs comparable history; zero base and incomplete capture do not invent growth", () => {
  const universe = universeKey(["000001"]);
  const history = Array.from({ length: 20 }, (_, i) => ({ date: `2026-08-${String(i+1).padStart(2,"0")}`, value: 100, universe, cutoff: "15:00:00", recordType: "measured", methodVersion: METHOD_VERSION, complete: true }));
  const run = (value, rows = history, complete = true) => historicalPercentile(value, rows, "2026-09-04", universe, complete, "15:00:00");
  const result = run(300);
  assert.equal(result.growthPct, 200); assert.equal(result.baselineMedian, 100); assert.equal(result.authorChange, 200);
  assert.equal(result.abnormalAttention, 1.092);
  assert.equal(run(300, history, false).growthPct, null);
  assert.equal(run(300, history.slice(0, 19)).growthPct, null);
  const zero = run(300, history.map(row => ({ ...row, value: 0 })));
  assert.equal(zero.growthPct, null); assert.equal(zero.lowBase, true);
  assert.equal(run(0, history.map(row => ({ ...row, value: 0 }))).score, 0);
  const script = "import json,sys\nfrom sentiment.measurement import historical_percentile\nv=json.load(sys.stdin)\nprint(json.dumps(historical_percentile(300,v['history'],'2026-09-04',v['universe'],True,'15:00:00'),ensure_ascii=False))";
  const response = spawnSync(process.env.PYTHON_BIN || "python", ["-c", script], { input: JSON.stringify({ history, universe }), encoding: "utf8", env: { ...process.env, PYTHONUTF8: "1" } });
  assert.equal(response.status, 0, response.stderr); assert.deepEqual(JSON.parse(response.stdout), result);
});

test("L1-L5 is deferred even for explicit novice and research language", () => {
  for (const text of ["我是新手，第一次买股票，怎么下单？", "跟着老师买入了", "如果上涨再分批买入，仓位不超过百分之十"] ) {
    const result = classifyText(text);
    assert.equal(result.level, "unknown");
    assert.ok(!result.evidence.some(value => value.startsWith("表达类型：")));
  }
});

test("board detail rejects historical membership substitution and detects repeated pages", async () => {
  const now = new Date("2026-09-05T10:00:00Z");
  await assert.rejects(collectBoardMembers("BK1512", "2026-09-03", now), /历史/);
  await assert.rejects(collectBoardMembers("..%2fanything", "2026-09-04", now), /代码/);
  const original = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json({ data: { total: 200, diff: Array.from({ length: 100 }, (_, i) => ({ f12: String(i+1).padStart(6,"0"), f14: "成分", f3: 4, f8: 5, f6: 100, f124: 1788507572 })) } }); };
  try { const result = await collectBoardMembers("BK1512", "2026-09-04", now); assert.equal(result.complete, false); assert.equal(calls, 2); assert.equal(result.members.length, 100); }
  finally { globalThis.fetch = original; }
});
