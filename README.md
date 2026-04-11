# Daily AI Report Pipeline

这个仓库新增了一个简化的日报能力，用于将抓取/整理后的结构化数据渲染为 Markdown，并通过通知适配层推送。

## 目录结构

- `templates/daily_report.md.j2`：日报模板（固定结构：当日摘要 / Papers Top N / Datasets Top N / 关键趋势观察）。
- `src/reporting.py`：模板渲染与 markdown 文件落盘。
- `src/notifier.py`：推送适配层，当前支持 `stdout` 与 Slack Webhook。
- `logs/`：错误与运行日志目录，避免静默失败。

## 本地运行

> 需要 Python 3.10+，并安装 `jinja2`。
# Trending AI Coding Tracker

一个用于抓取、分析并生成 AI Coding 趋势报告的小工具。

## 如何运行

### 1) 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install jinja2
```

示例：渲染并输出日报。

```python
from src.reporting import render_daily_report, save_report
from src.notifier import notify

context = {
    "report_date": "2026-04-11",
    "daily_summary": [
        "多模态模型在代码修复场景准确率继续提升",
        "开源 agent 框架围绕评测与可观测性持续完善",
        "企业开始关注低成本推理部署方案",
    ],
    "papers_top_n": 3,
    "datasets_top_n": 3,
    "papers": [
        {
            "title": "Paper A",
            "authors": ["Alice", "Bob"],
            "source": "arXiv",
            "url": "https://arxiv.org/abs/xxxx.xxxxx",
            "highlight": "提出更稳健的 agent 规划方法",
        },
    ],
    "datasets": [
        {
            "name": "Dataset A",
            "source": "Hugging Face",
            "url": "https://huggingface.co/datasets/example",
            "highlight": "新增真实任务级代码评测样本",
        },
    ],
    "trend_observations": [
        "agent coding benchmark 持续升温",
        "模型评测从单点指标转向端到端任务成功率",
    ],
}

markdown = render_daily_report(context)
save_report(markdown, "outputs/daily_report.md")
notify("stdout", markdown)
# notify("slack", markdown, webhook_url="https://hooks.slack.com/services/...")
```

## 定时任务

### 1) cron

每日上午 9 点执行（示例）：

```cron
0 9 * * * cd /path/to/repo && /path/to/repo/.venv/bin/python your_job.py >> /path/to/repo/logs/cron.log 2>&1
```

建议在 `your_job.py` 中调用：
1. 数据抓取/整理
2. `render_daily_report`
3. `save_report`
4. `notify`

### 2) GitHub Actions

创建 `.github/workflows/daily-report.yml`（示例骨架）：

```yaml
name: Daily Report

on:
  schedule:
    - cron: "0 1 * * *" # UTC 01:00
  workflow_dispatch:

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install deps
        run: pip install jinja2
      - name: Run job
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
        run: python your_job.py
```

## 失败重试与日志

- `src/reporting.py` 与 `src/notifier.py` 内建重试机制（默认 3 次，间隔 1 秒）。
- 失败会写入：
  - `logs/reporting.log`
  - `logs/notifier.log`
- 当重试耗尽时抛出异常，避免静默失败。
pip install -r requirements.txt
```

### 2) 抓取趋势数据（papers + datasets）

```bash
python scripts/trending_ai_coding.py fetch
```

### 3) 做 AI Coding 相关性筛选与排序

```bash
python scripts/trending_ai_coding.py analyze --min-score 6
```

### 4) 生成日报 / 周报 Markdown

日报：

```bash
python scripts/trending_ai_coding.py report --period daily --top-n 10
```

周报：

```bash
python scripts/trending_ai_coding.py report --period weekly --top-n 20
```

## 目录说明

```text
scripts/
  trending_ai_coding.py      # 主入口，支持 fetch / analyze / report
outputs/
  raw/
    papers_*.json            # 原始论文抓取
    datasets_*.json          # 原始数据集抓取
    analysis_*.json          # 分析与排序结果
  reports/
    YYYY-MM-DD.md            # 日报/周报 markdown
requirements.txt             # Python 依赖
```
