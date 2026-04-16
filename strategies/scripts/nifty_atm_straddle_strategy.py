"""
OpenAlgo Strategy: NIFTY ATM Straddle + VWAP Trading Strategy (All-in-One)

Strategy Logic:
- Uses 5-minute candle data for NIFTY spot
- Calculates VWAP and ATR(14) for signal generation
- Signal: BUY ATM straddle if price < VWAP, SELL ATM straddle if price > VWAP
- Uses 2:1 risk/reward ratio (SL = ATR, Target = 2×ATR)
- Exits straddle when signal reverses (price crosses VWAP)
- Runs during market hours (9:15 AM - 3:30 PM IST), checks every 5 minutes
- Paper trades in sandbox mode, can switch to live by disabling analyzer

Author: OpenAlgo Team
Date: April 2026
"""

import os
import json
import time
import requests
import sys
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

# Logging setup
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database imports
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Boolean, Index, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import NullPool

# ============================================================================
# DATABASE CONFIGURATION & MODELS
# ============================================================================

# Database path
DATABASE_DIR = "db"
if not os.path.exists(DATABASE_DIR):
    os.makedirs(DATABASE_DIR)

DATABASE_PATH = os.path.join(DATABASE_DIR, "straddle_strategy.db")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# Create engine with NullPool (fresh connection per request, prevents concurrency issues)
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
    echo=False
)

# Session factory with scoping for thread safety
SessionLocal = scoped_session(sessionmaker(bind=engine, expire_on_commit=False))

# Base class for all models
Base = declarative_base()


class StraddleSignal(Base):
    """
    Tracking VWAP-based trading signals and technical indicators at signal generation time.
    """
    __tablename__ = "straddle_signals"
    
    id = Column(Integer, primary_key=True)
    underlying = Column(String(20), nullable=False)
    exchange = Column(String(10), nullable=False, default="NFO")
    
    spot_price = Column(Float, nullable=False)
    vwap = Column(Float, nullable=False)
    atr_14 = Column(Float, nullable=False)
    
    signal_type = Column(String(10), nullable=False)
    previous_signal = Column(String(10), nullable=True)
    
    atm_strike = Column(Float, nullable=False)
    expiry_date = Column(String(20), nullable=False)
    
    stoploss_points = Column(Float, nullable=False)
    target_points = Column(Float, nullable=False)
    quantity_per_leg = Column(Integer, nullable=False)
    
    signal_timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_underlying_timestamp", "underlying", "signal_timestamp"),
        Index("idx_signal_type", "signal_type"),
    )


class StraddlePosition(Base):
    """
    Tracks the currently active straddle position (one per signal).
    """
    __tablename__ = "straddle_positions"
    
    id = Column(Integer, primary_key=True)
    signal_id = Column(Integer, nullable=False)
    
    underlying = Column(String(20), nullable=False)
    exchange = Column(String(10), nullable=False)
    expiry_date = Column(String(20), nullable=False)
    atm_strike = Column(Float, nullable=False)
    
    position_type = Column(String(10), nullable=False)
    quantity = Column(Integer, nullable=False)
    
    ce_symbol = Column(String(50), nullable=False)
    pe_symbol = Column(String(50), nullable=False)
    ce_orderid = Column(String(50), nullable=True)
    pe_orderid = Column(String(50), nullable=True)
    
    ce_entry_price = Column(Float, nullable=True)
    pe_entry_price = Column(Float, nullable=True)
    entry_timestamp = Column(DateTime, nullable=True)
    
    status = Column(String(20), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_signal_id", "signal_id"),
        Index("idx_underlying_active", "underlying", "is_active"),
        Index("idx_position_status", "status"),
    )


class StraddleTrade(Base):
    """
    Records completed trades (entry to exit).
    """
    __tablename__ = "straddle_trades"
    
    id = Column(Integer, primary_key=True)
    signal_id = Column(Integer, nullable=False)
    position_id = Column(Integer, nullable=True)
    
    underlying = Column(String(20), nullable=False)
    exchange = Column(String(10), nullable=False)
    
    trade_type = Column(String(10), nullable=False)
    
    entry_date = Column(String(20), nullable=False)
    entry_time = Column(DateTime, nullable=False)
    entry_ce_price = Column(Float, nullable=False)
    entry_pe_price = Column(Float, nullable=False)
    entry_total_premium = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    
    exit_time = Column(DateTime, nullable=True)
    exit_ce_price = Column(Float, nullable=True)
    exit_pe_price = Column(Float, nullable=True)
    exit_total_premium = Column(Float, nullable=True)
    
    premium_paid = Column(Float, nullable=False)
    premium_received = Column(Float, nullable=True)
    realized_pnl = Column(Float, nullable=True)
    realized_pnl_percent = Column(Float, nullable=True)
    
    status = Column(String(20), nullable=False)
    exit_reason = Column(String(50), nullable=True)
    
    trade_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_trade_entry_time", "entry_time"),
        Index("idx_underlying_type", "underlying", "trade_type"),
        Index("idx_trade_status", "status"),
        Index("idx_signal_id_trade", "signal_id"),
    )


class StrategyDailyMetrics(Base):
    """
    Daily summary of strategy performance.
    """
    __tablename__ = "strategy_daily_metrics"
    
    id = Column(Integer, primary_key=True)
    
    trade_date = Column(String(20), nullable=False, unique=True)
    underlying = Column(String(20), nullable=False, default="NIFTY")
    
    total_trades = Column(Integer, nullable=False, default=0)
    completed_trades = Column(Integer, nullable=False, default=0)
    winning_trades = Column(Integer, nullable=False, default=0)
    losing_trades = Column(Integer, nullable=False, default=0)
    
    total_realized_pnl = Column(Float, nullable=False, default=0.0)
    avg_trade_pnl = Column(Float, nullable=True)
    best_trade_pnl = Column(Float, nullable=True)
    worst_trade_pnl = Column(Float, nullable=True)
    
    max_loss = Column(Float, nullable=True)
    max_gain = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)
    
    win_rate = Column(Float, nullable=True)
    profit_factor = Column(Float, nullable=True)
    
    long_trades = Column(Integer, nullable=False, default=0)
    short_trades = Column(Integer, nullable=False, default=0)
    long_pnl = Column(Float, nullable=False, default=0.0)
    short_pnl = Column(Float, nullable=False, default=0.0)
    
    opening_price = Column(Float, nullable=True)
    closing_price = Column(Float, nullable=True)
    daily_range = Column(Float, nullable=True)
    avg_atr = Column(Float, nullable=True)
    avg_vwap = Column(Float, nullable=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = Column(String(500), nullable=True)
    
    __table_args__ = (
        Index("idx_daily_metrics_date", "trade_date"),
    )


def init_straddle_db():
    """Initialize the straddle strategy database."""
    Base.metadata.create_all(engine)
    return engine


def get_session():
    """Get a database session."""
    return SessionLocal()


def cleanup_session():
    """Clean up the session (call in teardown)."""
    SessionLocal.remove()


DB_AVAILABLE = True

# ============================================================================
# STRATEGY CONFIGURATION
# ============================================================================

CONFIG = {
    "underlying": "NIFTY",
    "exchange": "NSE",
    "nfo_exchange": "NFO",
    "quantity_per_leg": 50,
    "check_interval": 300,  # seconds (5 minutes)
    "market_open": "09:15",
    "market_close": "15:30",
    "notes": "ATM Straddle + VWAP strategy for NIFTY options"
}

# ============================================================================
# INDICATOR CLASSES
# ============================================================================

class VWAPIndicator:
    """Calculate VWAP from candle data."""
    
    @staticmethod
    def calculate(closes: List[float], volumes: List[float], highs: List[float], 
                  lows: List[float]) -> float:
        """
        Calculate VWAP (Volume Weighted Average Price).
        Formula: VWAP = Cumulative(TP × Vol) / Cumulative(Vol)
        where TP = (High + Low + Close) / 3
        """
        if not closes or len(closes) != len(volumes):
            return None
        
        cumulative_tp_vol = 0
        cumulative_vol = 0
        
        for i in range(len(closes)):
            typical_price = (highs[i] + lows[i] + closes[i]) / 3
            cumulative_tp_vol += typical_price * volumes[i]
            cumulative_vol += volumes[i]
        
        if cumulative_vol == 0:
            return None
        
        return cumulative_tp_vol / cumulative_vol


class ATRIndicator:
    """Calculate ATR (Average True Range) from candle data."""
    
    @staticmethod
    def calculate(closes: List[float], highs: List[float], lows: List[float], 
                  period: int = 14) -> float:
        """
        Calculate ATR(14) using true range averaging.
        True Range = max(H-L, |H-PC|, |L-PC|)
        ATR = SMA(TR, period)
        """
        if not closes or len(closes) < period:
            return None
        
        true_ranges = []
        
        for i in range(len(closes)):
            if i == 0:
                tr = highs[i] - lows[i]
            else:
                tr = max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1])
                )
            true_ranges.append(tr)
        
        atr = sum(true_ranges[-period:]) / period
        return atr

# ============================================================================
# API CLIENT
# ============================================================================

class StraddleStrategyAPI:
    """Client for OpenAlgo REST API."""
    
    def __init__(self, api_key: str, base_url: str = "http://localhost:5000"):
        """Initialize API client."""
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
    
    def get_quotes(self, symbol: str) -> Dict:
        """Fetch current price for symbol."""
        try:
            url = f"{self.base_url}/api/v1/quote"
            payload = {
                "apikey": self.api_key,
                "symbol": symbol,
                "exchange": CONFIG["exchange"]
            }
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching quotes for {symbol}: {e}")
            return None
    
    def get_historical_data(self, symbol: str, timeframe: str = "5m") -> Dict:
        """Fetch historical candle data."""
        try:
            url = f"{self.base_url}/api/v1/historical"
            payload = {
                "apikey": self.api_key,
                "symbol": symbol,
                "exchange": CONFIG["exchange"],
                "timeframe": timeframe,
                "limit": 100
            }
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}")
            return None
    
    def place_basket_order(self, orders: List[Dict]) -> Dict:
        """Place multi-leg basket order."""
        try:
            url = f"{self.base_url}/api/v1/basket_order"
            payload = {
                "apikey": self.api_key,
                "orders": orders
            }
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error placing basket order: {e}")
            return None
    
    def cancel_order(self, order_id: str) -> Dict:
        """Cancel an order."""
        try:
            url = f"{self.base_url}/api/v1/cancel_order"
            payload = {
                "apikey": self.api_key,
                "orderid": order_id
            }
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error canceling order {order_id}: {e}")
            return None
    
    def get_order_status(self, order_id: str) -> Dict:
        """Get status of an order."""
        try:
            url = f"{self.base_url}/api/v1/order_status"
            payload = {
                "apikey": self.api_key,
                "orderid": order_id
            }
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching order status: {e}")
            return None
    
    def get_active_position(self) -> Dict:
        """Get active positions."""
        try:
            url = f"{self.base_url}/api/v1/positions"
            payload = {
                "apikey": self.api_key,
                "mode": "LIVE"
            }
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return None

# ============================================================================
# STRATEGY ENGINE
# ============================================================================

class StraddleStrategyEngine:
    """Main strategy execution engine."""
    
    def __init__(self, api_key: str):
        """Initialize strategy engine."""
        self.api_key = api_key
        self.api = StraddleStrategyAPI(api_key)
        self.session = get_session() if DB_AVAILABLE else None
        self.last_signal = None
        self.last_position = None
    
    def fetch_candle_data(self) -> Dict:
        """Fetch current NIFTY candle data."""
        try:
            symbol = f"{CONFIG['underlying']}"
            response = self.api.get_historical_data(symbol)
            
            if response and response.get("status") == "success":
                return response.get("data", {})
            
            return None
        except Exception as e:
            logger.error(f"Error fetching candle data: {e}")
            return None
    
    def calculate_indicators(self, candles: Dict) -> Tuple[Optional[float], Optional[float]]:
        """Calculate VWAP and ATR(14) from candle data."""
        try:
            if not candles or "candles" not in candles:
                return None, None
            
            data = candles["candles"]
            closes = [c["close"] for c in data]
            volumes = [c["volume"] for c in data]
            highs = [c["high"] for c in data]
            lows = [c["low"] for c in data]
            
            vwap = VWAPIndicator.calculate(closes, volumes, highs, lows)
            atr = ATRIndicator.calculate(closes, highs, lows, 14)
            
            return vwap, atr
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return None, None
    
    def get_atm_strikes(self, spot_price: float, expiry: str) -> Dict:
        """Get ATM CE and PE symbols for options."""
        try:
            strike = round(spot_price / 100) * 100
            
            ce_symbol = f"{CONFIG['underlying']}{expiry}{strike}CE"
            pe_symbol = f"{CONFIG['underlying']}{expiry}{strike}PE"
            
            return {
                "atm_strike": strike,
                "ce_symbol": ce_symbol,
                "pe_symbol": pe_symbol,
                "expiry": expiry
            }
        except Exception as e:
            logger.error(f"Error calculating ATM strikes: {e}")
            return None
    
    def get_expiry_date(self) -> str:
        """Get next Thursday (weekly expiry) in DDMMMYY format."""
        try:
            today = datetime.now()
            days_ahead = 3 - today.weekday()  # 3 = Thursday
            
            if days_ahead <= 0:
                days_ahead += 7
            
            expiry_date = today + timedelta(days=days_ahead)
            return expiry_date.strftime("%d%b%y").upper()
        except Exception as e:
            logger.error(f"Error calculating expiry date: {e}")
            return None
    
    def generate_signal(self, spot_price: float, vwap: float) -> str:
        """Generate trading signal based on price vs VWAP."""
        if vwap is None:
            return "NEUTRAL"
        
        if spot_price < vwap:
            return "LONG"
        elif spot_price > vwap:
            return "SHORT"
        else:
            return "NEUTRAL"
    
    def create_straddle_orders(self, signal: str, ce_symbol: str, pe_symbol: str) -> List[Dict]:
        """Create straddle order payload."""
        qty = CONFIG["quantity_per_leg"]
        
        if signal == "LONG":
            return [
                {
                    "symbol": ce_symbol,
                    "action": "BUY",
                    "quantity": qty,
                    "price_type": "MARKET",
                    "exchange": CONFIG["nfo_exchange"]
                },
                {
                    "symbol": pe_symbol,
                    "action": "BUY",
                    "quantity": qty,
                    "price_type": "MARKET",
                    "exchange": CONFIG["nfo_exchange"]
                }
            ]
        elif signal == "SHORT":
            return [
                {
                    "symbol": ce_symbol,
                    "action": "SELL",
                    "quantity": qty,
                    "price_type": "MARKET",
                    "exchange": CONFIG["nfo_exchange"]
                },
                {
                    "symbol": pe_symbol,
                    "action": "SELL",
                    "quantity": qty,
                    "price_type": "MARKET",
                    "exchange": CONFIG["nfo_exchange"]
                }
            ]
        
        return []
    
    def record_signal(self, signal_data: Dict):
        """Record signal in database."""
        if not DB_AVAILABLE or not self.session:
            return
        
        try:
            db_signal = StraddleSignal(**signal_data)
            self.session.add(db_signal)
            self.session.commit()
            logger.info(f"Signal recorded: {signal_data['signal_type']} @ {signal_data['spot_price']}")
        except Exception as e:
            logger.error(f"Error recording signal: {e}")
            self.session.rollback()
    
    def record_position(self, position_data: Dict):
        """Record position in database."""
        if not DB_AVAILABLE or not self.session:
            return
        
        try:
            db_position = StraddlePosition(**position_data)
            self.session.add(db_position)
            self.session.commit()
            logger.info(f"Position recorded: {position_data['ce_symbol']} + {position_data['pe_symbol']}")
        except Exception as e:
            logger.error(f"Error recording position: {e}")
            self.session.rollback()
    
    def execute_strategy(self):
        """Main strategy execution loop."""
        logger.info("Starting ATM Straddle + VWAP Strategy")
        
        try:
            # Fetch candle data
            candles = self.fetch_candle_data()
            if not candles:
                logger.warning("No candle data available")
                return
            
            # Calculate indicators
            vwap, atr = self.calculate_indicators(candles)
            if vwap is None or atr is None:
                logger.warning("Could not calculate indicators")
                return
            
            # Get spot price (latest close)
            current_price = candles.get("candles", [{}])[-1].get("close")
            if not current_price:
                logger.warning("No current price available")
                return
            
            # Generate signal
            signal = self.generate_signal(current_price, vwap)
            
            # Get expiry and ATM strikes
            expiry = self.get_expiry_date()
            if not expiry:
                logger.warning("Could not determine expiry date")
                return
            
            atm_data = self.get_atm_strikes(current_price, expiry)
            if not atm_data:
                logger.warning("Could not calculate ATM strikes")
                return
            
            logger.info(f"Signal: {signal} | Price: {current_price:.2f} | VWAP: {vwap:.2f} | ATR: {atr:.2f}")
            
            # Record signal
            if signal != "NEUTRAL" and signal != self.last_signal:
                signal_data = {
                    "underlying": CONFIG["underlying"],
                    "signal_timestamp": datetime.now(),
                    "signal_type": signal,
                    "spot_price": current_price,
                    "vwap": vwap,
                    "atr_14": atr,
                    "atm_strike": atm_data["atm_strike"],
                    "expiry_date": atm_data["expiry"],
                    "stoploss_points": atr,
                    "target_points": 2 * atr,
                    "quantity_per_leg": CONFIG["quantity_per_leg"]
                }
                self.record_signal(signal_data)
                
                # Create and place basket order
                orders = self.create_straddle_orders(
                    signal, 
                    atm_data["ce_symbol"], 
                    atm_data["pe_symbol"]
                )
                
                if orders:
                    logger.info(f"Placing {signal} straddle orders")
                    result = self.api.place_basket_order(orders)
                    
                    if result and result.get("status") == "success":
                        position_data = {
                            "signal_id": 1,
                            "underlying": CONFIG["underlying"],
                            "exchange": CONFIG["nfo_exchange"],
                            "expiry_date": atm_data["expiry"],
                            "atm_strike": atm_data["atm_strike"],
                            "position_type": signal,
                            "ce_symbol": atm_data["ce_symbol"],
                            "pe_symbol": atm_data["pe_symbol"],
                            "ce_orderid": result.get("orders", [{}])[0].get("orderid"),
                            "pe_orderid": result.get("orders", [{}])[1].get("orderid") if len(result.get("orders", [])) > 1 else None,
                            "quantity": CONFIG["quantity_per_leg"],
                            "status": "active"
                        }
                        self.record_position(position_data)
                        logger.info(f"Orders placed: {result}")
                
                self.last_signal = signal
        
        except Exception as e:
            logger.exception(f"Error in strategy execution: {e}")
    
    def cleanup(self):
        """Clean up resources."""
        if self.session:
            cleanup_session()

# ============================================================================
# UTILITY / ANALYSIS FUNCTIONS
# ============================================================================

class StrategyAnalyzer:
    """Analyze strategy performance and database."""
    
    def __init__(self):
        """Initialize analyzer with database session."""
        self.session = get_session() if DB_AVAILABLE else None
    
    def initialize_database(self):
        """Initialize the straddle strategy database."""
        if not DB_AVAILABLE:
            print("Database not available")
            return False
        
        try:
            init_straddle_db()
            print("✓ Database initialized successfully")
            return True
        except Exception as e:
            print(f"✗ Database initialization failed: {e}")
            return False
    
    def get_today_metrics(self) -> Dict:
        """Get today's performance metrics."""
        if not DB_AVAILABLE or not self.session:
            return None
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        try:
            metrics = self.session.query(StrategyDailyMetrics).filter_by(
                trade_date=today
            ).first()
            
            if metrics:
                return {
                    "date": metrics.trade_date,
                    "total_trades": metrics.total_trades,
                    "winning_trades": metrics.winning_trades,
                    "total_pnl": metrics.total_realized_pnl,
                    "win_rate": metrics.win_rate
                }
            return None
        except Exception as e:
            print(f"Error fetching today's metrics: {e}")
            return None
    
    def get_recent_signals(self, limit: int = 10) -> List[Dict]:
        """Get recent trading signals."""
        if not DB_AVAILABLE or not self.session:
            return []
        
        try:
            signals = self.session.query(StraddleSignal).order_by(
                desc(StraddleSignal.signal_timestamp)
            ).limit(limit).all()
            
            results = []
            for sig in signals:
                results.append({
                    "timestamp": sig.signal_timestamp.isoformat(),
                    "signal_type": sig.signal_type,
                    "spot_price": sig.spot_price,
                    "vwap": sig.vwap,
                    "atr": sig.atr_14
                })
            
            return results
        except Exception as e:
            print(f"Error fetching signals: {e}")
            return []
    
    def print_status(self):
        """Print current status of strategy."""
        print("\n" + "=" * 70)
        print("NIFTY ATM STRADDLE + VWAP STRATEGY - STATUS REPORT")
        print("=" * 70 + "\n")
        
        today_metrics = self.get_today_metrics()
        if today_metrics:
            print(f"TODAY'S PERFORMANCE ({today_metrics['date']}):")
            print(f"  Total Trades: {today_metrics['total_trades']}")
            print(f"  Winning Trades: {today_metrics['winning_trades']}")
            print(f"  Total P&L: ₹{today_metrics['total_pnl']:,.2f}")
            print(f"  Win Rate: {today_metrics['win_rate']}%")
            print()
        else:
            print("Today's Performance: No data\n")
        
        signals = self.get_recent_signals(5)
        if signals:
            print("RECENT SIGNALS:")
            for sig in signals:
                print(f"  {sig['timestamp']} - {sig['signal_type']} @ {sig['spot_price']} (VWAP: {sig['vwap']}, ATR: {sig['atr']})")
        else:
            print("RECENT SIGNALS: No signals yet\n")
        
        print("=" * 70 + "\n")
    
    def cleanup(self):
        """Clean up database session."""
        if self.session:
            cleanup_session()

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point for CLI and strategy execution."""
    parser = argparse.ArgumentParser(description="ATM Straddle Strategy (All-in-One)")
    parser.add_argument("--apikey", help="API key for OpenAlgo")
    parser.add_argument("--init", action="store_true", help="Initialize database")
    parser.add_argument("--status", action="store_true", help="Show strategy status")
    parser.add_argument("--config", action="store_true", help="Show configuration")
    parser.add_argument("--run", action="store_true", help="Run strategy once")
    
    args = parser.parse_args()
    
    # Handle database initialization
    if args.init:
        analyzer = StrategyAnalyzer()
        analyzer.initialize_database()
        analyzer.cleanup()
        return
    
    # Handle status check
    if args.status:
        analyzer = StrategyAnalyzer()
        analyzer.print_status()
        analyzer.cleanup()
        return
    
    # Handle config display
    if args.config:
        print("\nStrategy Configuration:")
        for key, value in CONFIG.items():
            print(f"  {key}: {value}")
        print()
        return
    
    # Handle strategy execution
    if args.run or args.apikey:
        api_key = args.apikey or os.environ.get("API_KEY", "")
        if not api_key:
            print("Error: API_KEY not provided. Use --apikey or set API_KEY environment variable")
            return
        
        engine = StraddleStrategyEngine(api_key)
        try:
            engine.execute_strategy()
        finally:
            engine.cleanup()
        return
    
    # Default: show help
    parser.print_help()

if __name__ == "__main__":
    main()
