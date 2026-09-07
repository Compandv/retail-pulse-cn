import assert from "node:assert/strict";
import test from "node:test";

async function render(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request(`http://localhost${path}`, { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("renders separated V4 measurements and explicit coverage", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  for (const label of ["社区关注热度", "成交活跃分", "追涨表达占比", "已观察账户", "今日板块轮动", "单股主题代理", "指定日期", "市场体温计", "六维温度", "资金正在流向哪些板块", "主力净流入", "主力净流出", "恐贪情绪", "韭菜分", "跟风追涨表达", "追涨询问", "未知账户", "模型汇总解读", "同花顺", "东方财富"]) assert.ok(html.includes(label), label);
  assert.equal((html.match(/class="thermometer-card/g) || []).length, 5);
  assert.ok(html.includes("heat-80"));
  assert.doesNotMatch(html, /综合散户温度|综合买入指数|新手入场|L1\+L2 表达|散户五级分层|类型未知/);
});

test("online date windows, stock and basket scopes, quote mapping and empty states", async () => {
  const original = globalThis.fetch;
  let empty = false, calls = 0;
  globalThis.fetch = async request => {
    calls++;
    const url = new URL(String(request));
    if (url.hostname === "qt.gtimg.cn") {
      const symbol = decodeURIComponent(url.pathname.slice("/q=".length));
      const fields = Array(39).fill("");
      Object.assign(fields, { 1: "Test stock", 2: symbol.slice(2), 3: "11", 4: "10", 30: "20260904153520", 32: "10", 37: "100", 38: "3" });
      return new Response(`v_${symbol}="${fields.join("~")}";`);
    }
    if (url.hostname === "web.ifzq.gtimg.cn") {
      const symbol = url.searchParams.get("param").split(",")[0];
      const day = Array.from({ length: 20 }, (_, i) => [`2026-08-${String(i + 1).padStart(2, "0")}`, "10", "10", "11", "9", "100"]);
      day.push(["2026-09-04", "10", "11", "11", "10", "1000"]);
      return Response.json({ data: { [symbol]: { day } } });
    }
    if (url.hostname === "gbapi.eastmoney.com") {
      const code = url.searchParams.get("code");
      const samples = [["今天追高买入了", "2026-09-04 10:00:00"], ["不要追高，涨停也不买", "2026-09-04 11:00:00"], ["今天追高买入了", "2026-08-26 10:00:00"], ["今天追高买入了", "2026-09-04 16:00:00"]];
      return Response.json({ re: empty ? [] : samples.map(([text, date], i) => ({ stockbar_code: code, post_type: 0, post_id: `${code}${i}`, user_id: `${code}${i}`, post_title: text, post_publish_time: date, post_last_time: date })) });
    }
    throw new Error(`Unexpected fetch: ${url}`);
  };
  try {
    for (const [q, symbol, market] of [["920970", "bj920970", "A股·北交所"], ["bj920970", "bj920970", "A股·北交所"], ["900901", "sh900901", "A股·沪市"], ["002714", "sz002714", "A股·深市"]]) {
      const response = await render(`/api/stock-query?q=${q}&date=2026-09-04`);
      assert.equal(response.status, 200);
      const result = await response.json();
      assert.equal(result.kind, "stock");
      assert.equal(result.symbol, symbol); assert.equal(result.market, market);
      assert.equal(result.name, "Test stock");
      assert.equal(result.trading.members[0].price, 11);
      assert.equal(result.expressions.sampleCount, 2);
      assert.equal(result.expressions.chase, 50);
      assert.equal(result.attention.excludedDate, 2);
      assert.equal(result.attention.score, null);
      assert.ok(result.posts.every(row => row.date.slice(0, 10) === "2026-09-04" && row.date.slice(11) <= "15:00:00" && !("author" in row)));
    }
    const basket = await (await render("/api/stock-query?q=" + encodeURIComponent("猪肉") + "&date=2026-09-04")).json();
    assert.equal(basket.kind, "basket"); assert.equal(basket.members.length, 8); assert.equal(basket.trading.total, 8);
    assert.equal(basket.expressions.sampleCount, 16); assert.equal(basket.attention.observedAuthors, 16);
    empty = true;
    const missing = await (await render("/api/stock-query?q=920970&date=2026-09-04")).json();
    assert.equal(missing.expressions.chase, null); assert.equal(missing.attention.score, null);
    assert.equal(missing.trading.score, 100);
    const before = calls;
    assert.equal((await render("/api/stock-query?q=920970&date=2099-01-01")).status, 400);
    assert.equal(calls, before);
  } finally { globalThis.fetch = original; }
});
