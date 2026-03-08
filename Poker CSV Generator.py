from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


DEFAULT_CONFIG: Dict[str, Any] = {
    "input_file": "9c5fcd56-6f00-4cbc-8cb2-e42af340a63b.csv",
    "player_output_file": "player_statistics_by_session.csv",
    "session_output_file": "session_statistics_by_session.csv",
    "quality_output_file": "data_quality_issues.csv",
    "account_name": "Adv Plus Banking - 1686",
    "host_player": "Meet",
    "always_include_host": True,
    "alias_map": {"Dharmik": "Danon", "Ananth": "Pro"},
    "required_columns": [
        "From",
        "To",
        "Amount",
        "Setup Date",
        "Effective Date",
        "Session Number",
    ],
    "round_digits": 2,
    "balance_tolerance": 0.01,
}


def load_config(config_path: str) -> Dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    path = Path(config_path)
    if not path.exists():
        return config

    with path.open("r", encoding="utf-8-sig") as file:
        loaded = json.load(file)
    if not isinstance(loaded, dict):
        raise ValueError("Config file must be a JSON object.")

    for key, value in loaded.items():
        if key == "alias_map" and isinstance(value, dict):
            merged_alias_map = dict(config.get("alias_map", {}))
            merged_alias_map.update(value)
            config["alias_map"] = merged_alias_map
        else:
            config[key] = value
    return config


def _normalize_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _coerce_dates(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, format="%m.%d.%Y", errors="coerce")
    fallback = pd.to_datetime(series, errors="coerce")
    return parsed.fillna(fallback)


def convert_date_to_words(date_value: Any) -> str:
    def get_day_suffix(day: int) -> str:
        if 11 <= day <= 13:
            return "th"
        return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")

    date_obj = None
    if isinstance(date_value, pd.Timestamp):
        date_obj = date_value.date()
    elif isinstance(date_value, dt.date):
        date_obj = date_value
    else:
        raw_text = _normalize_text(date_value)
        if raw_text:
            for fmt in ("%m.%d.%Y", "%Y-%m-%d", "%m/%d/%Y"):
                try:
                    date_obj = dt.datetime.strptime(raw_text, fmt).date()
                    break
                except ValueError:
                    continue

    if date_obj is None:
        return "Unknown"

    day_suffix = get_day_suffix(date_obj.day)
    month_name = date_obj.strftime("%b")
    return f"{date_obj.day}{day_suffix} {month_name} {date_obj.year}"


def parse_bank_statement(statement_file: str, required_columns: List[str]) -> pd.DataFrame:
    bank_data = pd.read_csv(statement_file)
    missing_columns = [column for column in required_columns if column not in bank_data.columns]
    if missing_columns:
        raise ValueError(
            f"Missing required column(s): {', '.join(missing_columns)} in '{statement_file}'."
        )

    bank_data = bank_data.copy()
    bank_data["From"] = bank_data["From"].map(_normalize_text)
    bank_data["To"] = bank_data["To"].map(_normalize_text)
    bank_data["Setup Date"] = bank_data["Setup Date"].map(_normalize_text)
    bank_data["Effective Date"] = bank_data["Effective Date"].map(_normalize_text)
    bank_data["Amount"] = pd.to_numeric(
        bank_data["Amount"].astype(str).str.replace(r"[^\d\.-]", "", regex=True),
        errors="coerce",
    )
    bank_data["Session Number"] = pd.to_numeric(bank_data["Session Number"], errors="coerce")
    bank_data["Setup Date Parsed"] = _coerce_dates(bank_data["Setup Date"])
    bank_data["Effective Date Parsed"] = _coerce_dates(bank_data["Effective Date"])
    return bank_data


def parse_updated_bank_statement(statement_file: str) -> pd.DataFrame:
    # Backward-compatible alias used in the previous version.
    return parse_bank_statement(statement_file, DEFAULT_CONFIG["required_columns"])


def collect_data_quality_issues(bank_data: pd.DataFrame) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []

    for index, row in bank_data.iterrows():
        sheet_row = int(index) + 2

        if pd.isna(row["Session Number"]):
            issues.append(
                {
                    "Issue Type": "Missing Session Number",
                    "Row": sheet_row,
                    "Details": "Session Number could not be parsed.",
                }
            )

        if pd.isna(row["Amount"]):
            issues.append(
                {
                    "Issue Type": "Invalid Amount",
                    "Row": sheet_row,
                    "Details": "Amount could not be parsed as numeric value.",
                }
            )
        elif row["Amount"] <= 0:
            issues.append(
                {
                    "Issue Type": "Non-Positive Amount",
                    "Row": sheet_row,
                    "Details": "Amount should be greater than zero.",
                }
            )

        if not row["From"] and not row["To"]:
            issues.append(
                {
                    "Issue Type": "Missing Parties",
                    "Row": sheet_row,
                    "Details": "Both From and To are empty.",
                }
            )

        if not pd.isna(row["Setup Date"]) and row["Setup Date"] and pd.isna(row["Setup Date Parsed"]):
            issues.append(
                {
                    "Issue Type": "Unparseable Setup Date",
                    "Row": sheet_row,
                    "Details": f"Could not parse Setup Date '{row['Setup Date']}'.",
                }
            )

    return issues


def _infer_player_and_transaction_type(row: pd.Series, account_name: str) -> tuple[str, bool]:
    from_party = _normalize_text(row["From"])
    to_party = _normalize_text(row["To"])

    is_buy_in = not to_party
    if is_buy_in:
        player = from_party
    elif from_party == account_name:
        player = to_party
    elif to_party == account_name:
        player = from_party
        is_buy_in = True
    else:
        # Fallback path for uncommon transfer structures.
        player = to_party

    return player, is_buy_in


def calculate_session_statistics(bank_data: pd.DataFrame, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    alias_map: Dict[str, str] = config.get("alias_map", {})
    account_name = str(config.get("account_name", "")).strip()
    host_player = str(config.get("host_player", "")).strip()
    always_include_host = bool(config.get("always_include_host", True))
    round_digits = int(config.get("round_digits", 2))

    session_results: List[Dict[str, Any]] = []
    grouped = (
        bank_data.sort_values(["Session Number", "Setup Date Parsed"], na_position="last")
        .groupby("Session Number", dropna=True)
    )

    for session_number, transactions in grouped:
        players: Dict[str, Dict[str, Any]] = {}
        total_buy_ins = 0.0
        total_payouts = 0.0

        parsed_dates = transactions["Setup Date Parsed"].dropna()
        setup_date = parsed_dates.iloc[0] if not parsed_dates.empty else None
        session_date_text = convert_date_to_words(setup_date)
        session_date_iso = setup_date.date().isoformat() if setup_date is not None else ""

        for _, row in transactions.iterrows():
            amount = row["Amount"]
            if pd.isna(amount) or amount <= 0:
                continue

            player_name, is_buy_in = _infer_player_and_transaction_type(row, account_name)
            if not player_name:
                continue
            player_name = alias_map.get(player_name, player_name)

            if player_name not in players:
                players[player_name] = {
                    "Player": player_name,
                    "BuyIn_Times": 0,
                    "BuyIns": 0.0,
                    "Payouts": 0.0,
                    "ProfitLoss": 0.0,
                    "ROI (%)": None,
                }

            if is_buy_in:
                players[player_name]["BuyIns"] += float(amount)
                players[player_name]["BuyIn_Times"] += 1
                total_buy_ins += float(amount)
            else:
                players[player_name]["Payouts"] += float(amount)
                total_payouts += float(amount)

        normalized_host = alias_map.get(host_player, host_player) if host_player else ""
        if normalized_host:
            if always_include_host and normalized_host not in players:
                players[normalized_host] = {
                    "Player": normalized_host,
                    "BuyIn_Times": 0,
                    "BuyIns": 0.0,
                    "Payouts": 0.0,
                    "ProfitLoss": 0.0,
                    "ROI (%)": None,
                }

            if normalized_host in players:
                non_host_payouts = sum(
                    stats["Payouts"] for name, stats in players.items() if name != normalized_host
                )
                host_payout = round(total_buy_ins - non_host_payouts, round_digits)
                players[normalized_host]["Payouts"] = host_payout
                total_payouts = non_host_payouts + host_payout

        for stats in players.values():
            stats["BuyIns"] = round(stats["BuyIns"], round_digits)
            stats["Payouts"] = round(stats["Payouts"], round_digits)
            stats["ProfitLoss"] = round(stats["Payouts"] - stats["BuyIns"], round_digits)
            if stats["BuyIns"] > 0:
                stats["ROI (%)"] = round((stats["ProfitLoss"] / stats["BuyIns"]) * 100, 2)

        session_results.append(
            {
                "Session Number": int(session_number),
                "Session Date": session_date_text,
                "Session Date ISO": session_date_iso,
                "Total BuyIns": round(total_buy_ins, round_digits),
                "Total Payouts": round(total_payouts, round_digits),
                "Balance Delta": round(total_payouts - total_buy_ins, round_digits),
                "Players": sorted(
                    players.values(),
                    key=lambda item: (item["ProfitLoss"], item["Player"]),
                    reverse=True,
                ),
            }
        )

    return session_results


def build_player_statistics_dataframe(session_statistics: List[Dict[str, Any]]) -> pd.DataFrame:
    flattened_results: List[Dict[str, Any]] = []
    for session in session_statistics:
        for player_stats in session["Players"]:
            flattened_results.append(
                {
                    "Session Number": session["Session Number"],
                    "Session Date": session["Session Date"],
                    "Session Date ISO": session["Session Date ISO"],
                    "Player": player_stats["Player"],
                    "BuyIn_Times": player_stats["BuyIn_Times"],
                    "BuyIns": player_stats["BuyIns"],
                    "Payouts": player_stats["Payouts"],
                    "ProfitLoss": player_stats["ProfitLoss"],
                    "ROI (%)": player_stats["ROI (%)"],
                }
            )

    if not flattened_results:
        return pd.DataFrame(
            columns=[
                "Session Number",
                "Session Date",
                "Session Date ISO",
                "Player",
                "BuyIn_Times",
                "BuyIns",
                "Payouts",
                "ProfitLoss",
                "ROI (%)",
            ]
        )

    result = pd.DataFrame(flattened_results)
    return result.sort_values(["Session Number", "ProfitLoss"], ascending=[True, False]).reset_index(
        drop=True
    )


def build_session_statistics_dataframe(session_statistics: List[Dict[str, Any]]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for session in session_statistics:
        players = session["Players"]
        biggest_winner = max(players, key=lambda item: item["ProfitLoss"]) if players else None
        biggest_loser = min(players, key=lambda item: item["ProfitLoss"]) if players else None
        player_count = len(players)
        avg_buy_in = round(session["Total BuyIns"] / player_count, 2) if player_count else 0.0

        rows.append(
            {
                "Session Number": session["Session Number"],
                "Session Date": session["Session Date"],
                "Session Date ISO": session["Session Date ISO"],
                "Players": player_count,
                "Total BuyIns": session["Total BuyIns"],
                "Total Payouts": session["Total Payouts"],
                "Balance Delta": session["Balance Delta"],
                "Average BuyIn per Player": avg_buy_in,
                "Biggest Winner": biggest_winner["Player"] if biggest_winner else "",
                "Biggest Winner Profit": biggest_winner["ProfitLoss"] if biggest_winner else 0.0,
                "Biggest Loser": biggest_loser["Player"] if biggest_loser else "",
                "Biggest Loser Loss": biggest_loser["ProfitLoss"] if biggest_loser else 0.0,
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "Session Number",
                "Session Date",
                "Session Date ISO",
                "Players",
                "Total BuyIns",
                "Total Payouts",
                "Balance Delta",
                "Average BuyIn per Player",
                "Biggest Winner",
                "Biggest Winner Profit",
                "Biggest Loser",
                "Biggest Loser Loss",
            ]
        )

    return pd.DataFrame(rows).sort_values("Session Number").reset_index(drop=True)


def append_session_balance_issues(
    issues: List[Dict[str, Any]], session_df: pd.DataFrame, tolerance: float
) -> None:
    if session_df.empty:
        return
    out_of_balance = session_df[session_df["Balance Delta"].abs() > tolerance]
    for _, row in out_of_balance.iterrows():
        issues.append(
            {
                "Issue Type": "Session Balance Mismatch",
                "Row": int(row["Session Number"]),
                "Details": (
                    f"Session {int(row['Session Number'])} has balance delta "
                    f"{row['Balance Delta']:.2f}."
                ),
            }
        )


def run_pipeline(config: Dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    required_columns = list(config.get("required_columns", DEFAULT_CONFIG["required_columns"]))
    bank_data = parse_bank_statement(config["input_file"], required_columns)
    issues = collect_data_quality_issues(bank_data)

    clean_data = bank_data.dropna(subset=["Session Number", "Amount"]).copy()
    clean_data = clean_data[clean_data["Amount"] > 0].copy()

    session_statistics = calculate_session_statistics(clean_data, config)
    player_df = build_player_statistics_dataframe(session_statistics)
    session_df = build_session_statistics_dataframe(session_statistics)

    append_session_balance_issues(
        issues,
        session_df,
        float(config.get("balance_tolerance", DEFAULT_CONFIG["balance_tolerance"])),
    )
    issue_df = pd.DataFrame(issues, columns=["Issue Type", "Row", "Details"])
    return player_df, session_df, issue_df


def save_outputs(
    player_df: pd.DataFrame,
    session_df: pd.DataFrame,
    quality_df: pd.DataFrame,
    config: Dict[str, Any],
) -> None:
    player_df.to_csv(config["player_output_file"], index=False)
    session_df.to_csv(config["session_output_file"], index=False)
    quality_df.to_csv(config["quality_output_file"], index=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate poker statistics CSV files.")
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to JSON config file. Defaults to config.json.",
    )
    parser.add_argument("--input", default=None, help="Optional override for input CSV path.")
    parser.add_argument(
        "--player-output", default=None, help="Optional override for player stats CSV output path."
    )
    parser.add_argument(
        "--session-output", default=None, help="Optional override for session stats CSV output path."
    )
    parser.add_argument(
        "--quality-output", default=None, help="Optional override for quality issues CSV output path."
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)

    if args.input:
        config["input_file"] = args.input
    if args.player_output:
        config["player_output_file"] = args.player_output
    if args.session_output:
        config["session_output_file"] = args.session_output
    if args.quality_output:
        config["quality_output_file"] = args.quality_output

    player_df, session_df, quality_df = run_pipeline(config)
    save_outputs(player_df, session_df, quality_df, config)

    print(f"Generated {len(player_df)} player-session rows.")
    print(f"Generated {len(session_df)} session rows.")
    print(f"Logged {len(quality_df)} data-quality issue(s).")
    print(f"Player stats: {config['player_output_file']}")
    print(f"Session stats: {config['session_output_file']}")
    print(f"Data quality report: {config['quality_output_file']}")


if __name__ == "__main__":
    main()
