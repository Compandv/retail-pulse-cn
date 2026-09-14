export type DimensionKey = "discussion" | "spread" | "panic" | "refill" | "crowding" | "overheat" | "growth" | "chase" | "trading" | "leek";
export type ProfileLevel = { key: string; label: string; count: number; share: number | null; examples: { text: string; url: string; date: string; reason: string; supportingPosts: number }[] };
export type RetailProfile = { version: string; observedAccounts: number; classifiedAccounts: number; unknownAccounts: number; coverage: number; singleEvidenceAccounts: number; conflictingAccounts: number; eligible: boolean; pointEligible: boolean; l1l2Share: number | null; l1l2Bounds: number[] | null; levels: ProfileLevel[]; reason: string; enrichedPosts?: number; contentObservedAt?: string | null; contentSampling?: string };
export type LeekScore = { rawExpressionScore?: number | null; score: number | null; range: number[] | null; weights: Record<string, number>; inputs: Record<string, number | null>; missing: string[]; reason: string };
export type ReportPost = { text: string; url: string; date: string; code: string; intent: string; panic: boolean; refill: boolean; replies: number | null; forwards: number | null };
export type ReportSector = {
  expressionProfile?: {version: string; observedAccounts: number; unknownAccounts: number; unknownRate: number | null; eligible: boolean; reason: string; labels: {key: string; label: string; count: number; rate: number | null; examples: {text: string; evidence: string; url: string; date: string}[]}[]};
  id: string; code: string; name: string; selectionScore: number; rankingQuality?: string; historicalAttentionScore?: number | null; historicalAttentionMedian?: number | null; historicalBaselineDays?: number; changePct: number; turnover: number;
  dimensions: Record<DimensionKey, number | null>; shape: string; diagnosis: string;
  retailProfile?: RetailProfile; leekScore?: LeekScore;
  growth?: { score: number | null; today: number; previous: number; pairedMembers: number; previousDate: string; basis: string };
  overheatInputs: { discussion: number | null; spread: number | null; crowding: number | null; chaseRank: number | null };
  observation: { authors: number; observedPosts: number; sampleCount: number; memberTotal: number; memberObserved: number; memberComplete: number; sourceCoverage?: number; completeCoverage?: number; bodyObserved?: number; complete: boolean; eligible: boolean; density: number | null; interactionMean: number | null; panic: number | null; chase: number | null; refill: number | null; refillCount: number; chaseCount: number; panicCount: number; posts: ReportPost[] };
};
export type Thermometer = { key: string; name: string; score: number | null; unit: string; scope: string; detail: string; evidence?: { name: string; score: number | null; baselineDays: number }[] };
export type FundFlow = { boardId: string; code: string; name: string; kind: string; date: string; net: number; ratio: number | null; changePct: number | null; diagnosis: string; source: string; sourceUrl: string };
export type DailyReport = {
  llmReading?: {status: string; note?: string; model?: string; generatedAt?: string; reused?: boolean; sections?: Record<string, {text: string; factIds: string[]}>; facts?: {id: string; [key: string]: unknown}[]};
  meta: { discovery?: { universeStocks: number; sampleStocks: number; tagCoverage: number; candidateTopics: number; eligibleTopics: number; completeTopics?: number; rankingQuality?: string; cohortQuality?: string; selectedPartialTopics?: number; expandedStocks?: number; historicalBaselineDays?: number; amountCoverage: number; suppressed: {name: string; representedBy: string; reason?: string}[] }; version: string; analysisVersion?: string; tradeDate: string; previousDate: string; collectedAt: string; interactionAsOf: string; cutoff: string; selectionNote: string; marketSource: string; feedObserved: number; feedExpected: number; errors: { group: string; key: string; error: string }[]; flowNote: string };
  thermometers: Thermometer[]; sectors: ReportSector[]; summary: string;
  flows: { coverage: { kind: string; expected: number; observed: number }[]; rows: FundFlow[] };
};
