"""
bracket_pdf.py — Convert bracket HTML to PDF using WeasyPrint.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def html_to_pdf(html_path: str, pdf_path: str | None = None) -> str:
    """Convert a bracket HTML file to PDF.

    Parameters
    ----------
    html_path:
        Path to the HTML file.
    pdf_path:
        Output PDF path.  Defaults to replacing ``.html`` with ``.pdf``.

    Returns
    -------
    str — path to the generated PDF file.
    """
    from weasyprint import HTML

    html_path = Path(html_path)
    if not html_path.exists():
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    if pdf_path is None:
        pdf_path = str(html_path).replace(".html", ".pdf")

    HTML(filename=str(html_path)).write_pdf(pdf_path)
    logger.info("bracket_pdf: generated %s", pdf_path)
    return pdf_path


def generate_summary_pdf(
    runs: list[dict],
    season: int,
    model_version: str,
    output_dir: str = "/app/bracket_output",
) -> str:
    """Generate a multi-run summary PDF with champion frequencies and picks.

    Parameters
    ----------
    runs:
        List of run result dicts, each with champion, picks, top_champions.
    season:
        Tournament year.
    model_version:
        Model version string.
    output_dir:
        Directory to write the PDF.

    Returns
    -------
    str — path to the generated PDF file.
    """
    from weasyprint import HTML
    from collections import Counter

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Aggregate champion picks across runs
    champion_counter = Counter()
    for run in runs:
        champ = run.get("champion", "")
        if champ:
            champion_counter[champ] += 1

    n_runs = len(runs)
    champion_rows = ""
    for team, count in champion_counter.most_common():
        pct = count / n_runs * 100
        champion_rows += f"""
        <tr>
          <td>{team}</td>
          <td>{count}/{n_runs}</td>
          <td>{pct:.0f}%</td>
        </tr>"""

    # Per-run summaries
    run_rows = ""
    for i, run in enumerate(runs, 1):
        champ = run.get("champion", "N/A")
        sims = run.get("n_simulations", 0)
        upsets = sum(1 for p in run.get("picks", []) if p.get("is_upset"))
        run_rows += f"""
        <tr>
          <td>Run {i}</td>
          <td>{champ}</td>
          <td>{sims:,}</td>
          <td>{upsets}</td>
        </tr>"""

    # Most frequent Final Four across runs
    ff_counter = Counter()
    for run in runs:
        for p in run.get("picks", []):
            if p.get("round") == 5:
                ff_counter[p["winner"]] += 1
    ff_rows = ""
    for team, count in ff_counter.most_common(8):
        pct = count / n_runs * 100
        ff_rows += f"""
        <tr>
          <td>{team}</td>
          <td>{count}/{n_runs}</td>
          <td>{pct:.0f}%</td>
        </tr>"""

    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
@page {{ size: letter; margin: 0.75in; }}
body {{ font-family: Helvetica, Arial, sans-serif; color: #1a1a2e; font-size: 11px; }}
h1 {{ font-size: 22px; color: #1a1a2e; margin-bottom: 4px; }}
h2 {{ font-size: 16px; color: #1565c0; margin-top: 24px; margin-bottom: 8px; }}
.meta {{ color: #666; font-size: 10px; margin-bottom: 16px; }}
table {{ width: 100%; border-collapse: collapse; margin-bottom: 16px; }}
th {{ background: #1a1a2e; color: white; padding: 6px 10px; text-align: left; font-size: 10px; text-transform: uppercase; }}
td {{ padding: 5px 10px; border-bottom: 1px solid #e0e0e0; font-size: 11px; }}
tr:nth-child(even) {{ background: #f8f8f8; }}
.highlight {{ background: #e8f5e9 !important; font-weight: 700; }}
.footer {{ text-align: center; color: #aaa; font-size: 9px; margin-top: 24px; padding-top: 8px; border-top: 1px solid #e0e0e0; }}
</style>
</head>
<body>
<h1>{season} NCAA Tournament — Bracket Simulation Report</h1>
<div class="meta">Model: {model_version} | Runs: {n_runs} | CoastCapital Sports Analytics</div>

<h2>Champion Predictions (across {n_runs} runs)</h2>
<table>
  <thead><tr><th>Team</th><th>Picked</th><th>Frequency</th></tr></thead>
  <tbody>{champion_rows}</tbody>
</table>

<h2>Final Four Appearances</h2>
<table>
  <thead><tr><th>Team</th><th>Appearances</th><th>Frequency</th></tr></thead>
  <tbody>{ff_rows}</tbody>
</table>

<h2>Individual Run Results</h2>
<table>
  <thead><tr><th>Run</th><th>Champion</th><th>Simulations</th><th>Upsets</th></tr></thead>
  <tbody>{run_rows}</tbody>
</table>

<div class="footer">CoastCapital Sports Analytics — {season} NCAA Tournament Bracket Simulation</div>
</body>
</html>"""

    pdf_path = str(output_dir / f"{season}_bracket_summary.pdf")
    HTML(string=html_content).write_pdf(pdf_path)
    logger.info("bracket_pdf: generated summary PDF %s (%d runs)", pdf_path, n_runs)
    return pdf_path
