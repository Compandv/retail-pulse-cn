import type { MarketBoard } from "../app/market-types.ts";

export type BoardSort = "changePct" | "turnover" | "amount" | "activityHistory";
/** Filter after scoring: searching must not inflate the score of the sole result. */
export function sortedBoards(boards: MarketBoard[], kind: string, query: string, sort: BoardSort) {
  const keyword = query.normalize("NFKC").trim().toLowerCase();
  return boards.filter(row => row.kind === kind && (!keyword || `${row.name} ${row.code} ${row.leader?.name || ""}`.toLowerCase().includes(keyword)))
    .sort((a, b) => (b[sort] ?? -Infinity) - (a[sort] ?? -Infinity) || a.id.localeCompare(b.id));
}
