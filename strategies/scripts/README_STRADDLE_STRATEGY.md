# ATM Straddle + VWAP Strategy for OpenAlgo

A sophisticated Python trading strategy for NIFTY options that combines VWAP-based signal generation with ATM straddle execution and volatility-based position sizing.

## Overview

**Strategy Logic:**
- Calculates VWAP on 5-minute NIFTY spot candles
- Generates signals based on price relative to VWAP
- Executes ATM straddles (buy or sell) based on signals
- Uses ATR(14) for volatility-based stoploss and target calculation
- Uses 2:1 risk/reward ratio (SL = ATR points, Target = 2×ATR points)
- Exits positions when VWAP signal reverses (price crosses VWAP)
- Runs during market hours (9:15 AM - 3:30 PM IST)
- Checks for new signals every 5 minutes

**Paper Trading:** Run in sandbox mode first to validate strategy performance before going live

**Files Included:**
- `nifty_atm_straddle_vwap.py` — Main strategy engine
- `strategy_config.json` — Strategy configuration (customize as needed)
- `strategy_utils.py` — Utility script for database management and analysis
- `../../database/straddle_strategy_db.py` — Database models and schema

---

## Prerequisites

1. **OpenAlgo Installation** — Ensure OpenAlgo is installed and running
   ```bash
   cd /path/to/openalgo
   uv run app.py  # Development mode
   ```

2. **API Key** — Generate an API key in OpenAlgo
   - Login to OpenAlgo UI (default: http://localhost:5000)
   - Navigate to API Keys section
   - Create a new API key and copy it

3. **Database** — Initialize the strategy database (one-time setup)
   ```bash
   cd strategies/scripts/
   uv run strategy_utils.py --init
   ```

4. **Python 3.12+** — Required by OpenAlgo (use `uv` as specified in main CLAUDE.md)

---

## Setup and Deployment

### 1. Initialize Strategy Database

Run this once to create the database tables:

```bash
cd /path/to/openalgo/strategies/scripts
uv run strategy_utils.py --init
```

Output (on success):
```
✓ Database initialized successfully
```

This creates `db/straddle_strategy.db` with tables for signals, positions, trades, and daily metrics.

### 2. Verify Configuration

Check `strategy_config.json`:

```json
{
  "underlying": "NIFTY",
  "exchange": "NSE",
  "nfo_exchange": "NFO",
  "quantity_per_leg": 50,
  "check_interval": 300,
  "notes": "..."
}
```

Customize if needed:
- `quantity_per_leg`: Number of contracts per CE/PE leg (default: 50)
- `check_interval`: Minutes between signal checks (default: 300 = 5 min)
- `underlying`: NIFTY or BANKNIFTY
- Other parameters typically left as-is

### 3. Upload Strategy to OpenAlgo

**Option A: Via Web UI**

1. Open OpenAlgo: http://localhost:5000
2. Navigate to **Settings → Python Strategy**
3. Click **Upload Strategy**
4. Select `nifty_atm_straddle_vwap.py`
5. Enter strategy name: `NIFTY_ATM_Straddle_VWAP`
6. Click **Upload**

**Option B: Via API** (Advanced)

```bash
curl -X POST http://localhost:5000/python/upload \
  -F "strategy=@nifty_atm_straddle_vwap.py" \
  -F "strategy_name=NIFTY_ATM_Straddle_VWAP"
```

---

## Running the Strategy

### Paper Trading Mode (Sandbox)

**Step 1: Enable Analyzer Mode (Paper Trading)**

1. Open OpenAlgo UI: http://localhost:5000
2. Navigate to **Settings → Analyzer**
3. Toggle **Analyzer Mode: ON**
4. Set starting capital (default: ₹1 Crore)
5. Save settings

**Step 2: Schedule Strategy Execution**

1. Go to **Settings → Python Strategy**
2. Find your uploaded strategy: `NIFTY_ATM_Straddle_VWAP`
3. Click **Edit Schedule**
4. Set:
   - **Start Time:** 09:15 (market open)
   - **Repeat:** Daily
   - **Stop Time:** 15:30 (market close)
5. Click **Start**

Strategy will now run automatically each trading day at 9:15 AM IST.

**Step 3: Monitor Execution**

- Real-time logs: **Settings → Python Strategy → View Logs**
- Open terminal and run:
  ```bash
  cd strategies/scripts/
  uv run strategy_utils.py --status
  ```
  
Output example:
```
==============================================================================
NIFTY ATM STRADDLE + VWAP STRATEGY - STATUS REPORT
==============================================================================

TODAY'S PERFORMANCE (2024-04-16):
  Total Trades: 3
  Completed: 3
  Wins/Losses: 2/1
  Total P&L: ₹4,250.00
  Avg Trade: ₹1,416.67
  Win Rate: 66.67%
```

### Live Trading Mode

Once you're satisfied with paper trading results (typically 1-2 weeks):

**Step 1: Disable Analyzer Mode**

1. Open OpenAlgo UI: http://localhost:5000
2. Navigate to **Settings → Analyzer**
3. Toggle **Analyzer Mode: OFF**
4. Save settings

**Step 2: Ensure Broker Credentials Are Live**

1. Go to **Settings → Broker Credentials**
2. Verify broker login credentials match your LIVE account (not sandbox)
3. Save

**Step 3: Resume Strategy**

1. The same strategy script will now execute against LIVE broker
2. All orders will go to your live broker account
3. No code changes required

> **Note:** Disabling analyzer mode routes all orders to your live broker. Ensure broker credentials are correct before proceeding.

---

## Database and Performance Tracking

All trades, signals, and performance metrics are stored in `db/straddle_strategy.db`.

### Query Recent Data

```bash
cd strategies/scripts/
uv run strategy_utils.py --status
```

### View Performance Summary

```bash
# Last 7 days
uv run strategy_utils.py --summary 7

# Last 30 days  
uv run strategy_utils.py --summary 30
```

### Direct Database Access

Connect to the SQLite database directly:

```bash
sqlite3 db/straddle_strategy.db

# View today's signals:
sqlite> SELECT * FROM straddle_signals WHERE DATE(signal_timestamp) = DATE('now');

# View today's trades:
sqlite> SELECT * FROM straddle_trades WHERE DATE(trade_date) = DATE('now');

# View daily performance:
sqlite> SELECT * FROM strategy_daily_metrics ORDER BY trade_date DESC LIMIT 7;
```

### Database Tables

| Table | Purpose |
|-------|---------|
| `straddle_signals` | Trading signals (LONG/SHORT) with VWAP/ATR values |
| `straddle_positions` | Active and closed positions (links signals to orders) |
| `straddle_trades` | Completed trades with entry/exit prices and P&L |
| `strategy_daily_metrics` | Daily summaries (trades, P&L, win rate, max loss) |

---

## Strategy Parameters and Customization

### Signal Generation

**VWAP Calculation:**
- Time period: Last 100 5-minute candles (500 minutes ≈ 8+ hours)
- Formula: Cumulative(Typical Price × Volume) / Cumulative(Volume)
- Typical Price = (High + Low + Close) / 3

**Signal Logic:**
- **LONG (Buy Straddle):** Price < VWAP
- **SHORT (Sell Straddle):** Price > VWAP
- **Exit:** Signal reverses (price crosses VWAP)

**ATR Calculation:**
- Period: 14 candles
- Uses True Range method for volatility
- Stoploss = ATR (1 part)
- Target = 2×ATR (2 parts)

### Position Sizing

**Default:**
- Quantity per leg: 50 contracts
- Both CE and PE legs use same quantity

**Customization:**
Edit `strategy_config.json`:
```json
{
  "quantity_per_leg": 100  // Increase to 100 contracts
}
```

### Execution Timing

**Default:**
- Start time: 9:15 AM IST (market open)
- Stop time: 3:30 PM IST (market close)
- Check interval: 5 minutes
- Day: Monday-Friday (auto-skips weekends)

**Customization:**
Edit schedule in OpenAlgo UI (Settings → Python Strategy).

---

## Troubleshooting

### Strategy Not Starting

**Check 1: Analyzer Mode**
```bash
# Verify analyzer mode is enabled
curl http://localhost:5000/api/v1/analyzer
# Should return {"status": "enabled"}
```

**Check 2: API Credentials**
- Verify API key is correct in strategy_config.json or environment variable
- Check API key has "placeorder" and "quotes" permissions

**Check 3: Logs**
```bash
# View real-time logs
tail -f log/openalgo_*.log | grep -i "straddle\|strategy"

# Or check errors
cat log/errors.jsonl | tail -20
```

### Orders Not Executing

**Check 1: Sandbox Funds**
```bash
sqlite3 db/sandbox.db
sqlite> SELECT * FROM sandbox_funds;
```
- If `available_balance` is 0, increase `total_capital` in analyzer settings

**Check 2: Basket Order API**
- Verify `/api/v1/basket_order` endpoint is available
- Check that both CE and PE symbols are valid (correct expiry date, strike format)

**Check 3: Market Hours**
- Strategy only checks signals during 9:15 AM - 3:30 PM IST
- Verify system time is correct: `date` command

### Incorrect P&L Calculations

**Check 1: Database Integrity**
```bash
sqlite3 db/straddle_strategy.db
sqlite> PRAGMA integrity_check;
# Should return "ok"
```

**Check 2: Trade Status**
- Verify trades have both `entry_time` and `exit_time`
- Check `premium_paid` vs `premium_received` calculations
- Review `exit_reason` field (should be "signal_reversal" for normal exits)

### Strategy Performance Metrics Missing

**Rebuild Daily Metrics:**

If daily metrics are missing, manually recalculate:

```python
from database.straddle_strategy_db import get_session, StraddleTrade, StrategyDailyMetrics
from datetime import datetime

session = get_session()

# Get all completed trades for today
trades = session.query(StraddleTrade).filter(
    StraddleTrade.status == "closed",
    StraddleTrade.trade_date >= datetime.today()
).all()

# Manually create daily metrics
metrics = StrategyDailyMetrics(
    trade_date=datetime.now().strftime("%Y-%m-%d"),
    total_trades=len(trades),
    completed_trades=len(trades),
    winning_trades=sum(1 for t in trades if t.realized_pnl > 0),
    losing_trades=sum(1 for t in trades if t.realized_pnl < 0),
    total_realized_pnl=sum(t.realized_pnl for t in trades),
)
session.add(metrics)
session.commit()
```

---

## Advanced Usage

### Multi-Day Performance Analysis

```python
from strategies.scripts.strategy_utils import StrategyAnalyzer

analyzer = StrategyAnalyzer()
summary = analyzer.get_performance_summary(30)  # Last 30 days

print(f"Total P&L: ₹{summary['total_pnl']:,.2f}")
print(f"Win Rate: {summary['win_rate']:.2f}%")
print(f"Average Daily: ₹{summary['avg_daily_pnl']:,.2f}")
```

### Export Data for Analysis

```bash
# Export trades to CSV
sqlite3 db/straddle_strategy.db
sqlite> .headers on
sqlite> .mode csv
sqlite> .output trades.csv
sqlite> SELECT * FROM straddle_trades;
sqlite> .quit

# View in Excel or Python
import pandas as pd
trades = pd.read_csv('trades.csv')
print(trades.groupby('trade_type')['realized_pnl'].describe())
```

### Backtest Strategy (Optional)

Use OpenAlgo's Analyzer mode with historical data to backtest without placing real orders:

1. Enable Analyzer mode
2. Set historical date range
3. Run strategy
4. Review P&L without broker risk

---

## Important Notes

### Risk Management

1. **Start Small:** Begin with `quantity_per_leg: 10` for first few days
2. **Monitor Daily Losses:** Set maximum daily loss limit and stop trading if exceeded
3. **Margin Requirements:** Ensure sufficient broker margin for straddles
4. **Leverage Settings:** Check sandbox leverage settings match your broker's NRML/futures limits

### Market Hours

- Strategy runs **9:15 AM - 3:30 PM IST only** (configured in OpenAlgo)
- Weekly expiry updates dynamically (next Thursday)
- Monthly expiry handling: Manually update if switching strategies

### Analyzer Mode Production Setup

When running analyzer mode in production (paper trading for extended periods):

- Set up daily capital reset (default: Sunday 00:00 IST)
- Monitor sandbox funds balance
- Review error logs daily for failed orders
- Backup `db/straddle_strategy.db` regularly

---

## Support and Debugging

### Enable Debug Logging

Set in OpenAlgo `.env`:
```
FLASK_DEBUG=True
LOG_LEVEL=DEBUG
```

Then restart:
```bash
cd /path/to/openalgo
uv run app.py
```

### View Real-Time Execution

```bash
# Terminal 1: Watch logs
tail -f log/openalgo_*.log | grep -i straddle

# Terminal 2: Check status every minute
watch -n 60 'uv run strategies/scripts/strategy_utils.py --status'
```

### Common Issues && Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| "API_KEY not found" | Missing API key | Set `API_KEY` in `.env` or pass as env var |
| "No candle data available" | Broker API down or market closed | Check market hours (9:15-15:30 IST) |
| "Basket order failed" | Invalid symbols or exchange | Verify expiry date and strike format |
| "Permission denied" on DB | File permissions issue | `chmod 666 db/straddle_strategy.db` |
| "Signal not detected" | VWAP calculation error | Check that volumes > 0 in candle data |

---

## Next Steps

1. **Week 1:** Run in sandbox mode, monitor daily
2. **Week 2:** Validate win rate > 50% and daily P&L stability
3. **Week 3+:** Optional migration to live trading
4. **Ongoing:** Track performance, adjust quantity or ATR period if needed

Good luck with your trading! 📈
