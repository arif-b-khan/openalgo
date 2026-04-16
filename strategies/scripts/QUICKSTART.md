# NIFTY ATM Straddle + VWAP Strategy - Quick Start Guide

Welcome! Your trading strategy is now fully implemented and ready to deploy. Here's what's been created and how to get started.

## 📦 What's Been Created

### 1. **Database Schema** (`database/straddle_strategy_db.py`)
   - ✅ 4 SQLAlchemy models for tracking:
     - `StraddleSignal` — VWAP-based trading signals with ATR and technical indicators
     - `StraddlePosition` — Active positions linking signals to orders
     - `StraddleTrade` — Completed trades with entry/exit P&L
     - `StrategyDailyMetrics` — Daily performance summaries
   - ✅ Database file: `db/straddle_strategy.db` (already initialized)

### 2. **Main Strategy Logic** (`strategies/scripts/nifty_atm_straddle_vwap.py`)
   - ✅ ~750 lines of production-ready code including:
     - VWAP and ATR(14) indicator calculations
     - Signal generation (LONG/SHORT based on price vs VWAP)
     - Multi-leg basket order placement (CE + PE straddles)
     - Database logging of all signals, trades, and positions
     - Comprehensive error handling and logging
     - Expiry date resolution for weekly options

### 3. **Configuration File** (`strategies/scripts/strategy_config.json`)
   - ✅ Default settings: NIFTY, 50 contracts per leg, 5-minute checks

### 4. **Utility Tools** (`strategies/scripts/strategy_utils.py`)
   - ✅ Command-line utilities:
     - `--init` — Initialize database (done ✓)
     - `--status` — View current position and trade status
     - `--summary N` — Analyze performance for last N days

### 5. **Comprehensive Documentation** (`strategies/scripts/README_STRADDLE_STRATEGY.md`)
   - ✅ Complete setup guide, troubleshooting, advanced usage

---

## 🚀 Next Steps (Quick Timeline)

### Today (Setup — 10 minutes)

1. **Enable Analyzer Mode (Paper Trading)**
   ```
   OpenAlgo UI → Settings → Analyzer → Toggle ON
   ```

2. **Upload Strategy to OpenAlgo**
   ```
   OpenAlgo UI → Settings → Python Strategy → Upload → Select nifty_atm_straddle_vwap.py
   ```

3. **Schedule Daily Execution**
   ```
   Settings → Python Strategy → Find "NIFTY_ATM_Straddle_VWAP"
   → Edit Schedule → Start: 09:15, Stop: 15:30 → Save
   ```

### Tomorrow (First Trading Day)

- Strategy runs automatically at 9:15 AM IST
- Watch logs in real-time:
  ```bash
  cd strategies/scripts/
  uv run strategy_utils.py --status
  ```

### Days 2-14 (Paper Trading Period)

- Monitor daily P&L:
  ```bash
  uv run strategy_utils.py --summary 7
  ```
- Look for:
  - Win rate > 50%
  - Consistent positive days
  - Reasonable daily P&L (no huge drawdowns)

### Week 3+ (Optional: Go Live)

When satisfied with results:
1. Disable Analyzer Mode: `Settings → Analyzer → Toggle OFF`
2. Ensure broker credentials point to LIVE account
3. Strategy will now execute real trades (code unchanged)

---

## 📊 How It Works (Technical Overview)

```
Every 5 Minutes During 9:15 AM - 3:30 PM IST:
┌─────────────────────────────────────────────────────┐
│                                                     │
│ 1. Fetch 100 5-minute candles for NIFTY spot       │
│    (data source: broker API)                        │
│                                                     │
│ 2. Calculate VWAP and ATR(14)                       │
│    - VWAP = Σ(TP×Vol) / ΣVol                       │
│    - ATR = Average True Range (14 periods)          │
│                                                     │
│ 3. Generate Signal:                                 │
│    - IF price < VWAP → LONG (Buy Straddle)         │
│    - IF price > VWAP → SHORT (Sell Straddle)       │
│    - ELSE → Hold                                    │
│                                                     │
│ 4. On Signal Change:                                │
│    - Exit current straddle (if any)                │
│    - Calculate SL = ATR, TP = 2×ATR                 │
│    - Place new basket order:                        │
│      * For LONG: BUY CE + BUY PE                   │
│      * For SHORT: SELL CE + SELL PE                │
│                                                     │
│ 5. Log to Database:                                │
│    - Record signal, position, and trade data        │
│    - Update daily performance metrics               │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 💾 Database Structure

**Location:** `db/straddle_strategy.db`

**Tables:**

| Table | Purpose | Key Fields |
|-------|---------|-----------|
| `straddle_signals` | Trading signals | signal_type, spot_price, vwap, atr_14, atm_strike |
| `straddle_positions` | Active positions | ce_symbol, pe_symbol, ce_orderid, pe_orderid, status |
| `straddle_trades` | Closed trades | entry_price, exit_price, realized_pnl, exit_reason |
| `strategy_daily_metrics` | Daily summaries | total_trades, total_pnl, win_rate, best_trade |

**Query Examples:**

```bash
# View today's signals
sqlite3 db/straddle_strategy.db "SELECT * FROM straddle_signals WHERE DATE(signal_timestamp) = DATE('now');"

# View today's P&L
sqlite3 db/straddle_strategy.db "SELECT total_pnl, win_rate FROM strategy_daily_metrics WHERE trade_date = DATE('now');"

# Export trades to CSV for analysis
sqlite3 db/straddle_strategy.db ".headers on" ".mode csv" ".output trades.csv" "SELECT * FROM straddle_trades;" ".quit"
```

---

## ⚙️ Configuration & Customization

### Quantity Per Leg

Edit `strategies/scripts/strategy_config.json`:
```json
{
  "quantity_per_leg": 50  // Change this (start small: 10, 25, 50)
}
```

### Change Underlying

For BANKNIFTY instead of NIFTY:
```json
{
  "underlying": "BANKNIFTY"
}
```

### Execution Times

Edit in OpenAlgo UI → Settings → Python Strategy → Schedule Settings

---

## 📈 Monitoring Your Strategy

### Real-Time Status

```bash
cd e:\github\openalgo
uv run strategies/scripts/strategy_utils.py --status
```

### Daily Performance

```bash
# Last 7 days
uv run strategies/scripts/strategy_utils.py --summary 7

# Last 30 days
uv run strategies/scripts/strategy_utils.py --summary 30
```

### Live Logs

```bash
# Watch logs in real-time
tail -f log/openalgo_*.log | grep -i straddle
```

---

## ⚠️ Important Reminders

### Before Going Live

- ✅ Test in sandbox mode for at least 1-2 weeks
- ✅ Verify win rate > 50%
- ✅ Check that daily losses are within acceptable limits
- ✅ Ensure broker credentials are for LIVE account (not sandbox)

### Risk Management

- Start with `quantity_per_leg: 10` (not 50)
- Monitor daily P&L — stop if losing > ₹10k (adjustable)
- Verify sufficient margin available for straddles
- Note: Straddles require 2x margin of single leg due to short volatility

### Market Hours

- Strategy only runs **9:15 AM - 3:30 PM IST**
- Weekly expiry: Updates to next Thursday automatically
- Holidays: Skips automatically (weekend/market closed check)

---

## 🔧 Troubleshooting

### Strategy Not Running

**Check 1:** Analyzer mode enabled?
```bash
curl http://localhost:5000/api/v1/analyzer
# Should show: {"status": "enabled"}
```

**Check 2:** API key valid?
```bash
# Verify in OpenAlgo → Settings → API Keys
```

**Check 3:** Logs?
```bash
tail -f log/errors.jsonl | head -20
```

### Orders Not Executing

1. Check sandbox funds: `Settings → Analyzer → View Funds`
2. Check order logs: `Settings → Python Strategy → View Logs`
3. Verify expiry date is valid: `sqlite3 db/straddle_strategy.db "SELECT DISTINCT expiry_date FROM straddle_signals;"`

### No P&L Data

If trades executed but DB shows no data:
```bash
uv run strategies/scripts/strategy_utils.py --init  # Reinitialize (safe)
```

---

## 📞 Support Resources

- **Strategy Logic:** See comments in `nifty_atm_straddle_vwap.py`
- **Database Queries:** See `README_STRADDLE_STRATEGY.md` → Database section
- **OpenAlgo Issues:** See main CLAUDE.md → Troubleshooting
- **API Documentation:** http://localhost:5000/api/docs

---

## 📋 Deployment Checklist

- [ ] Database initialized: `uv run strategy_utils.py --init`
- [ ] Analyzer mode enabled in OpenAlgo
- [ ] Strategy uploaded to OpenAlgo
- [ ] Schedule configured (9:15 AM start)
- [ ] Config file reviewed (`strategy_config.json`)
- [ ] First day: Monitor logs closely
- [ ] Days 2-14: Collect performance data
- [ ] Decision: Continue paper trading or go live?

---

## 🎯 Success Metrics (Paper Trading Phase)

| Metric | Target | Status |
|--------|--------|--------|
| Win Rate | > 50% | ⏳ (in progress) |
| Avg Daily P&L | Positive | ⏳ (in progress) |
| Max Daily Loss | < 10% of capital | ⏳ (in progress) |
| Consistency | 3+ profitable days/week | ⏳ (in progress) |
| Signal Generation | 3-8 trades/day | ⏳ (in progress) |

---

## 🚀 Ready to Deploy?

1. **Start OpenAlgo:**
   ```bash
   cd e:\github\openalgo
   uv run app.py
   ```

2. **Upload & Schedule Strategy (via UI):** http://localhost:5000

3. **Monitor Tomorrow Morning:**
   ```bash
   cd strategies/scripts/
   uv run strategy_utils.py --status
   ```

Good luck! Your strategy is production-ready and waiting for the market to open. 📈

---

**Questions?** See `README_STRADDLE_STRATEGY.md` for comprehensive documentation.
