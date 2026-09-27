/** One day in the community history chart; also used for the archived pre-V4 series. */
export type HistoryPoint = {
  date: string;
  overall: number | null;
  direction: number | null;
  novice: number | null;
  fomo: number | null;
  panic: number | null;
  heat: number | null;
  intensity?: number | null;
  profitEffect?: number | null;
  recordType?: "estimated" | "measured";
  methodVersion?: string;
};
