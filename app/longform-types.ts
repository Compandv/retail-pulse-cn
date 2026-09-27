import type { Thermometer, ReportPost } from "./report-types";

export type DimensionKey = "heat" | "spread" | "shake" | "rebound" | "crowding";
export type Dimensions = Record<DimensionKey, number | null>;
export type LimitStock = { code: string; name: string; changePct: number | null; industry: string | null; boards?: number | null; streak?: string | null; breaks?: number | null; firstSeal?: string | null; lastSeal?: string | null; amount?: number | null; turnover?: number | null };

export type LongformTopic = {
  id: string; code: string; name: string; changePct: number | null; turnover: number | null; amount: number | null;
  dimensions: Dimensions; total: number | null; missing: string[]; totalChange: number | null; isNew: boolean;
  chaseTrial: { score: number | null; coverage: number | null; judged: number | null };
  inputs: Record<string, number | null>;
  shape: { key: string; label: string; reference: string | null; text: string };
  alert: { level: "red" | "yellow" | "green" | "grey"; text: string };
  evidence: ReportPost[];
  limitUpCount?: number; limitUpStocks?: LimitStock[];
};

export type LimitMetrics = {
  limitUp: number | null; limitDown: number | null; broken: number | null; yesterdayLimitUp: number | null; brokenRate: number | null;
  maxBoards: number | null; maxBoardStocks: { code: string; name: string }[]; ladder: Record<string, number> | null;
  yesterdayMean: number | null; yesterdayMedian: number | null; yesterdayStreakMean: number | null; yesterdayStreakCount: number | null;
  promotionRate: number | null; promoted: number | null;
};

export type FlowRow = { boardId: string; name: string; kind: string; net: number; changePct: number | null; diagnosis: string };
export type IndexRow = { symbol: string; name: string; close: number | null; changePct: number | null };
export type MarginRow = { date: string; financing: number | null; lending: number | null; total: number | null; netFinancing: number | null; change: number | null };
export type Anchor = { date: string; name: string; description: string; years: number;
  indices: { name: string; baseDate: string; base: number; close: number; changePct: number }[];
  margin: { base: MarginRow | null; end: MarginRow | null; changePct: number | null } };

export type WeeklyTopic = {
  id: string; name: string; days: string[]; appearances: number; scoredDays: number; total: number | null; dimensions: Dimensions; missing: string[];
  limitUps: number; meanChange: number | null; totalChange: number | null; isNew: boolean;
  shape: LongformTopic["shape"]; alert: LongformTopic["alert"];
};
export type WeeklyDay = {
  date: string; weekday: string; hasLongform: boolean; hasMarket: boolean; hasLimit: boolean; upRate: number | null; amount: number | null; up: number | null; down: number | null;
  limitUp: number | null; limitDown: number | null; brokenRate: number | null; maxBoards: number | null; mainline: LongformDaily["mainline"];
  shClose: number | null; shChange: number | null; topTopic: { name: string; total: number } | null;
};
export type WeeklyFlow = { boardId: string; name: string; kind: string; net: number; days: number };
export type LongformWeekly = {
  meta: { version: string; dimensionsVersion: string; week: string; sessions: string[]; startDate: string; endDate: string; builtAt: string;
    longformDays: string[]; missingDays: string[]; requiredDays: number; complete: boolean; topicsPublished: boolean; notes: string[] };
  timeline: WeeklyDay[];
  indices: (IndexRow & { high: number | null; baseDate?: string })[];
  topics: WeeklyTopic[];
  flows: { days: number; totalDays: number } & Record<"industry" | "concept", { inflow: WeeklyFlow[]; outflow: WeeklyFlow[] }>;
  market: { meanAmount: number | null; amountDays: number; upRates: (number | null)[]; minUpRate: number | null; meanLimitUp: number | null; maxBoards: number | null;
    mainlines: string[]; mainlineSwitches: number | null; shChange: number | null };
  recap: { label: string; previous: string; current: string }[];
  previousWeek: string | null;
  narrative: { source: string; title: string; oneLiner: string; conclusions: string[]; summary: string };
};

export type LongformDaily = {
  meta: { version: string; dimensionsVersion: string; tradeDate: string; previousDate: string; builtAt: string; reportSource: string | null; reportMethod: string | null;
    marketCollectedAt: string | null; limitCollectedAt: string | null; weights: Record<DimensionKey, number>;
    dimensions: { key: DimensionKey; label: string; formula: string }[]; notes: string[] };
  market: { up: number; down: number; flat: number; upRate: number | null; medianChange: number | null; amount: number | null; amountComplete: boolean; amountChange: number | null;
    diagnostics: { netAdvanceShare?: number | null; medianTurnover?: number | null; top10AmountShare?: number | null; distribution?: { key: string; name: string; count: number | null; share: number | null }[] } | null };
  thermometers: Thermometer[];
  limit: { metrics: LimitMetrics; coverage: Record<string, { expected: number | null; observed: number; complete: boolean; error: string | null }>; chainCheck: { previousDate: string; matchRate: number | null; passed: boolean } | null; collectedAt: string } | null;
  limitTop: LimitStock[];
  mainline: { id: string; name: string; limitUpCount: number; limitUpTotal: number; concentration: number; changePct: number | null } | null;
  topics: LongformTopic[];
  flows: Record<"industry" | "concept", { inflow: FlowRow[]; outflow: FlowRow[] }>;
  indices: IndexRow[];
  margin: MarginRow | null;
  anchors: Anchor[];
  narrative: { source: string; title: string; oneLiner: string; topics: Record<string, string> };
};
