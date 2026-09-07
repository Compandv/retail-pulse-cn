# 实施任务

1. 明确六维与体温口径：共享配置、方法文档；依据本期参考图与已有评分研究。
2. 核实资金和互动来源：`sentiment/report_sources.py`、`sentiment/observations.py`；依赖公开接口实测，核对日期、字段和单位。
3. 动态十强采样：每日重新选概念、采集全成分的两日窗口并去重；依赖市场日快照与已保存成分。
4. 计算与回放：`sentiment/report.py`、`scripts/update_report.py`；依赖 1–3，保留缺失、覆盖与私有原始记录。
5. 页面及配色：`app/MarketReport.tsx`、类型与样式、展示辅助函数；依赖真实计算结果。
6. 接入主流程（Connect to the main flow）：页面、每日入口、工作流及说明；三条采集路径分别尝试。
7. 端到端验证（End-to-end verification）：来源边界、语义反例、跨日混入、重复股票、符号排序、快照重放、构建及本地响应。
