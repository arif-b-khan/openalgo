"""
Database models for ATM Straddle + VWAP strategy tracking and performance metrics.
Stores signals, trades, positions, and daily performance summaries.
"""

from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Boolean, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import NullPool
import os

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
    
    Stores:
    - When signal was generated (timestamp)
    - Market conditions (price, VWAP, ATR, implied volatility)
    - Signal direction (LONG/SHORT/NEUTRAL)
    """
    __tablename__ = "straddle_signals"
    
    id = Column(Integer, primary_key=True)
    underlying = Column(String(20), nullable=False)  # e.g., "NIFTY", "BANKNIFTY"
    exchange = Column(String(10), nullable=False, default="NFO")
    
    # Market data at signal generation
    spot_price = Column(Float, nullable=False)  # LTP of underlying
    vwap = Column(Float, nullable=False)  # VWAP from last 100 5-min candles
    atr_14 = Column(Float, nullable=False)  # ATR (14 periods) for volatility
    
    # Signal logic
    signal_type = Column(String(10), nullable=False)  # "LONG" if price < VWAP, "SHORT" if price > VWAP, "NEUTRAL"
    previous_signal = Column(String(10), nullable=True)  # Previous signal (to detect reversals)
    
    # Straddle strike setup
    atm_strike = Column(Float, nullable=False)  # ATM strike price used for straddle
    expiry_date = Column(String(20), nullable=False)  # e.g., "26APR2024"
    
    # Risk management
    stoploss_points = Column(Float, nullable=False)  # SL = ATR (per 2:1 ratio)
    target_points = Column(Float, nullable=False)  # TP = 2 × ATR
    quantity_per_leg = Column(Integer, nullable=False)  # Quantity for CE and PE
    
    # System info
    signal_timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_underlying_timestamp", "underlying", "signal_timestamp"),
        Index("idx_signal_type", "signal_type"),
    )


class StraddlePosition(Base):
    """
    Tracks the currently active straddle position (one per signal).
    Links a signal to the actual orders placed and tracks position status.
    
    Stores:
    - Which signal this position came from
    - CE and PE order IDs
    - Entry prices and quantities
    - Current position status
    """
    __tablename__ = "straddle_positions"
    
    id = Column(Integer, primary_key=True)
    signal_id = Column(Integer, nullable=False)  # Foreign key to StraddleSignal
    
    # Position identification
    underlying = Column(String(20), nullable=False)
    exchange = Column(String(10), nullable=False)
    expiry_date = Column(String(20), nullable=False)
    atm_strike = Column(Float, nullable=False)
    
    # Position details
    position_type = Column(String(10), nullable=False)  # "LONG" (BUY straddle) or "SHORT" (SELL straddle)
    quantity = Column(Integer, nullable=False)  # Quantity per leg (CE and PE)
    
    # Order tracking
    ce_symbol = Column(String(50), nullable=False)  # Full CE symbol (e.g., "NIFTY26APR24800CE")
    pe_symbol = Column(String(50), nullable=False)  # Full PE symbol (e.g., "NIFTY26APR24800PE")
    ce_orderid = Column(String(50), nullable=True)  # OpenAlgo order ID for CE
    pe_orderid = Column(String(50), nullable=True)  # OpenAlgo order ID for PE
    
    # Entry details
    ce_entry_price = Column(Float, nullable=True)  # Execution price for CE leg
    pe_entry_price = Column(Float, nullable=True)  # Execution price for PE leg
    entry_timestamp = Column(DateTime, nullable=True)  # When straddle was fully executed
    
    # Position management
    status = Column(String(20), nullable=False)  # "active", "pending", "closed", "rejected"
    is_active = Column(Boolean, nullable=False, default=True)  # Quick flag for active positions
    
    # Metadata
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
    A single straddle position may result in one trade (exit when signal reverses).
    
    Stores:
    - Entry and exit details
    - Profit/loss calculations
    - Trade status and timestamps
    """
    __tablename__ = "straddle_trades"
    
    id = Column(Integer, primary_key=True)
    signal_id = Column(Integer, nullable=False)  # Which signal initiated this trade
    position_id = Column(Integer, nullable=True)  # Link to StraddlePosition (if applicable)
    
    # Trade identification
    underlying = Column(String(20), nullable=False)
    exchange = Column(String(10), nullable=False)
    
    # Trade direction
    trade_type = Column(String(10), nullable=False)  # "LONG" or "SHORT"
    
    # Entry details
    entry_date = Column(String(20), nullable=False)  # Trade date (YYYY-MM-DD format)
    entry_time = Column(DateTime, nullable=False)  # Entry timestamp
    entry_ce_price = Column(Float, nullable=False)  # CE leg entry price
    entry_pe_price = Column(Float, nullable=False)  # PE leg entry price
    entry_total_premium = Column(Float, nullable=False)  # Total debit/credit for straddle
    quantity = Column(Integer, nullable=False)  # Quantity per leg
    
    # Exit details (null until position closed)
    exit_time = Column(DateTime, nullable=True)  # Exit timestamp
    exit_ce_price = Column(Float, nullable=True)  # CE leg exit price
    exit_pe_price = Column(Float, nullable=True)  # PE leg exit price
    exit_total_premium = Column(Float, nullable=True)  # Total credit/debit at exit
    
    # Performance metrics
    premium_paid = Column(Float, nullable=False)  # Total premium paid (LONG) or received (SHORT)
    premium_received = Column(Float, nullable=True)  # Total premium received (or paid if negative)
    realized_pnl = Column(Float, nullable=True)  # Profit/loss on exit
    realized_pnl_percent = Column(Float, nullable=True)  # P&L as percentage
    
    # Trade status
    status = Column(String(20), nullable=False)  # "open", "closed", "cancelled"
    exit_reason = Column(String(50), nullable=True)  # "signal_reversal", "stoploss", "target_hit", "eod_square_off"
    
    # Timestamps
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
    Captures daily P&L, win rate, max loss, trade statistics for easy reporting.
    
    Stores:
    - One row per trading day
    - Aggregated metrics for the entire day
    """
    __tablename__ = "strategy_daily_metrics"
    
    id = Column(Integer, primary_key=True)
    
    # Date and period
    trade_date = Column(String(20), nullable=False, unique=True)  # YYYY-MM-DD format
    underlying = Column(String(20), nullable=False, default="NIFTY")
    
    # Trade statistics
    total_trades = Column(Integer, nullable=False, default=0)  # Total trades initiated
    completed_trades = Column(Integer, nullable=False, default=0)  # Trades that were closed
    winning_trades = Column(Integer, nullable=False, default=0)  # Trades with positive P&L
    losing_trades = Column(Integer, nullable=False, default=0)  # Trades with negative P&L
    
    # P&L summary
    total_realized_pnl = Column(Float, nullable=False, default=0.0)  # All closed trades P&L
    avg_trade_pnl = Column(Float, nullable=True)  # Average P&L per trade
    best_trade_pnl = Column(Float, nullable=True)  # Best performing trade
    worst_trade_pnl = Column(Float, nullable=True)  # Worst performing trade
    
    # Risk metrics
    max_loss = Column(Float, nullable=True)  # Maximum single loss (worst trade)
    max_gain = Column(Float, nullable=True)  # Maximum single gain (best trade)
    max_drawdown = Column(Float, nullable=True)  # Peak-to-trough during day
    
    # Statistics
    win_rate = Column(Float, nullable=True)  # Percentage of winning trades
    profit_factor = Column(Float, nullable=True)  # Sum of wins / Sum of losses
    
    # Long vs Short breakdown
    long_trades = Column(Integer, nullable=False, default=0)
    short_trades = Column(Integer, nullable=False, default=0)
    long_pnl = Column(Float, nullable=False, default=0.0)
    short_pnl = Column(Float, nullable=False, default=0.0)
    
    # Market context (optional)
    opening_price = Column(Float, nullable=True)  # NIFTY open
    closing_price = Column(Float, nullable=True)  # NIFTY close
    daily_range = Column(Float, nullable=True)  # High - Low for the day
    avg_atr = Column(Float, nullable=True)  # Average ATR during the day
    avg_vwap = Column(Float, nullable=True)  # Average VWAP during the day
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = Column(String(500), nullable=True)  # Any additional notes
    
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
