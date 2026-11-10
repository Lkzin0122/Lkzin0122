"""Render the profile's contribution panel using Python's standard library.

Data schema: https://docs.github.com/en/graphql/reference/users#contributioncalendar
The workflow uses GITHUB_TOKEN. --input accepts a saved contributionCalendar.
"""

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape


COLORS = {
    "NONE": "#232427",
    "FIRST_QUARTILE": "#594033",
    "SECOND_QUARTILE": "#936044",
    "THIRD_QUARTILE": "#CE9066",
    "FOURTH_QUARTILE": "#F2C49F",
}
MONTHS = ("JAN", "FEV", "MAR", "ABR", "MAI", "JUN",
          "JUL", "AGO", "SET", "OUT", "NOV", "DEZ")
QUERY = """
query ProfileActivity($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks {
          contributionDays { date contributionCount contributionLevel }
        }
      }
    }
  }
}
"""


@dataclass(frozen=True)
class Day:
    date: date
    count: int
    level: str

    @property
    def row(self):
        return (self.date.weekday() + 1) % 7

    @property
    def sunday(self):
        return self.date - timedelta(days=self.row)


def fetch_calendar(username, token):
    """Fail on incomplete API responses, keeping the last good SVG intact."""
    if not token:
        raise ValueError("Defina GITHUB_TOKEN ou use --input com um calendário salvo.")
    request = Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": username}}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Lkzin0122-profile-activity",
        },
    )
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
            break
        except (HTTPError, URLError, TimeoutError) as error:
            retryable = not isinstance(error, HTTPError) or error.code in (
                429, 500, 502, 503, 504,
            )
            if not retryable or attempt == 2:
                raise RuntimeError("Não foi possível consultar a API do GitHub.") from None
            time.sleep(2 ** attempt)
    if payload.get("errors"):
        raise RuntimeError("O GitHub retornou erros na consulta de contribuições.")
    user = (payload.get("data") or {}).get("user")
    if not user:
        raise ValueError(f"Perfil não encontrado: {username}.")
    return user["contributionsCollection"]["contributionCalendar"]


def parse_calendar(calendar):
    days = []
    for week in calendar["weeks"]:
        for raw in week["contributionDays"]:
            count, level = raw["contributionCount"], raw["contributionLevel"]
            if type(count) is not int or count < 0 or level not in COLORS:
                raise ValueError("Contagem ou intensidade de contribuição inválida.")
            if (count == 0) != (level == "NONE"):
                raise ValueError("A intensidade não corresponde à contagem de contribuições.")
            days.append(Day(date.fromisoformat(raw["date"]), count, level))
    if not days:
        raise ValueError("O calendário está vazio.")
    days.sort(key=lambda day: day.date)
    for previous, current in zip(days, days[1:]):
        if current.date != previous.date + timedelta(days=1):
            raise ValueError("O calendário contém datas repetidas ou dias ausentes.")
    weeks = {}
    for day in days:
        weeks.setdefault(day.sunday, []).append(day)
    if len(weeks) > 54:
        raise ValueError("O painel aceita no máximo 54 semanas.")
    return list(weeks.values())


def metrics(weeks):
    days = [day for week in weeks for day in week]
    longest = streak = 0
    for day in days:
        streak = streak + 1 if day.count else 0
        longest = max(longest, streak)
    return sum(day.count for day in days), sum(day.count > 0 for day in days), longest


def format_date(value):
    return f"{value.day:02d} {MONTHS[value.month - 1]} {value.year}"


def render_svg(weeks, username):
    total, active, longest = metrics(weeks)
    first, last = weeks[0][0].date, weeks[-1][-1].date
    grid_x, grid_y, pitch, size = 84, 310, 21, 17
    grid_width = (len(weeks) - 1) * pitch + size
    cells, months = [], []
    last_month_column = -3
    for column, week in enumerate(weeks):
        for day in week:
            x, y = grid_x + column * pitch, grid_y + day.row * pitch
            noun = "contribuição" if day.count == 1 else "contribuições"
            label = f"{day.date:%d/%m/%Y}: {day.count} {noun}"
            cells.append(
                f'    <rect class="day" x="{x}" y="{y}" width="{size}" height="{size}" '
                f'rx="4" fill="{COLORS[day.level]}"><title>{label}</title></rect>'
            )
        month_day = next((day for day in week if day.date.day == 1), None)
        # Leave enough room between labels in partial first/last months.
        if (column == 0 or month_day) and column - last_month_column >= 3:
            month = (month_day or week[0]).date.month
            months.append(f'    <text x="{grid_x + column * pitch}" y="290">{MONTHS[month - 1]}</text>')
            last_month_column = column

    recent = [sum(day.count for day in week) for week in weeks[-12:]]
    highest = max(max(recent), 1)
    points = [
        (846 + index * 370 / max(len(recent) - 1, 1), 224 - count / highest * 52)
        for index, count in enumerate(recent)
    ]
    line = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in points)
    area = line + f" L{points[-1][0]:.1f},233 L846,233 Z"
    legend = "\n".join(
        f'    <rect x="{1032 + i * 22}" y="487" width="16" height="16" rx="4" fill="{color}"/>'
        for i, color in enumerate(COLORS.values())
    )
    name = escape(username)
    formatted_total = f"{total:,}".replace(",", ".")
    duration_unit = "dia" if longest == 1 else "dias"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="528" viewBox="0 0 1280 528" fill="none" role="img" aria-labelledby="title desc">
  <title id="title">Código em movimento — @{name}</title>
  <desc id="desc">De {format_date(first)} a {format_date(last)}: {total} contribuições, {active} dias ativos e maior sequência de {longest} {duration_unit}. Cada quadrado representa um dia; tons mais claros indicam mais contribuições. A linha mostra os totais das últimas 12 semanas, incluindo a semana atual.</desc>
  <defs>
    <linearGradient id="area" x1="0" y1="168" x2="0" y2="233" gradientUnits="userSpaceOnUse"><stop stop-color="#E9AD87" stop-opacity=".24"/><stop offset="1" stop-color="#E9AD87" stop-opacity="0"/></linearGradient>
    <linearGradient id="scan"><stop stop-color="#F2C49F" stop-opacity="0"/><stop offset=".8" stop-color="#F2C49F" stop-opacity=".10"/><stop offset="1" stop-color="#F2C49F" stop-opacity="0"/></linearGradient>
    <clipPath id="calendar"><rect x="{grid_x}" y="{grid_y}" width="{grid_width}" height="143" rx="4"/></clipPath>
  </defs>
  <style>
    text {{ font-family:'Segoe UI',Helvetica,Arial,sans-serif; }}
    .muted {{ fill:#9D978F; font-size:11px; letter-spacing:1.4px; }}
    .scan {{ animation:scan 12s ease-in-out infinite; }}
    .pulse {{ transform-box:fill-box; transform-origin:center; animation:pulse 4s ease-in-out infinite; }}
    @keyframes scan {{ 0% {{ transform:translateX(-90px); opacity:0 }} 8% {{ opacity:1 }} 78% {{ transform:translateX({grid_width}px); opacity:1 }} 86%,100% {{ transform:translateX({grid_width}px); opacity:0 }} }}
    @keyframes pulse {{ 0%,100% {{ opacity:.35; transform:scale(.8) }} 50% {{ opacity:1; transform:scale(1.25) }} }}
    @media (prefers-reduced-motion:reduce) {{ .scan {{ display:none }} .pulse {{ animation:none }} }}
  </style>
  <rect x=".5" y=".5" width="1279" height="527" rx="22" fill="#101113" stroke="#303033"/>
  <text x="48" y="45" fill="#DCA37E" font-size="11" letter-spacing="2.5">CONSISTÊNCIA EM CADA LINHA</text>
  <text x="46" y="93" fill="#F2EDE6" font-size="34" font-weight="600" letter-spacing="-.8">Ideias virando código<tspan fill="#E9AD87">.</tspan></text>
  <rect x="1055" y="35" width="177" height="29" rx="14.5" fill="#24201D" stroke="#48382D"/>
  <circle class="pulse" cx="1071" cy="50" r="3" fill="#E9AD87"/>
  <text x="1083" y="54" fill="#DDB394" font-size="10" letter-spacing="1">ATIVIDADE NO GITHUB</text>
  <text x="1232" y="94" text-anchor="end" class="muted">@{name}</text>
  <path d="M48 124H1232M48 253H1232" stroke="#2A2B2E"/>
  <path d="M263 155V226M490 155V226M762 155V226" stroke="#2A2B2E"/>
  <g fill="#F2EDE6" font-size="47" font-weight="600" letter-spacing="-2">
    <text x="46" y="199">{formatted_total}</text><text x="302" y="199">{active}</text><text x="530" y="199">{longest}<tspan fill="#8F867C" font-size="20" letter-spacing="0"> {duration_unit}</tspan></text>
  </g>
  <g class="muted"><text x="48" y="226">CONTRIBUIÇÕES NO PERÍODO</text><text x="304" y="226">DIAS ATIVOS</text><text x="532" y="226">MAIOR SEQUÊNCIA</text></g>
  <text x="846" y="155" class="muted">ÚLTIMAS 12 SEMANAS</text>
  <path d="M846 233H1216" stroke="#2A2B2E"/>
  <path d="{area}" fill="url(#area)"/>
  <path d="{line}" stroke="#E9AD87" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <circle class="pulse" cx="{points[-1][0]:.1f}" cy="{points[-1][1]:.1f}" r="4" fill="#F2C49F"/>
  <g class="muted" font-size="10">
{chr(10).join(months)}
    <text x="48" y="343">Seg</text><text x="48" y="385">Qua</text><text x="48" y="427">Sex</text>
  </g>
  <g>
{chr(10).join(cells)}
  </g>
  <g clip-path="url(#calendar)"><rect class="scan" x="84" y="310" width="82" height="143" fill="url(#scan)"/></g>
  <text x="48" y="499" class="muted" letter-spacing=".6">{format_date(first)} — {format_date(last)}</text>
  <text x="551" y="499" fill="#817B74" font-size="10" letter-spacing=".7">DADOS ATÉ {format_date(last)}</text>
  <text x="978" y="499" fill="#9D978F" font-size="11">Menos</text>
{legend}
  <text x="1152" y="499" fill="#9D978F" font-size="11">Mais</text>
</svg>
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", default="Lkzin0122")
    parser.add_argument("--output", type=Path, default=Path("assets/activity.svg"))
    parser.add_argument("--input", type=Path, help="JSON do objeto contributionCalendar, para gerar offline.")
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", args.user):
            raise ValueError("Nome de usuário do GitHub inválido.")
        if args.input:
            calendar = json.loads(args.input.read_text(encoding="utf-8"))
        else:
            calendar = fetch_calendar(args.user, os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN"))
        svg = render_svg(parse_calendar(calendar), args.user)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(svg, encoding="utf-8", newline="\n")
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
        print(f"Erro ao gerar painel: {error}", file=sys.stderr)
        return 1
    print(f"Painel atualizado: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
