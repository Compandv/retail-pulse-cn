# 实施顺序

1. 定义分层证据、未知处理和账户分母：config/retail-profile.json、sentiment/retail_profile.py。
2. 修正日报已发现的追涨、恐慌、补仓误判，补充反例测试。
3. 计算六维和独立韭菜分，保存方法版本及原始输入：sentiment/report.py。
4. 实现十强分层表、成分条、证据和评分说明：app/MarketReport.tsx、app/report-types.ts、样式。
5. 接入平台全量资金榜，覆盖分页、单位、来源、缓存过期与失败：lib/fund-flow.ts、API 和界面。
6. 使用真实保存采集重算，检查样本覆盖；更新方法说明与旧暂缓记录。
7. 接入主流程：日报生成、首页、刷新、日期选择。
8. 端到端验证：规则反例、账户聚合、评分边界、来源分页、构建及本地接口核验。
