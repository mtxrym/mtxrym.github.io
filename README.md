# Trending AI Coding Tracker

一个用于抓取、分析并生成 AI Coding 趋势报告的小工具。

## 如何运行

### 1) 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
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
