import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// Transpile the real long-form components; next/link is replaced by a plain anchor.
const toModule = code => `data:text/javascript;base64,${Buffer.from(code).toString("base64")}`;
const linkStub = toModule(`import { jsx } from ${JSON.stringify(import.meta.resolve("react/jsx-runtime"))}; export default function Link({ href, children }) { return jsx("a", { href, children }); }`);
function compile(file, extra = {}) {
  let code = ts.transpileModule(readFileSync(new URL(`../app/${file}`, import.meta.url), "utf8"), { compilerOptions: {
    jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
  const map = { react: import.meta.resolve("react"), "react/jsx-runtime": import.meta.resolve("react/jsx-runtime"), "next/link": linkStub, ...extra };
  for (const [specifier, target] of Object.entries(map)) code = code.replaceAll(`"${specifier}"`, JSON.stringify(target));
  return toModule(code);
}
const ui = compile("longform-ui.tsx", { "html-to-image": toModule("export const toPng = async () => '';") });
const { LongformDailyView } = await import(compile("LongformDailyView.tsx", { "./longform-ui": ui }));
const { LongformWeeklyView } = await import(compile("LongformWeeklyView.tsx", { "./longform-ui": ui }));
const read = path => JSON.parse(readFileSync(new URL(`../public/data/${path}`, import.meta.url), "utf8"));
const FORBIDDEN = JSON.parse(readFileSync(new URL("../config/longform.json", import.meta.url), "utf8")).forbidden;
const visible = html => html.replace(/<[^>]+>/g, " ");

test("daily long-form renders every section, missing values and the risk notice", () => {
  // Saved data changes daily; one topic is stripped of a dimension so the missing path always renders.
  const data = structuredClone(read("longform/latest.json"));
  Object.assign(data.topics[0], { total: null, missing: ["动摇度"], dimensions: { ...data.topics[0].dimensions, shake: null } });
  const html = renderToStaticMarkup(React.createElement(LongformDailyView, { initial: data }));
  for (const label of ["五支温度计", "涨停生态", "十强题材排名", "逐格对比", "题材卡片", "资金底账", "市场底账", "口径说明", "不构成任何投资建议", "导出长图 PNG"]) assert.ok(html.includes(label), label);
  assert.ok(html.includes("缺动摇度"), "missing dimensions are named");
  assert.doesNotMatch(html, /NaN|undefined|null%/);
});

test("weekly long-form shows the published ranking with synthetic topics", () => {
  const data = structuredClone(read("weekly/latest.json"));
  const dims = { heat: 80, spread: 70, shake: 70, rebound: 50, crowding: 78 };
  data.meta.topicsPublished = true;
  data.topics = [
    { id: "a", name: "题材甲", days: ["2026-09-21", "2026-09-22"], appearances: 2, scoredDays: 2, total: 72.4, dimensions: dims, missing: [], limitUps: 5, meanChange: 1.2, totalChange: null, isNew: true,
      shape: { key: "hotShaky", label: "高热高动摇", reference: "镰刀型", text: "关注度和恐慌表达同时处于本表高位" }, alert: { level: "red", text: "换手与恐慌表达同处本表高位" } },
    { id: "b", name: "题材乙", days: ["2026-09-21"], appearances: 1, scoredDays: 0, total: null, dimensions: { ...dims, shake: null }, missing: ["动摇度"], limitUps: 0, meanChange: null, totalChange: null, isNew: false,
      shape: { key: "neutral", label: "中性", reference: null, text: "各维度没有突出的组合" }, alert: { level: "grey", text: "数据不足" } },
  ];
  const html = renderToStaticMarkup(React.createElement(LongformWeeklyView, { initial: data }));
  for (const label of ["题材甲 周分最高", "高热高动摇", "红灯", "缺动摇度", "五维雷达", "分维度排行", "市场时间线", "不构成任何投资建议"]) assert.ok(html.includes(label), label);
  assert.ok(!html.includes("本周不发布题材排名"));
  assert.doesNotMatch(html, /NaN|undefined/);
});

test("weekly long-form without enough days explains the missing ranking", () => {
  const data = structuredClone(read("weekly/latest.json"));
  Object.assign(data.meta, { topicsPublished: false, longformDays: data.meta.longformDays.slice(0, 1) });
  data.topics = [];
  const html = renderToStaticMarkup(React.createElement(LongformWeeklyView, { initial: data }));
  assert.ok(html.includes("本周不发布题材排名"));
  assert.ok(html.includes("上证指数"));
});

test("generated wording contains no advice words", () => {
  // Only text this project writes: board names and quoted posts are source data.
  const daily = read("longform/latest.json"), weekly = read("weekly/latest.json");
  const written = [daily.narrative.title, daily.narrative.oneLiner, ...Object.values(daily.narrative.topics),
    ...daily.topics.flatMap(t => [t.shape.text, t.alert.text]), ...daily.meta.notes,
    weekly.narrative.title, weekly.narrative.oneLiner, ...weekly.narrative.conclusions, weekly.narrative.summary, ...weekly.meta.notes];
  for (const text of written) for (const word of FORBIDDEN) assert.ok(!text.includes(word), `${word}: ${text}`);
  const chrome = visible(renderToStaticMarkup(React.createElement(LongformDailyView, { initial: { ...daily, topics: [], flows: { industry: { inflow: [], outflow: [] }, concept: { inflow: [], outflow: [] } } } })));
  for (const word of FORBIDDEN) assert.ok(!chrome.replace(/不构成任何投资建议|不是买卖信号/g, "").includes(word), word);
});
