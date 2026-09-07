import assert from "node:assert/strict";
import test from "node:test";
import { parseEastmoney, parseThs, collectLiveFlows, liveFlowRanking } from "../lib/fund-flow.ts";
import { rankProfiles } from "../lib/report-presentation.ts";

function html(page, pages, code, ordinal, net = "-2.50") { return `<table class="m-table J-ajax-table"><thead><th>流入资金(亿)</th><th>净额(亿)</th></thead><tr><td>${ordinal}</td><td><a href="http://q.10jqka.com.cn/thshy/detail/code/${code}/">测试行业</a></td><td>123</td><td>1.2%</td><td>10</td><td>12.5</td><td>${net}</td><td>10</td></tr></table><span class="page_info">${page}/${pages}</span>`; }

test("platforms retain their own units, fields and missing times", () => {
  const ths = parseThs(html(1,1,"881001",1), "industry").rows[0];
  assert.equal(ths.net, -250000000); assert.equal(ths.ratio, null); assert.equal(ths.sourceTime, null);
  const em = parseEastmoney(JSON.stringify({data:{total:1,diff:[{f12:"BK1001",f14:"示例",f62:-250000000,f184:-2.3,f3:1.2,f66:-1,f72:-2,f124:1788495600}]}}), "concept").rows[0];
  assert.equal(em.net, ths.net); assert.equal(em.ratio, -2.3); assert.ok(em.sourceTime); assert.equal(em.extraLarge,-1);
  assert.throws(() => parseThs("<script>login()</script>", "industry"));
  assert.throws(() => parseThs(html(1,1,"881001",1).replace('page_info','missing'), "industry"));
});

test("all platform pages enter ranking without local industry filters", async () => {
  const fetcher = async url => url.includes("page/2/") ? html(2,2,"881999",2,"4") : html(1,2,"881001",1);
  const result = await collectLiveFlows("ths","industry",fetcher);
  assert.equal(result.complete,true); assert.equal(result.rows.length,2); assert.equal(result.expected,2);
  assert.equal(liveFlowRanking(result.rows,"in")[0].code,"881999");
  assert.equal(liveFlowRanking(result.rows,"out")[0].code,"881001");
});

test("duplicate or failed pages cannot become a complete ranking", async () => {
  let result = await collectLiveFlows("ths","industry",async url => url.includes("page/2/") ? html(2,2,"881001",2) : html(1,2,"881001",1));
  assert.equal(result.complete,false); assert.ok(result.errors.length);
  result = await collectLiveFlows("ths","industry",async url => { if(url.includes("page/2/")) throw new Error("timeout"); return html(1,2,"881001",1); });
  assert.equal(result.complete,false); assert.equal(result.rows.length,1);
});

test("Eastmoney follows returned page size, not a presumed fixed sector count", async () => {
  const result = await collectLiveFlows("eastmoney","concept",async url => {
    const page = Number(new URL(url).searchParams.get("pn"));
    return JSON.stringify({data:{total:3,diff:(page === 1 ? [1,2] : [3]).map(n=>({f12:`BK100${n}`,f14:`新概念${n}`,f62:n*1e8,f184:n,f3:n}))}});
  });
  assert.equal(result.complete,true); assert.equal(result.rows.length,3);
});

test("profile ranking uses eligible account shares and keeps unknowns last", () => {
  const rows=[{id:"a",retailProfile:{eligible:true,l1l2Share:60,coverage:80}},{id:"b",retailProfile:{eligible:false,l1l2Share:null,coverage:0}},{id:"c",retailProfile:{eligible:true,l1l2Share:80,coverage:30}}];
  assert.deepEqual(rankProfiles(rows).map(r=>r.id),["c","a","b"]); assert.equal(rows[0].id,"a");
});
