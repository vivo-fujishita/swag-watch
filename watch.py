#!/usr/bin/env python3
"""Watch claude.dev/terminal swag (Clawd plushie / stickers) and post to Slack when it reopens.

Signals (either one opening counts as reopened):
  1. https://claude.dev/terminal/swag-status.json -> {"off": [...]}
  2. The Brilliant redemption form stops redirecting to /sorry

State is kept in state.json and committed by the workflow only when it changes.

Env (GitHub Secrets):
  SLACK_BOT_TOKEN   bot token (chat:write)
  SLACK_NOTIFY_CH   channel for every reopen
  SLACK_PLUSHIE_CH  channel for the plushie announcement (falls back to SLACK_NOTIFY_CH)
  SLACK_MENTIONS    e.g. "<@U1> <@U2>"
Usage:
  python watch.py          check and notify on closed -> open
  python watch.py --probe  verify token and channel access without posting anything
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, "state.json")
STATUS_URL = "https://claude.dev/terminal/swag-status.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
ITEMS = {
    "plushie": {"name": "Clawd ぬいぐるみ", "form": "https://app.brilliantmade.com/r/claude-code-plushies", "command": "/plushies"},
    "stickers": {"name": "ステッカー", "form": "https://app.brilliantmade.com/r/claude-code-stickers", "command": "/stickers"},
}

TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
NOTIFY_CH = os.environ.get("SLACK_NOTIFY_CH", "")
PLUSHIE_CH = os.environ.get("SLACK_PLUSHIE_CH", "") or NOTIFY_CH
MENTIONS = os.environ.get("SLACK_MENTIONS", "")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch_off():
    req = urllib.request.Request(STATUS_URL, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    off = data.get("off")
    if not isinstance(off, list):
        raise ValueError(f"unexpected payload: {data!r}")
    return set(off)


def form_open(url):
    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with opener.open(req, timeout=20) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            return "/sorry" not in (e.headers.get("Location") or "")
        raise


def slack(method, payload):
    req = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def post(channel, text):
    body = slack("chat.postMessage", {"channel": channel, "text": text, "username": "ATLAS"})
    if not body.get("ok") and body.get("error") in ("missing_scope", "invalid_arguments", "not_allowed_token_type"):
        body = slack("chat.postMessage", {"channel": channel, "text": text})
    return body.get("ok", False), body.get("error", "")


def announce(key, item, cur):
    status = f"status.json={'開' if cur['json'] else '閉'} / フォーム={'開' if cur['form'] else '閉'}"
    if key == "plushie":
        text = (
            f"{MENTIONS}\n"
            "Clawdぬいぐるみの配布、再開しました！\n"
            f"早い者勝ちなのでお早めに。claude.dev/terminal で {item['command']} か、フォームから直接どうぞ\n"
            f"{item['form']}"
        ).strip()
        ok, err = post(PLUSHIE_CH, text)
        if not ok:
            print(f"plushie channel post failed: {err}", flush=True)
            post(NOTIFY_CH, f"ぬいぐるみ再開の投稿に失敗しました（{err}）。貼り付け用:\n{text}")
    ok, err = post(NOTIFY_CH, f"{item['name']}の配布が再開しました\n申込フォーム: {item['form']}\n（{status}）")
    if not ok:
        raise RuntimeError(f"notify post failed: {err}")


def probe():
    auth = slack("auth.test", {})
    print("auth.test:", auth.get("ok"), auth.get("error", ""), auth.get("user", ""))
    good = auth.get("ok", False)
    for label, ch in (("notify", NOTIFY_CH), ("plushie", PLUSHIE_CH)):
        r = slack("chat.scheduleMessage", {"channel": ch, "text": "probe", "post_at": int(time.time()) + 86400 * 30})
        if r.get("ok"):
            slack("chat.deleteScheduledMessage", {"channel": r["channel"], "scheduled_message_id": r["scheduled_message_id"]})
        else:
            good = good and label != "notify"  # plushie channel falls back to notify
        print(f"{label} channel can post:", r.get("ok"), r.get("error", ""))
    off = fetch_off()
    print("swag off:", sorted(off), "/ plushie form open:", form_open(ITEMS["plushie"]["form"]))
    return 0 if good else 1


def main():
    if "--probe" in sys.argv:
        return probe()
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            prev = json.load(f).get("items", {})
    except (OSError, ValueError):
        prev = {}
    off = fetch_off()
    current = {}
    for key, item in ITEMS.items():
        j = key not in off
        f = form_open(item["form"])
        current[key] = {"json": j, "form": f, "open": j or f}
    for key, cur in current.items():
        if cur["open"] and not prev.get(key, {}).get("open", False):
            announce(key, ITEMS[key], cur)
    print(" ".join(f"{k}={'open' if v['open'] else 'closed'}(json={int(v['json'])},form={int(v['form'])})" for k, v in current.items()), flush=True)
    with open(STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump({"items": current}, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
