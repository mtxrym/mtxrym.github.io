# AI Coding 资讯看板

自动追踪 arXiv 与 Hugging Face 上和 AI 编程相关的论文、数据集，按相关性 / 热度 / 新鲜度 / 影响力综合打分，
通过 GitHub Actions 定时更新，发布为网页和 Android App。

- 网页：<https://mtxrym.github.io/>（支持“添加到主屏幕”，离线可看）
- Android App：[Releases](https://github.com/mtxrym/mtxrym.github.io/releases/latest) 下载 `ai-coding-feed.apk`（源码见 [`android/`](android/)）
- 原始数据：[`blog.json`](https://mtxrym.github.io/blog.json)、[`data/status.json`](https://mtxrym.github.io/data/status.json)
- 热榜聚合：<https://mtxrym.github.io/trending/>（微博、知乎、百度、头条、GitHub、Hacker News、华尔街见闻等，见[下文](#热榜聚合trending)）

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

## 大模型复核（DeepSeek-V4.1-Flash）

关键词规则负责“召回”（宽松初筛），DeepSeek 负责“判定”：对候选条目逐条打 0–100 分、选中文主题标签、写中文一句话总结。

| | 规则 | DeepSeek-V4.1-Flash（关闭思考） |
| --- | --- | --- |
| 非边界样本 F1 | 0.879（漏判 11 / 误收 2） | **1.000**（0 / 0） |
| 全部样本准确率 | 82.2% | **98.0%** |

评测集是 101 条人工标注的真实数据（[`tests/fixtures/relevance_gold.json`](tests/fixtures/relevance_gold.json)），用 `scripts/eval_relevance.py --llm` 复现。
开启思考（`reasoning_effort: low`）准确率反而略低、token 翻倍，所以默认关闭。

- **启用方式**：仓库 `Settings → Secrets and variables → Actions` 添加 `DEEPSEEK_API_KEY`。未配置时自动退回关键词规则，不影响更新。
- **费用**：判定结果缓存在 `data/llm_cache.json`，同一条内容只调用一次；日常每次运行只判定新出现的几十条，首次全量约 150 条、3.5 万 token。
- **容错**：单批调用失败只影响这一批（退回规则分），`status.json` 的 `llm.healthy` 会标记异常。
- **配置**：`config/update_policy.yaml` 的 `llm` 一节（模型、推理强度、送审门槛 `candidate_min_relevance`、收录门槛 `min_score`、单次预算等）。
  修改提示词请同时更新 `src/llm.py` 中的 `PROMPT_VERSION`，已缓存的判定会按新版本重新生成。

## 论文解读

为展示中的论文生成结构化中文解读：**问题 / 方法 / 结果（带关键数字）/ 启示 / 局限**，网页和 App 中点击“论文解读”展开。

- 优先读取 arXiv HTML 全文（去掉参考文献、目录，公式保留 LaTeX 源码，超长时保留前 75% + 结论部分）；没有 HTML 版本时退回完整摘要，界面上会标明“基于全文 / 基于摘要”
- 只为展示中的论文生成，结果缓存在 `data/digests.json`，每篇只生成一次；首次 24 篇约 37 秒、16.5 万 token，之后每次只处理新上榜的论文
- 质量抽检：24 篇解读中出现的 256 个数字全部能在原文中找到
- 配置：`config/update_policy.yaml` 的 `llm.digest` 一节

## 热榜聚合（/trending/）

参照 [NewsNow](https://github.com/ourongxing/newsnow)（MIT）复刻的多平台热榜，源列表和抓取逻辑移植自该项目，用 Python 重写。

- **页面**：<https://mtxrym.github.io/trending/>
  - 按 最热 / 实时 / 国内 / 国际 / 科技 / 财经 / 体育 分栏，`/` 快捷键搜索
  - “新”表示本轮新上榜，↑↓ 是热榜名次与上一轮相比的变化
  - 页面开着时每 5 分钟检查一次有没有新数据，有就自动刷新
- **我的收藏**：<https://mtxrym.github.io/trending/favorites.html>
  - 收藏源：点卡片右上角 ☆，收藏的源在这个页面单独展示，可以调整顺序
  - 收藏条目：鼠标移到条目上点书签图标，条目下榜后仍会保留
  - 收藏存在浏览器本地（localStorage）；换设备或备份用页面上的“导出 / 导入”（JSON 文件）
- **接口**（静态 JSON）：
  - [`/trending/data/index.json`](https://mtxrym.github.io/trending/data/index.json)：各源的名称、栏目、抓取状态、条数、错误信息
  - [`/trending/data/all.json`](https://mtxrym.github.io/trending/data/all.json)：全部源及条目
  - `/trending/data/<id>.json`：单个源，相当于 NewsNow 的 `/api/s?id=<id>`
  - 条目字段：`id / title / url`，可选 `info`（热度、分数等）、`hover`（摘要）、`time`（UTC）、`first_seen`（首次上榜时间）、`rank_delta`（名次变化，正数为上升）
- **抓取原则**：只发普通的公开请求，UA 如实标明身份；不伪造 cookie、签名、来源页，不处理反爬验证，被拒绝就如实显示为“暂时拿不到”。
  因此 NewsNow 里依赖这些手段的源会失败（如微博、抖音、雪球、财联社、B 站热门视频），酷安（需要伪造 App 签名）没有移植。
  `tests/test_trending.py` 会检查抓取代码里没有这类请求头
- **配置**：数据源在 [`config/trending_sources.yaml`](config/trending_sources.yaml)，抓取器在 [`src/trending/`](src/trending/)，两边按 id 对应
- **排查**：`python scripts/fetch_trending.py --only weibo,zhihu --dry-run`；改动抓取器后推到分支，`Trending Probe` 工作流会在 GitHub 运行环境里试抓全部源，结果在运行摘要里

### 热榜 · 定时更新

热榜数据不入库：`deploy-pages.yml` 每次部署前现抓，并对照线上上一版 `all.json` 标注新上榜、名次变化；某个源失败时沿用上一版数据（标记“旧数据”）。触发方式有三种：

| 触发 | 频率 | 说明 |
| --- | --- | --- |
| GitHub 定时任务 | 每小时（`17 * * * *`） | 保底，但在这个仓库上常延迟数小时甚至被跳过 |
| AI 资讯更新完成 | 每天 4 次 | `workflow_run` 触发部署，顺带刷新热榜 |
| 外部定时服务（推荐） | 每小时准点 | 调用 GitHub 接口手动触发部署，见下 |

要准点每小时刷新，用任意外部定时服务（[cron-job.org](https://cron-job.org)、Cloudflare Workers Cron 等）每小时调用一次部署工作流：

1. GitHub → Settings → Developer settings → Fine-grained tokens → Generate new token：
   Repository access 只选 `mtxrym/mtxrym.github.io`；Permissions 只给 **Actions: Read and write**（这个 token 只能触发 / 取消本仓库的工作流，不能改代码）
2. 在定时服务里新建任务，每小时一次：

   ```bash
   curl -X POST https://api.github.com/repos/mtxrym/mtxrym.github.io/actions/workflows/deploy-pages.yml/dispatches \
     -H "Authorization: Bearer <token>" \
     -H "Accept: application/vnd.github+json" \
     -H "X-GitHub-Api-Version: 2022-11-28" \
     -d '{"ref":"master"}'
   ```

   返回 `204` 即成功；在 Actions 页面能看到 `workflow_dispatch` 触发的 “Deploy GitHub Pages”。

数据源在 [`config/sources.yaml`](config/sources.yaml) 中维护：

| 数据源 | 说明 |
| --- | --- |
| arXiv cs.SE / cs.CL / cs.AI / cs.LG | 每日 RSS，读取完整列表后按相关性筛选，跳过 replace（旧论文新版本） |
| Hugging Face Daily Papers | 社区精选论文，提供点赞数与代码仓库；与 arXiv 同一篇论文会自动合并 |
| Hugging Face 数据集（code / swe） | 按 trendingScore 排序的数据集搜索 |

## 流水线

```
config/sources.yaml ──► src/sources.py   抓取并统一成 Record
                        src/relevance.py 相关性初筛：AI 信号 × 代码信号，标题加权
                        src/llm.py       DeepSeek 复核：打分、主题、中文一句话总结；论文解读（带缓存）
                        src/fulltext.py  arXiv HTML 全文提取
                        src/scoring.py   综合得分（0–100）
                        src/feed.py      去重合并 → 历史库滚动更新 → 选出展示条目
config/update_policy.yaml ─┘
                              │
                              ▼
        blog.json · data/*.json（状态、历史库、判定缓存、论文解读）──► GitHub Pages / Android App
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
python scripts/eval_relevance.py --llm          # 识别准确率评测（需要 DEEPSEEK_API_KEY）
python scripts/generate_blog_json.py            # 抓取并生成数据
python scripts/generate_blog_json.py --dry-run  # 只打印结果，不写文件
python scripts/trending_ai_coding.py --sources arxiv_cs_se   # 排查单个数据源
python scripts/fetch_trending.py                # 抓取热榜，写入 trending/data/（预览 /trending/）
python -m http.server 8000                      # 预览网页：http://localhost:8000
```

## GitHub Actions

| 工作流 | 触发 | 作用 |
| --- | --- | --- |
| `update-content.yml` | 定时（见上表）/ 手动 | 跑测试 → 生成数据 → 有变化时提交到 `master` |
| `deploy-pages.yml` | 推送到 `master` / 数据更新完成后 / 每小时 / 手动或外部定时调用 | 抓取热榜 → 部署 GitHub Pages |
| `trending-probe.yml` | 热榜抓取代码有改动的分支推送 / 手动 | 在 GitHub 运行环境里试抓全部热榜源，结果写进运行摘要 |
| `android.yml` | `android/` 有改动 / 手动 | 单元测试 → 构建 APK → 发布 Release |

> 数据更新用 `GITHUB_TOKEN` 推送，这类推送不会触发其他工作流的 `push` 事件，
> 所以部署工作流额外监听了 `workflow_run`，数据更新成功后自动部署。

首次使用需在仓库 `Settings → Pages` 中把 `Source` 设为 **GitHub Actions**。

## 目录结构

```text
index.html · index.css · app.js      网页
manifest.webmanifest · sw.js · assets/   PWA
blog.json                             展示数据（生成）
data/status.json · data/archive.json   数据源状态、历史库（生成）
data/llm_cache.json · data/digests.json 模型判定缓存、论文解读缓存（生成）
config/update_policy.yaml             更新策略
config/sources.yaml                   数据源
config/trending_sources.yaml          热榜数据源
trending/                             热榜页面、我的收藏页（data/ 由部署工作流生成，不入库）
src/                                  抓取、相关性、打分、合并逻辑
scripts/                              命令行入口
tests/                                单元测试
android/                              Android App
templates/ · src/reporting.py · src/notifier.py   Markdown 日报渲染与推送（stdout / Slack）
```
