"""
Utility script for ATM Straddle Strategy.
Provides tools for database management, strategy initialization, and performance analysis.
"""

import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.straddle_strategy_db import (
    init_straddle_db, get_session, cleanup_session,
    StraddleSignal, StraddlePosition, StraddleTrade, StrategyDailyMetrics
)
from sqlalchemy import func, desc


class StrategyAnalyzer:
    """Analyze strategy performance and database."""
    
    def __init__(self):
        """Initialize analyzer with database session."""
        self.session = get_session()
    
    def initialize_database(self):
        """Initialize the straddle strategy database."""
        try:
            init_straddle_db()
            print("✓ Database initialized successfully")
            return True
        except Exception as e:
            print(f"✗ Database initialization failed: {e}")
            return False
    
    def get_today_metrics(self) -> Dict:
        """Get today's performance metrics."""
        today = datetime.now().strftime("%Y-%m-%d")
        
        try:
            metrics = self.session.query(StrategyDailyMetrics).filter_by(
                trade_date=today
            ).first()
            
            if metrics:
                return {
                    "date": metrics.trade_date,
                    "total_trades": metrics.total_trades,
                    "completed_trades": metrics.completed_trades,
                    "winning_trades": metrics.winning_trades,
                    "losing_trades": metrics.losing_trades,
                    "total_pnl": metrics.total_realized_pnl,
                    "avg_pnl": metrics.avg_trade_pnl,
                    "win_rate": metrics.win_rate,
                    "best_trade": metrics.best_trade_pnl,
                    "worst_trade": metrics.worst_trade_pnl
                }
            return None
        except Exception as e:
            print(f"Error fetching today's metrics: {e}")
            return None
    
    def get_recent_signals(self, limit: int = 10) -> List[Dict]:
        """Get recent trading signals."""
        try:
            signals = self.session.query(StraddleSignal).order_by(
                desc(StraddleSignal.signal_timestamp)
            ).limit(limit).all()
            
            results = []
            for sig in signals:
                results.append({
                    "id": sig.id,
                    "timestamp": sig.signal_timestamp.isoformat(),
                    "signal_type": sig.signal_type,
                    "spot_price": sig.spot_price,
                    "vwap": sig.vwap,
                    "atr": sig.atr_14,
                    "atm_strike": sig.atm_strike,
                    "expiry": sig.expiry_date
                })
            
            return results
        except Exception as e:
            print(f"Error fetching signals: {e}")
            return []
    
    def get_open_position(self) -> Dict:
        """Get currently active position."""
        try:
            position = self.session.query(StraddlePosition).filter_by(
                is_active=True
            ).first()
            
            if position:
                return {
                    "position_id": position.id,
                    "signal_id": position.signal_id,
                    "type": position.position_type,
                    "ce_symbol": position.ce_symbol,
                    "pe_symbol": position.pe_symbol,
                    "ce_order_id": position.ce_orderid,
                    "pe_order_id": position.pe_orderid,
                    "quantity": position.quantity,
                    "status": position.status,
                    "created_at": position.created_at.isoformat()
                }
            return None
        except Exception as e:
            print(f"Error fetching open position: {e}")
            return None
    
    def get_recent_trades(self, limit: int = 20) -> List[Dict]:
        """Get recent completed trades."""
        try:
            trades = self.session.query(StraddleTrade).filter_by(
                status="closed"
            ).order_by(
                desc(StraddleTrade.entry_time)
            ).limit(limit).all()
            
            results = []
            for trade in trades:
                results.append({
                    "trade_id": trade.id,
                    "type": trade.trade_type,
                    "entry_time": trade.entry_time.isoformat(),
                    "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
                    "entry_premium": trade.premium_paid,
                    "exit_premium": trade.premium_received,
                    "pnl": trade.realized_pnl,
                    "pnl_pct": trade.realized_pnl_percent,
                    "exit_reason": trade.exit_reason,
                    "quantity": trade.quantity
                })
            
            return results
        except Exception as e:
            print(f"Error fetching trades: {e}")
            return []
    
    def get_performance_summary(self, days: int = 7) -> Dict:
        """Get performance summary for the last N days."""
        try:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            
            metrics = self.session.query(StrategyDailyMetrics).filter(
                StrategyDailyMetrics.trade_date >= cutoff_date
            ).all()
            
            if not metrics:
                return None
            
            total_trades = sum(m.total_trades for m in metrics)
            total_pnl = sum(m.total_realized_pnl for m in metrics)
            total_wins = sum(m.winning_trades for m in metrics)
            total_losses = sum(m.losing_trades for m in metrics)
            
            return {
                "period_days": days,
                "total_trading_days": len(metrics),
                "total_trades": total_trades,
                "total_wins": total_wins,
                "total_losses": total_losses,
                "total_pnl": total_pnl,
                "winning_days": sum(1 for m in metrics if m.total_realized_pnl > 0),
                "losing_days": sum(1 for m in metrics if m.total_realized_pnl < 0),
                "avg_daily_pnl": total_pnl / len(metrics) if metrics else 0,
                "win_rate": (total_wins / total_trades * 100) if total_trades > 0 else 0,
                "daily_metrics": [
                    {
                        "date": m.trade_date,
                        "trades": m.total_trades,
                        "pnl": m.total_realized_pnl,
                        "win_rate": m.win_rate
                    }
                    for m in sorted(metrics, key=lambda x: x.trade_date)
                ]
            }
        except Exception as e:
            print(f"Error calculating performance summary: {e}")
            return None
    
    def print_status(self):
        """Print current status of strategy."""
        print("\n" + "=" * 70)
        print("NIFTY ATM STRADDLE + VWAP STRATEGY - STATUS REPORT")
        print("=" * 70 + "\n")
        
        # Today's metrics
        today_metrics = self.get_today_metrics()
        if today_metrics:
            print(f"TODAY'S PERFORMANCE ({today_metrics['date']}):")
            print(f"  Total Trades: {today_metrics['total_trades']}")
            print(f"  Completed: {today_metrics['completed_trades']}")
            print(f"  Wins/Losses: {today_metrics['winning_trades']}/{today_metrics['losing_trades']}")
            print(f"  Total P&L: ₹{today_metrics['total_pnl']:,.2f}")
            print(f"  Avg Trade: ₹{today_metrics['avg_pnl']:.2f}")
            print(f"  Win Rate: {today_metrics['win_rate'] if today_metrics['win_rate'] else 'N/A'}%")
            print()
        
        # Open position
        open_pos = self.get_open_position()
        if open_pos:
            print(f"ACTIVE POSITION:")
            print(f"  Type: {open_pos['type']}")
            print(f"  CE: {open_pos['ce_symbol']} (Order: {open_pos['ce_order_id']})")
            print(f"  PE: {open_pos['pe_symbol']} (Order: {open_pos['pe_order_id']})")
            print(f"  Quantity: {open_pos['quantity']} per leg")
            print(f"  Status: {open_pos['status']}")
            print()
        else:
            print("ACTIVE POSITION: None\n")
        
        # Recent signals
        print("RECENT SIGNALS:")
        signals = self.get_recent_signals(5)
        if signals:
            for sig in signals:
                print(f"  {sig['timestamp']} - {sig['signal_type']} @ {sig['spot_price']} (VWAP: {sig['vwap']}, ATR: {sig['atr']})")
        else:
            print("  No signals yet\n")
        print()
        
        # Recent trades
        print("RECENT TRADES:")
        trades = self.get_recent_trades(5)
        if trades:
            for trade in trades:
                pnl_str = f"₹{trade['pnl']:,.2f} ({trade['pnl_pct']:.2f}%)"
                print(f"  {trade['entry_time']} - {trade['type']} {trade['quantity']} - {pnl_str} ({trade['exit_reason']})")
        else:
            print("  No closed trades yet\n")
        print()
        
        # Performance summary
        print("7-DAY PERFORMANCE SUMMARY:")
        summary = self.get_performance_summary(7)
        if summary and summary['total_trading_days'] > 0:
            print(f"  Trading Days: {summary['total_trading_days']}")
            print(f"  Total P&L: ₹{summary['total_pnl']:,.2f}")
            print(f"  Total Trades: {summary['total_trades']}")
            print(f"  Win Rate: {summary['win_rate']:.2f}%")
            print(f"  Avg Daily P&L: ₹{summary['avg_daily_pnl']:,.2f}")
        else:
            print("  Not enough data\n")
        
        print("\n" + "=" * 70 + "\n")
    
    def cleanup(self):
        """Clean up database session."""
        cleanup_session()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="ATM Straddle Strategy Utility")
    parser.add_argument(
        "--init", action="store_true",
        help="Initialize the strategy database"
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Show current strategy status"
    )
    parser.add_argument(
        "--summary", type=int, nargs="?", const=7,
        help="Show performance summary for last N days (default: 7)"
    )
    
    args = parser.parse_args()
    
    analyzer = StrategyAnalyzer()
    
    try:
        if args.init:
            analyzer.initialize_database()
        elif args.status:
            analyzer.print_status()
        elif args.summary is not None:
            summary = analyzer.get_performance_summary(args.summary)
            if summary:
                print(f"\n7-DAY PERFORMANCE SUMMARY:")
                print(f"  Trading Days: {summary['total_trading_days']}")
                print(f"  Total P&L: ₹{summary['total_pnl']:,.2f}")
                print(f"  Total Trades: {summary['total_trades']}")
                print(f"  Winning Days: {summary['winning_days']}")
                print(f"  Losing Days: {summary['losing_days']}")
                print(f"  Win Rate: {summary['win_rate']:.2f}%")
                print(f"  Average Daily P&L: ₹{summary['avg_daily_pnl']:,.2f}")
        else:
            analyzer.print_status()
    
    finally:
        analyzer.cleanup()


if __name__ == "__main__":
    main()
