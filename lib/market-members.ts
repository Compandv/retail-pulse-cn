import { fetchText, latestSession } from "./observations.ts";
import type { BoardDetails, BoardMember } from "../app/market-types.ts";

type Row = Record<string, unknown>;
const numeric = (value: unknown) => value == null || value === "" || typeof value === "boolean" || !Number.isFinite(Number(value)) ? null : Number(value);
export async function collectBoardMembers(code: string, day: string, now = new Date()): Promise<BoardDetails> {
  if (!/^BK\d{4,6}$/.test(code)) throw new Error("板块代码格式无效");
  // This endpoint exposes current membership, not point-in-time historical membership.
  if (day !== latestSession(now)) throw new Error("该历史日期尚未保存成分明细；不使用当前成分替代历史成分");
  const members = new Map<string, BoardMember>();
  let expected = 0, complete = false, reason = "已达分页上限，仅显示已取得成分";
  for (let page = 1; page <= 20; page++) {
    const params = new URLSearchParams({ pn: String(page), pz: "100", po: "1", np: "1", fltt: "2", invt: "2", ut: "bd1d9ddb04089700cf9c27f6f7426281", fid: "f3", fs: `b:${code} f:!50`, fields: "f3,f6,f8,f12,f14,f124" });
    try {
      const payload = JSON.parse(await fetchText(`https://17.push2.eastmoney.com/api/qt/clist/get?${params}`)) as { data?: { total?: number; diff?: Row[] | Record<string, Row> } };
      const data = payload.data;
      if (!data || !Number.isInteger(data.total) || !data.diff) throw new Error("板块成分结构异常");
      const rows = Array.isArray(data.diff) ? data.diff : Object.values(data.diff);
      if (page === 1) expected = data.total!;
      else if (expected !== data.total) { reason = "分页期间成分总数变化，覆盖未确认"; break; }
      let repeated = false;
      for (const raw of rows) {
        const stock = String(raw.f12 || "");
        if (!/^\d{6}$/.test(stock)) { repeated = true; continue; }
        if (members.has(stock)) { repeated = true; continue; }
        const timestamp = numeric(raw.f124);
        const date = timestamp != null && Number.isFinite(new Date(timestamp * 1000).getTime()) ? new Date(timestamp * 1000) : null;
        const local = date != null ? new Date(date.getTime() + 8 * 3600000) : null;
        const dateValid = local != null && local.toISOString().slice(0, 10) === day && local.getUTCHours() >= 15;
        const amount = numeric(raw.f6), turnover = numeric(raw.f8);
        members.set(stock, { code: stock, name: String(raw.f14 || stock), changePct: dateValid ? numeric(raw.f3) : null, amount: dateValid && amount != null && amount >= 0 ? amount : null, turnover: dateValid && turnover != null && turnover >= 0 ? turnover : null, asOf: date?.toISOString() ?? null });
      }
      if (repeated) { reason = "存在重复或无效成分，覆盖未确认"; break; }
      if (members.size === expected && expected > 0) { complete = true; reason = "当前成分清单已覆盖；行情只使用所选交易日"; break; }
      if (rows.length < 100) { reason = "来源提前结束，成分覆盖未确认"; break; }
    } catch (error) {
      if (!members.size) throw error;
      reason = "部分成分读取失败，仅显示已取得数据"; break;
    }
  }
  return { code, date: day, collectedAt: now.toISOString(), expected, complete, reason, members: [...members.values()].sort((a, b) => (b.changePct ?? -Infinity) - (a.changePct ?? -Infinity) || a.code.localeCompare(b.code)) };
}
