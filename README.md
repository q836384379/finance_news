# finance_news

GitHub Actions workspace for a daily finance briefing that is sent to Feishu.

Important files:

- `.github/workflows/daily-finance-news.yml`: scheduled workflow
- `scripts/generate_finance_brief.py`: builds a compact Chinese briefing from
  public market data and RSS headlines using only the Python standard library
- `tools/send-feishu-post.ps1`: sends the final Feishu post message using
  `FEISHU_WEBHOOK_URL` and optional `FEISHU_BOT_SECRET`

Required GitHub repository secrets:

- `FEISHU_WEBHOOK_URL`
- `FEISHU_BOT_SECRET`

Default schedule:

- `0 1 * * *` in GitHub Actions cron, which is `09:00` in `Asia/Shanghai`
