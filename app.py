
from __future__ import annotations

from itertools import combinations
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


PLAYER_STATS_PATH = Path("player_statistics_by_session.csv")
SESSION_STATS_PATH = Path("session_statistics_by_session.csv")
QUALITY_REPORT_PATH = Path("data_quality_issues.csv")

MONEY_FORMAT = {
    "BuyIns": "${:,.2f}",
    "Payouts": "${:,.2f}",
    "ProfitLoss": "${:,.2f}",
    "Profit StdDev": "${:,.2f}",
    "Profit Variance": "${:,.2f}",
    "Median Profit": "${:,.2f}",
    "Avg Profit/Session": "${:,.2f}",
    "ROI (%)": "{:,.2f}%",
    "Consistency Score": "{:,.3f}",
}


st.set_page_config(page_title="Poker Stats Dashboard", page_icon="cards", layout="wide")


def _to_numeric(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for column in columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def _parse_session_date(df: pd.DataFrame) -> pd.DataFrame:
    if "Session Date ISO" in df.columns:
        parsed = pd.to_datetime(df["Session Date ISO"], errors="coerce")
        if parsed.isna().all() and "Session Date" in df.columns:
            cleaned = (
                df["Session Date"]
                .astype(str)
                .str.replace(r"(\d{1,2})(st|nd|rd|th)", r"\1", regex=True)
            )
            parsed = pd.to_datetime(cleaned, errors="coerce")
    elif "Session Date" in df.columns:
        cleaned = (
            df["Session Date"]
            .astype(str)
            .str.replace(r"(\d{1,2})(st|nd|rd|th)", r"\1", regex=True)
        )
        parsed = pd.to_datetime(cleaned, errors="coerce")
    else:
        parsed = pd.NaT

    df["SessionDateParsed"] = parsed
    return df


@st.cache_data
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    players = pd.read_csv(PLAYER_STATS_PATH) if PLAYER_STATS_PATH.exists() else pd.DataFrame()
    sessions = pd.read_csv(SESSION_STATS_PATH) if SESSION_STATS_PATH.exists() else pd.DataFrame()
    quality = pd.read_csv(QUALITY_REPORT_PATH) if QUALITY_REPORT_PATH.exists() else pd.DataFrame()

    if not players.empty:
        players = _to_numeric(players, ["Session Number", "BuyIn_Times", "BuyIns", "Payouts", "ProfitLoss", "ROI (%)"])
        if "ROI (%)" not in players.columns:
            players["ROI (%)"] = players.apply(
                lambda row: round((row["ProfitLoss"] / row["BuyIns"]) * 100, 2)
                if row["BuyIns"] > 0
                else 0.0,
                axis=1,
            )
        players = _parse_session_date(players)

    if not sessions.empty:
        sessions = _to_numeric(
            sessions,
            [
                "Session Number",
                "Players",
                "Total BuyIns",
                "Total Payouts",
                "Balance Delta",
                "Average BuyIn per Player",
                "Biggest Winner Profit",
                "Biggest Loser Loss",
            ],
        )
        sessions = _parse_session_date(sessions)

    return players, sessions, quality


def build_leaderboard(data: pd.DataFrame) -> pd.DataFrame:
    leaderboard = (
        data.groupby("Player", as_index=False)
        .agg(
            {
                "Session Number": "nunique",
                "BuyIns": "sum",
                "Payouts": "sum",
                "ProfitLoss": "sum",
            }
        )
        .rename(columns={"Session Number": "Sessions Played"})
    )

    per_player_std = data.groupby("Player")["ProfitLoss"].std().rename("Profit StdDev")
    per_player_variance = data.groupby("Player")["ProfitLoss"].var().rename("Profit Variance")
    per_player_median = data.groupby("Player")["ProfitLoss"].median().rename("Median Profit")
    per_player_avg = data.groupby("Player")["ProfitLoss"].mean().rename("Avg Profit/Session")

    leaderboard = leaderboard.merge(per_player_std, left_on="Player", right_index=True, how="left")
    leaderboard = leaderboard.merge(per_player_variance, left_on="Player", right_index=True, how="left")
    leaderboard = leaderboard.merge(per_player_median, left_on="Player", right_index=True, how="left")
    leaderboard = leaderboard.merge(per_player_avg, left_on="Player", right_index=True, how="left")

    leaderboard["Profit StdDev"] = leaderboard["Profit StdDev"].fillna(0.0)
    leaderboard["Profit Variance"] = leaderboard["Profit Variance"].fillna(0.0)
    leaderboard["ROI (%)"] = leaderboard.apply(
        lambda row: round((row["ProfitLoss"] / row["BuyIns"]) * 100, 2) if row["BuyIns"] > 0 else 0.0,
        axis=1,
    )
    leaderboard["Consistency Score"] = leaderboard.apply(
        lambda row: round(row["Avg Profit/Session"] / row["Profit StdDev"], 3)
        if row["Profit StdDev"] > 0
        else 0.0,
        axis=1,
    )

    return leaderboard.sort_values("ProfitLoss", ascending=False).reset_index(drop=True)


def build_session_view(filtered_data: pd.DataFrame, filtered_sessions: pd.DataFrame) -> pd.DataFrame:
    if not filtered_sessions.empty:
        return filtered_sessions.sort_values("Session Number").copy()

    reconstructed = (
        filtered_data.groupby("Session Number", as_index=False)
        .agg(
            {
                "Session Date": "first",
                "SessionDateParsed": "first",
                "BuyIns": "sum",
                "Payouts": "sum",
                "Player": "nunique",
            }
        )
        .rename(columns={"BuyIns": "Total BuyIns", "Payouts": "Total Payouts", "Player": "Players"})
    )
    reconstructed["Balance Delta"] = reconstructed["Total Payouts"] - reconstructed["Total BuyIns"]
    return reconstructed.sort_values("Session Number").reset_index(drop=True)


def compute_table_chemistry(filtered_data: pd.DataFrame, regular_names: set[str]) -> pd.DataFrame:
    rows: list[dict] = []
    for _, group in filtered_data.groupby("Session Number"):
        regular_group = group[group["Player"].isin(regular_names)].copy()
        player_profit = regular_group.groupby("Player")["ProfitLoss"].sum().to_dict()
        players = sorted(player_profit.keys())
        if len(players) < 3:
            continue

        for combo in combinations(players, 3):
            profits = [player_profit[name] for name in combo]
            rows.append(
                {
                    "Combo": " + ".join(combo),
                    "Sessions": 1,
                    "Net Combo P/L": float(sum(profits)),
                    "Profit Spread": float(max(profits) - min(profits)),
                }
            )

    if not rows:
        return pd.DataFrame(columns=["Combo", "Sessions", "Net Combo P/L", "Avg Profit Spread"])

    chemistry = pd.DataFrame(rows).groupby("Combo", as_index=False).agg(
        {
            "Sessions": "sum",
            "Net Combo P/L": "sum",
            "Profit Spread": "mean",
        }
    )
    chemistry = chemistry.rename(columns={"Profit Spread": "Avg Profit Spread"})
    return chemistry.sort_values("Avg Profit Spread", ascending=False).reset_index(drop=True)


def compute_chaos_sessions(filtered_data: pd.DataFrame, regular_names: set[str]) -> pd.DataFrame:
    rows: list[dict] = []
    for session_number, group in filtered_data.groupby("Session Number"):
        regular_group = group[group["Player"].isin(regular_names)]
        if regular_group["Player"].nunique() < 3:
            continue

        profits = regular_group.groupby("Player")["ProfitLoss"].sum()
        rows.append(
            {
                "Session Number": int(session_number),
                "Players": int(profits.shape[0]),
                "Profit StdDev": float(profits.std(ddof=0)),
                "Profit Range": float(profits.max() - profits.min()),
            }
        )

    if not rows:
        return pd.DataFrame(columns=["Session Number", "Players", "Profit StdDev", "Profit Range"])

    return pd.DataFrame(rows).sort_values("Profit StdDev", ascending=False).reset_index(drop=True)


def compute_friendship_gaps(filtered_data: pd.DataFrame, regular_names: set[str]) -> pd.DataFrame:
    pair_map: dict[tuple[str, str], dict[str, float]] = {}

    for _, group in filtered_data.groupby("Session Number"):
        regular_group = group[group["Player"].isin(regular_names)]
        profits = regular_group.groupby("Player")["ProfitLoss"].sum().to_dict()
        players = sorted(profits.keys())
        if len(players) < 2:
            continue

        for a, b in combinations(players, 2):
            key = (a, b)
            if key not in pair_map:
                pair_map[key] = {"Sessions": 0.0, "Net Gap": 0.0}
            pair_map[key]["Sessions"] += 1
            pair_map[key]["Net Gap"] += float(profits[a] - profits[b])

    rows = []
    for (a, b), values in pair_map.items():
        net_gap = values["Net Gap"]
        rows.append(
            {
                "Pair": f"{a} vs {b}",
                "Sessions": int(values["Sessions"]),
                "Net Gap": round(net_gap, 2),
                "Absolute Gap": round(abs(net_gap), 2),
                "Edge": a if net_gap >= 0 else b,
            }
        )

    if not rows:
        return pd.DataFrame(columns=["Pair", "Sessions", "Net Gap", "Absolute Gap", "Edge"])

    return pd.DataFrame(rows).sort_values("Absolute Gap", ascending=False).reset_index(drop=True)


def compute_whale_alert(regulars: pd.DataFrame) -> pd.DataFrame:
    if regulars.empty:
        return regulars

    threshold = float(regulars["BuyIns"].quantile(0.75))
    whales = regulars[(regulars["BuyIns"] >= threshold) & (regulars["ROI (%)"] < 0)].copy()
    return whales.sort_values("BuyIns", ascending=False).reset_index(drop=True)


def compute_regular_momentum(regular_data: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    if regular_data.empty:
        return pd.DataFrame(columns=["Player", "Recent P/L", "Trend"])

    rows: list[dict] = []
    for player, group in regular_data.groupby("Player"):
        recent = group.sort_values("Session Number").tail(window)["ProfitLoss"]
        recent_pl = float(recent.sum())
        if recent_pl > 0:
            trend = "Heating Up"
        elif recent_pl < 0:
            trend = "Cooling Off"
        else:
            trend = "Flat"
        rows.append({"Player": player, "Recent P/L": recent_pl, "Trend": trend})

    return pd.DataFrame(rows).sort_values("Recent P/L", ascending=False).reset_index(drop=True)


def compute_regular_archetypes(regulars: pd.DataFrame) -> pd.DataFrame:
    if regulars.empty:
        return pd.DataFrame(columns=["Player", "Archetype", "Reason"])

    roi_median = float(regulars["ROI (%)"].median())
    vol_median = float(regulars["Profit StdDev"].median())

    rows: list[dict] = []
    for _, row in regulars.iterrows():
        roi = float(row["ROI (%)"])
        vol = float(row["Profit StdDev"])
        player = str(row["Player"])

        if roi >= roi_median and vol <= vol_median:
            archetype = "Sniper"
            reason = "Good ROI with controlled volatility"
        elif roi >= roi_median and vol > vol_median:
            archetype = "Gambit Master"
            reason = "High upside with high swings"
        elif roi < roi_median and vol <= vol_median:
            archetype = "Grinder"
            reason = "Stable profile, edge still developing"
        else:
            archetype = "Swing Chaser"
            reason = "High variance and negative ROI currently"

        rows.append({"Player": player, "Archetype": archetype, "Reason": reason})

    return pd.DataFrame(rows).sort_values("Player").reset_index(drop=True)


def compute_head_to_head_rivalries(regular_data: pd.DataFrame, min_shared_sessions: int = 3) -> pd.DataFrame:
    rows: list[dict] = []
    session_groups = regular_data.groupby("Session Number")

    pair_stats: dict[tuple[str, str], dict[str, int]] = {}
    for _, group in session_groups:
        profits = group.groupby("Player")["ProfitLoss"].sum().to_dict()
        players = sorted(profits.keys())
        for a, b in combinations(players, 2):
            key = (a, b)
            if key not in pair_stats:
                pair_stats[key] = {"Sessions": 0, "A_Wins": 0, "B_Wins": 0, "Ties": 0}
            pair_stats[key]["Sessions"] += 1
            if profits[a] > profits[b]:
                pair_stats[key]["A_Wins"] += 1
            elif profits[b] > profits[a]:
                pair_stats[key]["B_Wins"] += 1
            else:
                pair_stats[key]["Ties"] += 1

    for (a, b), stats in pair_stats.items():
        if stats["Sessions"] < min_shared_sessions:
            continue
        if stats["A_Wins"] >= stats["B_Wins"]:
            edge_player = a
            edge_wins = stats["A_Wins"]
        else:
            edge_player = b
            edge_wins = stats["B_Wins"]
        edge_rate = round((edge_wins / stats["Sessions"]) * 100, 2)
        rows.append(
            {
                "Rivalry": f"{a} vs {b}",
                "Shared Sessions": stats["Sessions"],
                "Edge": edge_player,
                "Edge Win Rate (%)": edge_rate,
                "Ties": stats["Ties"],
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=["Rivalry", "Shared Sessions", "Edge", "Edge Win Rate (%)", "Ties"]
        )
    return pd.DataFrame(rows).sort_values("Edge Win Rate (%)", ascending=False).reset_index(drop=True)


def compute_max_drawdown(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    cumulative = series.cumsum()
    running_max = cumulative.cummax()
    drawdown = cumulative - running_max
    return float(drawdown.min())


def compute_player_drawdown_table(regular_data: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for player, group in regular_data.groupby("Player"):
        ordered = group.sort_values("Session Number")["ProfitLoss"]
        rows.append(
            {
                "Player": player,
                "Max Drawdown": compute_max_drawdown(ordered),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["Player", "Max Drawdown"])
    return pd.DataFrame(rows).sort_values("Max Drawdown").reset_index(drop=True)

def compute_robin_hood_sessions(filtered_data: pd.DataFrame, regular_names: set[str]) -> pd.DataFrame:
    rows: list[dict] = []
    for session_number, group in filtered_data.groupby("Session Number"):
        regular_group = group[group["Player"].isin(regular_names)]
        profits = regular_group.groupby("Player")["ProfitLoss"].sum()
        if profits.shape[0] < 3:
            continue

        top_winner_profit = float(profits.max())
        top_winner_name = str(profits.idxmax())
        losses = profits[profits < 0].abs()
        if losses.shape[0] < 2 or top_winner_profit <= 0:
            continue

        loss_std = float(losses.std(ddof=0)) if losses.shape[0] > 1 else 0.0
        evenness = 1 / (1 + loss_std)
        score = float(losses.shape[0] * evenness)

        rows.append(
            {
                "Session Number": int(session_number),
                "Top Winner": top_winner_name,
                "Top Winner Profit": top_winner_profit,
                "Losing Players": int(losses.shape[0]),
                "Robin Hood Score": round(score, 4),
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "Session Number",
                "Top Winner",
                "Top Winner Profit",
                "Losing Players",
                "Robin Hood Score",
            ]
        )

    return pd.DataFrame(rows).sort_values("Robin Hood Score", ascending=False).reset_index(drop=True)


def build_regular_meme_board(regulars: pd.DataFrame, filtered_data: pd.DataFrame) -> list[tuple[str, str, str]]:
    if regulars.empty:
        return []

    regular_pool = filtered_data[filtered_data["Player"].isin(regulars["Player"])].copy()
    rebuy_series = (
        regular_pool.groupby("Player")["BuyIn_Times"].sum()
    )
    win_rate_series = (
        regular_pool
        .assign(Win=regular_pool["ProfitLoss"] > 0)
        .groupby("Player")["Win"]
        .mean()
        .mul(100)
    )
    silent_pool = regulars[regulars["Sessions Played"] >= 3]
    if silent_pool.empty:
        silent_pool = regulars

    comeback_scores: dict[str, float] = {}
    for player, group in regular_pool.groupby("Player"):
        score, sample = compute_comeback_score(group)
        if sample > 0:
            comeback_scores[player] = score

    drawdown_scores: dict[str, float] = {}
    for player, group in regular_pool.groupby("Player"):
        drawdown_scores[player] = compute_max_drawdown(group.sort_values("Session Number")["ProfitLoss"])

    bank_of_night = regulars.loc[regulars["ProfitLoss"].idxmax()]
    swing_king = regulars.loc[regulars["Profit StdDev"].idxmax()]
    roi_sniper = regulars.loc[regulars["ROI (%)"].idxmax()]
    iron_grinder = regulars.loc[regulars["Sessions Played"].idxmax()]
    silent_assassin = silent_pool.loc[silent_pool["Avg Profit/Session"].idxmax()]
    rebuy_king_name = str(rebuy_series.idxmax()) if not rebuy_series.empty else str(bank_of_night["Player"])
    rebuy_king_count = int(rebuy_series.max()) if not rebuy_series.empty else 0
    win_rate_wizard_name = str(win_rate_series.idxmax()) if not win_rate_series.empty else str(bank_of_night["Player"])
    win_rate_wizard = float(win_rate_series.max()) if not win_rate_series.empty else 0.0
    comeback_kid_name = max(comeback_scores, key=comeback_scores.get) if comeback_scores else str(bank_of_night["Player"])
    comeback_kid_score = float(comeback_scores.get(comeback_kid_name, 0.0))
    abyss_survivor_name = min(drawdown_scores, key=drawdown_scores.get) if drawdown_scores else str(bank_of_night["Player"])
    abyss_survivor_dd = float(drawdown_scores.get(abyss_survivor_name, 0.0))

    return [
        ("Bank Of The Night", str(bank_of_night["Player"]), f"Total profit ${bank_of_night['ProfitLoss']:,.2f}"),
        ("Rebuy King", rebuy_king_name, f"{rebuy_king_count} buy-ins fired"),
        (
            "Silent Assassin",
            str(silent_assassin["Player"]),
            f"Avg/session ${silent_assassin['Avg Profit/Session']:,.2f}",
        ),
        (
            "Swing King",
            str(swing_king["Player"]),
            f"Volatility ${swing_king['Profit StdDev']:,.2f}",
        ),
        ("ROI Sniper", str(roi_sniper["Player"]), f"ROI {roi_sniper['ROI (%)']:.2f}%"),
        ("Iron Grinder", str(iron_grinder["Player"]), f"{int(iron_grinder['Sessions Played'])} sessions"),
        ("Win Rate Wizard", win_rate_wizard_name, f"Win rate {win_rate_wizard:.2f}%"),
        ("Comeback Kid", comeback_kid_name, f"Recovery score ${comeback_kid_score:,.2f}"),
        ("Abyss Survivor", abyss_survivor_name, f"Max drawdown ${abyss_survivor_dd:,.2f}"),
    ]


def render_one_timer_fun_features(one_timers: pd.DataFrame) -> None:
    st.subheader("One-Timer Fun Corner")
    if one_timers.empty:
        st.info("No one-time players for current filters.")
        return

    best_debut = one_timers.loc[one_timers["ProfitLoss"].idxmax()]
    tough_night = one_timers.loc[one_timers["ProfitLoss"].idxmin()]
    efficiency = one_timers.loc[one_timers["ROI (%)"].idxmax()]

    col1, col2, col3 = st.columns(3)
    col1.metric("One-Night Legend", str(best_debut["Player"]), f"${best_debut['ProfitLoss']:,.2f}")
    col2.metric("Ouch Of The Night", str(tough_night["Player"]), f"${tough_night['ProfitLoss']:,.2f}")
    col3.metric("Hit-And-Run ROI", str(efficiency["Player"]), f"{efficiency['ROI (%)']:.2f}%")


def render_global_stats(filtered_data: pd.DataFrame, filtered_sessions: pd.DataFrame, min_sessions: int, top_n: int) -> None:
    st.title("Global Poker Statistics")

    leaderboard = build_leaderboard(filtered_data)
    regular_min_sessions = max(2, int(min_sessions))
    regulars = leaderboard[leaderboard["Sessions Played"] >= regular_min_sessions].copy()
    one_timers = leaderboard[leaderboard["Sessions Played"] == 1].copy()

    total_sessions = int(filtered_data["Session Number"].nunique())
    total_buyins = float(filtered_data["BuyIns"].sum())
    total_profit = float(filtered_data["ProfitLoss"].sum())

    session_view = build_session_view(filtered_data, filtered_sessions)
    biggest_pot = float(session_view["Total BuyIns"].max()) if not session_view.empty else 0.0
    avg_table_size = float(session_view["Players"].mean()) if not session_view.empty else 0.0

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Sessions", total_sessions)
    col2.metric("Regulars", int(regulars["Player"].nunique()))
    col3.metric("One-Timers", int(one_timers["Player"].nunique()))
    col4.metric("Total Buy-Ins", f"${total_buyins:,.2f}")
    col5.metric("Net P/L", f"${total_profit:,.2f}")
    st.caption(f"Largest pot: ${biggest_pot:,.2f} | Average table size: {avg_table_size:.2f} players")

    st.subheader("Regular Players Leaderboard")
    if regulars.empty:
        st.info("No regular players match the current filters.")
    else:
        st.dataframe(regulars.style.format(MONEY_FORMAT), use_container_width=True)

    st.subheader("One-Time Players Leaderboard")
    if one_timers.empty:
        st.info("No one-time players match the current filters.")
    else:
        st.dataframe(one_timers.style.format(MONEY_FORMAT), use_container_width=True)

    export_col1, export_col2 = st.columns(2)
    with export_col1:
        st.download_button(
            "Download Regulars Leaderboard CSV",
            data=regulars.to_csv(index=False).encode("utf-8"),
            file_name="regular_players_leaderboard.csv",
            mime="text/csv",
            disabled=regulars.empty,
        )
    with export_col2:
        st.download_button(
            "Download One-Timers Leaderboard CSV",
            data=one_timers.to_csv(index=False).encode("utf-8"),
            file_name="one_time_players_leaderboard.csv",
            mime="text/csv",
            disabled=one_timers.empty,
        )

    st.subheader("One-Timer Charts")
    one_col1, one_col2 = st.columns(2)
    with one_col1:
        if one_timers.empty:
            st.info("No one-time player chart data.")
        else:
            chart = px.bar(
                one_timers,
                x="Player",
                y="ProfitLoss",
                color="ProfitLoss",
                text_auto=True,
                title="Profit/Loss - One-Time Players",
                template="plotly_white",
            )
            st.plotly_chart(chart, use_container_width=True)

    with one_col2:
        if one_timers.empty:
            st.info("No one-time player chart data.")
        else:
            chart = px.pie(
                one_timers,
                names="Player",
                values="BuyIns",
                title="Buy-In Contributions - One-Time Players",
                template="plotly_white",
            )
            st.plotly_chart(chart, use_container_width=True)

    if not one_timers.empty:
        st.subheader("One-Timer Outcome Split")
        one_timer_outcomes = pd.DataFrame(
            {
                "Outcome": ["Winning Debuts", "Losing Debuts", "Break-Even Debuts"],
                "Count": [
                    int((one_timers["ProfitLoss"] > 0).sum()),
                    int((one_timers["ProfitLoss"] < 0).sum()),
                    int((one_timers["ProfitLoss"] == 0).sum()),
                ],
            }
        )
        outcome_chart = px.bar(
            one_timer_outcomes,
            x="Outcome",
            y="Count",
            color="Outcome",
            title="One-Time Player Outcomes",
            template="plotly_white",
        )
        st.plotly_chart(outcome_chart, use_container_width=True)

    render_one_timer_fun_features(one_timers)

    st.subheader("Regular Player Charts")
    reg_col1, reg_col2 = st.columns(2)
    with reg_col1:
        if regulars.empty:
            st.info("No regular-player chart data.")
        else:
            regular_profit_chart = px.bar(
                regulars,
                x="Player",
                y="ProfitLoss",
                title="Profit/Loss - Regular Players",
                text_auto=True,
                color="ProfitLoss",
                template="plotly_white",
            )
            st.plotly_chart(regular_profit_chart, use_container_width=True)

    with reg_col2:
        if regulars.empty:
            st.info("No regular-player chart data.")
        else:
            regular_buyin_chart = px.pie(
                regulars,
                names="Player",
                values="BuyIns",
                title="Buy-In Contributions - Regular Players",
                template="plotly_white",
            )
            st.plotly_chart(regular_buyin_chart, use_container_width=True)

    if regulars.empty:
        st.info("Regular-player advanced analytics need at least one regular in range.")
        return

    regular_names = set(regulars["Player"].tolist())
    regular_data = filtered_data[filtered_data["Player"].isin(regular_names)].copy()

    st.subheader("Top Regular Bankroll Trajectory")
    top_regular_names = regulars.head(int(top_n))["Player"].tolist()
    trajectory_source = regular_data[regular_data["Player"].isin(top_regular_names)]
    if trajectory_source.empty:
        st.info("No trajectory data for top regulars.")
    else:
        trajectory = (
            trajectory_source.pivot_table(index="Session Number", columns="Player", values="ProfitLoss", aggfunc="sum")
            .fillna(0)
            .sort_index()
            .cumsum()
            .reset_index()
        )
        melted = trajectory.melt(id_vars=["Session Number"], var_name="Player", value_name="Cumulative P/L")
        fig_trajectory = px.line(
            melted,
            x="Session Number",
            y="Cumulative P/L",
            color="Player",
            markers=True,
            title="Cumulative Profit by Session (Regulars)",
            template="plotly_white",
        )
        st.plotly_chart(fig_trajectory, use_container_width=True)

    adv_col1, adv_col2 = st.columns(2)
    with adv_col1:
        roi_chart = px.scatter(
            regulars,
            x="BuyIns",
            y="ProfitLoss",
            size="Sessions Played",
            color="ROI (%)",
            hover_name="Player",
            title="Regulars: Volume vs Profit",
            template="plotly_white",
        )
        st.plotly_chart(roi_chart, use_container_width=True)

    with adv_col2:
        volatility_chart = px.bar(
            regulars.sort_values("Profit StdDev", ascending=False).head(int(top_n)),
            x="Player",
            y="Profit StdDev",
            color="Profit StdDev",
            title="Regulars: Volatility Ranking",
            template="plotly_white",
        )
        st.plotly_chart(volatility_chart, use_container_width=True)

    st.subheader("Regular Consistency Quadrant")
    consistency_chart = px.scatter(
        regulars,
        x="Profit StdDev",
        y="Avg Profit/Session",
        size="Sessions Played",
        color="ProfitLoss",
        hover_name="Player",
        title="Avg Profit vs Volatility (Regulars)",
        template="plotly_white",
    )
    st.plotly_chart(consistency_chart, use_container_width=True)

    st.subheader("Table Chemistry (Regular Triples)")
    chemistry = compute_table_chemistry(regular_data, regular_names)
    if chemistry.empty:
        st.info("Need sessions with at least 3 regulars to compute chemistry.")
    else:
        chem_col1, chem_col2 = st.columns(2)
        with chem_col1:
            st.markdown("**Highest Spread Trios (Wild Tables)**")
            st.dataframe(
                chemistry.head(5).style.format(
                    {
                        "Net Combo P/L": "${:,.2f}",
                        "Avg Profit Spread": "${:,.2f}",
                    }
                ),
                use_container_width=True,
            )
        with chem_col2:
            st.markdown("**Lowest Spread Trios (Calm Tables)**")
            st.dataframe(
                chemistry.sort_values("Avg Profit Spread", ascending=True).head(5).style.format(
                    {
                        "Net Combo P/L": "${:,.2f}",
                        "Avg Profit Spread": "${:,.2f}",
                    }
                ),
                use_container_width=True,
            )

    st.subheader("Chaos Session Award")
    chaos = compute_chaos_sessions(regular_data, regular_names)
    if chaos.empty:
        st.info("Need at least 3 regular players in a session to compute chaos score.")
    else:
        top_chaos = chaos.iloc[0]
        st.write(
            f"Session **{int(top_chaos['Session Number'])}** was the wildest with "
            f"std dev **${top_chaos['Profit StdDev']:,.2f}** across **{int(top_chaos['Players'])}** regulars."
        )
        st.dataframe(chaos.head(5).style.format({"Profit StdDev": "${:,.2f}", "Profit Range": "${:,.2f}"}), use_container_width=True)

    st.subheader("Most Expensive Friendship")
    friendship = compute_friendship_gaps(regular_data, regular_names)
    if friendship.empty:
        st.info("Need at least two regulars sharing sessions to compute pair gaps.")
    else:
        top_pair = friendship.iloc[0]
        st.write(
            f"Biggest long-term gap: **{top_pair['Pair']}**, edge to **{top_pair['Edge']}** "
            f"by **${top_pair['Absolute Gap']:,.2f}**."
        )
        st.dataframe(friendship.head(8).style.format({"Net Gap": "${:,.2f}", "Absolute Gap": "${:,.2f}"}), use_container_width=True)

    st.subheader("Whale Alert (Regulars)")
    whales = compute_whale_alert(regulars)
    if whales.empty:
        st.success("No regular whales detected for current filters.")
    else:
        st.dataframe(whales.style.format(MONEY_FORMAT), use_container_width=True)

    st.subheader("Robin Hood Session")
    robin = compute_robin_hood_sessions(regular_data, regular_names)
    if robin.empty:
        st.info("Not enough loss distribution data to compute Robin Hood score.")
    else:
        champion = robin.iloc[0]
        st.write(
            f"Best redistribution vibe: session **{int(champion['Session Number'])}** "
            f"(winner: **{champion['Top Winner']}**, score: **{champion['Robin Hood Score']:.3f}**)."
        )
        st.dataframe(
            robin.head(5).style.format(
                {
                    "Top Winner Profit": "${:,.2f}",
                    "Robin Hood Score": "{:,.3f}",
                }
            ),
            use_container_width=True,
        )

    st.subheader("Regular Meme Leaderboard")
    meme_cards = build_regular_meme_board(regulars, regular_data)
    if not meme_cards:
        st.info("No meme awards available right now.")
    else:
        for title, name, note in meme_cards:
            st.write(f"**{title}**: {name} ({note})")

    st.subheader("Regular Title Wall")
    archetypes = compute_regular_archetypes(regulars)
    if archetypes.empty:
        st.info("No regular archetypes available.")
    else:
        st.dataframe(archetypes, use_container_width=True)

    st.subheader("Regular Momentum Board")
    momentum = compute_regular_momentum(regular_data, window=5)
    if momentum.empty:
        st.info("No momentum data available.")
    else:
        st.dataframe(
            momentum.head(12).style.format({"Recent P/L": "${:,.2f}"}),
            use_container_width=True,
        )

    st.subheader("Rivalry Win-Rate Table")
    rivalries = compute_head_to_head_rivalries(regular_data, min_shared_sessions=3)
    if rivalries.empty:
        st.info("Need more shared sessions between regulars for rivalry stats.")
    else:
        st.dataframe(
            rivalries.head(12).style.format({"Edge Win Rate (%)": "{:,.2f}%"}),
            use_container_width=True,
        )

    st.subheader("Drawdown Risk (Regulars)")
    drawdown_table = compute_player_drawdown_table(regular_data)
    if drawdown_table.empty:
        st.info("No drawdown data available.")
    else:
        st.dataframe(
            drawdown_table.style.format({"Max Drawdown": "${:,.2f}"}),
            use_container_width=True,
        )

    if not session_view.empty:
        st.subheader("Session Pot Trend")
        pot_chart = px.bar(
            session_view.sort_values("Session Number"),
            x="Session Number",
            y="Total BuyIns",
            color="Balance Delta" if "Balance Delta" in session_view.columns else None,
            title="Pot Size by Session",
            template="plotly_white",
        )
        st.plotly_chart(pot_chart, use_container_width=True)


def render_session_explorer(filtered_data: pd.DataFrame, filtered_sessions: pd.DataFrame) -> None:
    st.title("Session Explorer")

    session_view = build_session_view(filtered_data, filtered_sessions)
    session_options = sorted(session_view["Session Number"].dropna().astype(int).unique())
    if not session_options:
        st.info("No sessions available for current filters.")
        return

    selected_session = st.selectbox("Select Session", options=session_options)

    session_row = session_view.loc[session_view["Session Number"] == selected_session]
    if session_row.empty:
        st.warning("Selected session is not available in the current filter context.")
        return

    session_row = session_row.iloc[0]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Players", int(session_row.get("Players", 0)))
    col2.metric("Total Buy-Ins", f"${float(session_row.get('Total BuyIns', 0.0)):,.2f}")
    col3.metric("Total Payouts", f"${float(session_row.get('Total Payouts', 0.0)):,.2f}")
    col4.metric("Balance Delta", f"${float(session_row.get('Balance Delta', 0.0)):,.2f}")

    player_breakdown = filtered_data[filtered_data["Session Number"] == selected_session].copy()
    if player_breakdown.empty:
        st.info("No player records for this session with current filters.")
        return

    player_breakdown = player_breakdown.sort_values("ProfitLoss", ascending=False)
    fig_breakdown = px.bar(
        player_breakdown,
        x="Player",
        y="ProfitLoss",
        color="ProfitLoss",
        title=f"Player Results - Session {selected_session}",
        template="plotly_white",
    )
    st.plotly_chart(fig_breakdown, use_container_width=True)

    st.dataframe(
        player_breakdown[["Player", "BuyIn_Times", "BuyIns", "Payouts", "ProfitLoss", "ROI (%)"]].style.format(
            {
                "BuyIns": "${:,.2f}",
                "Payouts": "${:,.2f}",
                "ProfitLoss": "${:,.2f}",
                "ROI (%)": "{:,.2f}%",
            }
        ),
        use_container_width=True,
    )

def _streak_lengths(profit_series: pd.Series) -> tuple[int, int]:
    wins = profit_series > 0
    losses = profit_series < 0

    win_groups = (~wins.astype(int).diff().eq(0)).cumsum()
    win_lengths = wins.astype(int).groupby(win_groups).cumsum()
    longest_win = int(win_lengths[wins].max()) if not win_lengths[wins].empty else 0

    loss_groups = (~losses.astype(int).diff().eq(0)).cumsum()
    loss_lengths = losses.astype(int).groupby(loss_groups).cumsum()
    longest_loss = int(loss_lengths[losses].max()) if not loss_lengths[losses].empty else 0

    return longest_win, longest_loss


def compute_tilt_meter(player_data: pd.DataFrame) -> tuple[float, str, int]:
    losses = (player_data["ProfitLoss"] < 0).astype(int)
    if losses.shape[0] < 2:
        return 0.0, "Calm", 0

    back_to_back_losses = int(((losses == 1) & (losses.shift(1) == 1)).sum())
    tilt_percent = round((back_to_back_losses / max(1, losses.shape[0] - 1)) * 100, 2)

    if tilt_percent < 20:
        label = "Calm"
    elif tilt_percent < 45:
        label = "Warming Up"
    else:
        label = "Tilt Risk"

    return tilt_percent, label, back_to_back_losses


def compute_clutch_index(player_data: pd.DataFrame, session_view: pd.DataFrame) -> tuple[float, float, float, int]:
    if session_view.empty:
        return 0.0, 0.0, 0.0, 0

    merged = player_data.merge(
        session_view[["Session Number", "Total BuyIns"]],
        on="Session Number",
        how="left",
    )
    merged = merged.dropna(subset=["Total BuyIns"])
    if merged.empty:
        return 0.0, 0.0, 0.0, 0

    threshold = float(merged["Total BuyIns"].quantile(0.80))
    high_stakes = merged[merged["Total BuyIns"] >= threshold]
    if high_stakes.empty:
        return threshold, 0.0, 0.0, 0

    high_avg = float(high_stakes["ProfitLoss"].mean())
    overall_avg = float(merged["ProfitLoss"].mean())
    return threshold, high_avg, high_avg - overall_avg, int(high_stakes.shape[0])


def compute_weekend_warrior(player_data: pd.DataFrame) -> tuple[float, float, float]:
    data = player_data.dropna(subset=["SessionDateParsed"]).copy()
    if data.empty:
        return 0.0, 0.0, 0.0

    data["IsWeekendWarrior"] = data["SessionDateParsed"].dt.dayofweek.isin([4, 5])
    weekend = data[data["IsWeekendWarrior"]]["ProfitLoss"]
    weekdays = data[~data["IsWeekendWarrior"]]["ProfitLoss"]

    weekend_avg = float(weekend.mean()) if not weekend.empty else 0.0
    weekday_avg = float(weekdays.mean()) if not weekdays.empty else 0.0
    return weekend_avg, weekday_avg, weekend_avg - weekday_avg


def compute_comeback_score(player_data: pd.DataFrame) -> tuple[float, int]:
    ordered = player_data.sort_values("Session Number").reset_index(drop=True)
    if ordered.shape[0] < 2:
        return 0.0, 0

    rebounds: list[float] = []
    for idx in range(1, ordered.shape[0]):
        prev_profit = float(ordered.iloc[idx - 1]["ProfitLoss"])
        current_profit = float(ordered.iloc[idx]["ProfitLoss"])
        if prev_profit < 0:
            rebounds.append(current_profit - prev_profit)

    if not rebounds:
        return 0.0, 0
    return float(sum(rebounds) / len(rebounds)), len(rebounds)


def compute_pot_tier_performance(player_data: pd.DataFrame, session_view: pd.DataFrame) -> pd.DataFrame:
    if session_view.empty:
        return pd.DataFrame(columns=["Pot Tier", "Sessions", "Avg P/L", "Total P/L"])

    merged = player_data.merge(
        session_view[["Session Number", "Total BuyIns"]],
        on="Session Number",
        how="left",
    ).dropna(subset=["Total BuyIns"])
    if merged.empty:
        return pd.DataFrame(columns=["Pot Tier", "Sessions", "Avg P/L", "Total P/L"])

    low = float(merged["Total BuyIns"].quantile(0.33))
    high = float(merged["Total BuyIns"].quantile(0.66))

    def classify(pot: float) -> str:
        if pot <= low:
            return "Low Pot"
        if pot <= high:
            return "Mid Pot"
        return "High Pot"

    merged["Pot Tier"] = merged["Total BuyIns"].map(classify)
    result = (
        merged.groupby("Pot Tier", as_index=False)
        .agg({"ProfitLoss": ["count", "mean", "sum"]})
    )
    result.columns = ["Pot Tier", "Sessions", "Avg P/L", "Total P/L"]
    return result.sort_values("Sessions", ascending=False).reset_index(drop=True)


def compute_rival_radar(filtered_data: pd.DataFrame, selected_player: str, regular_names: set[str]) -> pd.DataFrame:
    selected_sessions = set(
        filtered_data.loc[filtered_data["Player"] == selected_player, "Session Number"].dropna().astype(int).tolist()
    )
    if not selected_sessions:
        return pd.DataFrame(columns=["Rival", "Shared Sessions", "Total P/L", "Avg P/L Per Shared Session"])

    rows: list[dict] = []
    for rival in sorted(regular_names):
        if rival == selected_player:
            continue

        rival_sessions = set(
            filtered_data.loc[filtered_data["Player"] == rival, "Session Number"].dropna().astype(int).tolist()
        )
        shared = sorted(selected_sessions.intersection(rival_sessions))
        if not shared:
            continue

        shared_profit = filtered_data[
            (filtered_data["Player"] == selected_player)
            & (filtered_data["Session Number"].isin(shared))
        ]["ProfitLoss"].sum()

        rows.append(
            {
                "Rival": rival,
                "Shared Sessions": len(shared),
                "Total P/L": float(shared_profit),
                "Avg P/L Per Shared Session": float(shared_profit / len(shared)),
            }
        )

    if not rows:
        return pd.DataFrame(columns=["Rival", "Shared Sessions", "Total P/L", "Avg P/L Per Shared Session"])

    return pd.DataFrame(rows).sort_values("Avg P/L Per Shared Session", ascending=False).reset_index(drop=True)


def compute_selected_head_to_head(
    filtered_data: pd.DataFrame, selected_player: str, regular_names: set[str]
) -> pd.DataFrame:
    regular_data = filtered_data[filtered_data["Player"].isin(regular_names)].copy()
    rows: list[dict] = []

    selected_sessions = set(
        regular_data.loc[regular_data["Player"] == selected_player, "Session Number"]
        .dropna()
        .astype(int)
        .tolist()
    )
    if not selected_sessions:
        return pd.DataFrame(
            columns=["Opponent", "Shared Sessions", "W", "L", "T", "Avg Diff", "Total Diff"]
        )

    for opponent in sorted(regular_names):
        if opponent == selected_player:
            continue

        opponent_sessions = set(
            regular_data.loc[regular_data["Player"] == opponent, "Session Number"]
            .dropna()
            .astype(int)
            .tolist()
        )
        shared = sorted(selected_sessions.intersection(opponent_sessions))
        if not shared:
            continue

        wins = losses = ties = 0
        diffs: list[float] = []
        for session in shared:
            session_rows = regular_data[
                (regular_data["Session Number"] == session)
                & (regular_data["Player"].isin([selected_player, opponent]))
            ]
            if session_rows["Player"].nunique() < 2:
                continue
            selected_pl = float(session_rows.loc[session_rows["Player"] == selected_player, "ProfitLoss"].sum())
            opponent_pl = float(session_rows.loc[session_rows["Player"] == opponent, "ProfitLoss"].sum())
            diff = selected_pl - opponent_pl
            diffs.append(diff)
            if diff > 0:
                wins += 1
            elif diff < 0:
                losses += 1
            else:
                ties += 1

        if not diffs:
            continue

        rows.append(
            {
                "Opponent": opponent,
                "Shared Sessions": len(diffs),
                "W": wins,
                "L": losses,
                "T": ties,
                "Avg Diff": float(sum(diffs) / len(diffs)),
                "Total Diff": float(sum(diffs)),
            }
        )

    if not rows:
        return pd.DataFrame(columns=["Opponent", "Shared Sessions", "W", "L", "T", "Avg Diff", "Total Diff"])
    return pd.DataFrame(rows).sort_values("Avg Diff", ascending=False).reset_index(drop=True)


def compute_regular_comparison_table(filtered_data: pd.DataFrame, regular_names: set[str]) -> pd.DataFrame:
    regular_data = filtered_data[filtered_data["Player"].isin(regular_names)].copy()
    if regular_data.empty:
        return pd.DataFrame(
            columns=[
                "Player",
                "Sessions Played",
                "ProfitLoss",
                "ROI (%)",
                "Avg Profit/Session",
                "Consistency Score",
                "Win Rate (%)",
                "Profit Rank",
                "ROI Rank",
                "Consistency Rank",
                "Win Rate Rank",
            ]
        )

    board = build_leaderboard(regular_data)
    board = board[board["Sessions Played"] > 1].copy()
    if board.empty:
        return pd.DataFrame(
            columns=[
                "Player",
                "Sessions Played",
                "ProfitLoss",
                "ROI (%)",
                "Avg Profit/Session",
                "Consistency Score",
                "Win Rate (%)",
                "Profit Rank",
                "ROI Rank",
                "Consistency Rank",
                "Win Rate Rank",
            ]
        )

    win_rate = (
        regular_data.assign(Win=regular_data["ProfitLoss"] > 0)
        .groupby("Player")["Win"]
        .mean()
        .mul(100)
        .rename("Win Rate (%)")
    )
    board = board.merge(win_rate, left_on="Player", right_index=True, how="left")
    board["Win Rate (%)"] = board["Win Rate (%)"].fillna(0.0)

    board["Profit Rank"] = board["ProfitLoss"].rank(method="min", ascending=False).astype(int)
    board["ROI Rank"] = board["ROI (%)"].rank(method="min", ascending=False).astype(int)
    board["Consistency Rank"] = board["Consistency Score"].rank(method="min", ascending=False).astype(int)
    board["Win Rate Rank"] = board["Win Rate (%)"].rank(method="min", ascending=False).astype(int)

    return board.sort_values("Profit Rank").reset_index(drop=True)


def heat_streak_label(player_data: pd.DataFrame) -> tuple[str, str]:
    recent = player_data.sort_values("Session Number").tail(5)
    wins = int((recent["ProfitLoss"] > 0).sum())
    losses = int((recent["ProfitLoss"] < 0).sum())

    if wins >= 4:
        return "On Fire", "Winning momentum is strong in recent sessions."
    if losses >= 4:
        return "Cold Deck", "Recent form is rough; variance may be running hot against you."
    return "Swing Mode", "Mixed recent sessions, currently in a variance cycle."


def render_regular_player_extras(
    selected_player: str,
    player_data: pd.DataFrame,
    filtered_data: pd.DataFrame,
    session_view: pd.DataFrame,
    regular_names: set[str],
) -> None:
    st.subheader("Regular-Only Feature Pack")

    comparison_table = compute_regular_comparison_table(filtered_data, regular_names)
    selected_comp = comparison_table.loc[comparison_table["Player"] == selected_player]
    if selected_comp.empty:
        st.info("Not enough regular-player comparison data.")
        return
    selected_comp = selected_comp.iloc[0]

    pool_avg_profit = float(comparison_table["Avg Profit/Session"].mean()) if not comparison_table.empty else 0.0
    pool_edge = float(selected_comp["Avg Profit/Session"] - pool_avg_profit)
    roi_median = float(comparison_table["ROI (%)"].median()) if not comparison_table.empty else 0.0
    consistency_median = (
        float(comparison_table["Consistency Score"].median()) if not comparison_table.empty else 0.0
    )

    tilt_pct, tilt_label, tilt_pairs = compute_tilt_meter(player_data)
    threshold, high_avg, clutch_delta, clutch_sessions = compute_clutch_index(player_data, session_view)

    avg_buyin = float(player_data["BuyIns"].mean()) if not player_data.empty else 0.0
    bad_beat_count = int(((player_data["BuyIns"] > avg_buyin) & (player_data["ProfitLoss"] < 0)).sum())
    bad_beat_rate = round((bad_beat_count / max(1, player_data.shape[0])) * 100, 2)

    weekend_avg, weekday_avg, weekend_edge = compute_weekend_warrior(player_data)
    comeback_score, comeback_sample = compute_comeback_score(player_data)
    max_drawdown = compute_max_drawdown(player_data.sort_values("Session Number")["ProfitLoss"])

    heat_label, heat_note = heat_streak_label(player_data)

    col1, col2, col3 = st.columns(3)
    col1.metric("Tilt Meter", f"{tilt_pct:.2f}%", f"{tilt_pairs} back-to-back loss pair(s)")
    col2.metric(
        "Clutch Index",
        f"${clutch_delta:,.2f}",
        f"High-pot avg ${high_avg:,.2f} | threshold ${threshold:,.2f}",
    )
    col3.metric("Bad Beat Magnet", f"{bad_beat_count}", f"{bad_beat_rate:.2f}% of sessions")

    col4, col5 = st.columns(2)
    col4.metric("Weekend Warrior Edge", f"${weekend_edge:,.2f}", f"Fri/Sat ${weekend_avg:,.2f} vs weekdays ${weekday_avg:,.2f}")
    col5.metric("Heat Streak Card", heat_label, heat_note)

    col6, col7 = st.columns(2)
    col6.metric("Comeback Score", f"${comeback_score:,.2f}", f"{comeback_sample} recovery spot(s)")
    col7.metric("Max Drawdown", f"${max_drawdown:,.2f}", "Worst bankroll dip")

    st.caption(
        f"Clutch sample size: {clutch_sessions} high-pot session(s). Tilt status: {tilt_label}."
    )

    st.subheader("Rival Radar")
    rival_radar = compute_rival_radar(filtered_data, selected_player, regular_names)
    if rival_radar.empty:
        st.info("No rival overlap sessions available.")
    else:
        best_rival = rival_radar.iloc[0]
        worst_rival = rival_radar.iloc[-1]
        st.write(
            f"Best matchup: **{best_rival['Rival']}** (${best_rival['Avg P/L Per Shared Session']:,.2f}/shared session)"
        )
        st.write(
            f"Worst matchup: **{worst_rival['Rival']}** (${worst_rival['Avg P/L Per Shared Session']:,.2f}/shared session)"
        )
        st.dataframe(
            rival_radar.head(10).style.format(
                {
                    "Total P/L": "${:,.2f}",
                    "Avg P/L Per Shared Session": "${:,.2f}",
                }
            ),
            use_container_width=True,
        )

    st.subheader("Head-To-Head Matrix")
    h2h = compute_selected_head_to_head(filtered_data, selected_player, regular_names)
    if h2h.empty:
        st.info("No head-to-head overlap found yet.")
    else:
        best_h2h = h2h.iloc[0]
        worst_h2h = h2h.iloc[-1]
        st.write(
            f"Best matchup right now: **{best_h2h['Opponent']}** "
            f"(avg diff **${best_h2h['Avg Diff']:,.2f}** over {int(best_h2h['Shared Sessions'])} sessions)."
        )
        st.write(
            f"Toughest matchup right now: **{worst_h2h['Opponent']}** "
            f"(avg diff **${worst_h2h['Avg Diff']:,.2f}** over {int(worst_h2h['Shared Sessions'])} sessions)."
        )
        st.dataframe(
            h2h.style.format(
                {
                    "Avg Diff": "${:,.2f}",
                    "Total Diff": "${:,.2f}",
                }
            ),
            use_container_width=True,
        )

    st.subheader("Regular Title Cards")
    if selected_comp["Profit Rank"] <= 3 and selected_comp["ROI (%)"] >= roi_median:
        persona = "Table Shark"
    elif selected_comp["ProfitLoss"] > 0:
        persona = "Stack Builder"
    elif selected_comp["ProfitLoss"] < 0:
        persona = "Variance Fighter"
    else:
        persona = "Neutral Grinder"

    if selected_comp["Consistency Score"] >= consistency_median:
        style_tag = "Consistent Closer"
    else:
        style_tag = "High Swing Artist"

    if not rival_radar.empty:
        matchup_spread = float(best_rival["Avg P/L Per Shared Session"] - worst_rival["Avg P/L Per Shared Session"])
        if matchup_spread >= 4:
            matchup_tag = "Table Exploiter"
        elif matchup_spread <= 1:
            matchup_tag = "Balanced Fighter"
        else:
            matchup_tag = "Selective Predator"
    else:
        matchup_tag = "Unknown Rival Profile"

    regular_fortune = "Stay patient and press your edge in deeper sessions."
    if selected_comp["Profit Rank"] == 1 and selected_comp["Win Rate Rank"] <= 2:
        regular_fortune = "You are the benchmark. People study your line now."
    elif selected_comp["Profit Rank"] >= max(3, int(len(comparison_table) * 0.7)):
        regular_fortune = "You are due for regression bounce if discipline stays tight."

    t1, t2, t3 = st.columns(3)
    t1.metric("Regular Persona", persona)
    t2.metric("Playstyle Tag", style_tag)
    t3.metric("Matchup Tag", matchup_tag)
    st.caption(f"Fortune Cookie: {regular_fortune}")

    st.subheader("Regular-vs-Regular Comparison")
    cmp1, cmp2, cmp3, cmp4 = st.columns(4)
    cmp1.metric("Profit Rank", f"#{int(selected_comp['Profit Rank'])}", f"/ {len(comparison_table)} regulars")
    cmp2.metric("ROI Rank", f"#{int(selected_comp['ROI Rank'])}", f"ROI {selected_comp['ROI (%)']:.2f}%")
    cmp3.metric("Win Rate Rank", f"#{int(selected_comp['Win Rate Rank'])}", f"{selected_comp['Win Rate (%)']:.2f}%")
    cmp4.metric("Pool Edge", f"${pool_edge:,.2f}", "Avg P/L vs regular pool")

    st.dataframe(
        comparison_table[
            [
                "Player",
                "Sessions Played",
                "ProfitLoss",
                "ROI (%)",
                "Win Rate (%)",
                "Profit Rank",
                "ROI Rank",
                "Win Rate Rank",
                "Consistency Rank",
            ]
        ].style.format(
            {
                "ProfitLoss": "${:,.2f}",
                "ROI (%)": "{:,.2f}%",
                "Win Rate (%)": "{:,.2f}%",
            }
        ),
        use_container_width=True,
    )

    st.subheader("Pot-Tier Performance")
    tier_performance = compute_pot_tier_performance(player_data, session_view)
    if tier_performance.empty:
        st.info("Not enough session pot data for tier split.")
    else:
        st.dataframe(
            tier_performance.style.format(
                {
                    "Avg P/L": "${:,.2f}",
                    "Total P/L": "${:,.2f}",
                }
            ),
            use_container_width=True,
        )


def render_one_timer_player_fun(player_data: pd.DataFrame) -> None:
    st.subheader("One-Timer Mini Feature Pack")
    row = player_data.iloc[-1]
    profit = float(row["ProfitLoss"])
    roi = float(row["ROI (%)"]) if pd.notna(row["ROI (%)"]) else 0.0
    buyins = float(row["BuyIns"])

    if profit > 0:
        vibe = "One-Night Legend"
    elif profit < 0:
        vibe = "Paid For The Story"
    else:
        vibe = "Balanced Debut"

    risk_label = "Big Splash" if buyins >= 10 else "Light Buy-In"
    escape_label = "Hit-And-Run" if roi > 50 else "Stayed Grounded"

    c1, c2, c3 = st.columns(3)
    c1.metric("Debut Vibe", vibe)
    c2.metric("Session Style", risk_label, f"${buyins:,.2f} buy-in")
    c3.metric("Exit Tag", escape_label, f"ROI {roi:,.2f}%")

    fortune = "Come back for a rematch."
    if profit > 0 and roi > 100:
        fortune = "Mic drop debut. Legend status."
    elif profit > 0:
        fortune = "Solid debut. The table remembers."
    elif profit < 0 and roi < -50:
        fortune = "Variance tax paid. Redemption arc pending."
    st.caption(f"Fortune Cookie: {fortune}")

def render_player_stats(filtered_data: pd.DataFrame, filtered_sessions: pd.DataFrame) -> None:
    st.title("Player-Specific Statistics")

    player_options = sorted(filtered_data["Player"].dropna().unique())
    if not player_options:
        st.info("No players available for current filters.")
        return

    selected_player = st.selectbox("Select Player", options=player_options)
    player_data = filtered_data.loc[filtered_data["Player"] == selected_player].copy()
    player_data = player_data.sort_values("Session Number")

    total_buyins = float(player_data["BuyIns"].sum())
    total_payouts = float(player_data["Payouts"].sum())
    total_profit = float(player_data["ProfitLoss"].sum())
    sessions_played = int(player_data["Session Number"].nunique())
    average_profit = float(player_data["ProfitLoss"].mean()) if not player_data.empty else 0.0
    volatility = float(player_data["ProfitLoss"].std()) if len(player_data) > 1 else 0.0
    roi = round((total_profit / total_buyins) * 100, 2) if total_buyins > 0 else 0.0
    is_regular = sessions_played > 1

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Sessions", sessions_played)
    col2.metric("Total Buy-Ins", f"${total_buyins:,.2f}")
    col3.metric("Net P/L", f"${total_profit:,.2f}")
    col4.metric("ROI", f"{roi:,.2f}%")
    col5.metric("Volatility", f"${volatility:,.2f}")

    st.caption(f"Total payouts: ${total_payouts:,.2f} | Average P/L per session: ${average_profit:,.2f}")

    trend_col1, trend_col2 = st.columns(2)
    with trend_col1:
        trend_chart = px.line(
            player_data,
            x="Session Number",
            y="ProfitLoss",
            title=f"Profit/Loss by Session - {selected_player}",
            markers=True,
            template="plotly_white",
        )
        st.plotly_chart(trend_chart, use_container_width=True)

    with trend_col2:
        player_data["Cumulative Profit/Loss"] = player_data["ProfitLoss"].cumsum()
        cumulative_chart = px.line(
            player_data,
            x="Session Number",
            y="Cumulative Profit/Loss",
            title=f"Cumulative Profit/Loss - {selected_player}",
            markers=True,
            template="plotly_white",
        )
        st.plotly_chart(cumulative_chart, use_container_width=True)

    distribution_col1, distribution_col2 = st.columns(2)
    with distribution_col1:
        histogram = px.histogram(
            player_data,
            x="ProfitLoss",
            nbins=20,
            title="Session Outcome Distribution",
            template="plotly_white",
        )
        st.plotly_chart(histogram, use_container_width=True)

    with distribution_col2:
        player_data["Rolling Avg (5)"] = player_data["ProfitLoss"].rolling(window=5, min_periods=1).mean()
        rolling_chart = px.line(
            player_data,
            x="Session Number",
            y="Rolling Avg (5)",
            title="Rolling Average (5 Sessions)",
            markers=True,
            template="plotly_white",
        )
        st.plotly_chart(rolling_chart, use_container_width=True)

    longest_win, longest_loss = _streak_lengths(player_data["ProfitLoss"])
    st.write(f"Longest winning streak: {longest_win} session(s)")
    st.write(f"Longest losing streak: {longest_loss} session(s)")

    session_view = build_session_view(filtered_data, filtered_sessions)
    if is_regular:
        regular_names = set(
            build_leaderboard(filtered_data)
            .loc[lambda df: df["Sessions Played"] > 1, "Player"]
            .tolist()
        )
        render_regular_player_extras(
            selected_player, player_data, filtered_data, session_view, regular_names
        )
    else:
        render_one_timer_player_fun(player_data)

    st.subheader("All Sessions")
    all_sessions = player_data.sort_values("Session Number", ascending=False)
    all_sessions_display = all_sessions.copy()
    if "SessionDateParsed" in all_sessions_display.columns:
        sortable_date = pd.to_datetime(all_sessions_display["SessionDateParsed"], errors="coerce")
        all_sessions_display["Session Date"] = sortable_date.dt.strftime("%Y-%m-%d")
        all_sessions_display["Session Date"] = all_sessions_display["Session Date"].fillna(
            all_sessions["Session Date"]
        )
    st.dataframe(
        all_sessions_display[["Session Number", "Session Date", "BuyIn_Times", "BuyIns", "Payouts", "ProfitLoss", "ROI (%)"]].style.format(
            {
                "BuyIns": "${:,.2f}",
                "Payouts": "${:,.2f}",
                "ProfitLoss": "${:,.2f}",
                "ROI (%)": "{:,.2f}%",
            }
        ),
        use_container_width=True,
    )


def render_quality_panel(filtered_sessions: pd.DataFrame, quality_df: pd.DataFrame) -> None:
    st.title("Data Quality")

    if not filtered_sessions.empty:
        mismatches = filtered_sessions[filtered_sessions["Balance Delta"].abs() > 0.01]
    else:
        mismatches = pd.DataFrame()

    st.subheader("Out-of-Balance Sessions")
    if mismatches.empty:
        st.success("No session balance mismatches found in current filter range.")
    else:
        st.dataframe(
            mismatches[
                [
                    "Session Number",
                    "Session Date",
                    "Total BuyIns",
                    "Total Payouts",
                    "Balance Delta",
                ]
            ].style.format(
                {
                    "Total BuyIns": "${:,.2f}",
                    "Total Payouts": "${:,.2f}",
                    "Balance Delta": "${:,.2f}",
                }
            ),
            use_container_width=True,
        )

    st.subheader("Input Parsing Issues")
    if quality_df.empty:
        st.info("No parsing issues were logged.")
    else:
        st.dataframe(quality_df, use_container_width=True)


players_df, sessions_df, quality_df = load_data()

if players_df.empty:
    st.error(
        "No player statistics file found. Run `python \"Poker CSV Generator.py\"` first to generate the data files."
    )
    st.stop()

st.sidebar.title("Navigation")
page = st.sidebar.radio(
    "Go to",
    ["Global Stats", "Session Explorer", "Player Stats", "Data Quality"],
)

session_min = int(players_df["Session Number"].min())
session_max = int(players_df["Session Number"].max())
selected_session_range = st.sidebar.slider(
    "Session range",
    min_value=session_min,
    max_value=session_max,
    value=(session_min, session_max),
)

date_candidates = pd.to_datetime(players_df["SessionDateParsed"], errors="coerce").dropna()
has_date_filter = not date_candidates.empty
if has_date_filter:
    min_date = date_candidates.min().date()
    max_date = date_candidates.max().date()
    selected_date_range = st.sidebar.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if isinstance(selected_date_range, tuple) and len(selected_date_range) == 2:
        start_date, end_date = selected_date_range
    else:
        start_date = selected_date_range
        end_date = selected_date_range
    if start_date > end_date:
        start_date, end_date = end_date, start_date
else:
    start_date = None
    end_date = None
    st.sidebar.caption("Date range disabled: no parseable session dates found.")

all_players = sorted(players_df["Player"].dropna().unique())
selected_players = st.sidebar.multiselect(
    "Players",
    options=all_players,
    default=all_players,
)

min_sessions_filter = st.sidebar.number_input(
    "Min sessions for regular analytics",
    min_value=1,
    max_value=max(1, session_max - session_min + 1),
    value=2,
    step=1,
)

top_n = st.sidebar.slider("Top regular players in charts", min_value=3, max_value=20, value=8)

filtered_players = players_df[
    (players_df["Session Number"] >= selected_session_range[0])
    & (players_df["Session Number"] <= selected_session_range[1])
].copy()

if selected_players:
    filtered_players = filtered_players[filtered_players["Player"].isin(selected_players)].copy()

if has_date_filter:
    parsed = pd.to_datetime(filtered_players["SessionDateParsed"], errors="coerce")
    filtered_players = filtered_players[
        parsed.dt.date.between(start_date, end_date, inclusive="both")
    ].copy()

if sessions_df.empty:
    filtered_sessions = pd.DataFrame()
else:
    filtered_sessions = sessions_df[
        (sessions_df["Session Number"] >= selected_session_range[0])
        & (sessions_df["Session Number"] <= selected_session_range[1])
    ].copy()

if has_date_filter and not filtered_sessions.empty:
    session_dates = pd.to_datetime(filtered_sessions["SessionDateParsed"], errors="coerce")
    filtered_sessions = filtered_sessions[
        session_dates.dt.date.between(start_date, end_date, inclusive="both")
    ].copy()

if filtered_players.empty:
    st.warning("No rows match the current filters.")
    st.stop()

if page == "Global Stats":
    render_global_stats(filtered_players, filtered_sessions, int(min_sessions_filter), int(top_n))
elif page == "Session Explorer":
    render_session_explorer(filtered_players, filtered_sessions)
elif page == "Player Stats":
    render_player_stats(filtered_players, filtered_sessions)
else:
    render_quality_panel(filtered_sessions, quality_df)
