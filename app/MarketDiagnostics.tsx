import { netAdvanceShare } from "../lib/data-quality";
import type { MarketSnapshot } from "./market-types";
const fmt = (n: number | null | undefined, digits = 2) => n == null || !Number.isFinite(n) ? "—" : n.toLocaleString("zh-CN", { maximumFractionDigits: digits });

export function MarketDiagnostics({ snapshot }: { snapshot: MarketSnapshot }) {
  const market = snapshot.market;
  const diagnostics = market.diagnostics?.version === "market-diagnostics-1.0" ? market.diagnostics : undefined;
  const breadth = diagnostics ? diagnostics.netAdvanceShare : netAdvanceShare(market);
  return <section className="market-diagnostics" aria-label="客观行情诊断">
    <div><span className="eyebrow">客观行情诊断 · {snapshot.meta.tradeDate}</span><h3>盘面强弱与成交分布</h3></div>
    <div className="diagnostic-facts">
      <div><span>净上涨广度</span><strong>{fmt(breadth)}{breadth == null ? "" : "%"}</strong><small>（上涨数 − 下跌数）÷ 有效涨跌幅股票数</small></div>
      <div><span>个股换手率中位数</span><strong>{fmt(diagnostics?.medianTurnover)}{diagnostics?.medianTurnover == null ? "" : "%"}</strong><small>{diagnostics ? `${diagnostics.turnoverCoverage} 只有当日换手率` : "此快照未保存该统计"}</small></div>
      <div><span>前10股成交额占比</span><strong>{fmt(diagnostics?.top10AmountShare)}{diagnostics?.top10AmountShare == null ? "" : "%"}</strong><small>{diagnostics?.concentrationReason || "此快照未保存全范围集中度"}</small></div>
    </div>
    {diagnostics ? <><div className="diagnostic-distribution">{diagnostics.distribution.map(band => <div key={band.key}><span>{band.name}</span><b>{fmt(band.count, 0)} 只 · {fmt(band.share, 1)}{band.share == null ? "" : "%"}</b>{band.share != null && Number.isFinite(band.share) ? <progress aria-label={band.name} value={band.share} max={100} /> : <small>未取得有效报价</small>}</div>)}</div>
      <p className="fine-print">涨跌分布覆盖 {diagnostics.changeCoverage}/{diagnostics.sourceTotal ?? "未知"} 只；成交额覆盖 {diagnostics.amountCoverage}/{diagnostics.sourceTotal ?? "未知"} 只。{diagnostics.catalogComplete ? "来源目录完整。" : "来源目录未完整核实，只描述已采集样本。"}{diagnostics.conflictingCodes ? ` 排除了 ${diagnostics.conflictingCodes} 个内容冲突的股票代码。` : ""} {diagnostics.note}</p></> : <p className="diagnostic-missing">历史快照没有保存分档涨跌、换手率中位数及成交集中度，保持缺失。净上涨广度仅由该快照原有涨跌家数计算，不引入当前行情；下次市场更新将保存新增诊断。</p>}
    <p className="fine-print">本区不参与韭菜分，不把 ±5% 当作涨跌停，也不推断散户成交或机构意图。涨停、炸板和连板晋级需要专用数据源，目前没有用涨幅阈值代替。</p>
  </section>;
}
