import type { Snapshot } from "../app/types";

export function answerResearchQuestion(question: string, snapshot: Snapshot) {
  const valid = snapshot.sectors.filter(sector => sector.overall != null);
  const keyword = question.toLowerCase();
  const matched = valid.filter(sector => [sector.name, sector.stockCode, sector.representative].some(name => name && keyword.includes(name.toLowerCase())));
  const metric = (value: number | null | undefined) => value == null ? "暂无" : value.toFixed(1);
  if (/公式|计算|怎么算|评分|依据/.test(question)) return { title: "评分依据", text: snapshot.meta.methodVersion === "MVP-3.0" ? "综合分 = 讨论热度 × 20% + 新手表达 × 25% + 追涨冲动 × 25% + 恐慌表达 × 20% + 方向强度 × 10%。分项范围均为 0–100；先按来源计算，再等权合并有效来源。置信度单独反映样本与覆盖，既不计入温度，也不等于预测准确率。" : `当前是 ${snapshot.meta.methodVersion} 旧版快照，尚未按新公式采集。旧公式含 20 分底座和向 50 分收缩，不能把旧分数当作 V3。`, sectorIds: [] };
  if (matched.length) return { title: matched.length > 1 ? "板块比较" : `${matched[0].name} · 快照解读`, text: matched.map(sector => `${sector.name}：温度 ${metric(sector.overall)}，热度 ${metric(sector.heat)}，新手 ${metric(sector.novice)}、追涨 ${metric(sector.fomo)}、恐慌 ${metric(sector.panic)}；${sector.heatChangeAvailable ? `热度较前次观测变化 ${sector.heatChange >= 0 ? "+" : ""}${metric(sector.heatChange)}` : "变化基线不足"}。当日 ${sector.sampleCount} 条／近三日 ${sector.sampleCount3d} 条，评分窗口为${sector.dataWindow}，置信 ${sector.confidence}。`).join("\n\n"), sectorIds: matched.map(sector => sector.id) };
  if (/升温|变化|降温/.test(question)) {
    const cooling = question.includes("降温");
    const sectors = valid.filter(sector => sector.heatChangeAvailable && (cooling ? sector.heatChange < 0 : sector.heatChange > 0)).sort((a, b) => cooling ? a.heatChange - b.heatChange : b.heatChange - a.heatChange).slice(0, 3);
    return { title: cooling ? "最近降温" : "最近升温", text: sectors.length ? sectors.map(sector => `${sector.name}：热度变化 ${sector.heatChange >= 0 ? "+" : ""}${metric(sector.heatChange)}，当前温度 ${metric(sector.overall)}，当日 ${sector.sampleCount} 条样本。`).join("\n") : "当前没有同时满足变化方向和可比较历史基线的板块，不能据此生成升降温排名。", sectorIds: sectors.map(sector => sector.id) };
  }
  if (/最热|热度|过热|市场|整体/.test(question)) {
    const sectors = [...valid].sort((a, b) => (b.heat ?? 0) - (a.heat ?? 0)).slice(0, 3);
    return { title: "当前讨论热度", text: `全市场温度 ${metric(snapshot.summary.overall)}，讨论热度 ${metric(snapshot.summary.heat)}，置信 ${snapshot.meta.confidence}。${sectors.map(sector => `${sector.name}热度 ${metric(sector.heat)}`).join("；")}。高热可能来自追涨或恐慌，需要结合表达证据理解。`, sectorIds: sectors.map(sector => sector.id) };
  }
  return { title: "可以回答的范围", text: "我可以解释当前评分、比较已配置板块，或列出升温／降温主题。试着输入准确的板块名、代表股票名称或代码。当前快照无法回答未覆盖标的、未来涨跌或买卖时点。", sectorIds: [] };
}
