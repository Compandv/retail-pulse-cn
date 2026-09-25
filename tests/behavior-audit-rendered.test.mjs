import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// Render the actual component with new and legacy records; no fixture mutation
// or data collection is needed to exercise the conditional audit columns.
const source = readFileSync(new URL("../app/FollowingComposition.tsx", import.meta.url), "utf8");
let compiled = ts.transpileModule(source, { compilerOptions: {
  jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022,
} }).outputText;
for (const specifier of ["react", "react/jsx-runtime", "../lib/following-method"]) {
  const resolved = specifier.startsWith(".") ? new URL("../lib/following-method.ts", import.meta.url).href : import.meta.resolve(specifier);
  compiled = compiled.replaceAll(`"${specifier}"`, JSON.stringify(resolved));
}
const { FollowingComposition } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
const saved = JSON.parse(readFileSync(new URL("../public/data/report/latest.json", import.meta.url), "utf8"));

test("audit columns preserve missing scores and identify the conditional denominator", () => {
  const report = structuredClone(saved);
  const profile = report.sectors[0].expressionProfile;
  profile.behaviorAudit = { version: "behavior-audit-0.1", targetAccounts: 20, judgedAccounts: 50, coverage: 50, score: null };
  const html = renderToStaticMarkup(React.createElement(FollowingComposition, { report }));
  assert.ok(html.includes("追涨表达比例（试验）"));
  assert.ok(html.includes("20/50 个可判断账户"));
  assert.ok(html.includes("50.0%"));
  assert.ok(html.includes("旧快照未记录"));
  assert.ok(html.includes("原口径排序不变"));
  assert.doesNotMatch(html, /NaN|undefined%/);
});

test("legacy snapshots do not acquire fabricated audit data", () => {
  const report = structuredClone(saved);
  for (const sector of report.sectors) delete sector.expressionProfile?.behaviorAudit;
  const html = renderToStaticMarkup(React.createElement(FollowingComposition, { report }));
  assert.ok(!html.includes("追涨表达比例（试验）"));
});
