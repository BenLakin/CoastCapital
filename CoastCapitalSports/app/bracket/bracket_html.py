"""
bracket_html.py — Generate a self-contained HTML bracket visualization.

Renders a complete NCAA tournament bracket as a single HTML file with
embedded CSS and JavaScript.  Shows predicted winners, probabilities,
seed info, and highlights upsets and contrarian picks.
"""

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

ROUND_LABELS = {
    1: "Round of 64",
    2: "Round of 32",
    3: "Sweet 16",
    4: "Elite 8",
    5: "Final Four",
    6: "Championship",
}


def generate_bracket_html(
    picks: list,
    simulation_results: dict,
    bracket_structure: dict,
    season: int,
    model_version: str,
    pool_size: int = 100,
    actual_winners: dict = None,
) -> str:
    """Generate a self-contained HTML bracket visualization.

    Parameters
    ----------
    picks:
        List of BracketPick objects from optimizer.optimize_bracket().
    simulation_results:
        Monte Carlo results with advancement_rates and champion_rates.
    bracket_structure:
        Bracket structure from bracket_data.
    season:
        Tournament season year.
    model_version:
        Model version string for display.
    pool_size:
        Pool size used in optimization.
    actual_winners:
        Optional dict of actual winners for backtesting comparison.

    Returns
    -------
    str — complete HTML document as a string.
    """
    # Serialize picks for JS
    picks_data = []
    for p in picks:
        d = p.to_dict() if hasattr(p, "to_dict") else {
            "round_number": p.round_number,
            "game_number": p.game_number,
            "region": p.region,
            "team_a": p.team_a,
            "team_b": p.team_b,
            "seed_a": p.seed_a,
            "seed_b": p.seed_b,
            "predicted_winner": p.predicted_winner,
            "win_probability": p.win_probability,
            "advancement_probability": p.advancement_probability,
            "is_upset": p.is_upset,
            "is_contrarian": p.is_contrarian,
            "pick_leverage": p.pick_leverage,
            "expected_points": p.expected_points,
        }
        picks_data.append(d)

    # Top 10 champions
    top_champions = sorted(
        simulation_results.get("champion_rates", {}).items(),
        key=lambda x: -x[1],
    )[:10]

    # Count upsets
    upset_count = sum(1 for p in picks_data if p.get("is_upset"))
    contrarian_count = sum(1 for p in picks_data if p.get("is_contrarian"))
    total_expected = sum(p.get("expected_points", 0) for p in picks_data)

    # Find champion
    champion = ""
    for p in picks_data:
        if p.get("round_number") == 6:
            winner = p.get("predicted_winner", "")
            champion = winner if isinstance(winner, str) else str(winner)
            break

    champion_prob = simulation_results.get("champion_rates", {}).get(champion, 0) * 100

    # Build region summaries
    region_names = bracket_structure.get("regions", [])
    regions_json = json.dumps(region_names)
    picks_json = json.dumps(picks_data)
    champions_json = json.dumps(top_champions)
    actuals_json = json.dumps(actual_winners or {})

    generated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{season} NCAA Tournament Bracket — CoastCapital</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; padding: 20px; }}
.header {{ text-align: center; margin-bottom: 24px; }}
.header h1 {{ font-size: 28px; color: #1a1a2e; }}
.header .meta {{ color: #666; font-size: 13px; margin-top: 4px; }}
.summary {{ display: flex; gap: 16px; justify-content: center; flex-wrap: wrap; margin-bottom: 24px; }}
.summary .card {{ background: white; border-radius: 8px; padding: 16px 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); text-align: center; min-width: 140px; }}
.summary .card .value {{ font-size: 24px; font-weight: 700; color: #1a1a2e; }}
.summary .card .label {{ font-size: 12px; color: #888; margin-top: 4px; text-transform: uppercase; }}
.bracket-container {{ overflow-x: auto; }}
.regions {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px; }}
.region {{ background: white; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
.region h2 {{ font-size: 18px; color: #1a1a2e; margin-bottom: 12px; border-bottom: 2px solid #e0e0e0; padding-bottom: 8px; }}
.matchup {{ display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; margin: 4px 0; border-radius: 4px; font-size: 13px; }}
.matchup.chalk {{ background: #e8f5e9; }}
.matchup.mild-upset {{ background: #fff3e0; }}
.matchup.major-upset {{ background: #ffebee; }}
.matchup.contrarian {{ border-left: 3px solid #1565c0; }}
.matchup .team {{ flex: 1; }}
.matchup .team.winner {{ font-weight: 700; }}
.matchup .seed {{ color: #888; font-size: 11px; margin-right: 6px; }}
.matchup .prob {{ color: #666; font-size: 11px; min-width: 40px; text-align: right; }}
.matchup .result {{ margin-left: 8px; font-size: 14px; }}
.round-header {{ font-size: 12px; font-weight: 600; color: #1565c0; margin: 12px 0 6px; text-transform: uppercase; }}
.final-four {{ background: white; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); text-align: center; }}
.final-four h2 {{ font-size: 20px; color: #1a1a2e; margin-bottom: 12px; }}
.champion-box {{ background: linear-gradient(135deg, #1a1a2e, #16213e); color: white; border-radius: 8px; padding: 20px; text-align: center; margin: 16px auto; max-width: 400px; }}
.champion-box .name {{ font-size: 24px; font-weight: 700; }}
.champion-box .detail {{ font-size: 13px; opacity: 0.8; margin-top: 4px; }}
.top-champions {{ background: white; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-top: 24px; }}
.top-champions h3 {{ margin-bottom: 12px; }}
.champ-row {{ display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid #f0f0f0; font-size: 13px; }}
.champ-row .bar {{ height: 16px; background: #1565c0; border-radius: 2px; min-width: 2px; }}
.footer {{ text-align: center; color: #aaa; font-size: 11px; margin-top: 24px; }}
</style>
</head>
<body>
<div class="header">
  <h1>{season} NCAA Tournament Bracket</h1>
  <div class="meta">Model: {model_version} | Pool size: {pool_size} | Generated: {generated_at}</div>
</div>

<div class="summary">
  <div class="card"><div class="value">{champion}</div><div class="label">Champion Pick</div></div>
  <div class="card"><div class="value">{total_expected:.0f}</div><div class="label">Expected Score</div></div>
  <div class="card"><div class="value">{upset_count}</div><div class="label">Upsets Picked</div></div>
  <div class="card"><div class="value">{contrarian_count}</div><div class="label">Contrarian Picks</div></div>
  <div class="card"><div class="value">{simulation_results.get('simulation_count', 0):,}</div><div class="label">Simulations</div></div>
</div>

<div class="bracket-container">
<div class="regions" id="regions"></div>
<div class="final-four" id="final-four"></div>
</div>

<div class="champion-box">
  <div class="name">{champion}</div>
  <div class="detail">Championship probability: {champion_prob:.1f}%</div>
</div>

<div class="top-champions">
  <h3>Top Championship Contenders</h3>
  <div id="champ-table"></div>
</div>

<div class="footer">
  CoastCapitalAnalytics | {season} NCAA Tournament Bracket Simulation
</div>

<script>
const picks = {picks_json};
const regions = {regions_json};
const topChampions = {champions_json};
const actuals = {actuals_json};

function renderRegions() {{
  const container = document.getElementById('regions');
  regions.forEach(region => {{
    const regionPicks = picks.filter(p => p.region === region);
    let html = '<div class="region"><h2>' + region + '</h2>';

    const rounds = [1, 2, 3, 4];
    rounds.forEach(r => {{
      const roundPicks = regionPicks.filter(p => p.round_number === r);
      if (roundPicks.length === 0) return;
      const roundLabels = {{1: 'Round of 64', 2: 'Round of 32', 3: 'Sweet 16', 4: 'Elite 8'}};
      html += '<div class="round-header">' + (roundLabels[r] || 'Round ' + r) + '</div>';
      roundPicks.forEach(p => {{
        let cls = 'matchup';
        if (p.is_contrarian) cls += ' contrarian';
        if (p.is_upset) {{
          const seedDiff = Math.abs(p.seed_a - p.seed_b);
          cls += seedDiff >= 5 ? ' major-upset' : ' mild-upset';
        }} else {{
          cls += ' chalk';
        }}
        const winnerIsA = p.predicted_winner === p.team_a;
        const aClass = winnerIsA ? 'team winner' : 'team';
        const bClass = !winnerIsA ? 'team winner' : 'team';
        const prob = (p.win_probability * 100).toFixed(1);

        let resultMark = '';
        const key = p.round_number + '_' + p.game_number;
        if (actuals[key]) {{
          resultMark = actuals[key] === p.predicted_winner ? ' <span class="result">&#10003;</span>' : ' <span class="result" style="color:red">&#10007;</span>';
        }}

        html += '<div class="' + cls + '">';
        html += '<span class="seed">(' + p.seed_a + ')</span><span class="' + aClass + '">' + p.team_a + '</span>';
        html += ' vs ';
        html += '<span class="seed">(' + p.seed_b + ')</span><span class="' + bClass + '">' + p.team_b + '</span>';
        html += '<span class="prob">' + prob + '%' + resultMark + '</span>';
        html += '</div>';
      }});
    }});
    html += '</div>';
    container.innerHTML += html;
  }});
}}

function renderFinalFour() {{
  const container = document.getElementById('final-four');
  const ffPicks = picks.filter(p => p.round_number >= 5);
  if (ffPicks.length === 0) return;
  let html = '<h2>Final Four & Championship</h2>';
  ffPicks.forEach(p => {{
    let cls = 'matchup';
    if (p.is_upset) cls += ' mild-upset';
    else cls += ' chalk';
    if (p.is_contrarian) cls += ' contrarian';
    const prob = (p.win_probability * 100).toFixed(1);
    const roundLabel = p.round_number === 6 ? 'Championship' : 'Final Four';
    html += '<div class="round-header">' + roundLabel + '</div>';
    html += '<div class="' + cls + '">';
    if (p.team_b) {{
      html += '<span class="seed">(' + p.seed_a + ')</span><span class="team winner">' + p.predicted_winner + '</span>';
      html += ' vs ';
      const other = p.predicted_winner === p.team_a ? p.team_b : p.team_a;
      const otherSeed = p.predicted_winner === p.team_a ? p.seed_b : p.seed_a;
      html += '<span class="seed">(' + otherSeed + ')</span><span class="team">' + other + '</span>';
    }} else {{
      html += '<span class="seed">(' + p.seed_a + ')</span><span class="team winner">' + p.predicted_winner + '</span>';
    }}
    html += '<span class="prob">' + prob + '%</span>';
    html += '</div>';
  }});
  container.innerHTML = html;
}}

function renderChampions() {{
  const container = document.getElementById('champ-table');
  const maxRate = topChampions.length > 0 ? topChampions[0][1] : 1;
  topChampions.forEach(([team, rate]) => {{
    const pct = (rate * 100).toFixed(1);
    const barWidth = Math.max(2, (rate / maxRate) * 200);
    container.innerHTML += '<div class="champ-row"><span>' + team + '</span><span><span class="bar" style="width:' + barWidth + 'px;display:inline-block"></span> ' + pct + '%</span></div>';
  }});
}}

renderRegions();
renderFinalFour();
renderChampions();
</script>
</body>
</html>"""

    return html


def save_bracket_html(html: str, filepath: str):
    """Write the HTML string to a file."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("save_bracket_html: wrote %d bytes to %s", len(html), filepath)
