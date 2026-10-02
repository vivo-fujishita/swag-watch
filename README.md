# swag-watch

Watches the Claude Code swag giveaway on claude.dev/terminal (Clawd plushie / sticker pack) every 5 minutes and posts to Slack when it reopens.

- watch.py: checks swag-status.json and the redemption form redirect
- state.json: last seen state, committed only when it changes
- Run "swag-watch" manually with probe=true to verify the Slack token and channels without posting
