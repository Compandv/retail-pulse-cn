import type { BaselinePoint, ClassifiedPost, ExpressionSummary } from "../lib/measurement";
import type { TradingSummary, Feed } from "../lib/observations";
import type { HistoryPoint } from "./types";

export type Attention = {
  score: number | null; baselineDays: number; minimumDays: number; reason: string;
  universe: string; complete: boolean; observedAuthors: number; observedPosts: number;
  unknownAuthorPosts: number; rawCount: number; analyzedCount: number;
  memberCoverage: number; memberTotal: number; source: string; cutoff: string;
  excludedDate: number; excludedNoise: number;
  baselineMedian?: number | null; growthPct?: number | null; abnormalAttention?: number | null;
  comparisonDate?: string | null; previousAuthors?: number | null; authorChange?: number | null; lowBase?: boolean;
};
export type ScopeResult = {
  id: string; name: string; kind: "stock" | "basket" | "proxy"; group?: string;
  description: string; members: Array<{ code: string; name: string; role: string }>;
  date: string; cutoff: string; dataWindow: string; methodVersion: string;
  attention: Attention; attentionShare?: number | null; expressions: ExpressionSummary;
  trading: TradingSummary; posts: Array<Omit<ClassifiedPost, "author">>;
  expressionSources?: string[]; feeds: Array<Omit<Feed, "rows">>; note: string;
  symbol?: string | null; market?: string; fetchedAt?: string;
};
export type ScopeHistory = { date: string; scopes: Array<{ id: string; heat: number | null; activity: number | null; chase: number | null; authors: number; complete: boolean }> };
export type MeasurementSnapshot = {
  meta: { methodVersion: string; tradeDate: string; generatedAt: string; collectedAt: string; cutoff: string; mode: string; historyNote: string;
    sources: Array<{ id: string; name: string; status: string; observedEntrances: number; totalEntrances: number }> };
  summary: ScopeResult; scopes: ScopeResult[]; history: HistoryPoint[]; scopeHistory: ScopeHistory[];
  attentionHistory: Record<string, BaselinePoint[]>;
  legacy?: { methodVersion: string; history: HistoryPoint[]; earlier?: { methodVersion: string; history: HistoryPoint[] } };
};
