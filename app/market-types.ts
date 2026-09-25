export type MarketSource = { id: string; name: string; expected: number | null; observed: number; dated: number; pages: number; complete: boolean; status: string; errors: string[] };
export type MarketBoard = {
  id: string; code: string; name: string; kind: "industry" | "concept";
  asOf: string | null; dateValid: boolean; price: number | null; changePct: number | null;
  amount: number | null; turnover: number | null; up: number | null; down: number | null;
  leader: { code: string; name: string; changePct: number | null } | null; sourceUrl: string;
  rank: number | null; turnoverRank: number | null; relativeActivity: number | null; relativeCount: number;
  activityHistory: number | null; baselineDays: number; previousDate: string | null;
  previousRank: number | null; rankChange: number | null; turnoverChange: number | null;
  catalogComplete: boolean; discussion: null;
  provider?: string; memberCount?: number | null; quoteCoverage?: number | null;
};
export type MarketDiagnosticsData = {
  version: string; sourceTotal: number | null; observed: number; catalogComplete: boolean; conflictingCodes: number;
  changeCoverage: number; turnoverCoverage: number; amountCoverage: number; amountComplete: boolean;
  netAdvanceShare: number | null; medianTurnover: number | null; top10AmountShare: number | null;
  concentrationReason: string; note: string;
  distribution: Array<{ key: string; name: string; count: number | null; share: number | null }>;
};
export type MarketSnapshot = {
  meta: { methodVersion: string; tradeDate: string; collectedAt: string; source: string; sourceId?: string; calculation?: string; sources: MarketSource[]; status: string; rankingNote: string };
  market: { diagnostics?: MarketDiagnosticsData; range: string; sourceTotal: number | null; observed: number; quoted: number; missingDate: number;
    up: number; down: number; flat: number; medianChange: number | null; upRate: number | null;
    amount: number | null; amountCoverage: number; amountComplete: boolean; amountChange: number | null; stockCodes: string[] };
  boards: MarketBoard[];
};
export type BoardMember = { code: string; name: string; changePct: number | null; amount: number | null; turnover: number | null; asOf: string | null };
export type BoardDetails = { code: string; date: string; collectedAt: string; expected: number; complete: boolean; members: BoardMember[]; reason: string; excludedMembers?: { code: string; name: string }[] };
