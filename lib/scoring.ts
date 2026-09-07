import config from "../config/scoring.json" with { type: "json" };

export const METHOD_VERSION = config.version;
export const SCORE_WEIGHTS = config.weights;
export const SCORE_LABELS = config.labels;
export type ScoreAxis = keyof typeof SCORE_WEIGHTS;
export type TextSignals = { novice: number; fomo: number; panic: number; direction: number; matched: string[] };
export type Scores = Record<ScoreAxis | "overall" | "direction", number>;
export type Evidence = { key: string; label: string; value: number; matched: string[] };
export const roundScore = (value: number) => Math.round(value * 10) / 10;
const clamp = (value: number) => Math.max(0, Math.min(100, value));

function hits(text: string, lexicon: Record<string, number>) {
  let score = 0;
  const matched: string[] = [];
  for (const [word, weight] of Object.entries(lexicon)) {
    const count = text.toLowerCase().split(word.toLowerCase()).length - 1;
    if (count) { score += Math.min(count, 2) * weight; matched.push(word); }
  }
  return { score, matched };
}

export function analyzeText(text: string): TextSignals | null {
  text = text.trim();
  if (text.length < 2 || text.length > 700 || config.spam.some(word => text.includes(word)) || config.prose.filter(word => text.includes(word)).length >= 2) return null;
  const novice = hits(text, config.lexicons.novice), fomo = hits(text, config.lexicons.fomo), panic = hits(text, config.lexicons.panic);
  const bull = hits(text, config.lexicons.bullish), bear = hits(text, config.lexicons.bearish);
  if (/[吗呢？?]$/.test(text)) novice.score += 0.8;
  const punctuation = (text.match(/[!！?？]/g) || []).length;
  if (punctuation >= 3) {
    const boost = Math.min(1.2, punctuation * 0.15);
    if (bull.score >= bear.score) fomo.score += boost; else panic.score += boost;
  }
  const saturate = (value: number) => 1 - Math.exp(-Math.max(0, value) / config.saturationScale);
  return { novice: saturate(novice.score), fomo: saturate(fomo.score), panic: saturate(panic.score), direction: Math.tanh((bull.score - bear.score) / 3.5), matched: [...new Set([...novice.matched, ...fomo.matched, ...panic.matched, ...bull.matched, ...bear.matched])] };
}

export function scorePosts(posts: TextSignals[]): Scores | null {
  if (!posts.length) return null;
  const average = (values: number[]) => values.reduce((sum, value) => sum + value, 0) / values.length;
  const axis = (key: "novice" | "fomo" | "panic") => roundScore(100 * (config.prevalenceWeight * posts.filter(post => post[key] >= config.signalThreshold).length / posts.length + (1 - config.prevalenceWeight) * average(posts.map(post => post[key]))));
  const direction = average(posts.map(post => post.direction)) * 100;
  const metrics = { novice: axis("novice"), fomo: axis("fomo"), panic: axis("panic"), direction: roundScore(direction), intensity: roundScore(Math.abs(direction)), heat: roundScore(Math.min(100, Math.log1p(posts.length) / Math.log1p(config.heatReference) * 100)) };
  return { ...metrics, overall: roundScore(Object.entries(SCORE_WEIGHTS).reduce((sum, [key, weight]) => sum + metrics[key as ScoreAxis] * weight, 0)) };
}

export function scoreContributions(metrics: Partial<Scores>) {
  return (Object.keys(SCORE_WEIGHTS) as ScoreAxis[]).map(key => ({ key, label: SCORE_LABELS[key], weight: SCORE_WEIGHTS[key], value: metrics[key] ?? null, points: metrics[key] == null ? null : roundScore(metrics[key] * SCORE_WEIGHTS[key]) }));
}

export function expressionEvidence(signals: TextSignals) {
  const evidence: Evidence[] = (["novice", "fomo", "panic"] as const).map(key => ({ key, label: SCORE_LABELS[key], value: roundScore(signals[key] * 100), matched: signals.matched.filter(word => word in config.lexicons[key]) }));
  evidence.push({ key: "direction", label: signals.direction >= 0 ? "看多方向" : "看空方向", value: roundScore(Math.abs(signals.direction) * 100), matched: signals.matched.filter(word => word in config.lexicons.bullish || word in config.lexicons.bearish) });
  const strongest = evidence.reduce((best, row) => row.value > best.value ? row : best);
  const reason = signals.matched.length ? `命中“${signals.matched.slice(0, 6).join("、")}”，以${strongest.label}信号为主。` : "未命中明显情绪关键词；问句和标点可能产生少量结构信号。";
  return { score: roundScore(Math.max(signals.novice, signals.fomo, signals.panic, Math.abs(signals.direction)) * 100), reasoning: `${reason}这是文本表达的规则解释，不判断作者真实身份。`, evidence };
}

export function participantIndices(metrics: Pick<Scores, "direction" | "fomo" | "panic">) {
  const buyIndex = roundScore(clamp(45 + metrics.direction * 0.22 + metrics.fomo * 0.48 - metrics.panic * 0.16));
  const sellIndex = roundScore(clamp(45 - metrics.direction * 0.22 + metrics.panic * 0.48 - metrics.fomo * 0.16));
  return { buyIndex, sellIndex, buySellRatio: roundScore(Math.min(99, sellIndex > 0.5 ? buyIndex / sellIndex : buyIndex > 0.5 ? 99 : 1)) };
}

export function scoreBand(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return { label: "暂无样本", color: "var(--muted)", key: "missing" };
  if (value < 20) return { label: "冷清", color: "var(--blue)", key: "cold" };
  if (value < 40) return { label: "温和", color: "var(--teal)", key: "mild" };
  if (value < 60) return { label: "活跃", color: "var(--amber)", key: "active" };
  if (value < 80) return { label: "高热", color: "var(--vermillion)", key: "hot" };
  return { label: "极热", color: "var(--purple)", key: "extreme" };
}
