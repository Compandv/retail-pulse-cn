"use client";

import { useEffect, useMemo, useState } from "react";

type MetricKey = "novice" | "fomo" | "panic" | "heat";
type ViewKey = "overview" | "sectors" | "explore" | "intelligence" | "method";

type HistoryPoint = {
  date: string;
  overall: number;
  direction: number;
  novice: number;
  fomo: number;
  panic: number;
  heat: number;
  profitEffect?: number;
  recordType?: "estimated" | "measured";
};

type ParticipantMix = {
  key: string;
  label: string;
  count: number;
  share: number;
};

type Sector = {
  id: string;
  name: string;
  stockCode?: string;
  group: string;
  representative: string;
  overall: number;
  direction: number;
  novice: number;
  fomo: number;
  panic: number;
  heat: number;
  sampleCount: number;
  sampleCount3d: number;
  sampleShare: number;
  sampleChange: number;
  dataWindow: string;
  mixWindow: string;
  confidence: string;
  change: number;
  heatChange: number;
  heatChange5d?: number | null;
  heatChangeAvailable: boolean;
  heatChange5dAvailable: boolean;
  heatTrend: string;
  heatSeries: Array<{ date: string; value: number }>;
  participantMix: ParticipantMix[];
  priceChange?: number | null;
  profitEffect: number;
  flowNet?: number | null;
  flow5d?: number | null;
  flowRatio?: number | null;
  flowAvailable: boolean;
  flowSource?: string;
  rank: number;
  rankChange: number;
  buyIndex?: number;
  sellIndex?: number;
  buySellRatio?: number;
};

type MarketStats = {
  heat: number;
  priceChange?: number | null;
  profitEffect: number;
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

type CommentRow = {
  id: string;
  date: string;
  source: string;
  sectorId: string;
  sectorName: string;
  excerpt: string;
  tone: "panic" | "fomo" | "novice" | "bull" | "bear" | "neutral";
  intent: string;
  signals: string[];
};

type Correlation = {
  days: number;
  minimumDays?: number;
  sufficient?: boolean;
  sectors: Array<{ id: string; name: string; group: string }>;
  matrix: Array<Array<number | null>>;
  pairs: Array<{ left: string; right: string; r: number; strength: string }>;
};

type CalendarPoint = {
  date: string;
  overall: number;
  heat: number;
  sampleCount: number | null;
  bucket: "hot" | "warm" | "cool" | "cold";
  recordType: "estimated" | "measured";
};

type Source = {
  id: string;
  name: string;
  status: "ok" | "partial" | "failed" | "demo";
  sampleCount: number;
  note: string;
};

type Snapshot = {
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
    buyIndex?: number;
    sellIndex?: number;
    buySellRatio?: number;
    change: number;
    sampleCount: number;
    label: string;
    readout: string;
  };
  history: HistoryPoint[];
  marketStats?: MarketStats;
  sectorHistory?: Array<{ date: string; sectors: Array<{ id: string; heat: number; overall: number }> }>;
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

const METRICS: Array<{ key: MetricKey; label: string; hint: string; color: string }> = [
  { key: "novice", label: "新手入场", hint: "求助、跟随与基础操作表达", color: "var(--blue)" },
  { key: "fomo", label: "追涨冲动", hint: "上车、梭哈与错失焦虑", color: "var(--vermillion)" },
  { key: "panic", label: "恐慌割肉", hint: "亏损、逃离与失控表达", color: "var(--purple)" },
  { key: "heat", label: "讨论热度", hint: "相对活跃度，不等于看多", color: "var(--amber)" },
];

const STATUS_LABELS: Record<Source["status"], string> = {
  ok: "正常",
  partial: "部分",
  failed: "缺失",
  demo: "演示",
};

function clamp(value: number, min = 0, max = 100) {
  return Math.min(max, Math.max(min, value));
}

function signed(value: number, suffix = "") {
  if (value > 0) return `+${value.toFixed(1)}${suffix}`;
  return `${value.toFixed(1)}${suffix}`;
}

function formatFlow(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}亿`;
}

function formatPct(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return signed(value, "%");
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit" }).format(
    new Date(`${value}T00:00:00+08:00`),
  );
}

function LineChart({ points, metric = "overall" }: { points: HistoryPoint[]; metric?: keyof HistoryPoint }) {
  const width = 760;
  const height = 238;
  const padX = 16;
  const padY = 22;
  const values = points.map((point) => {
    const raw = metric === "profitEffect" ? point.profitEffect ?? point.overall : point[metric];
    const value = Number(raw);
    return Number.isFinite(value) ? value : 50;
  });
  const isDirection = metric === "direction";
  const domainMin = isDirection ? -100 : 0;
  const domainMax = 100;
  const x = (index: number) => padX + (index / Math.max(points.length - 1, 1)) * (width - padX * 2);
  const y = (value: number) =>
    padY + ((domainMax - value) / (domainMax - domainMin)) * (height - padY * 2);
  const path = values.map((value, index) => `${index === 0 ? "M" : "L"}${x(index).toFixed(1)},${y(value).toFixed(1)}`).join(" ");
  const area = `${path} L${x(values.length - 1).toFixed(1)},${y(domainMin).toFixed(1)} L${x(0).toFixed(1)},${y(domainMin).toFixed(1)} Z`;
  const neutralY = y(isDirection ? 0 : 50);

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`最近 ${points.length} 个有观测交易日情绪趋势`}>
        <defs>
          <linearGradient id={`area-${metric}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#e85432" stopOpacity="0.24" />
            <stop offset="100%" stopColor="#e85432" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((ratio) => (
          <line key={ratio} x1={padX} x2={width - padX} y1={padY + ratio * (height - padY * 2)} y2={padY + ratio * (height - padY * 2)} className="grid-line" />
        ))}
        <line x1={padX} x2={width - padX} y1={neutralY} y2={neutralY} className="neutral-line" />
        {!isDirection && <path d={area} fill={`url(#area-${metric})`} />}
        <path d={path} className="trend-line" />
        {values.map((value, index) => (
          <circle key={`${points[index].date}-${value}`} cx={x(index)} cy={y(value)} r={index === values.length - 1 ? 4.6 : 2.1} className={index === values.length - 1 ? "last-dot" : "trend-dot"}>
            <title>{`${points[index].date}：${value.toFixed(1)}（${points[index].recordType === "estimated" ? "历史估算" : "实测"}）`}</title>
          </circle>
        ))}
      </svg>
      <div className="chart-axis" aria-hidden="true">
        <span>{formatDate(points[0]?.date ?? "")}</span>
        <span>{formatDate(points[Math.floor(points.length / 2)]?.date ?? "")}</span>
        <span>{formatDate(points[points.length - 1]?.date ?? "")}</span>
      </div>
    </div>
  );
}

function MetricCard({ label, value, hint, color }: { label: string; value: number; hint: string; color: string }) {
  return (
    <article className="metric-card">
      <div className="metric-head">
        <span>{label}</span>
        <strong>{value.toFixed(1)}</strong>
      </div>
      <div className="metric-track" aria-label={`${label} ${value.toFixed(1)} 分`}>
        <span style={{ width: `${clamp(value)}%`, background: color }} />
      </div>
      <p>{hint}</p>
    </article>
  );
}

function HeatSparkline({ points }: { points: Array<{ date: string; value: number }> }) {
  if (!points.length) return <div className="sparkline empty">等待每日数据</div>;
  const width = 220;
  const height = 42;
  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = Math.max(8, max - min);
  const x = (index: number) => (index / Math.max(1, points.length - 1)) * width;
  const y = (value: number) => 5 + ((max - value) / spread) * (height - 10);
  const path = points.map((point, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(point.value).toFixed(1)}`).join(" ");
  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="板块最近热度轨迹">
      {points.length > 1 && <path d={path} />}
      {points.map((point, index) => <circle key={point.date} cx={x(index)} cy={y(point.value)} r={index === points.length - 1 ? 3 : 2}><title>{point.date}：{point.value.toFixed(1)}</title></circle>)}
    </svg>
  );
}

function SectorCard({ sector }: { sector: Sector }) {
  const directionLabel = sector.direction > 8 ? "偏多" : sector.direction < -8 ? "偏空" : "中性";
  const mix = (sector.participantMix ?? []).slice(0, 4);
  const trendClass = !sector.heatChangeAvailable ? "flat" : sector.heatChange > 1 ? "hot" : sector.heatChange < -1 ? "cool" : "flat";
  return (
    <article className="sector-card">
      <div className="sector-topline">
        <div>
          <span className="eyebrow">{sector.group} · #{sector.rank} · {sector.confidence}级</span>
          <h3>{sector.name}</h3>
          <small className="representative">代表标的：{sector.representative}</small>
        </div>
        <div className="sector-score">
          <strong>{sector.overall.toFixed(0)}</strong>
          <span className={sector.change >= 0 ? "rise" : "fall"}>{signed(sector.change)}</span>
        </div>
      </div>
      <div className="sector-bar" aria-label={`${sector.name}温度 ${sector.overall.toFixed(1)} 分`}>
        <span style={{ width: `${clamp(sector.overall)}%` }} />
      </div>
      <div className="sector-hotline">
        <span className={`heat-badge ${trendClass}`}>{sector.heatTrend}</span>
        <span>热度 {sector.heat.toFixed(1)}</span>
        <b className={sector.heatChange >= 0 ? "rise" : "fall"}>{sector.heatChangeAvailable ? signed(sector.heatChange) : "—"}</b>
        <small>1日</small>
      </div>
      <div className="sector-five-day"><span>5日热度变化</span><b className={(sector.heatChange5d ?? 0) >= 0 ? "rise" : "fall"}>{sector.heatChange5dAvailable ? signed(sector.heatChange5d ?? 0) : "基线积累中"}</b></div>
      <HeatSparkline points={sector.heatSeries ?? []} />
      <div className="sector-detail-grid">
        <span><small>赚钱效应</small><b>{sector.profitEffect.toFixed(1)}</b></span>
        <span><small>代表股涨跌</small><b>{formatPct(sector.priceChange)}</b></span>
        <span><small>1日净流入</small><b className={sector.flowNet !== null && sector.flowNet !== undefined && sector.flowNet < 0 ? "fall" : "rise"}>{formatFlow(sector.flowNet)}</b></span>
        <span><small>5日净流入</small><b className={sector.flow5d !== null && sector.flow5d !== undefined && sector.flow5d < 0 ? "fall" : "rise"}>{formatFlow(sector.flow5d)}</b></span>
      </div>
      <div className="sector-stats">
        <span><b>{directionLabel}</b> {signed(sector.direction)}</span>
        <span><b>{sector.sampleCount}</b> 条当日 · 3日 {sector.sampleCount3d}</span>
      </div>
      <div className="sector-share"><span>散户讨论占比</span><b>{sector.sampleShare.toFixed(1)}%</b></div>
      <div className="participant-mix" aria-label={`${sector.name}散户表达构成`}>
        {mix.length ? mix.map((item) => <span key={item.key}><i style={{ width: `${item.share}%` }} />{item.label} {item.share.toFixed(0)}%</span>) : <span>暂无足够表达构成</span>}
      </div>
      <p className="mix-note">成分口径：{sector.mixWindow}聚合表达，不推断账号真实身份。</p>
    </article>
  );
}

function MarketStatCard({ label, value, hint, tone = "" }: { label: string; value: string; hint: string; tone?: string }) {
  return (
    <article className="market-stat-card">
      <span className="eyebrow">{label}</span>
      <strong className={tone}>{value}</strong>
      <small>{hint}</small>
    </article>
  );
}

function CommentFeed({ comments }: { comments: CommentRow[] }) {
  const toneLabel: Record<CommentRow["tone"], string> = {
    panic: "恐慌", fomo: "追涨", novice: "求助", bull: "看多", bear: "看空", neutral: "观望",
  };
  return (
    <div className="comment-feed">
      {comments.length ? comments.map((comment) => (
        <article className="comment-row" key={comment.id}>
          <div className={`comment-tone ${comment.tone}`}>{toneLabel[comment.tone]}</div>
          <div className="comment-body">
            <p>{comment.excerpt}</p>
            <small>{comment.sectorName} · {comment.source} · {comment.date}</small>
          </div>
          <span className="comment-intent">{comment.intent}</span>
        </article>
      )) : <div className="empty-state">今天还没有足够的匿名评论样本。</div>}
    </div>
  );
}

function MoodCalendar({ points }: { points: CalendarPoint[] }) {
  const bucketLabel = { hot: "亢奋", warm: "升温", cool: "平稳", cold: "冷清" };
  return (
    <div>
      <div className="calendar-grid">
        {points.length ? points.map((point) => (
          <div className={`calendar-cell ${point.bucket}`} key={point.date} title={`${point.date} · 温度 ${point.overall.toFixed(1)} · 热度 ${point.heat.toFixed(1)} · ${point.sampleCount == null ? "—" : `${point.sampleCount} 条`} · ${point.recordType === "estimated" ? "估算" : "实测"}`}>
            <strong>{point.date.slice(5)}</strong>
            <span>{point.overall.toFixed(0)}</span>
          </div>
        )) : <div className="empty-state">暂无 30 日数据，运行每日更新后会逐步填充。</div>}
      </div>
      <div className="calendar-legend">{Object.entries(bucketLabel).map(([key, label]) => <span key={key}><i className={`legend-swatch ${key}`} />{label}</span>)}<small>色块为情绪温度，数字为综合分</small></div>
    </div>
  );
}

function correlationColor(value: number | null) {
  if (value === null || !Number.isFinite(value)) return "rgba(148,163,184,.1)";
  if (value >= 0) return `rgba(232,84,50,${0.12 + Math.abs(value) * 0.55})`;
  return `rgba(36,122,107,${0.12 + Math.abs(value) * 0.55})`;
}

function CorrelationHeatmap({ correlation }: { correlation?: Correlation }) {
  if (!correlation || !correlation.sectors.length || correlation.sufficient === false) return <div className="empty-state">联动数据积累中：当前 {correlation?.days ?? 0} 个交易日，至少需要 {correlation?.minimumDays ?? 5} 个共同观测日。</div>;
  return (
    <div className="correlation-layout">
      <div className="heatmap-scroll">
        <table className="correlation-table">
          <thead><tr><th />{correlation.sectors.map((sector) => <th key={sector.id} title={sector.name}>{sector.name.slice(0, 4)}</th>)}</tr></thead>
          <tbody>{correlation.sectors.map((row, rowIndex) => <tr key={row.id}><th title={row.name}>{row.name}</th>{correlation.sectors.map((col, colIndex) => { const value = correlation.matrix[rowIndex]?.[colIndex] ?? null; return <td key={col.id} style={{ background: correlationColor(value) }} title={`${row.name} × ${col.name}：${value === null ? "数据不足" : value.toFixed(1)}`}>{value === null ? "·" : value.toFixed(1)}</td>; })}</tr>)}</tbody>
        </table>
      </div>
      <div className="pair-list"><span className="eyebrow">强联动对</span>{correlation.pairs.slice(0, 8).map((pair) => <div className="pair-row" key={`${pair.left}-${pair.right}`}><span>{pair.left} × {pair.right}</span><b className={pair.r >= 0 ? "rise" : "fall"}>{pair.r > 0 ? "+" : ""}{pair.r.toFixed(1)}</b></div>)}{!correlation.pairs.length && <p className="fine-print">当前样本还不足以形成显著联动。</p>}</div>
    </div>
  );
}

type OnlineStockPost = {
  title: string;
  score: number;
  date: string;
  url: string;
  matched: string[];
};

type OnlineStockResult = {
  input: string;
  code: string;
  symbol: string;
  name: string;
  market: string;
  quote: {
    price: number;
    changePct: number;
    asOf?: string;
    source?: string;
  } | null;
  metrics: {
    overall: number;
    heat: number;
    novice: number;
    fomo: number;
    panic: number;
    direction: number;
    buyIndex: number;
    sellIndex: number;
    buySellRatio: number;
    profitEffect: number;
  } | null;
  sampleCount: number;
  analyzedCount: number;
  posts: OnlineStockPost[];
  fetchError?: string | null;
  fetchedAt: string;
  durationMs: number;
  source: string;
  note: string;
};

function QueryPanel({ snapshot }: { snapshot: Snapshot }) {
  const [query, setQuery] = useState("");
  const [onlineResult, setOnlineResult] = useState<OnlineStockResult | null>(null);
  const [onlineLoading, setOnlineLoading] = useState(false);
  const [onlineError, setOnlineError] = useState("");
  const result = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return null;
    return snapshot.sectors.find((sector) => [sector.id, sector.name, sector.group].some((value) => String(value ?? "").toLowerCase().includes(keyword))) ?? null;
  }, [query, snapshot.sectors]);
  const relatedComments = result ? (snapshot.comments ?? []).filter((comment) => comment.sectorId === result.id).slice(0, 3) : [];
  const runQuery = async (value = query) => {
    const keyword = value.trim();
    if (!keyword) return;
    setQuery(keyword);
    setOnlineError("");
    setOnlineResult(null);
    // 已配置主题保留本地的完整历史和板块数据；代码/未配置名称走在线查询。
    const local = snapshot.sectors.find((sector) => [sector.id, sector.name, sector.group].some((item) => String(item ?? "").toLowerCase().includes(keyword.toLowerCase())));
    if (local) return;
    setOnlineLoading(true);
    try {
      const response = await fetch(`/api/stock-query?q=${encodeURIComponent(keyword)}`, { cache: "no-store" });
      const payload = await response.json() as OnlineStockResult & { error?: string };
      if (!response.ok || payload.error) throw new Error(payload.error || "在线查询失败");
      setOnlineResult(payload);
    } catch (error) {
      setOnlineError(error instanceof Error ? error.message : "在线查询失败，请稍后重试");
    } finally {
      setOnlineLoading(false);
    }
  };
  const onlineMetrics = onlineResult?.metrics;
  return (
    <article className="panel query-panel">
      <div className="panel-head"><div><span className="eyebrow">股票 / 主题查询</span><h2>查一只股票的情绪</h2></div><span className="online-badge">● 支持在线查询任意 A 股</span></div>
      <div className="query-form"><input aria-label="输入股票代码、名称或主题" placeholder="例如：600519、贵州茅台、300750、宁德时代" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void runQuery(); }} /><button onClick={() => void runQuery()} disabled={onlineLoading}>{onlineLoading ? "查询中…" : "查询"}</button></div>
      <div className="query-hints">试试：{snapshot.sectors.slice(0, 5).map((sector) => <button key={sector.id} onClick={() => void runQuery(sector.name)}>{sector.name}</button>)}</div>
      {onlineLoading && <div className="query-loading">正在查询公开代码、行情和股吧样本…</div>}
      {onlineError && <div className="query-error">在线查询失败：{onlineError}<br /><small>仍可查询已配置主题；上游公开接口可能暂时限流。</small></div>}
      {query && !result && !onlineResult && !onlineLoading && !onlineError && <div className="query-error">未匹配到本地主题，点击“查询”可在线查找任意 A 股。</div>}
      {result && !onlineResult && <div className="query-result"><div className="query-result-head"><div><span className="eyebrow">{result.group} · 代表标的 {result.representative}</span><h3>{result.name}</h3></div><strong>{result.overall.toFixed(1)}</strong></div><div className="query-stat-grid"><span>热度 <b>{result.heat.toFixed(1)}</b></span><span>买入 <b>{(result.buyIndex ?? 50).toFixed(1)}</b></span><span>卖出 <b>{(result.sellIndex ?? 50).toFixed(1)}</b></span><span>赚钱效应 <b>{result.profitEffect.toFixed(1)}</b></span><span>涨跌 <b>{formatPct(result.priceChange)}</b></span><span>净流入 <b>{formatFlow(result.flowNet)}</b></span></div><HeatSparkline points={result.heatSeries ?? []} /><CommentFeed comments={relatedComments} /></div>}
      {onlineResult && <div className="query-result online-query-result"><div className="query-result-head"><div><span className="eyebrow">{onlineResult.market} · {onlineResult.symbol} · 公开社区样本</span><h3>{onlineResult.name}</h3><small className="query-source">查询耗时 {onlineResult.durationMs}ms · {onlineResult.fetchedAt.slice(0, 16).replace("T", " ")}</small></div><strong>{onlineMetrics ? onlineMetrics.overall.toFixed(1) : "—"}</strong></div>{onlineMetrics ? <div className="query-stat-grid"><span>讨论热度 <b>{onlineMetrics.heat.toFixed(1)}</b></span><span>新手入场 <b>{onlineMetrics.novice.toFixed(1)}</b></span><span>追涨冲动 <b>{onlineMetrics.fomo.toFixed(1)}</b></span><span>恐慌割肉 <b>{onlineMetrics.panic.toFixed(1)}</b></span><span>买入指数 <b>{onlineMetrics.buyIndex.toFixed(1)}</b></span><span>卖出指数 <b>{onlineMetrics.sellIndex.toFixed(1)}</b></span><span>赚钱效应 <b>{onlineMetrics.profitEffect.toFixed(1)}</b></span><span>代表股涨跌 <b className={onlineResult.quote && onlineResult.quote.changePct >= 0 ? "rise" : "fall"}>{onlineResult.quote ? formatPct(onlineResult.quote.changePct) : "—"}</b></span></div> : <div className="query-empty">最近公开帖子不足，暂时无法计算情绪指数。</div>}{onlineResult.quote && <div className="query-quote"><b>{onlineResult.quote.price.toFixed(2)}</b><span className={onlineResult.quote.changePct >= 0 ? "rise" : "fall"}>{formatPct(onlineResult.quote.changePct)}</span><small>{onlineResult.quote.source} · {onlineResult.quote.asOf || "最新"}</small></div>}<div className="online-post-head"><span className="eyebrow">最近典型帖子</span><small>原始 {onlineResult.sampleCount} 条 · 有效分析 {onlineResult.analyzedCount} 条</small></div>{onlineResult.posts.length ? <div className="online-post-list">{onlineResult.posts.slice(0, 6).map((post) => <a className="online-post" href={post.url} target="_blank" rel="noreferrer" key={`${post.url}-${post.title}`}><span className="post-score">{post.score.toFixed(0)}</span><span><b>{post.title}</b><small>{post.date || "公开帖子"}{post.matched.length ? ` · 命中：${post.matched.slice(0, 3).join("、")}` : ""}</small></span></a>)}</div> : <div className="query-empty">暂无可展示的典型帖子。{onlineResult.fetchError ? ` ${onlineResult.fetchError}` : ""}</div>}<p className="online-note">{onlineResult.note}</p></div>}
      <p className="fine-print">个股结果来自公开社区样本代理；不等于完整市场情绪或板块成分指数，也不构成投资建议。</p>
    </article>
  );
}

function IntelligencePanel({ snapshot }: { snapshot: Snapshot }) {
  return (
    <section className="intelligence-grid">
      <article className="panel insight-card"><div className="panel-head"><div><span className="eyebrow">AI 智能解读 · 本地规则版</span><h2>今天市场怎么吵</h2></div><span className="pulse-dot" /></div><p>{snapshot.interpretation?.interpretation ?? "等待更多数据后生成解读。"}</p><small>解读引用当前快照的热度、情绪、样本与板块变化，不调用外部模型。</small></article>
      <article className="panel tongue-card"><div className="panel-head"><div><span className="eyebrow">毒舌所</span><h2>老韭菜短评</h2></div><span className="tongue-mark">🌶️</span></div><p>{snapshot.interpretation?.tongue ?? "数据还没攒够，先别急着给市场下结论。"}</p><small>辛辣表达只用于提醒偏差，不提供买卖指令。</small></article>
    </section>
  );
}

export function Dashboard({ initialSnapshot }: { initialSnapshot: Snapshot }) {
  const [view, setView] = useState<ViewKey>("overview");
  const [range, setRange] = useState(20);
  const [chartMetric, setChartMetric] = useState<"overall" | "direction" | "heat" | "profitEffect">("overall");
  const [sectorSort, setSectorSort] = useState<"heatChange" | "heat" | "flow" | "profit">("heatChange");
  const [sectorGroup, setSectorGroup] = useState("全部");
  const [snapshot, setSnapshot] = useState(initialSnapshot);
  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const response = await fetch(`/data/latest.json?refresh=${Date.now()}`, { cache: "no-store" });
        if (!response.ok) return;
        const next = await response.json() as Snapshot;
        if (active && next?.meta?.tradeDate) setSnapshot(next);
      } catch {
        // The bundled snapshot remains available when the local updater is offline.
      }
    };
    refresh();
    const timer = window.setInterval(refresh, 5 * 60 * 1000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);
  const history = useMemo(() => snapshot.history.slice(-range), [snapshot.history, range]);
  const marketStats = snapshot.marketStats;
  const sectorGroups = useMemo(() => ["全部", ...Array.from(new Set(snapshot.sectors.map((sector) => sector.group).filter(Boolean)))], [snapshot.sectors]);
  const rankedSectors = useMemo(() => {
    const sectors = snapshot.sectors.filter((sector) => sectorGroup === "全部" || sector.group === sectorGroup);
    if (sectorSort === "heatChange") return sectors.sort((a, b) => b.heatChange - a.heatChange || b.heat - a.heat);
    if (sectorSort === "heat") return sectors.sort((a, b) => b.heat - a.heat || b.overall - a.overall);
    if (sectorSort === "flow") return sectors.sort((a, b) => (b.flowNet ?? -Infinity) - (a.flowNet ?? -Infinity));
    return sectors.sort((a, b) => b.profitEffect - a.profitEffect || b.overall - a.overall);
  }, [snapshot.sectors, sectorGroup, sectorSort]);
  const hotSectors = useMemo(() => [...snapshot.sectors].sort((a, b) => b.heatChange - a.heatChange || b.heat - a.heat).slice(0, 4), [snapshot.sectors]);
  const availableSources = snapshot.meta.sources.filter((source) => source.status === "ok" || source.status === "partial" || source.status === "demo").length;
  const totalSources = snapshot.meta.sources.length;
  const directionText = snapshot.summary.direction > 8 ? "讨论明显偏多" : snapshot.summary.direction < -8 ? "讨论明显偏空" : "多空接近平衡";

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="散户温度计首页">
          <span className="brand-mark">温</span>
          <span><strong>散户温度计</strong><small>RETAIL PULSE · CN</small></span>
        </a>
        <nav aria-label="主要视图">
          {([
            ["overview", "全市场"],
            ["sectors", "板块雷达"],
            ["explore", "股票查询"],
            ["intelligence", "洞察中心"],
            ["method", "方法审计"],
          ] as Array<[ViewKey, string]>).map(([key, label]) => (
            <button key={key} className={view === key ? "active" : ""} onClick={() => setView(key)}>{label}</button>
          ))}
        </nav>
        <div className="asof">
          <span className={`mode-dot ${snapshot.meta.mode}`} />
          <span>{snapshot.meta.mode === "live" ? "实测快照" : "演示快照"}<small>{snapshot.meta.tradeDate}</small></span>
        </div>
      </header>

      {view === "overview" && (
        <>
          <section className="hero" id="top">
            <div className="hero-copy">
              <span className="kicker">A 股普通投资者社区情绪</span>
              <h1>市场有温度，<br />情绪有证据。</h1>
              <p>把新手求助、追涨冲动、恐慌割肉和多空方向拆开看。高热不等于看多，也不是买卖指令。</p>
              <div className="hero-meta">
                <span>方法 {snapshot.meta.methodVersion}</span>
                <span>{availableSources}/{totalSources} 来源可用</span>
                <span>{snapshot.summary.sampleCount} 条有效样本</span>
              </div>
            </div>

            <div className="score-panel">
              <div className="score-ring" style={{ "--score": snapshot.summary.overall } as React.CSSProperties}>
                <div><strong>{snapshot.summary.overall.toFixed(1)}</strong><span>/ 100</span></div>
              </div>
              <div className="score-copy">
                <span className="eyebrow">综合散户温度</span>
                <h2>{snapshot.summary.label}</h2>
                <p>{snapshot.summary.readout}</p>
                <div className="score-change">
                  <b className={snapshot.summary.change >= 0 ? "rise" : "fall"}>{signed(snapshot.summary.change)}</b>
                  <span>较上一交易日</span>
                </div>
              </div>
            </div>

            <aside className="direction-card">
              <div className="direction-heading">
                <span className="eyebrow">情绪方向</span>
                <strong>{signed(snapshot.summary.direction)}</strong>
              </div>
              <div className="direction-scale">
                <span className="scale-marker" style={{ left: `${clamp((snapshot.summary.direction + 100) / 2)}%` }} />
              </div>
              <div className="scale-labels"><span>极度看空</span><span>中性</span><span>极度看多</span></div>
              <p>{directionText}。方向与热度分开计算，避免把恐慌误读成冷清。</p>
            </aside>
          </section>

          <section className="metrics-grid" aria-label="情绪分项">
            {METRICS.map((metric) => <MetricCard key={metric.key} {...metric} value={snapshot.summary[metric.key]} />)}
          </section>

          {marketStats && (
            <section className="market-strip" aria-label="市场赚钱效应与资金流向">
              <MarketStatCard label="全市场热度" value={marketStats.heat.toFixed(1)} hint="社区讨论活跃度" tone="rise" />
              <MarketStatCard label="代表池赚钱效应" value={marketStats.profitEffect.toFixed(1)} hint={`${marketStats.breadthUp ?? 0} 涨 / ${marketStats.breadthDown ?? 0} 跌 · 中位 ${formatPct(marketStats.breadthMedianChange)}`} />
              <MarketStatCard label="代表池上涨率" value={`${(marketStats.breadthUpRate ?? 0).toFixed(1)}%`} hint={`${marketStats.breadthTotal ?? 0} 个细分主题代表标的`} tone={(marketStats.breadthUpRate ?? 0) >= 50 ? "rise" : "fall"} />
              <MarketStatCard label="代表池主力净流入" value={formatFlow(marketStats.flowNet)} hint={marketStats.flowAvailable ? `${marketStats.flowCoverage ?? 0}/${marketStats.flowTotal ?? 0} 个主题可得` : "暂无公开字段"} tone={marketStats.flowNet !== null && marketStats.flowNet !== undefined && marketStats.flowNet < 0 ? "fall" : "rise"} />
              <MarketStatCard label="综合买入指数" value={(snapshot.summary.buyIndex ?? 50).toFixed(1)} hint="追涨 / 加仓表达" tone="rise" />
              <MarketStatCard label="综合卖出指数" value={(snapshot.summary.sellIndex ?? 50).toFixed(1)} hint="割肉 / 离场表达" tone="fall" />
            </section>
          )}

          <section className="content-grid">
            <article className="panel trend-panel">
              <div className="panel-head">
                <div><span className="eyebrow">交易日序列</span><h2>情绪轨迹</h2></div>
                <div className="segmented" aria-label="图表选项">
                  <button className={chartMetric === "overall" ? "active" : ""} onClick={() => setChartMetric("overall")}>温度</button>
                  <button className={chartMetric === "heat" ? "active" : ""} onClick={() => setChartMetric("heat")}>热度</button>
                  <button className={chartMetric === "profitEffect" ? "active" : ""} onClick={() => setChartMetric("profitEffect")}>赚钱效应</button>
                  <button className={chartMetric === "direction" ? "active" : ""} onClick={() => setChartMetric("direction")}>方向</button>
                  {[10, 20, 60].map((days) => <button key={days} className={range === days ? "active" : ""} onClick={() => setRange(days)}>{days}日</button>)}
                </div>
              </div>
              <LineChart points={history} metric={chartMetric} />
              <p className="history-note"><span className="history-key estimated" />已显示 {history.length}/{range} 个有观测交易日。{snapshot.meta.historyNote ?? "历史曲线由每日实测逐步累积。"}</p>
            </article>

            <article className="panel signal-panel">
              <div className="panel-head"><div><span className="eyebrow">高频证据</span><h2>今日表达</h2></div></div>
              <div className="signal-list">
                {snapshot.signals.map((signal, index) => (
                  <div className="signal-row" key={signal.label}>
                    <span className={`signal-rank ${signal.tone}`}>{String(index + 1).padStart(2, "0")}</span>
                    <span>{signal.label}</span>
                    <strong>{signal.count}</strong>
                  </div>
                ))}
              </div>
              <p className="fine-print">仅展示聚合标签，不公开用户名、用户 ID 或完整原帖。</p>
            </article>
          </section>

          <section className="panel sectors-preview">
            <div className="panel-head">
              <div><span className="eyebrow">最近变化</span><h2>升温板块</h2></div>
              <button className="text-button" onClick={() => setView("sectors")}>查看全部板块 →</button>
            </div>
            <div className="sector-grid">{hotSectors.map((sector) => <SectorCard key={sector.id} sector={sector} />)}</div>
          </section>
          <IntelligencePanel snapshot={snapshot} />
          <section className="content-grid secondary-grid">
            <article className="panel"><div className="panel-head"><div><span className="eyebrow">匿名实时评论</span><h2>今天大家在说什么</h2></div><button className="text-button" onClick={() => setView("explore")}>查看更多 →</button></div><CommentFeed comments={(snapshot.comments ?? []).slice(0, 8)} /></article>
            <article className="panel"><div className="panel-head"><div><span className="eyebrow">30 日情绪日历</span><h2>情绪温度分布</h2></div><button className="text-button" onClick={() => setView("intelligence")}>查看详情 →</button></div><MoodCalendar points={(snapshot.calendar ?? []).slice(-30)} /></article>
          </section>
        </>
      )}

      {view === "sectors" && (
        <section className="view-page">
          <div className="view-intro"><span className="kicker">SECTOR RADAR</span><h1>板块情绪雷达</h1><p>把当前热度、最近升降温、赚钱效应代理、资金流和散户表达构成放在一起。资金流使用公开接口可得的代表标的字段，缺失时显示“—”。</p></div>
          {marketStats && (
            <section className="market-strip sector-market-strip" aria-label="全市场概览">
              <MarketStatCard label="市场热度" value={marketStats.heat.toFixed(1)} hint="社区讨论活跃度" tone="rise" />
              <MarketStatCard label="代表池赚钱效应" value={marketStats.profitEffect.toFixed(1)} hint={`${marketStats.breadthUp ?? 0} 涨 / ${marketStats.breadthDown ?? 0} 跌`} />
              <MarketStatCard label="代表池上涨率" value={`${(marketStats.breadthUpRate ?? 0).toFixed(1)}%`} hint={`中位涨跌 ${formatPct(marketStats.breadthMedianChange)}`} tone={(marketStats.breadthUpRate ?? 0) >= 50 ? "rise" : "fall"} />
              <MarketStatCard label="代表池主力净流入" value={formatFlow(marketStats.flowNet)} hint={marketStats.flowAvailable ? `${marketStats.flowCoverage ?? 0}/${marketStats.flowTotal ?? 0} 个主题可得` : "暂无公开字段"} tone={marketStats.flowNet !== null && marketStats.flowNet !== undefined && marketStats.flowNet < 0 ? "fall" : "rise"} />
            </section>
          )}
          <div className="sector-toolbar" aria-label="板块排序">
            <span>板块：</span>
            {sectorGroups.map((group) => <button key={group} className={sectorGroup === group ? "active" : ""} onClick={() => setSectorGroup(group)}>{group}</button>)}
          </div>
          <div className="sector-toolbar" aria-label="板块排序">
            <span>排序：</span>
            {([[
              "heatChange", "最近升温",
            ], ["heat", "当前热度"], ["flow", "净流入"], ["profit", "赚钱效应"]] as Array<[typeof sectorSort, string]>).map(([key, label]) => (
              <button key={key} className={sectorSort === key ? "active" : ""} onClick={() => setSectorSort(key)}>{label}</button>
            ))}
          </div>
          <div className="sector-grid full">{rankedSectors.map((sector) => <SectorCard key={sector.id} sector={sector} />)}</div>
        </section>
      )}

      {view === "explore" && (
        <section className="view-page">
          <div className="view-intro"><span className="kicker">STOCK & TOPIC EXPLORER</span><h1>股票与主题查询</h1><p>输入已配置的股票代码、股票名称或细分主题，查看情绪、热度曲线、买卖子指数和匿名评论。</p></div>
          <QueryPanel snapshot={snapshot} />
          <section className="panel explore-comments"><div className="panel-head"><div><span className="eyebrow">实时评论流</span><h2>匿名表达样本</h2></div><span className="eyebrow">{(snapshot.comments ?? []).length} 条</span></div><CommentFeed comments={snapshot.comments ?? []} /></section>
        </section>
      )}

      {view === "intelligence" && (
        <section className="view-page">
          <div className="view-intro"><span className="kicker">MARKET INTELLIGENCE</span><h1>联动与情绪日历</h1><p>把每日积累的数据变成可追踪的关系：哪些板块一起升温，哪些板块互相背离，市场情绪在过去 30 天如何切换。</p></div>
          <IntelligencePanel snapshot={snapshot} />
          <article className="panel"><div className="panel-head"><div><span className="eyebrow">板块联动热力图</span><h2>最近 {snapshot.correlation?.days ?? 0} 个有观测交易日</h2></div></div><CorrelationHeatmap correlation={snapshot.correlation} /></article>
          <article className="panel calendar-panel"><div className="panel-head"><div><span className="eyebrow">散户情绪日历</span><h2>最近 30 天</h2></div></div><MoodCalendar points={snapshot.calendar ?? []} /></article>
        </section>
      )}

      {view === "method" && (
        <section className="view-page">
          <div className="view-intro"><span className="kicker">METHOD & AUDIT</span><h1>方法与数据审计</h1><p>这里不是免责声明角落，而是指数本身的一部分：知道今天抓到了什么，也知道没抓到什么。</p></div>
          <div className="audit-grid">
            <article className="panel method-card">
              <span className="eyebrow">01 · 分类</span><h2>先拆信号，再合成</h2>
              <p>规则引擎识别新手求助、追涨、恐慌、多空和垃圾内容。四项分数独立保留，综合温度只负责表达情绪强度。</p>
            </article>
            <article className="panel method-card">
              <span className="eyebrow">02 · 公平</span><h2>来源不按帖子量夺权</h2>
              <p>每个来源先独立聚合，再等权合并。缺失来源保留中性席位并降低置信度，不把失败伪装成零帖子。</p>
            </article>
            <article className="panel method-card">
              <span className="eyebrow">03 · 隐私</span><h2>只输出聚合证据</h2>
              <p>运行缓存不进入网页；看板不展示用户标识。“新手”描述表达方式，不推断真实性别、职业或家庭身份。</p>
            </article>
            <article className="panel method-card">
              <span className="eyebrow">04 · 市场数据</span><h2>行情字段单独标注</h2>
              <p>赚钱效应结合代表标的涨跌与社区信号估算；净流入来自公开主力资金字段。它们是观察代理，不等于完整板块成分统计。</p>
            </article>
          </div>
          <article className="panel sources-panel">
            <div className="panel-head"><div><span className="eyebrow">来源状态</span><h2>{snapshot.meta.tradeDate} 采集覆盖</h2></div><strong>{Math.round(snapshot.meta.coverage * 100)}%</strong></div>
            <div className="source-table" role="table" aria-label="数据源状态">
              {snapshot.meta.sources.map((source) => (
                <div className="source-row" role="row" key={source.id}>
                  <span role="cell"><i className={`status ${source.status}`} />{source.name}</span>
                  <span role="cell">{STATUS_LABELS[source.status]}</span>
                  <strong role="cell">{source.sampleCount} 条</strong>
                  <span role="cell">{source.note}</span>
                </div>
              ))}
            </div>
          </article>
          <div className="diagnostic-grid">
            <div><span>有效帖子</span><strong>{snapshot.diagnostics.validPosts}</strong></div>
            <div><span>过滤内容</span><strong>{snapshot.diagnostics.filteredPosts}</strong></div>
            <div><span>匿名作者键</span><strong>{snapshot.diagnostics.uniqueAuthors}</strong></div>
            <div><span>来源一致度</span><strong>{snapshot.diagnostics.sourceAgreement}%</strong></div>
          </div>
        </section>
      )}

      <footer>
        <div><strong>散户温度计</strong><span>只观察群体表达，不识别真实“宝妈”或“韭菜”。</span></div>
        <p>{snapshot.meta.disclaimer}</p>
        <span>生成于 {new Date(snapshot.meta.generatedAt).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}</span>
      </footer>
    </main>
  );
}
