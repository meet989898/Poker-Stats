# Poker Statistics Dashboard

This is an interactive web application built with [Streamlit](https://streamlit.io/) that provides detailed analytics for poker sessions. It is designed for players to track performance, visualize trends, and explore various statistics.

## Features
- **Global Statistics**:
  - Total sessions played, buy-ins, payouts, and net profit/loss.
  - Leaderboard with profit variance and median profit per player.
  - Charts for total profit/loss and buy-ins by player.
  - Insights on the largest pot and most profitable/loss-heavy players.

- **Player-Specific Statistics**:
  - Detailed performance metrics for each player.
  - Charts for profit/loss trends and cumulative performance over sessions.
  - Longest winning and losing streaks per player.
  - Session breakdown with detailed buy-in and payout data.

## Getting Started
To run this app locally:

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/<your-username>/<your-repo>.git
   cd <your-repo>
   ```

2. **Install Dependencies**:
   Ensure you have Python installed, then install the required packages:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the App**:
   ```bash
   streamlit run app.py
   ```

4. **Access the App**:
   Open your browser and navigate to `http://localhost:8501`.

## Deployment
The app is deployed using [Streamlit Community Cloud](https://streamlit.io/cloud). You can access it directly via the following link:
**[Poker Statistics Dashboard](https://<your-streamlit-app-link>)**

## File Structure
- `app.py`: Main application file.
- `player_statistics_by_session.csv`: Data file containing session statistics.
- `requirements.txt`: Python dependencies.

## Contributing
Contributions are welcome! Feel free to fork this repository and submit a pull request.

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
