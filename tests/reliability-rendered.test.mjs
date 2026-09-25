import assert from "node:assert/strict";
import test from "node:test";

// Exercise the real production worker using saved snapshots. No outbound fetch.
test("saved snapshots render quality panels without fabricated new numeric fields", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  const { default: worker } = await import(workerUrl.href);
  const response = await worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
  assert.equal(response.status, 200);
  const html = await response.text();
  for (const label of ["这份报告的数据够不够", "已读完整窗口", "未记录", "客观行情诊断", "净上涨广度", "前10股成交额占比", "规则未命中"]) assert.ok(html.includes(label), label);
  assert.doesNotMatch(html, /NaN|Infinity|undefined%|L1\+L2占35/);
});
