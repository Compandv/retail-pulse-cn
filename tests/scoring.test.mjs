import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { analyzeText, scorePosts, scoreBand, participantIndices } from "../lib/scoring.ts";
import { answerResearchQuestion } from "../lib/research.ts";

test("full scale, empty samples and band boundaries", () => {
  const strong = { novice: 1, fomo: 1, panic: 1, direction: 1, matched: [] };
  assert.equal(scorePosts(Array(80).fill(strong)).overall, 100);
  assert.equal(scorePosts([]), null);
  assert.equal(scoreBand(0).label, "冷清");
  assert.equal(scoreBand(20).label, "温和");
  assert.equal(scoreBand(40).label, "活跃");
  assert.equal(scoreBand(60).label, "高热");
  assert.equal(scoreBand(80).label, "极热");
  assert.equal(scoreBand(null).label, "暂无样本");
});

test("Python daily scoring and online scoring agree on the same samples", () => {
  const texts = ["小白第一次上车，梭哈满仓必涨！！！", "亏麻了割肉清仓，救命！！！", "今天讨论一下成交量", "大佬，明天能买吗？", "添加微信老师带单", "看多加仓", "看空出货", "不玩了，跌停跑了"];
  const groups = [texts, [texts[0]], Array(100).fill(texts[1]), [], [texts[2]], [texts[3], texts[5], texts[6]]];
  const script = `import json,sys\nfrom datetime import datetime\nfrom sentiment.models import Post\nfrom sentiment.analyzer import analyze_post\nfrom sentiment.scoring import score_source\nfrom sentiment.pipeline import _participant_indices\nresults=[]\nfor texts in json.load(sys.stdin):\n posts=[analyze_post(Post('eastmoney','x','x',text,datetime(2026,9,4),'a')) for text in texts]\n metrics=score_source([post for post in posts if post is not None])\n results.append({**metrics,**_participant_indices(metrics)})\nprint(json.dumps(results))`;
  const result = spawnSync(process.env.PYTHON_BIN || "python", ["-c", script], { input: JSON.stringify(groups), encoding: "utf8", env: { ...process.env, PYTHONUTF8: "1" } });
  assert.equal(result.status, 0, `Python unavailable or failed: ${result.stderr}`);
  JSON.parse(result.stdout).forEach((expected, index) => {
    const scores = scorePosts(groups[index].map(analyzeText).filter(Boolean));
    if (!scores) { assert.equal(expected.overall, null); return; }
    for (const [key, value] of Object.entries({ ...scores, ...participantIndices(scores) })) assert.equal(value, expected[key], `group ${index}, ${key}`);
  });
});

test("research answers do not turn missing baselines into a warming ranking", () => {
  const sector = { id: "gold", name: "黄金", overall: 52, heat: 60, heatChange: 0, heatChangeAvailable: false };
  const snapshot = { meta: { methodVersion: "MVP-3.0" }, sectors: [sector] };
  const answer = answerResearchQuestion("今天哪些板块升温最快？", snapshot);
  assert.deepEqual(answer.sectorIds, []);
  assert.match(answer.text, /基线/);
  assert.match(answerResearchQuestion("明天股票会涨吗", snapshot).text, /无法回答/);
});
