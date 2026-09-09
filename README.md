# lzy-skills · LZY 自媒体方法论工具箱

刘志宇的自媒体分析方法技能集，运行在 [Claude Code](https://claude.com/claude-code) 的 skill 体系上（`~/.claude/skills/`）。

## 技能清单

| 技能 | 说明 |
|---|---|
| `lzy` | 工具箱主入口（路由 + help + 新增方法规范） |
| `lzy-douyin-teardown` | 抖音爆款拆解对比：爆款 vs 非爆款对照组，18 元素 + 扩展维度，输出规律报告 |
| `lzy-video-to-text` | 视频转文字：URL/本地文件 → TXT，本地 Whisper，行业词库纠错，免费离线 |

## 安装 / 更新

```bash
git clone https://github.com/liuzhiyu/lzy-skills.git
bash lzy-skills/install.sh
```

装完后在 Claude Code 里输入 `/lzy help` 查看用法。

## 目录结构

```
skills/
├── lzy/                  入口：路由表 + help + 新增方法规范 + 发布流程
├── lzy-douyin-teardown/  抖音爆款拆解（SKILL.md + scripts/ + VERSION）
└── lzy-video-to-text/    视频转文字（SKILL.md + scripts/ + glossary/ + VERSION）
```

## 机制

- **版本检查**：每个技能根目录有 `VERSION`，`scripts/check_update.sh` 每天最多联网查一次远端版本，有更新时提示。私有仓库场景下读取本机 `~/.workbuddy/.lzy-github-token` 做认证（勿外泄）。
- **发布**：本地 `~/.claude/skills/lzy*` 是源；改完跑 `validate.sh` 校验 → 升 `VERSION` → `publish.sh` 自动 clone 到 /tmp → 同步 → 校验 → commit → push。
- **新增方法**：见 `skills/lzy/SKILL.md` 的「如何新增一个方法」。
