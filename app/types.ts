export type MetricKey = "novice" | "fomo" | "panic" | "heat";
export type ViewKey = "overview" | "sectors" | "explore" | "intelligence" | "method";

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

export type ParticipantMix = {
  key: string;
  label: string;
  count: number;
  share: number;
};

export type Sector = {
  id: string;
  name: string;
  stockCode?: string;
  group: string;
  representative: string;
  overall: number | null;
  direction: number | null;
  novice: number | null;
  fomo: number | null;
  panic: number | null;
  heat: number | null;
  intensity?: number | null;
  sampleCount: number;
  sampleCount3d: number;
  sampleShare: number;
  sampleChange: number;
  dataWindow: string;
  mixWindow: string;
  confidence: string;
  change: number | null;
  heatChange: number;
  heatChange5d?: number | null;
  heatChangeAvailable: boolean;
  heatChange5dAvailable: boolean;
  heatTrend: string;
  heatSeries: Array<{ date: string; value: number }>;
  participantMix: ParticipantMix[];
  priceChange?: number | null;
  profitEffect: number | null;
  flowNet?: number | null;
  flow5d?: number | null;
  flowRatio?: number | null;
  flowAvailable: boolean;
  flowSource?: string;
  rank: number;
  rankChange: number;
  buyIndex?: number | null;
  sellIndex?: number | null;
  buySellRatio?: number | null;
};

export type MarketStats = {
  heat: number | null;
  priceChange?: number | null;
  profitEffect: number | null;
  flowNet?: number | null;
  flow5d?: number | null;
  flowAvailable: boolean;
  flowCoverage?: number;
  flowTotal?: number;
  breadthUp?: number;
  breadthDown?: number;
  breadthFlat?: number;
  breadthTotal?: number;
  breadthUpRate?: number;
  breadthMedianChange?: number;
  quoteSource?: string;
  flowSource?: string;
  note: string;
};

export type CommentRow = {
  id: string;
  date: string;
  source: string;
  sectorId: string;
  sectorName: string;
  excerpt: string;
  tone: "panic" | "fomo" | "novice" | "bull" | "bear" | "neutral";
  intent: string;
  signals: string[];
  score?: number;
  reasoning?: string;
  url?: string;
  evidence?: Array<{ key: string; label: string; value: number; matched: string[] }>;
};

export type Correlation = {
  days: number;
  minimumDays?: number;
  sufficient?: boolean;
  sectors: Array<{ id: string; name: string; group: string }>;
  matrix: Array<Array<number | null>>;
  pairs: Array<{ left: string; right: string; r: number; strength: string }>;
};

export type CalendarPoint = {
  date: string;
  overall: number | null;
  heat: number | null;
  sampleCount: number | null;
  bucket: "hot" | "warm" | "cool" | "cold";
  recordType: "estimated" | "measured";
};

export type Source = {
  id: string;
  name: string;
  status: "ok" | "partial" | "failed" | "demo";
  sampleCount: number;
  note: string;
};

export type Snapshot = {
  meta: {
    generatedAt: string;
    tradeDate: string;
    mode: "live" | "demo";
    methodVersion: string;
    coverage: number;
    confidence: string;
    disclaimer: string;
    historyMode?: string;
    estimatedHistoryPoints?: number;
    historyNote?: string;
    sources: Source[];
  };
  summary: {
    overall: number;
    direction: number;
    novice: number;
    fomo: number;
    panic: number;
    heat: number;
    buyIndex?: number | null;
    sellIndex?: number | null;
    buySellRatio?: number | null;
    change: number | null;
    sampleCount: number;
    label: string;
    readout: string;
  };
  history: HistoryPoint[];
  legacy?: { methodVersion: string; history: HistoryPoint[]; sectorHistory: SectorHistoryPoint[] };
  marketStats?: MarketStats;
  sectorHistory?: SectorHistoryPoint[];
  sectors: Sector[];
  signals: Array<{ label: string; count: number; tone: "hot" | "cool" | "neutral" }>;
  comments?: CommentRow[];
  calendar?: CalendarPoint[];
  correlation?: Correlation;
  interpretation?: { interpretation: string; tongue: string };
  diagnostics: {
    validPosts: number;
    filteredPosts: number;
    uniqueAuthors: number;
    sourceAgreement: number;
  };
};


export type SectorHistoryPoint = { date: string; recordType?: "estimated" | "measured"; sectors: Array<{ id: string; overall: number | null; heat: number | null; sampleCount?: number; direction?: number | null; profitEffect?: number | null; buyIndex?: number | null; sellIndex?: number | null }> };
