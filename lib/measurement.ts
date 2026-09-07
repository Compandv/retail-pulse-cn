import config from "../config/measurement.json" with { type: "json" };
import legacyConfig from "../config/scoring.json" with { type: "json" };

export const METHOD_VERSION = config.version;
export const MEASUREMENT = config;
export type Intent = keyof typeof config.intentLabels;
export type Level = keyof typeof config.levelLabels;
export type Classification = { intent: Intent; intentLabel: string; level: Level; levelLabel: string; chase: boolean; reportedChase: boolean; panic: boolean; bullish: boolean; bearish: boolean; evidence: string[]; reason: string };
export type Observation = { id: string; text: string; date: string; source: string; author: string; code: string; url: string; contentKind?: string };
export type ClassifiedPost = Observation & { classification: Classification };
export const round = (value: number) => Math.round(value * 10) / 10;
type Pattern = keyof typeof config.patterns;
const has = (key: Pattern, text: string) => new RegExp(config.patterns[key], "i").test(text);
const matches = (key: Pattern, text: string) => [...text.matchAll(new RegExp(config.patterns[key], "gi"))];

/** Context rules, not a trained model or a probability of a real trade. */
export function classifyText(input: string): Classification | null {
  const text = input.normalize("NFKC").replace(/\s+/g, " ").trim();
  if (text.length < 2 || text.length > 2000 || new RegExp(config.spamPatterns).test(text) || legacyConfig.spam.some(word => text.includes(word)) || legacyConfig.prose.filter(word => text.includes(word)).length >= 2) return null;
  const evidence: string[] = [];
  const intents = new Set<Intent>();
  let bullish = false, bearish = false, panic = false;
  const clauses = text.match(new RegExp(config.patterns.clauses, "g")) || [text];
  const ownContext = clauses.filter(clause => !has("thirdParty", clause) && !has("rhetorical", clause) && !has("historical", clause) && !has("refusal", clause)).join("，");
  for (const raw of clauses) {
    const clause = raw.trim();
    const related = ["chase", "buy", "rising", "urgent", "panic", "bullish", "bearish"].some(key => has(key as Pattern, clause));
    if (!related) continue;
    if (has("rhetorical", clause)) { intents.add("avoid"); evidence.push(`反问：${clause}`); continue; }
    if (has("historical", clause)) { intents.add("past"); evidence.push(`历史回顾：${clause}`); continue; }
    if (has("thirdParty", clause) && !has("following", clause)) { intents.add("quoted"); evidence.push(`他人观点：${clause}`); continue; }
    if (has("refusal", clause)) { intents.add("avoid"); evidence.push(`劝阻或观望：${clause}`); continue; }
    const positiveHits = (key: Pattern) => matches(key, clause).filter(match => !has("negation", clause.slice(Math.max(0, match.index! - 8), match.index)));
    const chase = positiveHits("chase").length > 0;
    const buy = positiveHits("buy").length > 0;
    const rising = has("rising", ownContext);
    const urgent = has("urgent", clause) && (buy || rising);
    // A wish for a limit-up is not an intention to buy at a higher price.
    if (chase || ((urgent || buy) && rising)) {
      if (has("question", clause) && !has("reported", clause)) intents.add("chase_question");
      else if (has("reported", clause) && !/如果|假如|打算|准备|明天|计划/.test(clause)) intents.add("reported_chase");
      else intents.add("chase_intent");
      evidence.push(`追涨语境：${clause}`);
    } else if (urgent && buy) { intents.add("aggressive_buy"); evidence.push(`激进买入，缺少追涨价格语境：${clause}`); }
    else if (buy) { intents.add("buy"); evidence.push(`买入表达：${clause}`); }
    else if (has("wish", clause) && positiveHits("rising").length) { intents.add("wish"); evidence.push(`看涨期待：${clause}`); }
    if (positiveHits("panic").length && !(has("plan", clause) && has("condition", text))) { panic = true; evidence.push(`恐慌表达：${clause}`); }
    if (positiveHits("bullish").length) bullish = true;
    if (positiveHits("bearish").length) bearish = true;
  }
  const order: Intent[] = ["reported_chase", "chase_intent", "chase_question", "aggressive_buy", "buy", "wish", "avoid", "past", "quoted"];
  const intent = order.find(item => intents.has(item)) ?? (panic ? "panic" : "discussion");
  let level: Level = "unknown";
  // The label is a style of the text, not the author's actual experience.
  const own = clauses.filter(clause => !has("thirdParty", clause) && !has("rhetorical", clause)).join("，");
  const hasOwn = (key: Pattern) => matches(key, own).some(match => !has("negation", own.slice(Math.max(0, match.index! - 8), match.index)));
  if (config.levelsEnabled) {
    if (hasOwn("basic")) level = "L1";
    else if (text.length >= 70 && hasOwn("research") && hasOwn("evidence") && hasOwn("comparison") && hasOwn("risk")) level = "L5";
    else if (text.length >= 35 && hasOwn("scenario") && matches("risk", own).length >= 2 && hasOwn("condition")) level = "L4";
    else if (text.length >= 20 && hasOwn("plan") && hasOwn("condition")) level = "L3";
    else if (has("following", text) && !has("refusal", text) && !has("rhetorical", text)) level = "L2";
  }
  if (level !== "unknown") evidence.push(`表达类型：${config.levelLabels[level]}（语境规则试验）`);
  return { intent, intentLabel: config.intentLabels[intent], level, levelLabel: config.levelLabels[level], chase: intent === "reported_chase" || intent === "chase_intent", reportedChase: intent === "reported_chase", panic, bullish, bearish, evidence: [...new Set(evidence)].slice(0, 6), reason: evidence.length ? "按语境区分行动、期待、转述和否定；自述不等于已核实成交。" : "缺少足够的行动或类型证据，保留为一般讨论／无法判断。" };
}

export function prepareObservations(rows: Observation[], date: string, cutoff = "23:59:59") {
  const seen = new Set<string>(), authorCounts = new Map<string, number>();
  const authors = new Set<string>();
  const analyzed: ClassifiedPost[] = [];
  let observedPosts = 0, unknownAuthorPosts = 0, excludedDate = 0, excludedNoise = 0;
  const ordered = [...rows].sort((a, b) => b.date.localeCompare(a.date) || b.source.localeCompare(a.source) || b.id.localeCompare(a.id));
  for (const row of ordered) {
    if (row.date.slice(0, 10) !== date || row.date.slice(11, 19) > cutoff) { excludedDate++; continue; }
    const classification = classifyText(row.text);
    if (!classification) { excludedNoise++; continue; }
    // Different accounts saying the same thing are still different observed
    // participants; do not erase a crowd by globally deduplicating its words.
    const identity = `${row.source}:${row.author || `missing:${row.id}`}:${row.text.toLowerCase().replace(/\s+/g, "")}`;
    if (seen.has(identity)) { excludedNoise++; continue; }
    seen.add(identity);
    observedPosts++;
    if (row.author) authors.add(`${row.source}:${row.author}`); else unknownAuthorPosts++;
    const authorKey = row.author ? `${row.source}:${row.author}` : `${row.source}:missing:${row.id}`;
    const count = authorCounts.get(authorKey) || 0;
    authorCounts.set(authorKey, count + 1);
    if (count < config.maxPostsPerAuthor) analyzed.push({ ...row, classification });
  }
  return { analyzed, observedPosts, observedAuthors: authors.size, unknownAuthorPosts, excludedDate, excludedNoise };
}

export function summarizeExpressions(posts: ClassifiedPost[]) {
  const total = posts.length;
  const rate = (count: number) => total ? round(count / total * 100) : null;
  const count = (key: "chase" | "reportedChase" | "panic" | "bullish" | "bearish") => posts.filter(post => post.classification[key]).length;
  const levels = (Object.keys(config.levelLabels) as Level[]).map(key => { const n = posts.filter(post => post.classification.level === key).length; return { key, label: config.levelLabels[key], count: n, share: rate(n) }; });
  const intents = (Object.keys(config.intentLabels) as Intent[]).map(key => { const n = posts.filter(post => post.classification.intent === key).length; return { key, label: config.intentLabels[key], count: n, share: rate(n) }; });
  return { sampleCount: total, chase: rate(count("chase")), reportedChase: rate(count("reportedChase")), panic: rate(count("panic")), bullish: rate(count("bullish")), bearish: rate(count("bearish")), direction: total ? round((count("bullish") - count("bearish")) / total * 100) : null, intensity: rate(posts.filter(post => post.classification.bullish || post.classification.bearish).length), levels, intents, levelCoverage: rate(total - levels.find(row => row.key === "unknown")!.count), l1l2Share: rate(levels.filter(row => row.key === "L1" || row.key === "L2").reduce((sum, row) => sum + row.count, 0)), thin: total < config.minimumSemanticSamples };
}
export type ExpressionSummary = ReturnType<typeof summarizeExpressions>;
export type BaselinePoint = { date: string; value: number | null; complete: boolean; universe: string; methodVersion: string; recordType?: string; cutoff: string };
export function historicalPercentile(value: number | null, history: BaselinePoint[], date: string, universe: string, complete: boolean, cutoff: string) {
  const byDate = new Map<string, BaselinePoint>();
  for (const row of history) if (row.date < date && row.complete && row.universe === universe && row.methodVersion === METHOD_VERSION && row.recordType === "measured" && row.cutoff === cutoff && row.value != null && Number.isFinite(row.value) && row.value >= 0) byDate.set(row.date, row);
  const past = [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date)).slice(-config.baselineDays);
  const validValue = value != null && Number.isFinite(value) && value >= 0;
  const reason = !complete ? "当前采集覆盖不足" : !validValue ? "账户标识不足" : past.length < config.minimumBaselineDays ? "历史基线不足" : value === 0 ? "窗口内无有效讨论" : "历史分位";
  const ready = complete && validValue && past.length >= config.minimumBaselineDays;
  const score = ready ? value === 0 ? 0 : round(100 * past.reduce((sum, row) => sum + (row.value! < value! ? 1 : row.value === value ? 0.5 : 0), 0) / past.length) : null;
  const recent = past.slice(-20).map(row => row.value!).sort((a, b) => a - b);
  const median = ready ? (recent[Math.floor((recent.length - 1) / 2)] + recent[Math.floor(recent.length / 2)]) / 2 : null;
  const previous = complete && validValue ? past.at(-1) : undefined;
  return { score, baselineDays: past.length, minimumDays: config.minimumBaselineDays, reason,
    baselineMedian: median, growthPct: median != null && median > 0 ? round((value! / median - 1) * 100) : null,
    abnormalAttention: median != null ? Math.round(Math.log((1 + value!) / (1 + median)) * 1000) / 1000 : null,
    comparisonDate: previous?.date ?? null, previousAuthors: previous?.value ?? null,
    authorChange: previous ? value! - previous.value! : null, lowBase: median === 0 };
}

export function marketPrefix(code: string) { return /^(920|[48])/.test(code) ? "bj" : /^[569]/.test(code) ? "sh" : "sz"; }
export function universeKey(codes: string[], source = "eastmoney") { return `${config.scopeVersion}:${source}:${[...new Set(codes)].sort().join(",")}`; }
