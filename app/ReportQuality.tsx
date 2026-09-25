import { reportQuality, sectorQuality } from "../lib/data-quality";
import { FOLLOWING_METHOD } from "../lib/following-method";
import type { DailyReport } from "./report-types";
const count = (n: number | null | undefined) => n == null ? "未记录" : n.toLocaleString("zh-CN");
const pct = (n: number | null | undefined) => n == null ? "未记录" : `${n.toFixed(1)}%`;

export function ReportQuality({ report }: { report: DailyReport }) {
  const quality = reportQuality(report);
  return <section className="panel quality-panel" aria-label="报告数据质量">
    <div className="panel-head"><div><span className="eyebrow">先看覆盖，再读分数 · {report.meta.tradeDate}</span><h2>这份报告的数据够不够？</h2></div></div>
    <div className="quality-facts">
      <div><span>有效采集入口</span><strong>{count(quality.feedObserved)} / {count(quality.feedExpected)}</strong><small>成功读取不等于完整翻页</small></div>
      <div><span>已读完整窗口</span><strong>{count(quality.feedComplete)} / {count(quality.feedExpected)}</strong><small>{quality.completeCoverage == null ? "旧快照缺此字段时不倒推" : `完整覆盖 ${pct(quality.completeCoverage)}`}</small></div>
      <div><span>题材韭菜分已发布</span><strong>{quality.publishedScores} / {quality.sectors}</strong><small>不满足门槛时保留空值</small></div>
      <div><span>未知率超过 {FOLLOWING_METHOD.maximumUnknownRate}%</span><strong>{quality.highUnknownSectors} 个题材</strong><small>未知多不等于市场理性</small></div>
    </div>
    <p className="fine-print">质量是采样覆盖与可解释性，不是预测准确率。{quality.completeSectors}/{quality.sectors} 个题材的全部成分已读完整窗口；{quality.errors} 项采集错误。题材之间账户可能重叠，不能相加当作全市场人数。</p>
    <details className="quality-details"><summary>展开每个题材的来源、正文与未知拆分</summary>
      <div className="v4-table-scroll"><table className="v4-table quality-table"><thead><tr><th>题材</th><th>有效 / 完整 / 应采入口</th><th>分析文本与正文</th><th>未知账户拆分</th><th>综合分发布依据</th></tr></thead><tbody>{report.sectors.map(sector => {
        const o = sector.observation, p = sector.expressionProfile, audit = sectorQuality(sector);
        return <tr key={sector.id}><th>{sector.name}<small>观察 {count(p?.observedAccounts ?? o.authors)} 个账户</small></th>
          <td>{count(o.memberObserved)} / {count(o.memberComplete)} / {count(o.memberTotal)}<small>{o.complete ? "窗口完整" : "窗口存在截断或缺失"}</small></td>
          <td>{count(o.sampleCount)} 条<small>正文 {count(audit.bodyTexts)} · 仅标题 {count(audit.titleOnlyTexts)} · 内容类型未标注 {count(audit.unspecifiedTexts)}</small><small>其中核验补读正文 {count(audit.enrichedBodies)} 条</small></td>
          <td>未知 {count(p?.unknownAccounts)} · {pct(p?.unknownRate)}<small>已抽样但规则未命中：{count(audit.unmatched)}</small><small>未进入分析样本：{count(audit.unsampled)}</small><small>账户标识缺失：{count(audit.identityMissingPosts)} 条帖子</small></td>
          <td>{sector.leekScore?.score == null ? "未发布" : sector.leekScore.score}<small>{sector.leekScore?.reason || "此历史方法未保存发布依据"}</small></td></tr>;
      })}</tbody></table></div>
      <p className="fine-print">“未命中”不等于没有相应行为；“未抽样”不推断为中性。旧快照未保存的拆分显示“未记录”，不会为了降低未知率重分类。补读正文只是正文来源之一，旧字段不能反推全部正文覆盖。</p>
    </details>
  </section>;
}
