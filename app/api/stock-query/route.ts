import themesConfig from "../../../config/themes.json";
import targetsConfig from "../../../config/targets.json";
import persisted from "../../../public/data/latest.json";
import { METHOD_VERSION, prepareObservations, summarizeExpressions, historicalPercentile, universeKey, marketPrefix, type BaselinePoint } from "../../../lib/measurement";
import { collectFeed, collectTrading, summarizeTrading, latestSession, validSession, CUTOFF, fetchText, mapLimit } from "../../../lib/observations";

type Member = { code: string; name: string; role: string; prefix?: string };
async function resolve(input: string): Promise<{ id: string; name: string; kind: "stock" | "basket" | "proxy"; description: string; members: Member[] }> {
  const normalized = input.trim().toLowerCase();
  const theme = themesConfig.themes.find(item => item.id === normalized || item.name === input || item.aliases.includes(input));
  if (theme) return { ...theme, kind: "basket" };
  const target = targetsConfig.targets.find(item => item.id === normalized || item.name === input);
  if (target && target.id !== "market") return { id: target.id, name: target.name, kind: "proxy", description: `单股主题代理：${target.representative || target.name}，尚未覆盖整个板块。`, members: [{ code: target.stockCode, name: target.representative || target.name, role: "单股代理" }] };
  const exactName = [...themesConfig.themes.flatMap(item => item.members), ...targetsConfig.targets.map(item => ({ code: item.stockCode, name: "representative" in item ? item.representative : item.name }))].find(item => item.name === input);
  const parsed = input.toUpperCase().match(/^(?:(SH|SZ|BJ))?(\d{6})$/);
  let code = parsed?.[2] || exactName?.code;
  let prefix = parsed?.[1]?.toLowerCase();
  let name = exactName?.name || input;
  if (!code) {
    const raw = await fetchText(`https://smartbox.gtimg.cn/s3/?q=${encodeURIComponent(input)}&t=gp`);
    const hint = raw.match(/v_hint="([^"]*)"/)?.[1];
    let decoded = hint || "";
    try { decoded = JSON.parse(`"${decoded}"`); } catch { /* Plain hints need no escape decoding. */ }
    const parts = decoded.split("^")[0].split("~");
    if (parts.length >= 3 && /^(sh|sz|bj)$/.test(parts[0]) && /^\d{6}$/.test(parts[1])) { prefix = parts[0]; code = parts[1]; name = parts[2]; }
  }
  if (!code) throw new Error("未找到 A 股代码或已配置主题，请输入如 920970、牧原股份或猪肉");
  return { id: code, name, kind: "stock", description: "个股公开社区观察，不代表整个行业或实际持仓人数。", members: [{ code, name, role: "个股", prefix: prefix || marketPrefix(code) }] };
}

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const input = (params.get("q") || params.get("code") || "").trim();
  const date = params.get("date") || latestSession();
  if (!input || input.length > 80) return Response.json({ error: "请输入股票代码、名称或主题（最多 80 字）" }, { status: 400 });
  if (!validSession(date)) return Response.json({ error: "请选择 2026 年已收盘的交易日；不支持未来日期、休市日或无效日期" }, { status: 400 });
  const started = Date.now();
  try {
    const scope = await resolve(input);
    const collected = await mapLimit(scope.members, 4, async member => {
      const [feed, trading] = await Promise.all([collectFeed(member.code, date), collectTrading(member.code, date, member.prefix)]);
      return { feed, trading, member };
    });
    const feeds = collected.map(row => row.feed);
    const prepared = prepareObservations(feeds.flatMap(feed => feed.rows), date, CUTOFF);
    const expressions = summarizeExpressions(prepared.analyzed);
    const complete = feeds.every(feed => feed.complete && !feed.error);
    const universe = universeKey(scope.members.map(member => member.code));
    const history = (persisted as unknown as { attentionHistory?: Record<string, BaselinePoint[]> }).attentionHistory?.[universe] || [];
    const attention = { ...historicalPercentile(prepared.unknownAuthorPosts ? null : prepared.observedAuthors, history, date, universe, complete, CUTOFF), universe, complete, observedAuthors: prepared.observedAuthors, observedPosts: prepared.observedPosts, unknownAuthorPosts: prepared.unknownAuthorPosts, rawCount: feeds.reduce((sum, feed) => sum + feed.rawCount, 0), analyzedCount: expressions.sampleCount, memberCoverage: feeds.filter(feed => feed.complete).length, memberTotal: feeds.length, source: "东方财富公开列表", cutoff: CUTOFF, excludedDate: prepared.excludedDate, excludedNoise: prepared.excludedNoise };
    const trading = summarizeTrading(collected.map(row => row.trading));
    const posts = prepared.analyzed.slice().sort((a, b) => b.date.localeCompare(a.date)).slice(0, 80).map(post => { const { author, ...publicPost } = post; void author; return publicPost; });
    const single = trading.members[0];
    return Response.json({ methodVersion: METHOD_VERSION, input, id: scope.id, name: scope.kind === "stock" ? single.name : scope.name, kind: scope.kind, description: scope.description, members: scope.members.map((member, index) => ({ ...member, name: trading.members[index].name })), date, cutoff: CUTOFF, dataWindow: `${date} 00:00–15:00（北京时间）`, symbol: scope.kind === "stock" ? `${scope.members[0].prefix}${scope.members[0].code}` : null, market: scope.kind === "stock" ? ({ bj: "A股·北交所", sh: "A股·沪市", sz: "A股·深市" }[scope.members[0].prefix!] || "A股") : "自定义主题观察", attention, expressions, trading, posts, feeds: feeds.map(feed => { const { rows, ...info } = feed; void rows; return info; }), fetchedAt: new Date().toISOString(), durationMs: Date.now() - started, note: "比例的分母为本窗口内去重、每账户限量后的表达样本；L1–L5 分级暂缓。账户数为所采社区已观察数，不是持仓人数。" }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) { return Response.json({ error: error instanceof Error ? error.message : "查询失败" }, { status: 502 }); }
}
