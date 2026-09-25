"use client";
import { useEffect, useState } from "react";
import { displayBeijingTime, snapshotHealth } from "../lib/data-quality";

export function SnapshotHealth({ name, tradeDate, collectedAt, methodVersion, expectedMethodVersion, historical = false }: {
  name: string; tradeDate: string; collectedAt?: string; methodVersion?: string; expectedMethodVersion?: string; historical?: boolean;
}) {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    const update = () => setNow(new Date());
    const first = setTimeout(update, 0), interval = setInterval(update, 60000);
    return () => { clearTimeout(first); clearInterval(interval); };
  }, []);
  const health = snapshotHealth({ tradeDate, methodVersion, expectedMethodVersion, historical, now });
  const warning = health.methodMismatch || ["stale", "invalid", "calendar-unknown"].includes(health.state);
  return <aside className={`snapshot-health ${warning ? "snapshot-warning" : ""}`} aria-label={`${name}数据状态`}>
    <div className="snapshot-heading"><strong>{name} · {health.title}</strong><span>交易日 {tradeDate}</span></div>
    <p>{health.detail}</p>
    {health.methodMismatch && <p className="snapshot-method-warning">方法版本不一致：此快照为 {methodVersion || "未记录"}，当前代码使用 {expectedMethodVersion}。升级代码不会重算旧数据；历史值保留原口径，不直接跨版本比较。</p>}
    <details><summary>采集时间与方法</summary><p>采集于 {displayBeijingTime(collectedAt)}（北京时间）；快照方法 {methodVersion || "未记录"}。更新时间不代表数据采集完整度。</p></details>
  </aside>;
}
