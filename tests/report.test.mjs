import assert from "node:assert/strict";
import test from "node:test";
import { temperatureTone, rankFlows } from "../lib/report-presentation.ts";

test("temperature colours keep unknown, zero and threshold values distinct", () => {
  for (const [value, key] of [[null,"missing"],[NaN,"missing"],[0,"cold"],[19.9,"cold"],[20,"cool"],[40,"neutral"],[60,"warm"],[80,"hot"],[100,"hot"]]) assert.equal(temperatureTone(value).key,key);
});

test("fund rankings separate taxonomy, signs and descending outflow magnitude", () => {
  const rows = [{code:"a",kind:"industry",net:2},{code:"b",kind:"industry",net:9},{code:"c",kind:"industry",net:-30},{code:"d",kind:"industry",net:-5},{code:"e",kind:"industry",net:0},{code:"f",kind:"concept",net:900}];
  assert.deepEqual(rankFlows(rows,"industry","in").map(r=>r.code),["b","a"]);
  assert.deepEqual(rankFlows(rows,"industry","out").map(r=>r.code),["c","d"]);
  assert.deepEqual(rankFlows(rows,"concept","in").map(r=>r.code),["f"]);
  assert.equal(rows[0].code,"a");
});
