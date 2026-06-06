#!/usr/bin/env python3
"""
trade.py — simple buy/sell CLI for portfolio.csv

Usage:
  python trade.py buy  TICKER SHARES [long_term|trading]
  python trade.py sell TICKER SHARES
  python trade.py show
"""

import sys
import os
import pandas as pd
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

CSV_PATH = 'portfolio.csv'


def load():
    if not os.path.exists(CSV_PATH):
        return pd.DataFrame(columns=['ticker', 'value_usd', 'weight', 'change_today', 'type'])
    return pd.read_csv(CSV_PATH)


def save(df):
    total = df['value_usd'].sum()
    df['weight'] = (df['value_usd'] / total * 100).round(2) if total > 0 else 0
    df['value_usd'] = df['value_usd'].round(2)
    df.to_csv(CSV_PATH, index=False)


def live_price(ticker):
    try:
        price = yf.Ticker(ticker).fast_info.last_price
        if price is None:
            raise ValueError("no price returned")
        return float(price)
    except Exception as e:
        print(f"Error: could not fetch live price for {ticker} ({e})")
        sys.exit(1)


def cmd_buy(args):
    if len(args) < 2:
        print("Usage: python trade.py buy TICKER SHARES [long_term|trading]")
        sys.exit(1)

    ticker = args[0].upper()
    shares = float(args[1])
    stock_type = args[2] if len(args) >= 3 and args[2] in ('long_term', 'trading') else None

    price = live_price(ticker)
    df = load()
    added = round(shares * price, 2)

    if ticker in df['ticker'].values:
        df.loc[df['ticker'] == ticker, 'value_usd'] += added
        if stock_type:
            df.loc[df['ticker'] == ticker, 'type'] = stock_type
        resolved_type = df.loc[df['ticker'] == ticker, 'type'].values[0]
    else:
        resolved_type = stock_type or 'long_term'
        new_row = pd.DataFrame([{
            'ticker': ticker,
            'value_usd': added,
            'weight': 0,
            'change_today': 0.0,
            'type': resolved_type,
        }])
        df = pd.concat([df, new_row], ignore_index=True)

    save(df)
    print(f"Bought  {shares} x {ticker} @ ${price:.2f}  ->  +${added:.2f}  [{resolved_type}]")
    print(f"New {ticker} value: ${df.loc[df['ticker']==ticker,'value_usd'].values[0]:.2f}")


def cmd_sell(args):
    if len(args) < 2:
        print("Usage: python trade.py sell TICKER SHARES")
        sys.exit(1)

    ticker = args[0].upper()
    shares = float(args[1])

    df = load()

    if ticker not in df['ticker'].values:
        print(f"Error: {ticker} is not in your portfolio.")
        sys.exit(1)

    price = live_price(ticker)
    removed = round(shares * price, 2)
    current = df.loc[df['ticker'] == ticker, 'value_usd'].values[0]

    if removed > current + 0.01:
        print(f"Error: trying to sell ${removed:.2f} but {ticker} is only worth ${current:.2f}.")
        sys.exit(1)

    new_val = round(current - removed, 2)
    if new_val <= 0:
        df = df[df['ticker'] != ticker]
        print(f"Sold    {shares} x {ticker} @ ${price:.2f}  ->  -${removed:.2f}  (position closed)")
    else:
        df.loc[df['ticker'] == ticker, 'value_usd'] = new_val
        print(f"Sold    {shares} x {ticker} @ ${price:.2f}  ->  -${removed:.2f}")
        print(f"New {ticker} value: ${new_val:.2f}")

    save(df)


def cmd_show():
    df = load()
    if df.empty:
        print("Portfolio is empty.")
        return

    total = df['value_usd'].sum()

    header = f"{'TICKER':<8}  {'VALUE ($)':>10}  {'WEIGHT':>7}  {'TODAY':>8}  {'TYPE':<12}"
    divider = "-" * len(header)
    print()
    print(header)
    print(divider)
    for _, row in df.iterrows():
        today = row['change_today']
        today_str = f"{float(today):+.2f}%" if today not in ('', None) else "  —"
        print(f"{row['ticker']:<8}  {row['value_usd']:>10.2f}  {row['weight']:>6.2f}%  {today_str:>8}  {row['type']:<12}")
    print(divider)
    print(f"{'TOTAL':<8}  {total:>10.2f}  {'100.00%':>7}")
    print()


COMMANDS = {'buy': cmd_buy, 'sell': cmd_sell, 'show': cmd_show}

if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("Commands: buy TICKER SHARES [type]  |  sell TICKER SHARES  |  show")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == 'show':
        cmd_show()
    else:
        COMMANDS[cmd](sys.argv[2:])
