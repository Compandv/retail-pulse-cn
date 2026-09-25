import { MEASUREMENT, marketPrefix, round, type Observation } from "./measurement.ts";

export const CUTOFF = "15:00:00";
export { latestSession, validSession } from "./trading-calendar.ts";

export async function fetchText(url: string, charset = "utf-8", timeout = 8000) {
  const response = await fetch(url, { signal: AbortSignal.timeout(timeout), headers: { "User-Agent": "Mozilla/5.0", Accept: "application/json,text/plain,*/*" } });
  if (!response.ok) throw new Error(`数据源返回 ${response.status}`);
  return new TextDecoder(charset).decode(await response.arrayBuffer());
}
type Row = Record<string, unknown>;
const clean = (value: unknown) => String(value || "").replace(/<[^>]*>/g, " ").normalize("NFKC").replace(/\s+/g, " ").trim().slice(0, 1800);
export type Feed = { code: string; rows: Observation[]; rawCount: number; pages: number; complete: boolean; reason: string; error: string | null };

/** A bounded public feed observation, never a claim to cover all investors. */
export async function collectFeed(code: string, day: string): Promise<Feed> {
  const result: Feed = { code, rows: [], rawCount: 0, pages: 0, complete: false, reason: "已达分页上限，数量为已观察下限", error: null };
  const seenPages = new Set<string>();
  let olderPages = 0;
  for (let page = 1; page <= MEASUREMENT.maxPages; page++) {
    const params = new URLSearchParams({ code, sorttype: "1", ps: String(MEASUREMENT.pageSize), p: String(page), from: "CommonBaPost", deviceid: "2f7f40de-2fb0-4d84-8a31-111111111111", version: "200", product: "Guba", plat: "Web" });
    try {
      const data = JSON.parse(await fetchText(`https://gbapi.eastmoney.com/webarticlelist/api/Article/Articlelist?${params}`)) as Row;
      if (!Array.isArray(data.re)) throw new Error("帖子列表结构异常");
      const rows = data.re.filter(row => row && typeof row === "object") as Row[];
      result.pages++;
      const pageKey = rows.map(row => String(row.post_id || row.post_title)).join("|");
      if (rows.length && seenPages.has(pageKey)) { result.reason = "列表重复返回，覆盖未确认"; break; }
      seenPages.add(pageKey);
      result.rawCount += rows.length;
      for (const row of rows) {
        if (String(row.stockbar_code) !== code || Number(row.post_type || 0) !== 0 || row.institution) continue;
        const accreditation = (row.user_extendinfos as Row | undefined)?.user_accreditinfos;
        if (accreditation && accreditation !== "[]" && !(Array.isArray(accreditation) && !accreditation.length)) continue;
        const date = String(row.post_publish_time || "");
        if (!/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/.test(date)) continue;
        const id = String(row.post_id || "");
        result.rows.push({ id: id || `${code}:${date}:${clean(row.post_title).slice(0, 20)}`, text: clean(row.post_content || row.post_title), date: date.slice(0, 19), source: "eastmoney", author: String(row.user_id || ""), code, url: /^\d+$/.test(id) ? `https://guba.eastmoney.com/news,${code},${id}.html` : "", contentKind: row.post_content ? "正文" : "标题" });
      }
      // Pinned old posts cannot establish a boundary. Activity time also must
      // predate the window, so a resurfaced old title cannot stop pagination.
      const ordinary = rows.filter(row => !Number(row.post_top_status || 0));
      const older = ordinary.length > 0 && ordinary.every(row => { const published = String(row.post_publish_time || ""), active = String(row.post_last_time || ""); return /^\d{4}-\d{2}-\d{2}/.test(published) && /^\d{4}-\d{2}-\d{2}/.test(active) && published.slice(0, 10) < day && active.slice(0, 10) < day; });
      olderPages = older ? olderPages + 1 : 0;
      if (rows.length < MEASUREMENT.pageSize || olderPages >= 2) { result.complete = true; result.reason = rows.length < MEASUREMENT.pageSize ? "公开列表已读至末页" : "连续两页已越过日期起点"; break; }
    } catch (error) { result.error = error instanceof Error ? error.message : "读取失败"; result.reason = "部分采集失败，数量为已观察下限"; break; }
  }
  return result;
}

export type TradingRow = { code: string; name: string; price: number | null; changePct: number | null; turnover: number | null; amount: number | null; volumeRatio: number | null; activityScore: number | null; baselineDays: number; asOf: string; source: string; error: string | null };
const finite = (value: unknown): number | null => value == null || value === "" || value === "-" || !Number.isFinite(Number(value)) ? null : Number(value);
export async function collectTrading(code: string, day: string, prefix = marketPrefix(code)): Promise<TradingRow> {
  const result: TradingRow = { code, name: code, price: null, changePct: null, turnover: null, amount: null, volumeRatio: null, activityScore: null, baselineDays: 0, asOf: "", source: "", error: null };
  const symbol = `${prefix}${code}`;
  try {
    const raw = await fetchText(`https://qt.gtimg.cn/q=${symbol}`, "gb18030");
    const fields = raw.match(new RegExp(`v_${symbol}="([^"]*)"`))?.[1].split("~");
    if (fields && fields.length >= 39 && fields[2] === code) {
      result.name = fields[1] || code;
      if (fields[30]?.startsWith(day.replaceAll("-", ""))) Object.assign(result, { price: finite(fields[3]), changePct: finite(fields[32]), turnover: finite(fields[38]), amount: finite(fields[37]) == null ? null : Number(fields[37]) * 10000, asOf: fields[30], source: "腾讯公开报价" });
    }
  } catch { /* The historical endpoint can still provide the selected close. */ }
  try {
    const param = `${symbol},day,,${day},80,qfq`;
    const payload = JSON.parse(await fetchText(`https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=${encodeURIComponent(param)}`)) as { data?: Record<string, { qfqday?: string[][]; day?: string[][] }> };
    const rows = (payload.data?.[symbol]?.qfqday || payload.data?.[symbol]?.day || []).filter(row => row.length >= 6 && row[0] <= day).sort((a, b) => a[0].localeCompare(b[0]));
    const current = rows.find(row => row[0] === day);
    const past = rows.filter(row => row[0] < day);
    if (current) {
      const missingQuote = result.price == null;
      if (missingQuote) result.price = finite(current[2]);
      const previousClose = finite(past.at(-1)?.[2]);
      if (missingQuote && previousClose != null && previousClose > 0 && result.price != null) result.changePct = round((result.price / previousClose - 1) * 100);
      result.asOf = `${day} 15:00`;
      result.source = missingQuote ? "腾讯公开日线（参考价前复权；成交量历史分位）" : "腾讯公开报价 + 日线成交量";
      const volumes = past.slice(-60).map(row => finite(row[5])).filter((value): value is number => value != null && value > 0);
      const volume = finite(current[5]);
      result.baselineDays = volumes.length;
      if (volumes.length >= MEASUREMENT.minimumBaselineDays && volume != null) {
        result.activityScore = round(100 * volumes.reduce((sum, value) => sum + (value < volume ? 1 : value === volume ? .5 : 0), 0) / volumes.length);
        result.volumeRatio = round(volume / (volumes.slice(-20).reduce((a, b) => a + b, 0) / 20));
      }
    } else result.error = "所选日期历史日线缺失";
  } catch { result.error = "历史成交基线暂不可用"; }
  return result;
}

export function summarizeTrading(rows: TradingRow[]) {
  const quoted = rows.filter(row => row.changePct != null);
  const scored = rows.filter(row => row.activityScore != null);
  const minCoverage = Math.ceil(rows.length * .7);
  const up = quoted.filter(row => row.changePct! > 0).length;
  return { score: scored.length >= minCoverage && minCoverage > 0 ? round(scored.reduce((sum, row) => sum + row.activityScore!, 0) / scored.length) : null, coverage: quoted.length, baselineCoverage: scored.length, total: rows.length, up, down: quoted.filter(row => row.changePct! < 0).length, upRate: quoted.length ? round(up / quoted.length * 100) : null, averageChange: quoted.length ? round(quoted.reduce((sum, row) => sum + row.changePct!, 0) / quoted.length) : null, members: rows, reason: scored.length < minCoverage ? "历史成交基线不足" : "成分成交量历史分位的等权均值" };
}
export type TradingSummary = ReturnType<typeof summarizeTrading>;

export async function mapLimit<T, U>(items: T[], limit: number, action: (item: T) => Promise<U>): Promise<U[]> {
  const results: U[] = Array(items.length);
  let cursor = 0;
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, async () => { while (cursor < items.length) { const index = cursor++; results[index] = await action(items[index]); } }));
  return results;
}
