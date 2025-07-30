import pandas as pd
import datetime

# Path to the bank statement file
bank_statement_file = '9c5fcd56-6f00-4cbc-8cb2-e42af340a63b.csv'

# Function to parse the updated bank statement
def parse_updated_bank_statement(statement_file):
    bank_data = pd.read_csv(statement_file)
    bank_data['Effective Date'] = pd.to_datetime(bank_data['Effective Date'], errors='coerce')
    bank_data['Amount'] = bank_data['Amount'].replace(r'[^\d.]', '', regex=True).astype(float)
    return bank_data


def convert_date_to_words(date_str):

    # print(date_str)

    # Suffixes for day numbers
    def get_day_suffix(day):
        if 11 <= day <= 13:
            return "th"
        return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")

    # Parse the input date
    month, day, year = map(int, date_str.split('.'))
    date_obj = datetime.date(year, month, day)

    # Month name
    month_name = date_obj.strftime("%B")

    # Construct the word date
    day_suffix = get_day_suffix(day)
    word_date = f"{day}{day_suffix} {month_name[:3]} {year}"

    # print(word_date)
    return word_date

# Function to calculate per-player statistics for each session
def calculate_session_statistics(bank_data):

    anonymous_players = {'Dharmik': 'D_Anonymous', 'Ananth': 'Pro'}

    # Initialize a DataFrame to store results
    session_results = []

    account = 'Adv Plus Banking - 1686'

    # print(bank_data)

    # Group by session number
    grouped = bank_data.groupby('Session Number')

    # print(grouped)

    for session_number, transactions in grouped:
        # print(session_number)
        # print(transactions)
        session_data = {
            'Session Number': session_number,
            'Session Date': convert_date_to_words(str(transactions.iloc[0]['Setup Date'])),
            'Total BuyIns': 0,
            'Total Payouts': 0,
            'Players': []
        }

        # Process each transaction in the session
        for _, row in transactions.iterrows():
            # print(f"\n{session_data}")
            # print()
            # print(row['Setup Date'])
            player = row['From'] if row['From'] != account else row['To']
            if player in anonymous_players:
                player = anonymous_players[player]
            is_buy_in = pd.isna(row['To'])

            # print(is_buy_in, player)

            # Update totals and individual player stats
            if is_buy_in:
                session_data['Total BuyIns'] += row['Amount']
            else:
                session_data['Total Payouts'] += row['Amount']

            # Add/update player stats
            player_stats = next((p for p in session_data['Players'] if p['Player'] == player), None)
            if not player_stats:
                player_stats = {
                    'Player': player,
                    # 'Session Date': convert_date_to_words(str(row['Setup Date'])),
                    'BuyIn_Times': 0,
                    'BuyIns': 0,
                    'Payouts': 0,
                    'ProfitLoss': 0
                }
                session_data['Players'].append(player_stats)

            if is_buy_in:
                player_stats['BuyIns'] += row['Amount']
                player_stats['BuyIn_Times'] += 1
            else:
                player_stats['Payouts'] += row['Amount']



        # Add/update player stats
        player_stats = next((p for p in session_data['Players'] if p['Player'] == 'Meet'), None)
        # Add "Meet Gandhi" stats
        meet_profit_loss = round(session_data['Total BuyIns'] - player_stats['BuyIns'] - session_data['Total Payouts'], 2)
        # print(meet_profit_loss)
        meet_payout = round(player_stats['BuyIns'] + meet_profit_loss, 2)
        # print(player_stats['BuyIns'], meet_payout)
        player_stats['Payouts'] = meet_payout
        # session_data['Players'].append({
        #     'Player': 'Meet Gandhi',
        #     'BuyIns': max(p['BuyIns'] for p in session_data['Players'] if p['Player'] != 'Meet Gandhi'),
        #     'Payouts': 0,
        #     'ProfitLoss': meet_profit_loss
        # })

        # Calculate profit/loss for each player
        for player_stats in session_data['Players']:
            player_stats['ProfitLoss'] = round(player_stats['Payouts'] - player_stats['BuyIns'], 2)

        session_results.append(session_data)

    return session_results

# Main process
if __name__ == "__main__":
    # Parse updated bank statement
    bank_data = parse_updated_bank_statement(bank_statement_file)

    # Calculate statistics
    session_statistics = calculate_session_statistics(bank_data)

    # Flatten and save results
    flattened_results = []
    for session in session_statistics:
        for player_stats in session['Players']:
            flattened_results.append({
                'Session Number': session['Session Number'],
                'Session Date': session['Session Date'],
                'Player': player_stats['Player'],
                'BuyIn_Times': player_stats['BuyIn_Times'],
                'BuyIns': player_stats['BuyIns'],
                'Payouts': player_stats['Payouts'],
                'ProfitLoss': player_stats['ProfitLoss']
            })

    results_df = pd.DataFrame(flattened_results)
    print("Player Statistics by Session:")
    print(results_df)

    # Save results to a file
    results_df.to_csv('player_statistics_by_session.csv', index=False)
    print("\nResults saved to 'player_statistics_by_session.csv'.")
