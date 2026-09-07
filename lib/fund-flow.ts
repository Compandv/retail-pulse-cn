export type FlowSource = "eastmoney" | "ths";
export type FlowKind = "industry" | "concept";
export type LiveFlowRow = { code: string; name: string; kind: FlowKind; net: number; ratio: number | null; changePct: number | null; inflow?: number | null; outflow?: number | null; large?: number | null; extraLarge?: number | null; medium?: number | null; small?: number | null; sourceTime: string | null; sourceUrl: string; diagnosis: string };
export type LiveFlowSnapshot = { source: FlowSource; kind: FlowKind; label: string; metric: string; collectedAt: string; sourceTime: string | null; expected: number | null; complete: boolean; stale: boolean; errors: string[]; rows: LiveFlowRow[] };
type TextFetcher = (url: string, source: FlowSource) => Promise<string>;
type Raw = Record<string, unknown>;
const num = (value: unknown) => value === null || value === undefined || value === "" || typeof value === "boolean" || !Number.isFinite(Number(value)) ? null : Number(value);
const plain = (html: string) => html.replace(/<[^>]*>/g, "").replace(/&nbsp;|&#160;/g, " ").replace(/&amp;/g, "&").trim();
export function flowReading(net: number, change: number | null) {
  if (!net) return "净额接近平衡";
  if (change == null) return net > 0 ? "资金净流入" : "资金净流出";
  return net > 0 ? change > 0 ? "上涨与净流入同向" : change < 0 ? "价格回落、资金净流入" : "价格持平、资金净流入" : change > 0 ? "价格上涨、资金净流出" : change < 0 ? "价格与资金共同走弱" : "价格持平、资金净流出";
}

export async function fetchPlatformText(url: string, source: FlowSource) {
  const response = await fetch(url, { signal: AbortSignal.timeout(12000), headers: { "User-Agent": "Mozilla/5.0", "Referer": source === "ths" ? "https://data.10jqka.com.cn/" : "https://data.eastmoney.com/", "Accept": "text/html,application/json" }, cache: "no-store" });
  if (!response.ok) throw new Error(`来源返回 HTTP ${response.status}`);
  const bytes = await response.arrayBuffer();
  if (bytes.byteLength > 3_000_000) throw new Error("来源响应过大");
  const utf = new TextDecoder().decode(bytes);
  return source === "ths" && (/charset=["']?gb/i.test(response.headers.get("content-type") || "") || /charset\s*=\s*["']?gb/i.test(utf)) ? new TextDecoder("gb18030").decode(bytes) : utf;
}

export function parseEastmoney(body: string, kind: FlowKind) {
  const data = (JSON.parse(body) as { data?: { total: number; diff: Raw[] | Record<string, Raw> } }).data;
  if (!data || !Number.isInteger(data.total) || data.total < 1 || !data.diff) throw new Error("东方财富资金结构不可用");
  const input = Array.isArray(data.diff) ? data.diff : Object.values(data.diff);
  const rows: LiveFlowRow[] = [];
  for (const r of input) {
    const code = String(r.f12 || ""), net = num(r.f62), change = num(r.f3), stamp = num(r.f124);
    if (!/^BK\d{4,6}$/.test(code) || net == null) continue;
    rows.push({ code, name: String(r.f14 || code), kind, net, ratio: num(r.f184), changePct: change, extraLarge: num(r.f66), large: num(r.f72), medium: num(r.f78), small: num(r.f84), sourceTime: stamp && stamp > 0 && stamp < 1e11 ? new Date(stamp * 1000).toISOString() : null, sourceUrl: `https://data.eastmoney.com/bkzj/${code}.html`, diagnosis: flowReading(net, change) });
  }
  return { rows, total: data.total, pageSize: input.length, invalid: input.length - rows.length };
}

export function parseThs(body: string, kind: FlowKind) {
  const table = body.match(/<table\b[^>]*class=["'][^"']*m-table[^"']*["'][\s\S]*?<\/table>/i)?.[0];
  if (!table || !/流入资金\(亿\)|流入资金（亿）/.test(plain(table)) || !/净额/.test(plain(table))) throw new Error("同花顺未返回可识别的资金表");
  const pager = body.match(/class=["']page_info["'][^>]*>\s*(\d+)\s*\/\s*(\d+)/i);
  if (!pager) throw new Error("同花顺未提供分页范围，无法确认全榜");
  const rows: LiveFlowRow[] = []; let lastOrdinal = 0, invalid = 0;
  for (const tr of table.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/gi)) {
    const cells = [...tr[1].matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/gi)].map(m => m[1]);
    if (!cells.length) continue;
    const link = cells[1]?.match(/href=["'](https?:\/\/q\.10jqka\.com\.cn\/(?:thshy|gn)\/detail\/code\/(\d+)\/)["']/i);
    const net = num(plain(cells[6] || "")), change = num(plain(cells[3] || "").replace("%", ""));
    const ordinal = num(plain(cells[0] || ""));
    if (!link || net == null || !ordinal) { invalid++; continue; }
    lastOrdinal = Math.max(lastOrdinal, ordinal);
    rows.push({ code: link[2], name: plain(cells[1]), kind, net: net * 1e8, ratio: null, changePct: change, inflow: num(plain(cells[4])) == null ? null : Number(plain(cells[4])) * 1e8, outflow: num(plain(cells[5])) == null ? null : Number(plain(cells[5])) * 1e8, sourceTime: null, sourceUrl: link[1].replace(/^http:/, "https:"), diagnosis: flowReading(net, change) });
  }
  if (!rows.length) throw new Error("同花顺资金表为空或字段发生变化");
  return { rows, page: Number(pager[1]), pages: Number(pager[2]), lastOrdinal, invalid };
}

export async function collectLiveFlows(source: FlowSource, kind: FlowKind, fetcher: TextFetcher = fetchPlatformText, now = new Date()): Promise<LiveFlowSnapshot> {
  const found = new Map<string, LiveFlowRow>(), errors: string[] = [];
  let expected: number | null = null, pages = 1, pageSize = 100, duplicate = false, finished = 0;
  const readPage = async (page: number) => {
    if (source === "eastmoney") {
      const query = new URLSearchParams({ pn: String(page), pz: "100", po: "0", np: "1", fltt: "2", invt: "2", ut: "8dec03ba335b81bf4ebdf7b29ec27d15", fid: "f12", fs: `m:90+t:${kind === "industry" ? 2 : 3}`, fields: "f12,f14,f3,f62,f184,f66,f72,f78,f84,f124" });
      const value = parseEastmoney(await fetcher(`https://push2.eastmoney.com/api/qt/clist/get?${query}`, source), kind);
      if (page === 1) { expected = value.total; pageSize = value.pageSize; if (!pageSize) throw new Error("来源首页为空"); pages = Math.ceil(expected / pageSize); }
      if (value.total !== expected || value.invalid) throw new Error("分页总数变化或存在缺失资金字段");
      return value.rows;
    }
    const base = `https://data.10jqka.com.cn/funds/${kind === "industry" ? "hyzjl" : "gnzjl"}/`;
    const value = parseThs(await fetcher(page === 1 ? base : `${base}field/tradezdf/order/desc/page/${page}/`, source), kind);
    if (page === 1) pages = value.pages;
    if (value.page !== page || value.pages !== pages || value.invalid) throw new Error("分页重复、范围变化或存在无效行");
    if (page === pages) expected = value.lastOrdinal;
    return value.rows;
  };
  const append = (rows: LiveFlowRow[]) => { for (const row of rows) { if (found.has(row.code)) duplicate = true; found.set(row.code, row); } finished++; };
  append(await readPage(1));
  const bounded = Math.min(30, pages);
  for (let start = 2; start <= bounded; start += 3) {
    const batch = await Promise.allSettled(Array.from({ length: Math.min(3, bounded - start + 1) }, (_, i) => readPage(start + i)));
    batch.forEach((result, i) => { if (result.status === "fulfilled") append(result.value); else errors.push(`第${start + i}页：${result.reason instanceof Error ? result.reason.message : "读取失败"}`); });
  }
  if (pages > bounded) errors.push("来源分页超过本次读取上限");
  if (duplicate) errors.push("分页发现重复板块，全榜覆盖未确认");
  const rows = [...found.values()], stamps = rows.flatMap(r => r.sourceTime ? [r.sourceTime] : []).sort();
  return { source, kind, label: source === "eastmoney" ? "东方财富" : "同花顺", metric: source === "eastmoney" ? "主力净流入" : "资金净额", collectedAt: now.toISOString(), sourceTime: stamps.length === rows.length ? stamps[0] : null, expected, complete: !errors.length && finished === pages && rows.length === expected, stale: false, errors, rows };
}

export function liveFlowRanking(rows: LiveFlowRow[], direction: "in" | "out", sort: "net" | "ratio" = "net") {
  return rows.filter(r => direction === "in" ? r.net > 0 : r.net < 0).filter(r => sort !== "ratio" || r.ratio != null).sort((a, b) => (direction === "in" ? 1 : -1) * ((b[sort] ?? 0) - (a[sort] ?? 0)) || a.code.localeCompare(b.code));
}
