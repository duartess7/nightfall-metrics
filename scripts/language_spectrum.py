#!/usr/bin/env python3
"""Generate the Nightfall Language Spectrum from public GitHub repositories."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path


API = "https://api.github.com"
COLORS = ["#c7a4f6", "#a871ed", "#8650cf", "#6639a4", "#4b2b78", "#352047"]


def request_json(path: str, token: str | None = None):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "nightfall-language-spectrum",
        "X-GitHub-Api-Version": "2026-03-10",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"{API}{path}", headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def public_repositories(username: str, token: str | None) -> list[dict]:
    repositories = []
    for page in range(1, 11):
        batch = request_json(
            f"/users/{urllib.parse.quote(username)}/repos"
            f"?per_page=100&type=owner&sort=updated&page={page}",
            token,
        )
        repositories.extend(repo for repo in batch if not repo.get("fork"))
        if len(batch) < 100:
            break
    return repositories


def language_totals(repositories: list[dict], token: str | None) -> tuple[Counter, int]:
    totals = Counter()
    repositories_with_code = 0
    for repository in repositories:
        owner = urllib.parse.quote(repository["owner"]["login"])
        name = urllib.parse.quote(repository["name"])
        try:
            languages = request_json(f"/repos/{owner}/{name}/languages", token)
        except (urllib.error.HTTPError, urllib.error.URLError):
            continue
        if languages:
            repositories_with_code += 1
            totals.update({language: int(amount) for language, amount in languages.items()})
    return totals, repositories_with_code


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def human_bytes(amount: int) -> str:
    value = float(amount)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{value:.1f}GB"


def metric_card(x: int, label: str, value: str, detail: str) -> str:
    return f"""<g transform="translate({x} 112)">
      <rect width="238" height="96" rx="8" fill="#0d0a13" stroke="#2d1b43"/>
      <path d="M0 9V0h9 M229 0h9v9 M238 87v9h-9 M9 96H0v-9" stroke="#8b5cf6" fill="none"/>
      <text x="18" y="27" class="label">{esc(label)}</text>
      <text x="18" y="61" class="value">{esc(value)}</text>
      <text x="18" y="82" class="detail">{esc(detail)}</text>
    </g>"""


def render(username: str, repositories: list[dict], totals: Counter, coded_repos: int) -> str:
    ranked = totals.most_common(6)
    total_bytes = sum(totals.values())
    dominant = ranked[0][0] if ranked else "AWAITING"
    updated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    cards = "".join(
        (
            metric_card(54, "PUBLIC ARCHIVES", str(len(repositories)), f"{coded_repos} contain code"),
            metric_card(306, "LANGUAGES FOUND", str(len(totals)), "GitHub Linguist index"),
            metric_card(558, "CODE INDEXED", human_bytes(total_bytes), "language-classified bytes"),
            metric_card(810, "DOMINANT SIGNAL", dominant.upper(), "highest byte frequency"),
        )
    )

    segments = []
    cursor = 54.0
    usable_width = 992.0
    for index, (language, amount) in enumerate(ranked):
        width = usable_width * amount / total_bytes if total_bytes else 0
        segments.append(
            f'<rect x="{cursor:.1f}" y="259" width="{max(width, 2):.1f}" height="22" '
            f'fill="{COLORS[index]}"><title>{esc(language)}: {amount / total_bytes * 100:.1f}%</title></rect>'
        )
        cursor += width

    rows = []
    for index, (language, amount) in enumerate(ranked):
        column = index % 2
        row = index // 2
        x = 54 + column * 505
        y = 326 + row * 42
        percentage = amount / total_bytes * 100 if total_bytes else 0
        rows.append(
            f'<g transform="translate({x} {y})">'
            f'<circle cx="6" cy="-4" r="5" fill="{COLORS[index]}" filter="url(#glow)"/>'
            f'<text x="22" class="lang">{esc(language)}</text>'
            f'<text x="310" text-anchor="end" class="pct">{percentage:.1f}%</text>'
            f'<rect x="326" y="-12" width="123" height="8" rx="4" fill="#171020"/>'
            f'<rect x="326" y="-12" width="{max(percentage * 1.23, 2):.1f}" height="8" rx="4" fill="{COLORS[index]}"/>'
            f'<text x="478" text-anchor="end" class="detail">{human_bytes(amount)}</text>'
            f'</g>'
        )

    if not ranked:
        rows.append('<text x="54" y="338" class="detail">waiting for the first public language signal...</text>')
    elif len(ranked) == 1:
        rows.append(
            '<g transform="translate(559 326)">'
            '<rect width="487" height="74" rx="7" fill="#0c0911" stroke="#24172f" stroke-dasharray="4 5"/>'
            '<text x="22" y="31" class="label">NEXT FREQUENCY</text>'
            '<text x="22" y="54" class="detail">waiting for another public language signal...</text>'
            '</g>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="470" viewBox="0 0 1100 470" role="img" aria-labelledby="title desc">
  <title id="title">Language Spectrum for {esc(username)}</title>
  <desc id="desc">Languages used across public, non-fork GitHub repositories, measured by bytes of code.</desc>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#07050a"/><stop offset="1" stop-color="#10091a"/></linearGradient>
    <filter id="glow"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M28 0H0V28" fill="none" stroke="#8b5cf6" stroke-opacity=".055"/></pattern>
    <style>
      text {{ font-family: Consolas, 'Courier New', monospace; }}
      .kicker {{ fill:#8b5cf6; font-size:12px; letter-spacing:3px; }}
      .title {{ fill:#eee8f7; font-size:30px; font-weight:700; letter-spacing:4px; }}
      .label {{ fill:#887a99; font-size:11px; letter-spacing:1.4px; }}
      .value {{ fill:#d8c5f4; font-size:27px; font-weight:700; }}
      .detail,.pct {{ fill:#776b85; font-size:11px; }}
      .lang {{ fill:#ded5e8; font-size:14px; font-weight:700; }}
      .blink {{ animation:blink 1.6s step-end infinite; }}
      @keyframes blink {{ 50% {{ opacity:.25 }} }}
    </style>
  </defs>
  <rect x="1" y="1" width="1098" height="468" rx="14" fill="url(#bg)" stroke="#342047" stroke-width="2"/>
  <rect x="1" y="1" width="1098" height="468" rx="14" fill="url(#grid)"/>
  <path d="M31 1H1v30 M1069 1h30v30 M1099 439v30h-30 M31 469H1v-30" stroke="#a76ff0" stroke-width="2" fill="none"/>
  <g transform="translate(54 36)">
    <circle cx="6" cy="5" r="4" fill="#b794f4" filter="url(#glow)" class="blink"/>
    <text x="22" y="9" class="kicker">SCAN / {esc(username.upper())}</text>
    <text y="49" class="title">LANGUAGE SPECTRUM</text>
    <text x="992" y="10" text-anchor="end" class="detail">UPDATED {updated}</text>
    <text x="992" y="48" text-anchor="end" class="kicker">PUBLIC REPOSITORIES // NO FORKS</text>
  </g>
  {cards}
  <text x="54" y="242" class="kicker">CODE DNA // BYTE DISTRIBUTION</text>
  <rect x="54" y="259" width="992" height="22" rx="6" fill="#171020"/>
  <clipPath id="bar"><rect x="54" y="259" width="992" height="22" rx="6"/></clipPath>
  <g clip-path="url(#bar)">{''.join(segments)}</g>
  {''.join(rows)}
  <path d="M54 433H1046" stroke="#291b39"/>
  <text x="54" y="453" class="detail">GitHub Linguist telemetry / generated automatically / public owned repositories</text>
  <text x="1046" y="453" text-anchor="end" class="kicker">NIGHTFALL SYSTEM</text>
</svg>
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="duartess7")
    parser.add_argument("--output", default="metrics/languages.svg")
    args = parser.parse_args()
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")

    repositories = public_repositories(args.username, token)
    totals, coded_repos = language_totals(repositories, token)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        render(args.username, repositories, totals, coded_repos), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
