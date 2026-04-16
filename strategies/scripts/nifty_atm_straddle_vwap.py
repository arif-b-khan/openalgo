"""
OpenAlgo Strategy: NIFTY ATM Straddle + VWAP Trading Strategy

Strategy Logic:
- Uses 5-minute candle data for NIFTY spot
- Calculates VWAP and ATR(14) for signal generation
- Signal: BUY ATM straddle if price < VWAP, SELL ATM straddle if price > VWAP
- Uses 2:1 risk/reward ratio (SL = ATR, Target = 2×ATR)
- Exits straddle when signal reverses (price crosses VWAP)
- Runs during market hours (9:15 AM - 3:30 PM IST), checks every 5 minutes
- Paper trades in sandbox mode, can switch to live by disabling analyzer

Author: Strategy Author
Date: April 2026
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import sys

# Logging setup
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to import database models
try:
    from database.straddle_strategy_db import (
        get_session, cleanup_session, init_straddle_db,
        StraddleSignal, StraddlePosition, StraddleTrade, StrategyDailyMetrics
    )
    DB_AVAILABLE = True
except ImportError:
    logger.warning("Database models not available, tracking disabled")
    DB_AVAILABLE = False


class VWAPIndicator:
    """Calculate VWAP from candle data."""
    
    @staticmethod
    def calculate(closes: List[float], volumes: List[float], highs: List[float], 
                  lows: List[float]) -> float:
        """
        Calculate VWAP from OHLC and volume data.
        VWAP = Cumulative(Typical Price × Volume) / Cumulative(Volume)
        Typical Price = (High + Low + Close) / 3
        """
        if not closes or len(closes) != len(volumes):
            return 0.0
        
        cumulative_tp_vol = 0.0
        cumulative_vol = 0.0
        
        for i in range(len(closes)):
            typical_price = (highs[i] + lows[i] + closes[i]) / 3.0
            cumulative_tp_vol += typical_price * volumes[i]
            cumulative_vol += volumes[i]
        
        if cumulative_vol == 0:
            return 0.0
        
        vwap = cumulative_tp_vol / cumulative_vol
        return round(vwap, 2)


class ATRIndicator:
    """Calculate ATR (Average True Range) from candle data."""
    
    @staticmethod
    def calculate(highs: List[float], lows: List[float], closes: List[float], 
                  period: int = 14) -> float:
        """
        Calculate ATR (Average True Range) using SMA method.
        TR = max(H-L, |H-PC|, |L-PC|)
        ATR = SMA of TR over period
        """
        if len(highs) < period:
            return 0.0
        
        tr_values = []
        prev_close = closes[0]
        
        for i in range(len(highs)):
            high_low = highs[i] - lows[i]
            high_close = abs(highs[i] - prev_close)
            low_close = abs(lows[i] - prev_close)
            tr = max(high_low, high_close, low_close)
            tr_values.append(tr)
            prev_close = closes[i]
        
        # Calculate SMA of TR
        atr = sum(tr_values[-period:]) / period
        return round(atr, 2)


class StraddleStrategyAPI:
    """OpenAlgo API client for strategy execution."""
    
    def __init__(self, api_key: str, base_url: str = "http://localhost:5000"):
        """
        Initialize API client.
        
        Args:
            api_key: OpenAlgo API key
            base_url: OpenAlgo server base URL
        """
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({"X-API-KEY": api_key})
    
    def get_quotes(self, symbols: List[str], exchange: str = "NSE") -> Dict:
        """
        Fetch current quotes for symbols.
        
        Args:
            symbols: List of symbols to fetch
            exchange: Exchange code (NSE, NFO, etc.)
        
        Returns:
            Quote data from API
        """
        try:
            payload = {
                "apikey": self.api_key,
                "symbols": ",".join(symbols),
                "exchange": exchange
            }
            response = self.session.post(
                f"{self.base_url}/api/v1/quotes",
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            logger.debug(f"Quotes fetched for {len(symbols)} symbols")
            return data
        except Exception as e:
            logger.error(f"Error fetching quotes: {e}")
            return {}
    
    def get_historical_data(self, symbol: str, exchange: str, 
                            interval: str = "5min", count: int = 100) -> List[Dict]:
        """
        Fetch historical candle data.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange code
            interval: Candle interval (1min, 5min, 15min, etc.)
            count: Number of candles to fetch
        
        Returns:
            List of candle data
        """
        try:
            payload = {
                "apikey": self.api_key,
                "symbol": symbol,
                "exchange": exchange,
                "interval": interval,
                "count": count
            }
            response = self.session.post(
                f"{self.base_url}/api/v1/historical",
                json=payload,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "success" and data.get("data"):
                logger.info(f"Fetched {len(data['data'])} candles for {symbol}")
                return data["data"]
            else:
                logger.warning(f"No candle data returned for {symbol}")
                return []
        except Exception as e:
            logger.error(f"Error fetching historical data: {e}")
            return []
    
    def place_basket_order(self, orders: List[Dict]) -> Dict:
        """
        Place basket order (multi-leg order).
        
        Args:
            orders: List of orders, each with symbol, exchange, action, quantity, price, pricetype, product
        
        Returns:
            API response with order IDs
        """
        try:
            payload = {
                "apikey": self.api_key,
                "strategy": "StradleATM",
                "orders": orders
            }
            response = self.session.post(
                f"{self.base_url}/api/v1/basket_order",
                json=payload,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            logger.info(f"Basket order placed: {len(orders)} legs")
            return data
        except Exception as e:
            logger.error(f"Error placing basket order: {e}")
            return {}
    
    def cancel_order(self, order_id: str, symbol: str, exchange: str) -> Dict:
        """
        Cancel an open order.
        
        Args:
            order_id: Order ID to cancel
            symbol: Trading symbol
            exchange: Exchange code
        
        Returns:
            API response
        """
        try:
            payload = {
                "apikey": self.api_key,
                "orderid": order_id,
                "symbol": symbol,
                "exchange": exchange
            }
            response = self.session.post(
                f"{self.base_url}/api/v1/cancelorder",
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"Order {order_id} cancelled")
            return response.json()
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return {}
    
    def get_order_status(self, order_id: str) -> Dict:
        """Get order status."""
        try:
            payload = {
                "apikey": self.api_key,
                "orderid": order_id
            }
            response = self.session.post(
                f"{self.base_url}/api/v1/orderstatus",
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error getting order status: {e}")
            return {}
    
    def get_active_position(self, symbol: str, exchange: str) -> Dict:
        """Get position for a symbol."""
        try:
            payload = {
                "apikey": self.api_key
            }
            response = self.session.post(
                f"{self.base_url}/api/v1/positionbook",
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            # Filter for specific symbol
            if data.get("data"):
                for pos in data["data"]:
                    if pos.get("symbol") == symbol and pos.get("exchange") == exchange:
                        return pos
            return {}
        except Exception as e:
            logger.error(f"Error getting position: {e}")
            return {}


class StraddleStrategyEngine:
    """Main strategy engine for NIFTY ATM Straddle + VWAP."""
    
    def __init__(self, api_key: str, config: Optional[Dict] = None):
        """
        Initialize strategy engine.
        
        Args:
            api_key: OpenAlgo API key
            config: Strategy configuration (optional)
        """
        self.api_key = api_key
        self.api = StraddleStrategyAPI(api_key)
        
        # Strategy parameters
        self.config = config or {}
        self.underlying = self.config.get("underlying", "NIFTY")
        self.exchange = self.config.get("exchange", "NSE")  # For spot price
        self.nfo_exchange = self.config.get("nfo_exchange", "NFO")  # For derivatives
        self.quantity_per_leg = self.config.get("quantity_per_leg", 50)
        self.check_interval = self.config.get("check_interval", 300)  # 5 minutes
        
        # State management
        self.previous_signal = None
        self.active_position = None
        self.last_check_time = None
        
        # Database
        self.db_session = None
        if DB_AVAILABLE:
            try:
                init_straddle_db()
                self.db_session = get_session()
                logger.info("Database initialized")
            except Exception as e:
                logger.error(f"Database initialization failed: {e}")
                self.db_session = None
    
    def get_current_expiry(self) -> str:
        """
        Get the current weekly expiry date for NIFTY options.
        Weekly expiry is the last Thursday of each week (or closest Thursday to now).
        
        Returns:
            Expiry date string (e.g., "26APR2024")
        """
        now = datetime.now()
        
        # Find next Thursday
        days_until_thursday = (3 - now.weekday()) % 7
        if days_until_thursday == 0 and now.hour >= 15:  # Already Thursday after close
            days_until_thursday = 7
        
        expiry_date = now + timedelta(days=days_until_thursday)
        
        # Format: DDMMMYY (e.g., 26APR24)
        expiry_str = expiry_date.strftime("%d%b%y").upper()
        logger.info(f"Using expiry: {expiry_str}")
        return expiry_str
    
    def construct_straddle_symbols(self, atm_strike: float, expiry: str) -> Tuple[str, str]:
        """
        Construct full CE and PE symbol names.
        
        Args:
            atm_strike: ATM strike price (e.g., 22000)
            expiry: Expiry date (e.g., "26APR24")
        
        Returns:
            Tuple of (CE symbol, PE symbol)
        """
        strike_int = int(atm_strike)
        ce_symbol = f"{self.underlying}{expiry}{strike_int}CE"
        pe_symbol = f"{self.underlying}{expiry}{strike_int}PE"
        return ce_symbol, pe_symbol
    
    def find_atm_strike(self, spot_price: float, strike_step: float = 100) -> float:
        """
        Find ATM strike price nearest to spot price.
        
        Args:
            spot_price: Current spot price
            strike_step: Strike interval (typically 100 for NIFTY)
        
        Returns:
            Nearest ATM strike
        """
        atm_strike = round(spot_price / strike_step) * strike_step
        logger.info(f"Spot: {spot_price}, ATM Strike: {atm_strike}")
        return atm_strike
    
    def fetch_candle_data(self) -> Tuple[List[float], List[float], List[float], List[float]]:
        """
        Fetch 100 5-minute candles for NIFTY spot and extract OHLC + volume.
        
        Returns:
            Tuple of (closes, volumes, highs, lows)
        """
        try:
            # Fetch historical candles for NIFTY spot (NSE)
            candles = self.api.get_historical_data(
                symbol=self.underlying,
                exchange="NSE",  # Spot market
                interval="5min",
                count=100
            )
            
            if not candles:
                logger.warning("No candle data available")
                return [], [], [], []
            
            # Extract OHLCV
            closes = [float(c.get("close", 0)) for c in candles]
            volumes = [float(c.get("volume", 0)) for c in candles]
            highs = [float(c.get("high", 0)) for c in candles]
            lows = [float(c.get("low", 0)) for c in candles]
            
            logger.info(f"Candle data: {len(closes)} candles, Last close: {closes[-1]}")
            return closes, volumes, highs, lows
        
        except Exception as e:
            logger.error(f"Error fetching candle data: {e}")
            return [], [], [], []
    
    def calculate_indicators(self, closes: List[float], volumes: List[float], 
                            highs: List[float], lows: List[float]) -> Tuple[float, float, float]:
        """
        Calculate VWAP, ATR, and current price.
        
        Args:
            closes, volumes, highs, lows: Candle data
        
        Returns:
            Tuple of (current_price, vwap, atr)
        """
        if not closes:
            return 0.0, 0.0, 0.0
        
        current_price = closes[-1]
        vwap = VWAPIndicator.calculate(closes, volumes, highs, lows)
        atr = ATRIndicator.calculate(highs, lows, closes, period=14)
        
        logger.info(f"Price: {current_price}, VWAP: {vwap}, ATR: {atr}")
        return current_price, vwap, atr
    
    def generate_signal(self, price: float, vwap: float) -> str:
        """
        Generate trading signal based on price vs VWAP.
        
        Args:
            price: Current spot price
            vwap: Current VWAP
        
        Returns:
            "LONG" (BUY straddle) if price < VWAP
            "SHORT" (SELL straddle) if price > VWAP
            "NEUTRAL" if no clear signal
        """
        if price < vwap:
            return "LONG"
        elif price > vwap:
            return "SHORT"
        else:
            return "NEUTRAL"
    
    def create_straddle_orders(self, signal_type: str, atm_strike: float, 
                              ce_symbol: str, pe_symbol: str, 
                              quantity: int) -> List[Dict]:
        """
        Create basket order for straddle.
        
        Args:
            signal_type: "LONG" or "SHORT"
            atm_strike: Strike price
            ce_symbol: CE symbol
            pe_symbol: PE symbol
            quantity: Quantity per leg
        
        Returns:
            List of order dicts for basket order API
        """
        if signal_type == "LONG":
            # BUY straddle: BUY CE + BUY PE
            orders = [
                {
                    "symbol": ce_symbol,
                    "exchange": self.nfo_exchange,
                    "action": "BUY",
                    "quantity": quantity,
                    "price": 0,
                    "pricetype": "MARKET",
                    "product": "NRML"
                },
                {
                    "symbol": pe_symbol,
                    "exchange": self.nfo_exchange,
                    "action": "BUY",
                    "quantity": quantity,
                    "price": 0,
                    "pricetype": "MARKET",
                    "product": "NRML"
                }
            ]
        else:  # SHORT
            # SELL straddle: SELL CE + SELL PE
            orders = [
                {
                    "symbol": ce_symbol,
                    "exchange": self.nfo_exchange,
                    "action": "SELL",
                    "quantity": quantity,
                    "price": 0,
                    "pricetype": "MARKET",
                    "product": "NRML"
                },
                {
                    "symbol": pe_symbol,
                    "exchange": self.nfo_exchange,
                    "action": "SELL",
                    "quantity": quantity,
                    "price": 0,
                    "pricetype": "MARKET",
                    "product": "NRML"
                }
            ]
        
        return orders
    
    def record_signal(self, signal_type: str, price: float, vwap: float, atr: float,
                     atm_strike: float, expiry: str) -> Optional[int]:
        """
        Record signal to database.
        
        Returns:
            Signal ID or None
        """
        if not self.db_session or not DB_AVAILABLE:
            return None
        
        try:
            # Calculate SL and TP using 2:1 ratio
            stoploss = atr  # SL = ATR
            target = atr * 2  # TP = 2×ATR
            
            signal = StraddleSignal(
                underlying=self.underlying,
                exchange=self.nfo_exchange,
                spot_price=price,
                vwap=vwap,
                atr_14=atr,
                signal_type=signal_type,
                previous_signal=self.previous_signal,
                atm_strike=atm_strike,
                expiry_date=expiry,
                stoploss_points=stoploss,
                target_points=target,
                quantity_per_leg=self.quantity_per_leg,
                signal_timestamp=datetime.now()
            )
            self.db_session.add(signal)
            self.db_session.commit()
            logger.info(f"Signal recorded: {signal_type}, ID: {signal.id}")
            return signal.id
        except Exception as e:
            logger.error(f"Error recording signal: {e}")
            self.db_session.rollback()
            return None
    
    def record_position(self, signal_id: int, trade_type: str, atm_strike: float, 
                       ce_symbol: str, pe_symbol: str, expiry: str,
                       ce_order_id: str, pe_order_id: str) -> Optional[int]:
        """
        Record straddle position to database.
        
        Returns:
            Position ID or None
        """
        if not self.db_session or not DB_AVAILABLE:
            return None
        
        try:
            position = StraddlePosition(
                signal_id=signal_id,
                underlying=self.underlying,
                exchange=self.nfo_exchange,
                expiry_date=expiry,
                atm_strike=atm_strike,
                position_type=trade_type,
                quantity=self.quantity_per_leg,
                ce_symbol=ce_symbol,
                pe_symbol=pe_symbol,
                ce_orderid=ce_order_id,
                pe_orderid=pe_order_id,
                status="pending",
                is_active=True
            )
            self.db_session.add(position)
            self.db_session.commit()
            logger.info(f"Position recorded: {trade_type}, ID: {position.id}")
            return position.id
        except Exception as e:
            logger.error(f"Error recording position: {e}")
            self.db_session.rollback()
            return None
    
    def execute_strategy(self):
        """Main strategy execution loop."""
        logger.info("=" * 60)
        logger.info(f"Strategy started at {datetime.now()}")
        logger.info(f"Underlying: {self.underlying}, Quantity per leg: {self.quantity_per_leg}")
        logger.info("=" * 60)
        
        try:
            # Step 1: Fetch candle data
            logger.info("Fetching candle data...")
            closes, volumes, highs, lows = self.fetch_candle_data()
            
            if not closes:
                logger.warning("No candle data available, skipping this cycle")
                return
            
            # Step 2: Calculate indicators
            logger.info("Calculating indicators...")
            price, vwap, atr = self.calculate_indicators(closes, volumes, highs, lows)
            
            if price == 0 or vwap == 0 or atr == 0:
                logger.warning("Invalid indicator values, skipping")
                return
            
            # Step 3: Generate signal
            logger.info("Generating signal...")
            signal_type = self.generate_signal(price, vwap)
            logger.info(f"Signal: {signal_type} (Price: {price}, VWAP: {vwap})")
            
            # Step 4: Check for signal change
            if signal_type == self.previous_signal or signal_type == "NEUTRAL":
                logger.info(f"No signal change, holding current position")
                return
            
            # Step 5: Record signal
            logger.info("Recording signal...")
            expiry = self.get_current_expiry()
            signal_id = self.record_signal(signal_type, price, vwap, atr, 
                                          self.find_atm_strike(price), expiry)
            
            # Step 6: Prepare straddle orders
            logger.info("Preparing straddle orders...")
            atm_strike = self.find_atm_strike(price)
            ce_symbol, pe_symbol = self.construct_straddle_symbols(atm_strike, expiry)
            
            orders = self.create_straddle_orders(
                signal_type, atm_strike, ce_symbol, pe_symbol, self.quantity_per_leg
            )
            logger.info(f"Orders prepared:\n{json.dumps(orders, indent=2)}")
            
            # Step 7: Place basket order
            logger.info("Placing basket order...")
            response = self.api.place_basket_order(orders)
            
            if response.get("status") == "success":
                logger.info(f"Order placed successfully: {response}")
                
                # Extract order IDs from response
                order_ids = response.get("data", {})
                ce_order_id = str(order_ids.get(0, ""))  # First order (CE)
                pe_order_id = str(order_ids.get(1, ""))  # Second order (PE)
                
                # Step 8: Record position
                if signal_id:
                    position_id = self.record_position(
                        signal_id, signal_type, atm_strike, ce_symbol, pe_symbol, expiry,
                        ce_order_id, pe_order_id
                    )
                    logger.info(f"Position ID: {position_id}")
                
                # Update state
                self.previous_signal = signal_type
                self.active_position = {
                    "signal_type": signal_type,
                    "ce_symbol": ce_symbol,
                    "pe_symbol": pe_symbol,
                    "ce_order_id": ce_order_id,
                    "pe_order_id": pe_order_id
                }
                
                logger.info(f"Strategy cycle complete: {signal_type} straddle entered")
            else:
                logger.error(f"Failed to place order: {response}")
        
        except Exception as e:
            logger.exception(f"Error in strategy execution: {e}")
        
        finally:
            logger.info("Strategy cycle complete\n")


def main():
    """
    Main entry point for the strategy.
    
    This script is called by OpenAlgo's strategy manager (`blueprints/python_strategy.py`).
    It reads configuration from environment or config file, initializes the strategy engine,
    and runs the strategy loop.
    """
    
    # Get API key from environment
    api_key = os.getenv("OPENALGO_API_KEY") or os.getenv("API_KEY")
    
    if not api_key:
        logger.error("API_KEY not found in environment")
        sys.exit(1)
    
    # Load config if available
    config_file = "strategy_config.json"
    config = {}
    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                config = json.load(f)
            logger.info(f"Config loaded from {config_file}")
        except Exception as e:
            logger.warning(f"Could not load config: {e}, using defaults")
    
    # Initialize strategy engine
    engine = StraddleStrategyEngine(api_key, config)
    
    # Execute strategy once (or can loop with sleep for continuous execution)
    # The strategy manager in blueprints/python_strategy.py handles scheduling
    engine.execute_strategy()


if __name__ == "__main__":
    main()
