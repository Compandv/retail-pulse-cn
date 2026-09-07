"use client";
import { useEffect, useRef, useState } from "react";
import type { DailyReport, ReportSector } from "./report-types";
import { rankProfiles } from "../lib/report-presentation";

const pct = (value: number | null | undefined) => value == null ? "—" : `${value.toFixed(1)}%`;
const labels = ["L1 小白", "L2 入门", "L3 经验", "L4 进阶", "L5 专业"];

function ProfileEvidence({ sector, onClose }: { sector: ReportSector; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null), profile = sector.retailProfile!;
  useEffect(() => { ref.current?.showModal(); }, []);
  return <dialog ref={ref} className="research-dialog v4-dialog profile-dialog" onCancel={onClose} onClose={onClose}>
    <button className="v4-dialog-close" onClick={onClose}>关闭 ×</button>
    <span className="eyebrow">按账户汇总 · 发言推定</span><h2>{sector.name} · 五级表达构成</h2>
    <p>观察 {profile.observedAccounts} 个账户，已判定 {profile.classifiedAccounts} 个，未知 {profile.unknownAccounts} 个。每账户每板块一票，最多使用三条去重发言；{profile.singleEvidenceAccounts} 个账户只有一条分层证据，{profile.conflictingAccounts} 个因证据冲突保留未知。</p>
    <p className="fine-print">{profile.contentSampling}。已补正文 {profile.enrichedPosts ?? 0} 条{profile.contentObservedAt ? `，正文观测于 ${new Date(profile.contentObservedAt).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })}` : ""}。正文可能在发表后编辑，不当作当时已经观测到的文本。</p>
    <p className="report-detail-note">L1+L2 = 已判定的 L1、L2 账户 ÷ 全部已判定账户。未知账户不会当作高等级。若将未知分别视为全部高等级／全部低等级，全观察样本的 L1+L2 范围为 {profile.l1l2Bounds?.map(pct).join("—") ?? "—"}；该范围不包含规则误判的不确定性。</p>
    {profile.levels.map((level, index) => <section className={`profile-level level-${level.key}`} key={level.key}><h3>{labels[index]} · {level.label} <span>{level.count} 个 / {pct(level.share)}</span></h3>
      {level.examples.length ? level.examples.map((example, i) => <article className="profile-example" key={i}><p>{example.text}</p><small>{example.reason} · 同账户 {example.supportingPosts} 条支持证据</small><a href={example.url} target="_blank" rel="noreferrer">核对原帖 ↗</a></article>) : <p className="fine-print">当前没有符合此层次的证据。</p>}
    </section>)}
    <p className="fine-print">这是表达层次的规则推定，不能认证职业、真实投资年限或收益水平。宏观术语本身不构成专业证据。</p>
  </dialog>;
}

export function RetailComposition({ report }: { report: DailyReport }) {
  const [selected, setSelected] = useState<ReportSector | null>(null);
  const rows = rankProfiles(report.sectors), usable = rows.filter(row => row.retailProfile?.eligible);
  const coverage = rows.flatMap(row => row.retailProfile ? [row.retailProfile.coverage] : []);
  return <section className="panel report-section profile-section"><div className="report-section-heading"><span className="report-step profile-step">03</span><div><span className="eyebrow">散户五级分层 · 十强热点</span><h2>这波行情，讨论者呈现怎样的分析层次？</h2></div><span className="report-tag">发言推定 · 非身份认证</span></div>
    <p className="report-summary">按<strong>已判定账户中的 L1+L2 占比</strong>降序；每个账户只计一票。{usable.length} 个板块达到最低分类样本量，未知账户单独列出。点击板块可核对依据。</p>
    {!!coverage.length && Math.max(...coverage) < 50 && <p className="fund-status fund-stale">当前分类覆盖仅 {pct(Math.min(...coverage))}—{pct(Math.max(...coverage))}，多数账户无法判断。即使已判定样本的 L1+L2 为100%，也不能推断整个板块均为新手；本期韭菜分仅显示范围。</p>}
    <div className="profile-legend">{labels.map((label, index) => <span key={label}><i className={`level-fill-L${index + 1}`} />{label}</span>)}<span className="fine-print">L3 企业证据 · L4 产业传导 · L5 宏观与风险推演</span></div>
    <div className="report-matrix-scroll"><table className="profile-table"><caption>L1–L5 百分比均以已判定账户为分母，成分条也仅展示已判定部分</caption><thead><tr><th>热门板块</th>{labels.map(label => <th key={label}>{label}</th>)}<th>L1+L2 占比</th><th>已判定构成</th><th>分类覆盖 / 未知</th></tr></thead><tbody>{rows.map((sector, index) => {
      const p = sector.retailProfile;
      return <tr key={sector.id}><th><button disabled={!p} onClick={() => setSelected(sector)}><span className="matrix-rank">{String(index + 1).padStart(2, "0")}</span>{sector.name} ↗</button></th>
        {labels.map((label, i) => <td className={`level-L${i + 1}`} key={label}>{p?.eligible ? pct(p.levels[i].share) : "—"}</td>)}
        <td className="profile-low-share">{pct(p?.l1l2Share)}{p?.eligible && !p.pointEligible && <small>覆盖有限</small>}</td>
        <td><div className="profile-stack" role="img" aria-label={p?.eligible ? p.levels.map((l, i) => `${labels[i]} ${pct(l.share)}`).join("，") : "样本不足"}>{p?.eligible ? p.levels.map(l => <span className={`level-fill-${l.key}`} style={{ width: `${l.count / p.classifiedAccounts * 100}%` }} key={l.key} />) : <span className="profile-unknown-fill" style={{ width: "100%" }} />}</div></td>
        <td className="profile-coverage">{p ? <>{p.classifiedAccounts}/{p.observedAccounts} · {pct(p.coverage)}<small>未知 {p.unknownAccounts} 个{!p.eligible ? " · 样本不足" : ""}</small></> : "本日未计算"}</td>
      </tr>;
    })}</tbody></table></div>
    <p className="report-footnote">普通讨论不默认归为 L1；说到“政策”“加息”不自动晋级。需要至少20个可判定账户才展示比例，覆盖不足50%时韭菜分只显示不确定范围。这里观察到的是公开讨论账户，不能外推为全体持仓散户。</p>
    {selected && <ProfileEvidence sector={selected} onClose={() => setSelected(null)} />}
  </section>;
}
