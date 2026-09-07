# OpenAI 语义对照分析

> 当前日常流程已改为本地规则分类＋一次模型汇总解读，详见 [新版方法](METHOD_FOLLOWING.md)。本文逐条对照部分仅用于旧版调试；API平台配置仍有效。

## 切换 API 平台

在 `.env.agent.local` 配置以下三个字段，并将 `OPENAI_API_KEY` 换成对应平台的密钥。这个变量名为兼容旧配置保留，并不限制提供商。地址是API基础地址，不是聊天网页，也不要附加 `/responses` 或 `/chat/completions`；程序自动拼接。必须使用HTTPS，不跟随重定向。

| 平台 | OPENAI_BASE_URL | OPENAI_API_TYPE | OPENAI_MODEL 示例 |
| --- | --- | --- | --- |
| OpenAI（默认） | https://api.openai.com/v1 | responses | gpt-5.4-mini |
| DeepSeek | https://api.deepseek.com | chat_completions | deepseek-v4-flash |
| 智谱 GLM | https://open.bigmodel.cn/api/paas/v4 | chat_completions | glm-4.7 |

其他平台可以填写其提供的兼容API地址和实际可用模型名。仅支持上述两种接口协议，不保证所有网站/模型兼容。密钥和待分析文本会发往你配置的平台。模型权限、计费和输出能力以对应平台为准。

Chat Completions使用JSON模式及提示词中的输出约定，收到结果后继续进行同样的严格字段和原文证据校验；截断、空输出、拒绝不会当作成功。它不代表服务端支持OpenAI的严格JSON Schema约束。切换地址、接口类型或模型都会隔离缓存。新增兼容传输版本也会使旧缓存失效。

配置示例依据：[DeepSeek接口文档](https://api-docs.deepseek.com/api/create-chat-completion/)、[智谱接口文档](https://docs.bigmodel.cn/api-reference/模型-api/对话补全)。尚未使用真实密钥进行三方联调。

运行方式：用户手动运行时采集、分析；没有 Agent 轮询或后台调度。原来的 GitHub 定时触发已移除，保留手动入口。网页资金流刷新是独立的数据读取，不调用模型。

## 配置与运行

将根目录 `agent.env.example` 复制为 `.env.agent.local`，在本地填写 `OPENAI_API_KEY`。该文件已由 `.gitignore` 排除。不要把密钥发到聊天或写进前端。进程环境变量优先于文件。

初始模型 `gpt-5.4-mini`，可用 `OPENAI_MODEL` 更换。使用 OpenAI Responses API、严格 JSON Schema、`store:false`；不依赖额外 Python SDK。接口依据：[结构化输出](https://developers.openai.com/api/docs/guides/structured-outputs)、[模型说明](https://developers.openai.com/api/docs/models/gpt-5.4-mini)。

```powershell
# 正常使用：重新采集，随后分析新增样本
.\run_daily.cmd
# 只查看已有采集快照的新增/缓存数量，不调用模型
.\analyze_comments.cmd --dry-run
# 对已有快照分析，首次可少量试运行；不重新抓取网站
.\analyze_comments.cmd --max-new 12
# 填写review中的human字段后，离线计算对照指标
.\analyze_comments.cmd --evaluate work/semantic-agent/reviews/<报告文件>.json
```

日常默认单次最多新增120条、每批6条；未处理内容下次手动运行继续。可设置 `RETAIL_AGENT_MAX_NEW_POSTS`。`RETAIL_AGENT_MODE=off` 可关闭；当前只开放 `shadow` 对照模式。`update_report.py --capture ...` 默认离线回放，显式加 `--agent` 才调用模型。

## 去重和可追溯性

每次正常采集重新请求帖子列表，因此同日新增内容可以进入分析。仍沿用项目已有收盘日窗口、成分股采样和每账户最多三条限制；不是逐条抓取所有评论，也不是盘中全市场实时分析。

缓存按交易日、来源、匿名账户、规范化正文，以及模型/提示词/输出约定版本隔离。同一作者跨重叠板块的相同文本只分析一次；不同作者不合并。正文更新或方法修改需重新分析。名单变化后复用可匹配内容；没有新增则不调用API。列表需要重新读取才能发现新增，已分析正文不会重复送模型。

模型看到当前原文及最多两条同账户较早发言，不发送账户标识、密钥或完整网页。正文作为不可信数据处理，模型没有浏览、下单或执行工具。证据必须逐字存在于当前文本。结构错误、拒绝或连接失败不写成功缓存、不用规则冒充AI；本次停止发送，下次手动运行继续。超时可能已经产生费用，因此不自动重试。同一方法/交易日通过进程锁避免并发重复请求。

## 标注、汇总和验证

标准在 `config/semantic-agent-prompt.md`，包括多空、追涨/疑问/劝阻/转述/历史、恐慌、补仓、L1～L5、原文证据和判断理由。分析层次不等于真实投资经验；仅提“美国加息”不能判L5，不能判断的内容保留unknown。询问“还能追吗”不等于已经追高买入。

私有结果位于 `work/semantic-agent/`，对照文件位于其 `reviews/` 目录，包含规则与AI的同文本比较、分歧和人工复核栏，以及逐板块候选构成。每账户一票，沿用冲突留空规则。覆盖不足80%的板块不输出行为率；可分类账户不足20个不输出L1+L2点估计，分类覆盖不足50%不支持正式点分数。缺失标注始终保留，不能重新归一化成“人人都是L1/L2”。

人工复核时填写 `human.reviewed=true` 及 level/chase/panic/refill 真值，未知可以填写 level=`unknown`。脚本同时计算规则和模型的准确率、行为精确率/召回率及混淆计数；未复核样本不充当真值。重复运行保留复核内容，被新采样替换的旧条目归档，不删除。

本阶段不修改正式温度计、六维或韭菜分权重，也不自动把AI候选替换为正式结果。下一阶段需用真实样本分层抽检：覆盖十个板块、疑问/反讽/否定/转述、各等级及unknown，检查误报和漏报，再确定是否接管。没有真实API调用及人工真值之前，不声称模型更准确。
