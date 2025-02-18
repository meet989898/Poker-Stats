import streamlit as st
import pandas as pd
import plotly.express as px

# Load data
@st.cache_data
def load_data():
    df = pd.read_csv('player_statistics_by_session.csv')
    df = df[df['Player'] != 'D_Anonymous']  # Exclude the player
    return df

data = load_data()

# Global Statistics Page
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Global Stats", "Player Stats"])

if page == "Global Stats":
    st.title("Global Poker Statistics")

    # Global Metrics
    total_sessions = data['Session Number'].nunique()
    total_buyins = data['BuyIns'].sum()
    total_payouts = data['Payouts'].sum()
    net_profit_loss = data['ProfitLoss'].sum()

    st.subheader("Overall Metrics")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Sessions", total_sessions)
    col2.metric("Total Buy-Ins", f"${total_buyins:,.2f}")
    # col3.metric("Total Payouts", f"${total_payouts:,.2f}")
    # col4.metric("Net Profit/Loss", f"${net_profit_loss:,.2f}")

    # Leaderboard
    st.subheader("Leaderboard")
    leaderboard = data.groupby('Player').agg({
        'Session Number': 'nunique',  # Total sessions played per player
        'BuyIns': 'sum',
        'Payouts': 'sum',
        'ProfitLoss': 'sum'
    }).reset_index().sort_values(by='ProfitLoss', ascending=False)
    leaderboard.rename(columns={'Session Number': 'Sessions Played'}, inplace=True)
    leaderboard['Profit Variance'] = data.groupby('Player')['ProfitLoss'].var().reset_index(drop=True)
    leaderboard['Median Profit'] = data.groupby('Player')['ProfitLoss'].median().reset_index(drop=True)
    st.dataframe(leaderboard.style.format({
        'BuyIns': '${:,.2f}',
        'Payouts': '${:,.2f}',
        'ProfitLoss': '${:,.2f}',
        'Profit Variance': '${:,.2f}',
        'Median Profit': '${:,.2f}'
    }))

    # Global Charts
    st.subheader("Total Profit/Loss by Player")
    profit_chart = px.bar(leaderboard, x='Player', y='ProfitLoss', title="Total Profit/Loss", text_auto=True)
    st.plotly_chart(profit_chart)

    st.subheader("Total Buy-Ins by Player")
    buyin_chart = px.pie(leaderboard, names='Player', values='BuyIns', title="Buy-In Contributions")
    st.plotly_chart(buyin_chart)

    # Additional Global Stats
    st.subheader("Additional Global Stats")
    avg_buyins_per_session = data['BuyIns'].sum() / data['Session Number'].nunique()
    st.write(f"Average Buy-Ins Per Session: **${avg_buyins_per_session:,.2f}**")

    most_profitable_player = leaderboard.loc[leaderboard['ProfitLoss'].idxmax()]['Player']
    most_loss_player = leaderboard.loc[leaderboard['ProfitLoss'].idxmin()]['Player']
    st.write(f"Most Profitable Player: **{most_profitable_player}**")
    st.write(f"Player with Most Losses: **{most_loss_player}**")

    largest_pot = data.groupby('Session Number')['BuyIns'].sum().max()
    st.write(f"Largest Pot in a Single Session: **${largest_pot:,.2f}**")

elif page == "Player Stats":
    st.title("Player-Specific Statistics")

    # Player Selection
    selected_player = st.selectbox("Select Player", options=sorted(data['Player'].unique()))
    player_data = data.loc[data['Player'] == selected_player].copy()

    # Player Metrics
    st.subheader(f"Statistics for {selected_player}")
    player_total_buyins = player_data['BuyIns'].sum()
    player_total_sessions = player_data['Session Number'].nunique()
    player_number_buyins = player_data['BuyIn_Times'].sum()
    player_total_payouts = player_data['Payouts'].sum()
    player_net_profit_loss = player_data['ProfitLoss'].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Sessions Played", player_total_sessions)
    col1.metric("Total Buy-Ins", f"${player_total_buyins:,.2f}")
    col1.metric("Times Bought-In", player_number_buyins)
    col2.metric("Total Payouts", f"${player_total_payouts:,.2f}")
    col3.metric("Net Profit/Loss", f"${player_net_profit_loss:,.2f}")

    # Player Trends
    st.subheader("Profit/Loss Trend Over Time")
    trend_chart = px.line(player_data, x='Session Number', y='ProfitLoss', title=f"Profit/Loss Trend for {selected_player}")
    st.plotly_chart(trend_chart)

    # Cumulative Profit/Loss
    st.subheader("Cumulative Profit/Loss")
    player_data['Cumulative Profit/Loss'] = player_data['ProfitLoss'].cumsum()
    cumulative_chart = px.line(player_data, x='Session Number', y='Cumulative Profit/Loss',
                                title=f"Cumulative Profit/Loss for {selected_player}")
    st.plotly_chart(cumulative_chart)

    # Player Session Breakdown
    st.subheader("Session Breakdown")
    session_breakdown = player_data[['Session Number', 'Session Date', 'BuyIn_Times', 'BuyIns', 'Payouts', 'ProfitLoss']]
    st.dataframe(session_breakdown.style.format({
        'BuyIns': '${:,.2f}',
        'Payouts': '${:,.2f}',
        'ProfitLoss': '${:,.2f}'
    }))

    # Player Streaks
    st.subheader("Win/Loss Streaks")
    player_data['Win'] = player_data['ProfitLoss'] > 0
    player_data['Loss'] = player_data['ProfitLoss'] < 0

    # Longest win streak
    win_streak_groups = (~player_data['Win'].astype(int).diff().eq(0)).cumsum()
    win_streak_lengths = player_data['Win'].astype(int).groupby(win_streak_groups).cumsum()
    longest_win_streak = win_streak_lengths[player_data['Win']].max() if not win_streak_lengths[player_data['Win']].empty else 0

    # Longest loss streak
    loss_streak_groups = (~player_data['Loss'].astype(int).diff().eq(0)).cumsum()
    loss_streak_lengths = player_data['Loss'].astype(int).groupby(loss_streak_groups).cumsum()
    longest_loss_streak = loss_streak_lengths[player_data['Loss']].max() if not loss_streak_lengths[player_data['Loss']].empty else 0

    st.write(f"Longest Winning Streak: **{longest_win_streak} sessions**")
    st.write(f"Longest Losing Streak: **{longest_loss_streak} sessions**")

    # Global Comparison
    st.subheader("Comparison with Global Stats")
    global_avg_profit = data['ProfitLoss'].mean()
    player_avg_profit = player_data['ProfitLoss'].mean()

    st.write(f"Average Global Profit/Loss: **${global_avg_profit:,.2f}**")
    st.write(f"Average Profit/Loss for {selected_player}: **${player_avg_profit:,.2f}**")

    comparison_chart = px.bar(
        x=["Global Average", f"{selected_player} Average"],
        y=[global_avg_profit, player_avg_profit],
        labels={"x": "Metric", "y": "Average Profit/Loss"},
        title="Comparison of Averages"
    )
    st.plotly_chart(comparison_chart)

    # Additional Player Stats
    st.subheader("Additional Player Stats")
    player_highest_profit = player_data['ProfitLoss'].max()
    player_highest_loss = player_data['ProfitLoss'].min()

    st.write(f"Highest Profit in a Single Session: **${player_highest_profit:,.2f}**")
    st.write(f"Highest Loss in a Single Session: **${player_highest_loss:,.2f}**")
