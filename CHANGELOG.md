# lzy-skills 更新日志

> 记录每次发布的内容。格式参照 WorkBuddy Changelog：倒序排列，条目用「新增 / 优化 / 修复」前缀，一行一条。
> **发布流程要求**：每次发布前在本文件顶部加一节（日期 + 主版本号 + 条目），再跑 publish.sh。
> 版本号说明：**自 2.0.0 起全工具箱共用一个主版本号**（存于 `skills/lzy/VERSION`），子技能不再有独立版本。

## 2.0.0 🚀（2026-09-10）

- 新增单一主版本号机制：只有 `skills/lzy/VERSION` 一个版本号，全部子技能共用；子技能目录不再有各自 VERSION
- 优化版本检查：任何技能的 check_update.sh 都对比主版本号，发现不一致即提示整体更新（整体安装/更新本来就是唯一更新方式）
- 优化发布流程：升版本只需改一处，消灭「漏升某个技能版本」和「README 版本行同步不过来」两类事故
- 语义化规则不变：小修 +0.0.1，新增方法/大改 +0.1.0

## 2026-09-10 · 账号归档链接 + 转录排障（video-to-text 1.1.0 / account-archive 1.1.0）

- lzy-video-to-text 1.1.0：新增位置参数兼容——`transcribe.py <URL或路径>` 与 `--input` 等价，AI 照文档跑不再报参数错误
- lzy-video-to-text 1.1.0：新增缺环境时的清晰指引——报错直接给出绝对路径的 `setup_env.py --install` 命令（全新环境实测验证）
- lzy-video-to-text 1.1.0：优化完成输出——最后一行打印输出 txt 的**绝对路径**，避免稿件落在相对目录找不到
- lzy-video-to-text 1.1.0：SKILL.md 故障速查新增「新电脑首次使用」「找不到稿子」两行
- lzy-account-archive 1.1.0：STATUS.md 新增「全部作品清单」表——按发布日期倒序，每条标题即原帖链接（url 缺失时按 id 自动构造），赞评转藏与全文归档状态一目了然

## 2026-09-10 · 新增方法：账号存量归档（lzy 1.4.0 / account-archive 1.0.0）

- 新增 lzy-account-archive：给抖音/小红书账号抓 90 天存量（标题+正文全文+赞评转藏）入本地持久仓库，之后只抓增量，当天发布不收
- 新增仓库管理器 archive.py：init / known / pending / merge / stats / report 六命令，唯一入库口
- 新增指标历史：同一作品每次抓到新指标自动留档 history，天然支持趋势分析
- 新增规则：缺发布日期的新条目拒收并记问题清单（不编数据）；平铺指标字段（digg_count 顶层）正确映射；已入库条目允许无日期补全更新
- 数据仓库置于技能目录外（默认 ~/WorkBuddy/lzy-data/accounts/），不进 GitHub
- 抓取脚本：抖音列表复用 teardown 已验证的滚动懒加载逻辑；详情页优先读 SSR 数据（RENDER_DATA / __INITIAL_STATE__），比 DOM 选择器抗改版

## 2026-09-10 · 新增方法：口播文案校正（lzy 1.3.0 / script-coach 1.0.0）

- 新增 lzy-script-coach：智宇师兄大号口播文案校正——主题闸门 + 七项体检打分 + 最小改动改写 + 自嗨急救，基于 23 条真实视频规律
- 纯方法论技能，零脚本零依赖，装完即用
- 新增「迭代纪律」节：真实校正后新规律当天回写升版本；被推翻的结论标记作废不删除

## 2026-09-10 · 新增方法：抖音搜索词漏斗（lzy 1.2.0 / douyin-funnel 1.0.0）

- 新增 lzy-douyin-funnel：抖音搜索词完整漏斗——Top100 内容生态 landscape（词频/分类/话题/身份桶）+ 逐条评论区客资识别（A1-A4/B/C + 四象限控制变量），合并 HTML 报告
- 新增 setup_env.py：依赖装进技能自带 .venv，体检/--install 两种模式，退出码 0/1/2
- 新增 jieba 安装兜底：pip 报 EEXIST 时自动从本机已有 venv 复制（纯 Python 包跨 venv 通用）
- shell 脚本 zsh → bash（`${0:A:h}` → `$(cd "$(dirname "$0")" && pwd)`），跨平台兼容

## 2026-09-09 · 仓库转公开 + 发布链路加固（lzy 1.1.1 / teardown 1.0.1 / video-to-text 1.0.1）

- 仓库由私有转为公开，README 重写快速安装（一句话安装 + 环境依赖表）+ 跨平台说明（Windows/Linux 现状）
- 新增 publish.sh 推送后远端 HEAD 自校验——防「以为发了其实没发」
- 修复 check_update.sh 全角字符紧邻变量名导致的 unbound variable 误报（`$REMOTE（` → `${REMOTE}（`）
- 新增 lzy 入口 help 协议：`/lzy help` 输出用法与路由表，参数为空不擅自执行
- 端到端验证：匿名新用户 clone → install.sh → 三技能齐全 → 版本检查静默正常

## 2026-09-09 · 首次发布（lzy 1.1.0 / douyin-teardown 1.0.0 / video-to-text 1.0.0）

- 新增 lzy 工具箱入口：路由表 + help + 「如何新增一个方法」规范（命名 lzy-\<方法\>、对照组思维、验证程度三档标注、踩坑当天回写、作废结论保留）
- 新增 lzy-douyin-teardown：抖音爆款拆解对比——爆款 vs 非爆款对照组，18 元素 + 扩展维度，6 步工作流，输出规律报告
- 新增 lzy-video-to-text：视频转文字——URL/本地文件 → TXT，本地 Whisper 免费离线，四套行业词库纠错，含回炉矫正 polish.py
- 新增版本检查：每技能 scripts/check_update.sh，每天最多联网查一次远端 VERSION，有更新提示、无更新静默
- 新增发布工具链：validate.sh（frontmatter/脚本语法/VERSION/路由一致性校验）+ install.sh（新机器一键安装）+ publish.sh（clone→sync→validate→push）
