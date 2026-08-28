#!/usr/bin/env python3
"""Generate the custom Nightfall GitHub telemetry card."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path


API = "https://api.github.com"


def request_json(path: str, token: str | None = None, payload: dict | None = None):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "nightfall-metrics",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(f"{API}{path}", data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def contribution_data(username: str, token: str | None):
    if not token:
        return None
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays { contributionCount date }
            }
          }
        }
      }
    }
    """
    try:
        result = request_json(
            "/graphql", token, {"query": query, "variables": {"login": username}}
        )
        calendar = result["data"]["user"]["contributionsCollection"][
            "contributionCalendar"
        ]
        days = [day for week in calendar["weeks"] for day in week["contributionDays"]]
        return {"total": calendar["totalContributions"], "days": days}
    except (KeyError, TypeError, urllib.error.URLError):
        return None


def streaks(days: list[dict]) -> tuple[int, int]:
    counts = [int(day["contributionCount"]) for day in days]
    longest = current = running = 0
    for count in counts:
        if count:
            running += 1
            longest = max(longest, running)
        else:
            running = 0
    for count in reversed(counts):
        if count:
            current += 1
        else:
            break
    return current, longest


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def metric_card(x: int, label: str, value: str, detail: str) -> str:
    return f"""<g transform="translate({x} 128)">
      <rect width="238" height="116" rx="8" fill="#0d0a13" stroke="#2d1b43"/>
      <path d="M0 9V0h9 M229 0h9v9 M238 107v9h-9 M9 116H0v-9" stroke="#8b5cf6" fill="none"/>
      <text x="18" y="29" class="label">{esc(label)}</text>
      <text x="18" y="72" class="value">{esc(value)}</text>
      <text x="18" y="97" class="detail">{esc(detail)}</text>
    </g>"""


def render(username: str, profile: dict, repos: list[dict], events: list[dict], contrib):
    stars = sum(repo.get("stargazers_count", 0) for repo in repos)
    forks = sum(repo.get("forks_count", 0) for repo in repos)
    pushes = [event for event in events if event.get("type") == "PushEvent"]
    active_days = len({event.get("created_at", "")[:10] for event in events})
    repo_activity = Counter(
        event.get("repo", {}).get("name", "").split("/")[-1] for event in pushes
    )
    repo_activity.pop("", None)
    signal_repo = repo_activity.most_common(1)[0][0] if repo_activity else "quiet channel"

    days = contrib["days"] if contrib else []
    total_contrib = contrib["total"] if contrib else None
    current_streak, longest_streak = streaks(days) if days else (0, 0)
    last_28 = days[-28:] if days else []
    pulse = sum(int(day["contributionCount"]) for day in last_28)

    created = dt.datetime.fromisoformat(profile["created_at"].replace("Z", "+00:00"))
    account_years = max((dt.datetime.now(dt.timezone.utc) - created).days // 365, 0)
    updated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    event_names = {
        "PushEvent": "PUSH",
        "CreateEvent": "CREATE",
        "PullRequestEvent": "PULL REQUEST",
        "IssuesEvent": "ISSUE",
        "WatchEvent": "STAR",
        "ForkEvent": "FORK",
        "ReleaseEvent": "RELEASE",
    }
    transmission_rows = []
    for i, event in enumerate(events[:5]):
        y = 340 + i * 39
        kind = event_names.get(event.get("type"), event.get("type", "EVENT").replace("Event", "").upper())
        repo_name = event.get("repo", {}).get("name", "unknown").split("/")[-1]
        stamp = event.get("created_at", "")[5:16].replace("T", " ") or "--"
        transmission_rows.append(
            f'<circle cx="68" cy="{y - 5}" r="3" fill="#8b5cf6"/>'
            f'<text x="82" y="{y}" class="event">{esc(kind)}</text>'
            f'<text x="205" y="{y}" class="lang">{esc(repo_name[:27])}</text>'
            f'<text x="574" y="{y}" text-anchor="end" class="pct">{esc(stamp)} UTC</text>'
        )
    if not transmission_rows:
        transmission_rows.append('<text x="68" y="340" class="detail">waiting for the next public transmission...</text>')

    heat = []
    heat_days = days[-364:] if days else []
    max_count = max((int(day["contributionCount"]) for day in heat_days), default=1)
    for index, day in enumerate(heat_days):
        week, weekday = divmod(index, 7)
        count = int(day["contributionCount"])
        level = 0 if count == 0 else min(4, 1 + int(count / max_count * 3))
        colors = ["#15101d", "#302047", "#57338a", "#8452c7", "#b794f4"]
        x, y = 651 + week * 8, 354 + weekday * 14
        heat.append(
            f'<rect x="{x}" y="{y}" width="6" height="10" rx="2" fill="{colors[level]}">'
            f'<title>{esc(day["date"])}: {count} contributions</title></rect>'
        )

    if not heat:
        for index in range(364):
            week, weekday = divmod(index, 7)
            x, y = 651 + week * 8, 354 + weekday * 14
            heat.append(f'<rect x="{x}" y="{y}" width="6" height="10" rx="2" fill="#15101d"/>')

    cards = "".join(
        [
            metric_card(54, "CONTRIBUTIONS // 1Y", str(total_contrib or "SYNC"), f"{pulse} in the last 28 days"),
            metric_card(306, "PUBLIC REPOSITORIES", str(profile.get("public_repos", 0)), f"{forks} forks across the archive"),
            metric_card(558, "STARS COLLECTED", str(stars), f"{profile.get('followers', 0)} watchers online"),
            metric_card(810, "CURRENT STREAK", f"{current_streak}D" if contrib else "SYNC", f"longest signal: {longest_streak} days"),
        ]
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="620" viewBox="0 0 1100 620" role="img" aria-labelledby="title desc">
  <title id="title">Nightfall GitHub telemetry for {esc(username)}</title>
  <desc id="desc">Custom live GitHub statistics, languages, streak and contribution activity.</desc>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#07050a"/><stop offset="1" stop-color="#10091a"/></linearGradient>
    <linearGradient id="beam"><stop stop-color="#8b5cf6" stop-opacity="0"/><stop offset=".5" stop-color="#b794f4"/><stop offset="1" stop-color="#8b5cf6" stop-opacity="0"/></linearGradient>
    <filter id="glow"><feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M28 0H0V28" fill="none" stroke="#8b5cf6" stroke-opacity=".055"/></pattern>
    <style>
      text {{ font-family: Consolas, 'Courier New', monospace; }}
      .kicker {{ fill:#8b5cf6; font-size:12px; letter-spacing:3px; }}
      .title {{ fill:#eee8f7; font-size:30px; font-weight:700; letter-spacing:4px; }}
      .label {{ fill:#887a99; font-size:11px; letter-spacing:1.4px; }}
      .value {{ fill:#d8c5f4; font-size:33px; font-weight:700; }}
      .detail,.pct {{ fill:#776b85; font-size:11px; }}
      .section {{ fill:#aa88d4; font-size:12px; letter-spacing:2px; }}
      .lang {{ fill:#ded5e8; font-size:13px; }}
      .event {{ fill:#a98bce; font-size:11px; letter-spacing:1px; }}
      .scan {{ animation:scan 5s linear infinite; }}
      .blink {{ animation:blink 1.6s step-end infinite; }}
      @keyframes scan {{ from {{ transform:translateX(-500px) }} to {{ transform:translateX(1100px) }} }}
      @keyframes blink {{ 50% {{ opacity:.25 }} }}
    </style>
  </defs>
  <rect x="1" y="1" width="1098" height="618" rx="14" fill="url(#bg)" stroke="#342047" stroke-width="2"/>
  <rect x="1" y="1" width="1098" height="618" rx="14" fill="url(#grid)"/>
  <path d="M31 1H1v30 M1069 1h30v30 M1099 589v30h-30 M31 619H1v-30" stroke="#a76ff0" stroke-width="2" fill="none"/>
  <g transform="translate(54 42)">
    <circle cx="6" cy="5" r="4" fill="#b794f4" filter="url(#glow)" class="blink"/>
    <text x="22" y="9" class="kicker">LIVE / {esc(username.upper())}</text>
    <text y="49" class="title">NIGHTFALL PROTOCOL</text>
    <text x="992" y="10" text-anchor="end" class="detail">UPDATED {updated}</text>
    <text x="992" y="48" text-anchor="end" class="kicker">ACCOUNT AGE // {account_years}Y</text>
  </g>
  <rect y="107" width="480" height="1" fill="url(#beam)" class="scan"/>
  {cards}
  <path d="M54 280H1046" stroke="#291b39"/>
  <text x="54" y="306" class="section">RECENT TRANSMISSIONS</text>
  <text x="626" y="306" class="section">CONTRIBUTION SIGNAL // 52 WEEKS</text>
  {''.join(transmission_rows)}
  <g>{''.join(heat)}</g>
  <g transform="translate(626 478)">
    <rect width="420" height="78" rx="7" fill="#0c0911" stroke="#24172f"/>
    <text x="18" y="26" class="label">LAST PUBLIC TRANSMISSION</text>
    <text x="18" y="51" class="lang">{esc(signal_repo)}</text>
    <text x="402" y="26" text-anchor="end" class="label">RECENT SIGNAL</text>
    <text x="402" y="51" text-anchor="end" class="lang">{len(pushes)} pushes / {active_days} active days</text>
  </g>
  <path d="M54 579H1046" stroke="#291b39"/>
  <text x="54" y="600" class="detail">github telemetry / generated automatically / source: public GitHub API</text>
  <text x="1046" y="600" text-anchor="end" class="kicker">MEMENTO MORI</text>
</svg>
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="duartess7")
    parser.add_argument("--output", default="metrics/nightfall.svg")
    args = parser.parse_args()
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")

    profile = request_json(f"/users/{args.username}", token)
    repos = request_json(
        f"/users/{args.username}/repos?per_page=100&type=owner&sort=updated", token
    )
    try:
        events = request_json(f"/users/{args.username}/events/public?per_page=100", token)
    except urllib.error.URLError:
        events = []
    contrib = contribution_data(args.username, token)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(args.username, profile, repos, events, contrib), encoding="utf-8")


if __name__ == "__main__":
    main()
