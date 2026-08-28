#!/usr/bin/env python3
"""Generate the paired Nightfall profile dashboard."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import os
import urllib.error
from collections import Counter
from pathlib import Path

import language_spectrum as languages
import nightfall_metrics as telemetry


PALETTE = ["#c7a4f6", "#a871ed", "#8650cf", "#6639a4", "#4b2b78"]


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def stat(x: int, y: int, label: str, value: str, detail: str) -> str:
    return f"""<g transform="translate({x} {y})">
      <rect width="230" height="72" rx="7" fill="#0d0a13" stroke="#2d1b43"/>
      <text x="15" y="21" class="label">{esc(label)}</text>
      <text x="15" y="48" class="stat">{esc(value)}</text>
      <text x="215" y="48" text-anchor="end" class="detail">{esc(detail)}</text>
    </g>"""


def collect(username: str, token: str | None):
    profile = telemetry.request_json(f"/users/{username}", token)
    repositories = languages.public_repositories(username, token)
    try:
        events = telemetry.request_json(
            f"/users/{username}/events/public?per_page=100", token
        )
    except urllib.error.URLError:
        events = []
    contribution = telemetry.contribution_data(username, token)
    language_totals, coded_repositories = languages.language_totals(
        repositories, token
    )
    return profile, repositories, events, contribution, language_totals, coded_repositories


def render(username: str, profile: dict, repositories: list[dict], events: list[dict], contribution, language_totals: Counter, coded_repositories: int) -> str:
    stars = sum(repository.get("stargazers_count", 0) for repository in repositories)
    forks = sum(repository.get("forks_count", 0) for repository in repositories)
    pushes = [event for event in events if event.get("type") == "PushEvent"]
    active_days = len({event.get("created_at", "")[:10] for event in events})
    recent_repo = (
        pushes[0].get("repo", {}).get("name", "quiet channel").split("/")[-1]
        if pushes
        else "quiet channel"
    )

    contribution_days = contribution["days"] if contribution else []
    total_contributions = contribution["total"] if contribution else None
    current_streak, longest_streak = (
        telemetry.streaks(contribution_days) if contribution_days else (0, 0)
    )
    pulse = sum(
        int(day["contributionCount"]) for day in contribution_days[-28:]
    )

    heat = []
    heat_days = contribution_days[-182:]
    maximum = max(
        (int(day["contributionCount"]) for day in heat_days), default=1
    )
    heat_colors = ["#15101d", "#302047", "#57338a", "#8452c7", "#c7a4f6"]
    for index, day in enumerate(heat_days):
        week, weekday = divmod(index, 7)
        count = int(day["contributionCount"])
        level = 0 if count == 0 else min(4, 1 + int(count / maximum * 3))
        heat.append(
            f'<rect x="{28 + week * 18}" y="{309 + weekday * 13}" width="14" height="9" rx="2" fill="{heat_colors[level]}">'
            f'<title>{esc(day["date"])}: {count} contributions</title></rect>'
        )
    if not heat:
        for index in range(182):
            week, weekday = divmod(index, 7)
            heat.append(
                f'<rect x="{28 + week * 18}" y="{309 + weekday * 13}" width="14" height="9" rx="2" fill="#15101d"/>'
            )

    ranked = language_totals.most_common(5)
    total_bytes = sum(language_totals.values())
    dominant = ranked[0][0] if ranked else "AWAITING"
    segments = []
    cursor = 24.0
    for index, (language, amount) in enumerate(ranked):
        width = 487 * amount / total_bytes if total_bytes else 0
        segments.append(
            f'<rect x="{cursor:.1f}" y="235" width="{max(width, 2):.1f}" height="18" fill="{PALETTE[index]}">'
            f'<title>{esc(language)}: {amount / total_bytes * 100:.1f}%</title></rect>'
        )
        cursor += width

    language_rows = []
    for index, (language, amount) in enumerate(ranked):
        y = 294 + index * 42
        percentage = amount / total_bytes * 100 if total_bytes else 0
        language_rows.append(
            f'<circle cx="31" cy="{y - 4}" r="5" fill="{PALETTE[index]}" filter="url(#glow)"/>'
            f'<text x="47" y="{y}" class="lang">{esc(language)}</text>'
            f'<text x="310" y="{y}" text-anchor="end" class="pct">{percentage:.1f}%</text>'
            f'<rect x="326" y="{y - 12}" width="118" height="8" rx="4" fill="#171020"/>'
            f'<rect x="326" y="{y - 12}" width="{max(percentage * 1.18, 2):.1f}" height="8" rx="4" fill="{PALETTE[index]}"/>'
            f'<text x="506" y="{y}" text-anchor="end" class="detail">{languages.human_bytes(amount)}</text>'
        )
    if not language_rows:
        language_rows.append(
            '<text x="24" y="294" class="detail">waiting for the first public language signal...</text>'
        )
    elif len(language_rows) == 1:
        language_rows.append(
            '<rect x="24" y="330" width="487" height="188" rx="8" fill="#0c0911" stroke="#2d1b43" stroke-dasharray="5 6"/>'
            '<text x="44" y="363" class="label">NEXT FREQUENCY // ARMED</text>'
            '<text x="44" y="393" class="lang">AWAITING A NEW LANGUAGE SIGNAL</text>'
            '<text x="44" y="418" class="detail">publish another coded repository to expand the spectrum</text>'
            '<path d="M44 464h36l12-17 20 34 18-53 18 36h30l14-24 15 24h40l12-12 12 12h36" fill="none" stroke="#8b5cf6" stroke-width="2" opacity=".75"/>'
            '<circle cx="80" cy="464" r="3" fill="#c7a4f6" filter="url(#glow)"/>'
            '<circle cx="148" cy="464" r="3" fill="#c7a4f6" filter="url(#glow)"/>'
            '<circle cx="192" cy="464" r="3" fill="#c7a4f6" filter="url(#glow)"/>'
            '<text x="491" y="500" text-anchor="end" class="kicker">AUTO-SCAN // 03:17 UTC</text>'
        )
    elif len(language_rows) < 5:
        y = 294 + len(language_rows) * 42
        language_rows.append(
            f'<text x="24" y="{y}" class="detail">+ awaiting new public frequencies</text>'
        )

    updated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    left_stats = "".join(
        (
            stat(24, 104, "CONTRIBUTIONS // 1Y", str(total_contributions or "SYNC"), f"28D {pulse}"),
            stat(281, 104, "PUBLIC ARCHIVES", str(profile.get("public_repos", 0)), f"FORKS {forks}"),
            stat(24, 190, "STARS COLLECTED", str(stars), f"WATCH {profile.get('followers', 0)}"),
            stat(281, 190, "CURRENT STREAK", f"{current_streak}D" if contribution else "SYNC", f"MAX {longest_streak}D"),
        )
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="590" viewBox="0 0 1100 590" role="img" aria-labelledby="title desc">
  <title id="title">Nightfall paired GitHub dashboard for {esc(username)}</title>
  <desc id="desc">GitHub telemetry and public language distribution displayed in two equal panels.</desc>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#07050a"/><stop offset="1" stop-color="#10091a"/></linearGradient>
    <filter id="glow"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M28 0H0V28" fill="none" stroke="#8b5cf6" stroke-opacity=".055"/></pattern>
    <clipPath id="dna"><rect x="24" y="235" width="487" height="18" rx="5"/></clipPath>
    <style>
      text {{ font-family: Consolas, 'Courier New', monospace; }}
      .kicker {{ fill:#8b5cf6; font-size:10px; letter-spacing:2.2px; }}
      .title {{ fill:#eee8f7; font-size:23px; font-weight:700; letter-spacing:3px; }}
      .label {{ fill:#887a99; font-size:9px; letter-spacing:1px; }}
      .stat {{ fill:#d8c5f4; font-size:23px; font-weight:700; }}
      .detail,.pct {{ fill:#776b85; font-size:9px; }}
      .lang {{ fill:#ded5e8; font-size:13px; font-weight:700; }}
      .hero {{ fill:#d8c5f4; font-size:30px; font-weight:700; }}
      .blink {{ animation:blink 1.6s step-end infinite; }}
      @keyframes blink {{ 50% {{ opacity:.25 }} }}
    </style>
  </defs>

  <g>
    <rect x="1" y="1" width="533" height="588" rx="14" fill="url(#bg)" stroke="#342047" stroke-width="2"/>
    <rect x="1" y="1" width="533" height="588" rx="14" fill="url(#grid)"/>
    <path d="M27 1H1v26 M508 1h26v26 M534 563v26h-26 M27 589H1v-26" stroke="#a76ff0" stroke-width="2" fill="none"/>
    <circle cx="30" cy="34" r="4" fill="#b794f4" filter="url(#glow)" class="blink"/>
    <text x="45" y="38" class="kicker">LIVE / {esc(username.upper())}</text>
    <text x="24" y="78" class="title">NIGHTFALL PROTOCOL</text>
    {left_stats}
    <text x="24" y="291" class="kicker">CONTRIBUTION SIGNAL // 26 WEEKS</text>
    <g>{''.join(heat)}</g>
    <rect x="24" y="426" width="487" height="92" rx="7" fill="#0c0911" stroke="#24172f"/>
    <text x="41" y="453" class="label">LAST PUBLIC TRANSMISSION</text>
    <text x="41" y="481" class="lang">{esc(recent_repo[:28])}</text>
    <text x="494" y="453" text-anchor="end" class="label">RECENT SIGNAL</text>
    <text x="494" y="481" text-anchor="end" class="detail">{len(pushes)} pushes / {active_days} active days</text>
    <text x="24" y="555" class="detail">UPDATED {updated}</text>
    <text x="510" y="555" text-anchor="end" class="kicker">MEMENTO MORI</text>
  </g>

  <g transform="translate(566)">
    <rect x="1" y="1" width="533" height="588" rx="14" fill="url(#bg)" stroke="#342047" stroke-width="2"/>
    <rect x="1" y="1" width="533" height="588" rx="14" fill="url(#grid)"/>
    <path d="M27 1H1v26 M508 1h26v26 M534 563v26h-26 M27 589H1v-26" stroke="#a76ff0" stroke-width="2" fill="none"/>
    <circle cx="30" cy="34" r="4" fill="#b794f4" filter="url(#glow)" class="blink"/>
    <text x="45" y="38" class="kicker">SCAN / PUBLIC REPOSITORIES</text>
    <text x="24" y="78" class="title">LANGUAGE SPECTRUM</text>
    <rect x="24" y="104" width="487" height="101" rx="8" fill="#0d0a13" stroke="#2d1b43"/>
    <text x="42" y="130" class="label">DOMINANT SIGNAL</text>
    <text x="42" y="170" class="hero">{esc(dominant.upper())}</text>
    <text x="493" y="131" text-anchor="end" class="detail">{len(repositories)} PUBLIC ARCHIVES</text>
    <text x="493" y="151" text-anchor="end" class="detail">{coded_repositories} WITH CODE</text>
    <text x="493" y="171" text-anchor="end" class="detail">{len(language_totals)} LANGUAGES</text>
    <text x="493" y="191" text-anchor="end" class="detail">{languages.human_bytes(total_bytes)} INDEXED</text>
    <text x="24" y="224" class="kicker">CODE DNA // BYTE DISTRIBUTION</text>
    <rect x="24" y="235" width="487" height="18" rx="5" fill="#171020"/>
    <g clip-path="url(#dna)">{''.join(segments)}</g>
    {''.join(language_rows)}
    <text x="24" y="555" class="detail">GITHUB LINGUIST / FORKS EXCLUDED</text>
    <text x="510" y="555" text-anchor="end" class="kicker">NIGHTFALL SYSTEM</text>
  </g>
</svg>
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="duartess7")
    parser.add_argument("--output", default="metrics/overview.svg")
    args = parser.parse_args()
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    data = collect(args.username, token)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(args.username, *data), encoding="utf-8")


if __name__ == "__main__":
    main()
