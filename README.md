# AI Coding 资讯看板

自动追踪 arXiv 与 Hugging Face 上和 AI 编程相关的论文、数据集，按相关性 / 热度 / 新鲜度 / 影响力综合打分，
通过 GitHub Actions 定时更新，发布为网页和 Android App。

- 网页：<https://mtxrym.github.io/>（支持“添加到主屏幕”，离线可看）
- Android App：[Releases](https://github.com/mtxrym/mtxrym.github.io/releases/latest) 下载 `ai-coding-feed.apk`（源码见 [`android/`](android/)）
- 原始数据：[`blog.json`](https://mtxrym.github.io/blog.json)、[`data/status.json`](https://mtxrym.github.io/data/status.json)

## 数据更新策略

**所有策略参数都在 [`config/update_policy.yaml`](config/update_policy.yaml) 里维护**，改完不用动代码，下一次定时任务生效。
网页和 App 会读取 `data/status.json` 中的策略摘要并展示出来。

| 参数 | 当前值 | 说明 |
| --- | --- | --- |
| 抓取频率 | 每天 4 次（UTC 05:30 / 11:30 / 17:30 / 23:30） | 05:30 紧跟 arXiv 每日刷新（美东午夜，UTC 04:00–05:00）；其余三次跟进 HF 点赞热度；避开整点防止 GitHub 定时任务延迟 |
| 展示窗口 | 最近 7 天首次收录 | 滚动窗口，arXiv 周末停更时页面也不会空 |
| 展示上限 | 30 条，其中数据集最多 6 条 | |
| 相关性门槛 | ≥ 35 / 100 | 低于门槛的内容不进历史库、不展示 |
| 历史保留 | 14 天（按最后出现日期） | 用于跨天去重、记录首次收录时间 |
| 滞后判定 | 96 小时没有新条目 | arXiv 周五、周六不发布，留足余量 |
| 打分权重 | 相关性 50% · 热度 20% · 新鲜度 20% · 影响力 10% | 新鲜度半衰期 3 天 |

唯一的例外是抓取频率：GitHub 只认 [`.github/workflows/update-content.yml`](.github/workflows/update-content.yml) 里的 cron，
改频率时两处要一起改（`tests/test_policy.py` 会检查两者一致，不一致时定时任务会在测试步骤失败）。

数据源在 [`config/sources.yaml`](config/sources.yaml) 中维护：

| 数据源 | 说明 |
| --- | --- |
| arXiv cs.SE / cs.CL / cs.AI / cs.LG | 每日 RSS，读取完整列表后按相关性筛选，跳过 replace（旧论文新版本） |
| Hugging Face Daily Papers | 社区精选论文，提供点赞数与代码仓库；与 arXiv 同一篇论文会自动合并 |
| Hugging Face 数据集（code / swe） | 按 trendingScore 排序的数据集搜索 |

## 流水线

```
config/sources.yaml ──► src/sources.py   抓取并统一成 Record
                        src/relevance.py 相关性：AI 信号 × 代码信号，标题加权
                        src/scoring.py   综合得分（0–100）
                        src/feed.py      去重合并 → 历史库滚动更新 → 选出展示条目
config/update_policy.yaml ─┘
                              │
                              ▼
        blog.json · data/status.json · data/archive.json ──► GitHub Pages / Android App
```

`scripts/generate_blog_json.py` 串起整个流程：

- 内容没有变化时不改写任何文件，不会产生空提交；
- 部分数据源失败时照常生成，并在 `status.json` 中标记；
- **所有**数据源都失败时以非零状态退出（GitHub 会发邮件提醒），保留旧数据不变。

## 本地运行

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m unittest discover -s tests -t .      # 单元测试
python scripts/generate_blog_json.py            # 抓取并生成数据
python scripts/generate_blog_json.py --dry-run  # 只打印结果，不写文件
python scripts/trending_ai_coding.py --sources arxiv_cs_se   # 排查单个数据源
python -m http.server 8000                      # 预览网页：http://localhost:8000
```

## GitHub Actions

| 工作流 | 触发 | 作用 |
| --- | --- | --- |
| `update-content.yml` | 定时（见上表）/ 手动 | 跑测试 → 生成数据 → 有变化时提交到 `master` |
| `deploy-pages.yml` | 推送到 `master` / 数据更新完成后 / 手动 | 部署 GitHub Pages |
| `android.yml` | `android/` 有改动 / 手动 | 单元测试 → 构建 APK → 发布 Release |

> 数据更新用 `GITHUB_TOKEN` 推送，这类推送不会触发其他工作流的 `push` 事件，
> 所以部署工作流额外监听了 `workflow_run`，数据更新成功后自动部署。

首次使用需在仓库 `Settings → Pages` 中把 `Source` 设为 **GitHub Actions**。

## 目录结构

```text
index.html · index.css · app.js      网页
manifest.webmanifest · sw.js · assets/   PWA
blog.json                             展示数据（生成）
data/status.json · data/archive.json  数据源状态、历史库（生成）
config/update_policy.yaml             更新策略
config/sources.yaml                   数据源
src/                                  抓取、相关性、打分、合并逻辑
scripts/                              命令行入口
tests/                                单元测试
android/                              Android App
templates/ · src/reporting.py · src/notifier.py   Markdown 日报渲染与推送（stdout / Slack）
```
