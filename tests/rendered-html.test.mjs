import assert from "node:assert/strict";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("renders the sentiment dashboard", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /<title>散户温度计｜A股社区情绪<\/title>/);
  assert.match(html, /市场有温度/);
  assert.match(html, /综合散户温度/);
  assert.match(html, /代表池赚钱效应/);
  assert.match(html, /升温板块/);
  assert.match(html, /(?:演示快照|实测快照)/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton/);
});
