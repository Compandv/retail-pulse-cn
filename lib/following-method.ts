import definition from "../config/following.json" with { type: "json" };
import reportConfig from "../config/report.json" with { type: "json" };

export const FOLLOWING_METHOD = definition;
export type FollowingKey = keyof typeof definition.weights;
export const FOLLOWING_KEYS = Object.keys(definition.weights) as FollowingKey[];
/** Display saved weights without silently replacing a historical formula. */
export function savedFollowingFormula(weights?: Record<string, number> | null): string {
  if (!weights || !Object.keys(weights).length || !Object.values(weights).every(n => Number.isFinite(n) && n >= 0 && n <= 1) || Math.abs(Object.values(weights).reduce((a, b) => a + b, 0) - 1) > 1e-9) return "未记录或权重无效";
  return Object.entries(weights).map(([key, weight]) =>
    `${definition.labels[key as keyof typeof definition.labels] ?? key} ${Number((weight * 100).toFixed(2))}%`
  ).join(" + ");
}
export const FOLLOWING_FORMULA = savedFollowingFormula(definition.weights);

export const FOLLOWING_EXPLANATION = `韭菜分 = ${FOLLOWING_FORMULA}。每个来源的账户等权，每账户最多${definition.maxPostsPerAccount}条去重发言，同项取最高强度；自述已追买计${definition.chaseDoneStrength}，明确计划计${definition.chasePlanStrength}。至少${definition.minimumAccounts}个观察账户、有效采集入口覆盖${reportConfig.minimumMemberCoverage * 100}%且账户标识完整才出分；题材发现日报未知账户超过${definition.maximumUnknownRate}%时隐藏综合分。未知账户仍在分母中，标签可以重叠。低分不等于理性，不表示真实买卖或未来涨跌。`;

export const MEASUREMENT_ANSWER = `社区关注热度使用同口径历史账户数分位，至少需要20个有效历史日；社区追涨和恐慌按有效文本统计，讨论升温比较前20个有效日账户数中位数。十强日报另外按账户统计：${FOLLOWING_EXPLANATION} 当前不使用L1–L5等级，历史报告保留原方法，不跨版本直接比较。`;

export function expectedReportMethod(meta: { discovery?: unknown }): string {
  return meta.discovery ? definition.topicAnalysisVersion : definition.version;
}
