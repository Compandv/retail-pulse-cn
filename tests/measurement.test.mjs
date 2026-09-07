import assert from "node:assert/strict";
import test from "node:test";
import { spawnSync } from "node:child_process";
import { classifyText, prepareObservations, summarizeExpressions, historicalPercentile, METHOD_VERSION, universeKey } from "../lib/measurement.ts";
import { collectFeed, collectTrading, summarizeTrading, latestSession, validSession } from "../lib/observations.ts";

const examples = [
  ["加仓加仓加仓，趋势向上，加仓猛干！", "chase_intent", true, "unknown"],
  ["今天追高买入了", "reported_chase", true, "unknown"],
  ["不要追高，涨停也不买", "avoid", false, "unknown"],
  ["你们喊涨停我就要追吗？", "avoid", false, "unknown"],
  ["别人追高，我观望", "quoted", false, "unknown"],
  ["昨天追高买入了", "past", false, "unknown"],
  ["2:30来个涨停好不好", "wish", false, "unknown"],
  ["冲，这是洗盘，大概率涨停", "chase_intent", true, "unknown"],
  ["现在还能追高吗？", "chase_question", false, "unknown"],
  ["持续下跌，加仓补仓", "buy", false, "unknown"],
  ["满仓了，不是新手", "aggressive_buy", false, "unknown"],
  ["跟着老师买入了", "buy", false, "unknown"],
  ["我是新手，第一次买股票，怎么下单？", "discussion", false, "unknown"],
  ["我不是小白，不要追高", "avoid", false, "unknown"],
  ["我的计划是分批买入，跌破10元就止损，单次仓位不超过10%。", "buy", false, "unknown"],
  ["如果突破失败，我会把仓位控制在十分之一；否则保持观望。最坏情景下回撤超过百分之五就止损，避免单一判断。", "discussion", false, "unknown"],
  ["根据公司年报披露的现金流和利润率数据，与同行比较，目前估值低于相近企业，但这依赖未来产能利用率的假设。需要对比不同成本曲线，评估行业需求下降时的回撤风险。如果数据来源发生变化，应重新计算估值，而不是只看今天股价涨跌。", "discussion", false, "unknown"],
  ["国资券商，费率可调，开户享新客专属福利", null, false, null],
];

test("context regression: wishes, negations, quotes and past trades are not current chasing", () => {
  for (const [text, intent, chase, level] of examples) {
    const result = classifyText(text);
    if (intent == null) { assert.equal(result, null, text); continue; }
    assert.equal(result.intent, intent, text);
    assert.equal(result.chase, chase, text);
    assert.equal(result.level, level, text);
  }
  assert.equal(classifyText("不要追高，涨停也不买").bullish, false);
  assert.equal(classifyText("盈利清仓止盈").panic, false);
});

const post = (id, author, text, date = "2026-09-04 10:00:00") => ({ id, author, text, date, source: "eastmoney", code: "920970", url: "" });
test("count distinct people before author sampling; do not erase identical crowd expressions", () => {
  const rows = [post("1", "a", "涨停加油"), post("2", "b", "涨停加油"), post("3", "a", "涨停加油"), ...[4, 5, 6, 7].map(i => post(String(i), "a", `今天第${i}次买入`)), post("8", "", "观察行情"), post("9", "", "观察行情"), post("10", "z", "今天追高买入了", "2026-08-26 10:00:00"), post("11", "z", "今天追高买入了", "2026-09-04 15:00:01")];
  const prepared = prepareObservations(rows, "2026-09-04", "15:00:00");
  assert.equal(prepared.observedAuthors, 2);
  assert.equal(prepared.observedPosts, 8);
  assert.equal(prepared.unknownAuthorPosts, 2);
  assert.equal(prepared.excludedDate, 2);
  assert.equal(prepared.analyzed.length, 6);
  const summary = summarizeExpressions(prepared.analyzed);
  assert.equal(summary.levels.reduce((sum, row) => sum + row.count, 0), summary.sampleCount);
  assert.equal(summary.levels.find(row => row.key === "unknown").share, 100);
  assert.equal(summarizeExpressions([]).chase, null);
});

test("historical rank requires comparable prior measured dates and complete current coverage", () => {
  const universe = universeKey(["920970"]);
  const history = Array.from({ length: 20 }, (_, i) => ({ date: `2026-08-${String(i + 1).padStart(2, "0")}`, value: i + 1, complete: true, universe, methodVersion: METHOD_VERSION, recordType: "measured", cutoff: "15:00:00" }));
  const run = (rows, complete = true, value = 10) => historicalPercentile(value, rows, "2026-09-04", universe, complete, "15:00:00");
  assert.equal(run(history).score, 47.5);
  assert.equal(run([...history, { ...history[0], date: "2026-09-04", value: 0 }, { ...history[0], date: "2026-09-05", value: 0 }]).score, 47.5);
  assert.equal(run(history, false).score, null);
  assert.equal(run(history, true, null).score, null);
  assert.equal(run(history.map(row => ({ ...row, recordType: "estimated" }))).score, null);
  assert.equal(run(history.map(row => ({ ...row, methodVersion: "MVP-3.0" }))).score, null);
  assert.equal(run(history.map(row => ({ ...row, universe: "different basket" }))).score, null);
  assert.equal(run(history.map(row => ({ ...row, cutoff: "23:59:59" }))).score, null);
  assert.equal(run([...history.slice(0, 19), history[0]]).score, null);
  assert.equal(run(history, true, 30).score, 100);
});

test("Python and online V4 classification and aggregation agree", () => {
  const rows = examples.filter(row => row[1] != null).map(([text], i) => post(String(i), String(i), text));
  const script = "import json,sys\nfrom sentiment.measurement import classify_text,prepare_observations,summarize_expressions\nr=json.load(sys.stdin)\np=prepare_observations(r,'2026-09-04','15:00:00')\nprint(json.dumps({'classification':[classify_text(x['text']) for x in r],'summary':summarize_expressions(p['analyzed'])},ensure_ascii=False))";
  const response = spawnSync(process.env.PYTHON_BIN || "python", ["-c", script], { input: JSON.stringify(rows), encoding: "utf8", env: { ...process.env, PYTHONUTF8: "1" } });
  assert.equal(response.status, 0, response.stderr);
  const python = JSON.parse(response.stdout);
  assert.deepEqual(python.classification, rows.map(row => classifyText(row.text)));
  assert.deepEqual(python.summary, summarizeExpressions(prepareObservations(rows, "2026-09-04", "15:00:00").analyzed));
});

test("feed pagination does not stop at a pinned old post, and repeated pages remain incomplete", async () => {
  const original = globalThis.fetch;
  let requests = 0;
  const row = { stockbar_code: "920970", post_type: 0, post_id: "1", user_id: "a", post_title: "今天追高买入了", post_publish_time: "2026-09-04 10:00:00", post_last_time: "2026-09-04 10:00:00", post_top_status: 0 };
  globalThis.fetch = async () => { requests++; return Response.json({ re: [...Array.from({ length: 99 }, (_, i) => ({ ...row, post_id: String(i) })), { ...row, post_id: "old", post_top_status: 1, post_publish_time: "2026-08-26 10:00:00", post_last_time: "2026-08-26 10:00:00" }] }); };
  try { const result = await collectFeed("920970", "2026-09-04"); assert.equal(requests, 2); assert.equal(result.complete, false); assert.match(result.reason, /重复/); }
  finally { globalThis.fetch = original; }
});

test("selected-date trading baseline ignores future rows and does not invent prices", async () => {
  const original = globalThis.fetch;
  const history = Array.from({ length: 20 }, (_, i) => [`2026-08-${String(i + 1).padStart(2, "0")}`, "10", "10", "11", "9", String(100 + i)]);
  history.push(["2026-09-04", "10", "11", "11", "10", "1000"], ["2026-09-05", "11", "100", "100", "11", "100000"]);
  globalThis.fetch = async request => String(request).includes("fqkline") ? Response.json({ data: { bj920970: { day: history } } }) : new Response("", { status: 503 });
  try {
    const result = await collectTrading("920970", "2026-09-04");
    assert.equal(result.price, 11); assert.equal(result.changePct, 10); assert.equal(result.activityScore, 100); assert.equal(result.baselineDays, 20);
    assert.equal(result.turnover, null);
    assert.equal(summarizeTrading([result, { ...result, activityScore: null }, { ...result, activityScore: null }]).score, null);
    assert.equal(summarizeTrading([result]).score, 100);
  } finally { globalThis.fetch = original; }
});

test("query dates use Shanghai sessions and validate calendar dates", () => {
  const now = new Date("2026-09-05T10:00:00Z");
  assert.equal(latestSession(now), "2026-09-04");
  assert.equal(validSession("2026-09-04", now), true);
  for (const value of ["2026-09-05", "2026-09-07", "2026-02-30", "2026-05-01", "2025-12-31"]) assert.equal(validSession(value, now), false, value);
});
