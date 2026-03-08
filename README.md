# Poker Stats

A small pipeline + dashboard for tracking poker sessions from bank transaction CSV exports.

## What this project now includes

- Config-driven CSV generation (`config.json`)
- Input validation and a data-quality report (`data_quality_issues.csv`)
- Per-player session stats (`player_statistics_by_session.csv`)
- Per-session summary stats (`session_statistics_by_session.csv`)
- Enhanced Streamlit dashboard with:
  - global leaderboard with ROI and consistency metrics
  - session explorer page
  - player analytics (rolling average, volatility, streaks)
  - data-quality page
  - CSV download for filtered leaderboard

## Files

- `Poker CSV Generator.py`: data pipeline and report generator
- `app.py`: Streamlit dashboard
- `config.json`: pipeline settings
- `tests/test_generator.py`: pytest coverage for core logic

## Quick start

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Generate stats CSV files:

```bash
python "Poker CSV Generator.py"
```

4. Start dashboard:

```bash
streamlit run app.py
```

## Config

Edit `config.json` to change:

- input file path
- output file names
- account name
- host player
- player aliases
- balance mismatch tolerance

## Tests

Run:

```bash
pytest -q
```

## Cool feature ideas to add next

- Session notes and tags (`cash game`, `tournament`, `special event`)
- Buy-in tier analysis (`$5`, `$10`, `$20`) and performance per tier
- Head-to-head overlap stats (who performs best when specific players are present)
- Forecasting panel for expected player variance in next 5 sessions
- Auto-ingest latest bank CSV from a watched folder
