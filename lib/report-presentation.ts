import type { FundFlow, ReportSector } from "../app/report-types.ts";

export function rankProfiles(sectors: ReportSector[]) {
  return [...sectors].sort((a, b) => {
    const x = a.retailProfile, y = b.retailProfile;
    return (y?.eligible ? y.l1l2Share ?? -1 : -1) - (x?.eligible ? x.l1l2Share ?? -1 : -1)
      || (y?.coverage ?? 0) - (x?.coverage ?? 0) || a.id.localeCompare(b.id);
  });
}

export function temperatureTone(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return { name: "待补数据", key: "missing", ink: "#617183", background: "#edf0f3" };
  if (value >= 80) return { name: "高位", key: "hot", ink: "#b52b20", background: "#fce6e2" };
  if (value >= 60) return { name: "偏高", key: "warm", ink: "#a44908", background: "#ffe2c7" };
  if (value >= 40) return { name: "中位", key: "neutral", ink: "#805d00", background: "#fff1c3" };
  if (value >= 20) return { name: "偏低", key: "cool", ink: "#246ba1", background: "#dfedf8" };
  return { name: "低位", key: "cold", ink: "#087c59", background: "#e0f2e9" };
}

export function rankFlows(rows: FundFlow[], kind: string, direction: "in" | "out") {
  return rows.filter(row => row.kind === kind && Number.isFinite(row.net) && (direction === "in" ? row.net > 0 : row.net < 0))
    .sort((a, b) => (direction === "in" ? b.net - a.net : a.net - b.net) || a.code.localeCompare(b.code));
}
