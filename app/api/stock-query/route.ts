/**
 * 在线个股情绪查询。
 *
 * 这个接口只读取东方财富股吧和腾讯公开行情，不需要登录、Cookie 或密钥。
 * 情绪分是“公开社区样本代理”，和每日快照使用同一套透明关键词规则。
 */

type AnyRecord = Record<string, unknown>;

const USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36";

const NOVICE: Record<string, number> = {
  小白: 3, 新手: 3, 新人: 2, 第一次: 2, 请教: 2, 求助: 2, 大佬: 1, 老师: 1,
  能买吗: 3, 怎么买: 3, 怎么操作: 3, 该不该: 2, 要不要: 2, 可以吗: 1.5, 什么意思: 2,
  求带: 2, 听说: 1.5, 朋友说: 2, 博主说: 2, 解套: 1.5, 成本多少: 1,
};
const FOMO: Record<string, number> = {
  上车: 2, 冲: 1, 梭哈: 3, 满仓: 2.5, "all in": 3, 起飞: 2, 暴涨: 2, 翻倍: 2.5,
  稳赚: 3, 必涨: 3, 躺赚: 3, 踏空: 2, 错过: 2, 后悔没买: 3, 买少了: 2, 再不买: 2.5, 忍不住: 1.5,
};
const PANIC: Record<string, number> = {
  割肉: 3, 清仓: 2.5, 止损: 1.5, 不玩了: 2.5, 救命: 3, 完了: 2, 亏麻: 3, 亏惨: 2.5,
  血亏: 3, 深套: 2.5, 套牢: 2, 崩盘: 3, 跌惨: 2.5, 跑了: 1.5, 心态崩: 3,
};
const BULLISH: Record<string, number> = {
  看多: 2, 看涨: 2, 上涨: 1, 大涨: 2, 涨停: 2.5, 起飞: 2, 突破: 1.5, 抄底: 1.5,
  加仓: 1.5, 买入: 1, 牛市: 2, 利空出尽: 2.5, 黄金坑: 2.5, 反包: 2,
};
const BEARISH: Record<string, number> = {
  看空: 2, 看跌: 2, 下跌: 1, 大跌: 2, 跌停: 2.5, 崩盘: 3, 破位: 2, 割肉: 2,
  清仓: 2, 卖出: 1, 熊市: 2, 出货: 2, 套牢: 1.5, 亏麻: 2.5, 跑路: 2,
};
const SPAM = ["开户链接", "扫码进群", "老师带单", "内部消息", "添加微信", "点击领取", "诊股", "荐股", "免费领取", "财富号"];
const PROSE = ["证券研究报告", "风险提示如下", "投资评级", "目标价", "研报"];

function clean(value: unknown, max = 500): string {
  return String(value ?? "").replace(/<br\s*\/?>(?=.)/gi, " ").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, max);
}

function weightedHits(text: string, lexicon: Record<string, number>) {
  let score = 0;
  const matched: string[] = [];
  for (const [phrase, weight] of Object.entries(lexicon)) {
    const count = text.toLowerCase().split(phrase.toLowerCase()).length - 1;
    if (count > 0) { score += weight * Math.min(count, 2); matched.push(phrase); }
  }
  return { score, matched };
}

function saturate(raw: number, scale = 4) { return 1 - Math.exp(-Math.max(0, raw) / scale); }

type Analyzed = { title: string; text: string; score: number; novice: number; fomo: number; panic: number; direction: number; matched: string[]; url: string; date: string };

function analyze(title: string, published: string, code: string, id: string): Analyzed | null {
  const text = clean(title);
  if (text.length < 2 || text.length > 700 || SPAM.some((p) => text.includes(p)) || PROSE.filter((p) => text.includes(p)).length >= 2) return null;
  const noviceRaw = weightedHits(text, NOVICE);
  const fomoRaw = weightedHits(text, FOMO);
  const panicRaw = weightedHits(text, PANIC);
  const bullRaw = weightedHits(text, BULLISH);
  const bearRaw = weightedHits(text, BEARISH);
  let novice = noviceRaw.score, fomo = fomoRaw.score, panic = panicRaw.score;
  if (/[吗呢？?]$/.test(text)) novice += 0.8;
  const punctuation = (text.match(/[!！?？]/g) || []).length;
  if (punctuation >= 3) {
    const boost = Math.min(1.2, punctuation * 0.15);
    if (bullRaw.score >= bearRaw.score) fomo += boost; else panic += boost;
  }
  const direction = Math.tanh((bullRaw.score - bearRaw.score) / 3.5);
  const n = saturate(novice), f = saturate(fomo), p = saturate(panic);
  const score = Math.round(Math.max(0, Math.min(100, 20 + n * 35 + f * 30 + p * 30 + Math.abs(direction) * 15)) * 10) / 10;
  const matched = [...new Set([...noviceRaw.matched, ...fomoRaw.matched, ...panicRaw.matched, ...bullRaw.matched, ...bearRaw.matched])];
  return { title: text, text, score: Math.max(0, Math.min(100, score)), novice: n * 100, fomo: f * 100, panic: p * 100, direction: direction * 100, matched, url: `https://guba.eastmoney.com/news,${code},${id}.html`, date: published };
}

function normalizeInput(input: string) {
  const raw = input.trim();
  const upper = raw.toUpperCase();
  const prefixed = upper.match(/^(SH|SZ|BJ|OF|HK|US)([A-Z0-9]+)$/);
  if (prefixed) return { prefix: prefixed[1].toLowerCase(), code: prefixed[2], display: raw };
  if (/^\d{6}$/.test(upper)) return { prefix: /^[569]/.test(upper) ? "sh" : /^[48]/.test(upper) ? "bj" : "sz", code: upper, display: raw };
  if (/^\d{5}$/.test(upper)) return { prefix: "hk", code: upper, display: raw };
  if (/^[A-Z]{1,6}$/.test(upper)) return { prefix: "us", code: upper, display: raw };
  return null;
}

async function fetchText(url: string, timeoutMs = 12000, charset: "utf-8" | "gb18030" = "utf-8"): Promise<string> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { signal: controller.signal, headers: { "User-Agent": USER_AGENT, Accept: "application/json,text/plain,*/*" } });
    if (!response.ok) throw new Error(`上游返回 ${response.status}`);
    const buffer = await response.arrayBuffer();
    try { return new TextDecoder(charset).decode(buffer); } catch { return new TextDecoder().decode(buffer); }
  } finally { clearTimeout(timer); }
}

async function resolveCode(input: string) {
  const normalized = normalizeInput(input);
  if (normalized) return normalized;
  const hint = await fetchText(`https://smartbox.gtimg.cn/s3/?q=${encodeURIComponent(input)}&t=gp`, 8000);
  const match = hint.match(/v_hint="([^"]*)"/);
  if (match) {
    const parts = match[1].split("~");
    if (parts.length >= 3 && /^\d{6}$/.test(parts[1])) return { prefix: parts[0].toLowerCase(), code: parts[1], display: input, resolvedName: parts[2] };
  }
  throw new Error("未找到股票代码，请输入 6 位 A 股代码（也支持 sh600519 / hk00700 / NVDA）");
}

async function quote(symbol: string) {
  try {
    const raw = await fetchText(`https://qt.gtimg.cn/q=${encodeURIComponent(symbol)}`, 12000, "gb18030");
    const match = raw.match(new RegExp(`v_${symbol}="([^"]*)"`, "i"));
    if (!match) return null;
    const fields = match[1].split("~");
    const price = Number(fields[3]), previous = Number(fields[4]);
    if (!Number.isFinite(price) || !price) return null;
    const change = Number(fields[31]), changePct = Number(fields[32]);
    return { name: fields[1] || "", price, previousClose: previous, change: Number.isFinite(change) ? change : price - previous, changePct: Number.isFinite(changePct) ? changePct : (price / previous - 1) * 100, high: Number(fields[33]), low: Number(fields[34]), asOf: fields[30] || "", source: "腾讯行情公开报价" };
  } catch { return null; }
}

async function posts(code: string): Promise<{ rows: Analyzed[]; rawCount: number; error?: string }> {
  const query = new URLSearchParams({ code, sorttype: "1", ps: "100", p: "1", from: "CommonBaPost", deviceid: "2f7f40de-2fb0-4d84-8a31-111111111111", version: "200", product: "Guba", plat: "Web" });
  try {
    const payload = JSON.parse(await fetchText(`https://gbapi.eastmoney.com/webarticlelist/api/Article/Articlelist?${query}`, 16000)) as AnyRecord;
    const rows = Array.isArray(payload.re) ? payload.re : [];
    const analyzed: Analyzed[] = [];
    for (const row of rows) {
      if (!row || typeof row !== "object") continue;
      const item = row as AnyRecord;
      if (String(item.stockbar_code || "") !== code || Number(item.post_type || 0) !== 0 || item.institution) continue;
      const id = String(item.post_id || item.article_id || item.post_publish_time || "");
      const parsed = analyze(String(item.post_title || ""), String(item.post_publish_time || item.post_display_time || ""), code, id);
      if (parsed) analyzed.push(parsed);
    }
    return { rows: analyzed, rawCount: rows.length };
  } catch (error) { return { rows: [], rawCount: 0, error: error instanceof Error ? error.message : "股吧暂时不可用" }; }
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const input = url.searchParams.get("q") || url.searchParams.get("code") || "";
  if (!input.trim()) return Response.json({ error: "请输入股票代码或名称" }, { status: 400 });
  const started = Date.now();
  try {
    const info = await resolveCode(input);
    const symbol = `${info.prefix}${info.code}`;
    const [quoteData, postData] = await Promise.all([quote(symbol), info.prefix === "sh" || info.prefix === "sz" || info.prefix === "bj" || info.prefix === "of" ? posts(info.code) : Promise.resolve({ rows: [], rawCount: 0, error: "港股/美股暂不接入股吧样本" })]);
    const rows = postData.rows;
    const count = rows.length;
    const novice = count ? rows.reduce((s, r) => s + r.novice, 0) / count : 50;
    const fomo = count ? rows.reduce((s, r) => s + r.fomo, 0) / count : 50;
    const panic = count ? rows.reduce((s, r) => s + r.panic, 0) / count : 50;
    const direction = count ? rows.reduce((s, r) => s + r.direction, 0) / count : 0;
    const heat = count ? Math.min(100, Math.log1p(count) / Math.log1p(80) * 100) : 0;
    const overall = count ? Math.min(100, Math.max(0, 20 + heat * 0.3 + fomo * 0.2 + novice * 0.15 + panic * 0.1 + Math.abs(direction) * 0.1)) : null;
    const buyIndex = Math.max(0, Math.min(100, 45 + direction * 0.22 + fomo * 0.48 - panic * 0.16));
    const sellIndex = Math.max(0, Math.min(100, 45 - direction * 0.22 + panic * 0.48 - fomo * 0.16));
    return Response.json({
      input, code: info.code, symbol, name: quoteData?.name || info.resolvedName || input, market: info.prefix === "sh" ? "A股·沪市" : info.prefix === "sz" ? "A股·深市" : info.prefix === "bj" ? "A股·北交所" : info.prefix === "hk" ? "港股" : info.prefix === "us" ? "美股" : info.prefix.toUpperCase(),
      quote: quoteData, metrics: overall === null ? null : { overall: Math.round(overall * 10) / 10, heat: Math.round(heat * 10) / 10, novice: Math.round(novice * 10) / 10, fomo: Math.round(fomo * 10) / 10, panic: Math.round(panic * 10) / 10, direction: Math.round(direction * 10) / 10, buyIndex: Math.round(buyIndex * 10) / 10, sellIndex: Math.round(sellIndex * 10) / 10, buySellRatio: Math.round((buyIndex / Math.max(0.5, sellIndex)) * 100) / 100, profitEffect: Math.round((50 + direction * 0.12 + (fomo - panic) * 0.2 + (quoteData?.changePct || 0) * 3.5) * 10) / 10 },
      sampleCount: postData.rawCount, analyzedCount: count, posts: rows.sort((a, b) => b.score - a.score).slice(0, 12), fetchError: postData.error || null, fetchedAt: new Date().toISOString(), durationMs: Date.now() - started, source: "东方财富股吧公开帖子 + 腾讯公开行情", note: "个股情绪为公开社区样本代理，不等于全市场投资者情绪，也不构成投资建议。",
    });
  } catch (error) { return Response.json({ error: error instanceof Error ? error.message : "查询失败" }, { status: 502 }); }
}
