# finance_news

GitHub Actions workspace for two Feishu finance briefings:

- Morning China-facing briefing at `08:00 Asia/Shanghai`
- Evening US-investor briefing at `20:30 Asia/Shanghai`

Important files:

- `.github/workflows/morning-finance-news.yml`: morning workflow
- `.github/workflows/us-investor-evening-news.yml`: evening workflow
- `scripts/generate_morning_brief.py`: builds the morning `财经早报 / A股/港股视角 / 风险提示`
- `scripts/generate_evening_brief.py`: builds the evening `美股投资者视角 / 今晚关注 / 风险提示`
- `scripts/finance_brief_common.py`: shared market/news/translation helpers
- `tools/send-feishu-post.ps1`: sends the final Feishu post message using
  `FEISHU_WEBHOOK_URL` and optional `FEISHU_BOT_SECRET`

Required GitHub repository secrets:

- `FEISHU_WEBHOOK_URL`
- `FEISHU_BOT_SECRET`

Current schedules:

- Morning workflow: `0 0 * * *` UTC = `08:00 Asia/Shanghai`
- Evening workflow: `30 12 * * *` UTC = `20:30 Asia/Shanghai`
