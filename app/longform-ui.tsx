"use client";
import { useState, type RefObject } from "react";
import type { DimensionKey, Dimensions } from "./longform-types";

export const DIMENSIONS: { key: DimensionKey; label: string }[] = [
  { key: "heat", label: "热度" }, { key: "spread", label: "扩散力" }, { key: "shake", label: "动摇度" }, { key: "rebound", label: "回补力" }, { key: "crowding", label: "拥挤度" },
];
export const LIGHT_LABEL = { red: "红", yellow: "黄", green: "绿", grey: "灰" } as const;

export const num = (value: number | null | undefined, digits = 1) => value == null ? "—" : value.toFixed(digits);
export const pct = (value: number | null | undefined, digits = 2) => value == null ? "—" : `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
export const yi = (value: number | null | undefined) => {
  if (value == null) return "—";
  if (Math.abs(value) >= 1e12) return `${(value / 1e12).toFixed(2)} 万亿`;
  return `${(value / 1e8).toFixed(Math.abs(value) >= 1e10 ? 0 : 2)} 亿`;
};
export const signClass = (value: number | null | undefined) => value == null || value === 0 ? "" : value > 0 ? "rise" : "fall";
export const heatClass = (value: number | null | undefined) => value == null ? "heat-missing" : value >= 80 ? "heat-80" : value >= 60 ? "heat-60" : value >= 40 ? "heat-40" : value >= 20 ? "heat-20" : "heat-0";

/** Five-axis radar. Missing axes are marked and the outline is not closed across them. */
export function Radar({ dims, size = 250 }: { dims: Dimensions; size?: number }) {
  const center = size / 2, radius = size / 2 - 42;
  const point = (index: number, value: number) => {
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / DIMENSIONS.length;
    return [center + Math.cos(angle) * radius * value / 100, center + Math.sin(angle) * radius * value / 100];
  };
  const complete = DIMENSIONS.every(d => dims[d.key] != null);
  const outline = complete ? DIMENSIONS.map((d, i) => point(i, dims[d.key] as number).join(",")).join(" ") : "";
  return <svg className="lf-radar" viewBox={`0 0 ${size} ${size}`} role="img" aria-label={"五维雷达：" + DIMENSIONS.map(d => `${d.label}${num(dims[d.key], 0)}`).join("、")}>
    {[25, 50, 75, 100].map(level => <polygon key={level} points={DIMENSIONS.map((_, i) => point(i, level).join(",")).join(" ")} className="lf-radar-grid" />)}
    {DIMENSIONS.map((d, i) => { const [x, y] = point(i, 100); return <line key={d.key} x1={center} y1={center} x2={x} y2={y} className="lf-radar-grid" />; })}
    {complete && <polygon points={outline} className="lf-radar-shape" />}
    {DIMENSIONS.map((d, i) => dims[d.key] == null ? null : <circle key={d.key} cx={point(i, dims[d.key] as number)[0]} cy={point(i, dims[d.key] as number)[1]} r={4} className="lf-radar-dot" />)}
    {DIMENSIONS.map((d, i) => { const [x, y] = point(i, 128); return <text key={d.key} x={x} y={y} textAnchor="middle" dominantBaseline="middle" className="lf-radar-label">{d.label} {num(dims[d.key], 0)}</text>; })}
  </svg>;
}

export function DimensionBars({ dims }: { dims: Dimensions }) {
  return <div className="lf-bars">{DIMENSIONS.map(d => <div key={d.key} className="lf-bar-row">
    <span>{d.label}</span>
    <div className="lf-bar-track"><i className={heatClass(dims[d.key])} style={{ width: `${dims[d.key] ?? 0}%` }} /></div>
    <b>{num(dims[d.key], 0)}</b>
  </div>)}</div>;
}

export function Light({ level, text }: { level: keyof typeof LIGHT_LABEL; text: string }) {
  return <span className={`lf-light lf-light-${level}`} title={text}><i aria-hidden="true" />{LIGHT_LABEL[level]}灯</span>;
}

export function RiskNotice({ compact = false }: { compact?: boolean }) {
  return <p className={compact ? "lf-risk lf-risk-compact" : "lf-risk"}>
    <strong>风险提示：</strong>本页为公开数据的统计与规则分类，仅供信息观察和研究，<strong>不构成任何投资建议</strong>。分数和标签描述的是题材之间的相对位置，不是买卖信号；数据可能延迟、缺失或出错。股市有风险，投资可能损失本金。
  </p>;
}

/** Renders the long page to PNG in the browser; nothing is uploaded. */
export function ExportButton({ target, fileName }: { target: RefObject<HTMLElement | null>; fileName: string }) {
  const [state, setState] = useState<"idle" | "busy" | "error">("idle");
  const run = async () => {
    if (!target.current) return;
    setState("busy");
    try {
      const { toPng } = await import("html-to-image");
      const url = await toPng(target.current, { pixelRatio: 2, backgroundColor: "#f6f3ec", cacheBust: true, filter: node => !(node instanceof HTMLElement && node.dataset.exportSkip === "true") });
      const link = document.createElement("a");
      link.href = url; link.download = fileName; link.click();
      setState("idle");
    } catch {
      setState("error");
    }
  };
  return <button type="button" className="lf-export" onClick={run} disabled={state === "busy"} data-export-skip="true">
    {state === "busy" ? "正在生成长图…" : state === "error" ? "导出失败，点此重试" : "导出长图 PNG"}
  </button>;
}
