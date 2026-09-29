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

/** Plain-language meaning of each dimension, shown before the charts that use them. */
export const DIMENSION_HELP: Record<DimensionKey, string> = {
  heat: "讨论有多热、钱有多少：讨论度占 40%，题材成交额占 60%。",
  spread: "讨论是否在向更多人扩散、是否比前一天升温：传播力与讨论升温各占一半。",
  shake: "帖子里的恐慌、割肉表达多不多，以及是否放量下跌：恐慌表达占 60%，放量下跌占 40%。",
  rebound: "说“卖飞了、想接回、补仓”这类话的帖子占比，反映下跌后是否还有人想买回。",
  crowding: "成分股换手率的高低。换手越高，交易越集中、越拥挤。",
};
export const DIMENSION_GUIDE: [string, string][] = [
  ...DIMENSIONS.map(d => [d.label, DIMENSION_HELP[d.key]] as [string, string]),
  ["分数怎么读", "每项 0–100，是当天十强题材之间的相对排名：100 = 十个里最高，50 ≈ 居中。不是绝对强弱，冷清的日子也会有题材拿高分。"],
];

/** Section-opening glossary; stays visible in the exported image. */
export function Guide({ items, note }: { items: [string, string][]; note?: string }) {
  return <div className="lf-guide">
    <span className="lf-guide-title">怎么看</span>
    <dl>{items.map(([term, text]) => <div key={term}><dt>{term}</dt><dd>{text}</dd></div>)}</dl>
    {note && <p>{note}</p>}
  </div>;
}

// Colours and fonts are SVG attributes, not CSS classes: the PNG export does not carry
// class styles into SVG children, which painted the shape black with oversized labels.
const RADAR_INK = { grid: "#d9e0e5", axis: "#c3ccd3", shape: "#24618e", dot: "#163b57", name: "#53616c", value: "#16324a" };
const RADAR_FONT = '"Segoe UI", "Microsoft YaHei", sans-serif';

/** Five-axis radar. Missing axes are marked and the outline is not closed across them. */
export function Radar({ dims, size = 200 }: { dims: Dimensions; size?: number }) {
  const center = size / 2, radius = size / 2 - 34, padX = 30, padY = 6;
  const angle = (index: number) => -Math.PI / 2 + (index * 2 * Math.PI) / DIMENSIONS.length;
  const point = (index: number, value: number) => [center + Math.cos(angle(index)) * radius * value / 100, center + Math.sin(angle(index)) * radius * value / 100];
  const complete = DIMENSIONS.every(d => dims[d.key] != null);
  const outline = complete ? DIMENSIONS.map((d, i) => point(i, dims[d.key] as number).join(",")).join(" ") : "";
  return <svg className="lf-radar" viewBox={`${-padX} ${-padY} ${size + 2 * padX} ${size + 2 * padY}`} fontFamily={RADAR_FONT} role="img" aria-label={"五维雷达：" + DIMENSIONS.map(d => `${d.label}${num(dims[d.key], 0)}`).join("、")}>
    {[25, 50, 75, 100].map(level => <polygon key={level} points={DIMENSIONS.map((_, i) => point(i, level).join(",")).join(" ")} fill={level === 100 ? "#f7f9fa" : "none"} stroke={RADAR_INK.grid} strokeWidth={1} />)}
    {DIMENSIONS.map((d, i) => { const [x, y] = point(i, 100); return <line key={d.key} x1={center} y1={center} x2={x} y2={y} stroke={RADAR_INK.axis} strokeWidth={1} />; })}
    {complete && <polygon points={outline} fill={RADAR_INK.shape} fillOpacity={0.2} stroke={RADAR_INK.shape} strokeWidth={2} strokeLinejoin="round" />}
    {DIMENSIONS.map((d, i) => dims[d.key] == null ? null : <circle key={d.key} cx={point(i, dims[d.key] as number)[0]} cy={point(i, dims[d.key] as number)[1]} r={3.5} fill={RADAR_INK.dot} />)}
    {DIMENSIONS.map((d, i) => {
      // Name above value; side labels are anchored away from the chart so they never overlap it.
      const [x, y] = point(i, 116), cos = Math.cos(angle(i)), sin = Math.sin(angle(i));
      const anchor = cos > 0.3 ? "start" : cos < -0.3 ? "end" : "middle";
      const middle = y + (sin < -0.9 ? -12 : sin > 0.5 ? 12 : 0);
      return <text key={d.key} textAnchor={anchor} dominantBaseline="middle">
        <tspan x={x} y={middle - 8} fontSize={13} fill={RADAR_INK.name}>{d.label}</tspan>
        <tspan x={x} y={middle + 8} fontSize={15} fontWeight={700} fill={RADAR_INK.value}>{num(dims[d.key], 0)}</tspan>
      </text>;
    })}
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
