"""Application configuration loaded from environment variables / .env."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Project root: D:\ZaiAgentTrading
BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / "backend" / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Data provider (Twelve Data) ---
    twelve_data_api_key: str = ""
    twelve_data_base_url: str = "https://api.twelvedata.com"
    symbol: str = "XAU/USD"
    timeframe: str = "5min"  # default dashboard view timeframe
    # comma-separated list of symbols the scanner runs on every cycle
    symbols: str = "XAU/USD,BTC/USD"
    # comma-separated list of timeframes the scanner runs on every cycle
    scan_timeframes: str = "5min,15min,1h,4h"

    # --- ZAI (GLM) LLM ---
    zai_api_key: str = ""
    zai_base_url: str = "https://api.z.ai/api/paas/v4/"
    zai_model: str = "glm-5.2"

    # --- Telegram ---
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # --- Strategy params (tunable) ---
    crt_range_window: int = 6        # candles that form the consolidation range
    crt_displacement_k: float = 1.0  # displacement body >= k * ATR
    crt_atr_period: int = 14
    crt_sl_buffer_atr: float = 0.15  # SL buffer beyond the sweep wick, in ATR
    crt_min_rr: float = 2.0          # minimum reward:risk floor for TP
    crt_lookforward_candles: int = 3 # candles to wait for TP/SL before expiring
    crt_scan_lookback: int = 30      # candles to re-scan each cycle

    # --- Premium/Discount filter (ICT enhancement) ---
    crt_pd_penalty: float = 20.0     # confidence penalty when entry is on the wrong side of equilibrium
    crt_pd_strict: bool = False      # if True, drop P/D-failing setups entirely

    # --- Killzone time windows (ICT Silver Bullet, UTC) ---
    crt_killzone_bonus: float = 15.0        # confidence bonus inside a killzone
    crt_killzone_off_penalty: float = 8.0   # penalty when outside any killzone

    # --- Power of 3 (Asian range -> London Judas sweep) ---
    # Skip the PO3 signal if the Asian session range is already wider than this
    # (% of asia_low) — a wide Asia range usually means a trend day, not an
    # accumulation/manipulation setup. 1.0 = 1%.
    crt_po3_max_range_pct: float = 1.0

    # --- Per-timeframe strategy overrides (JSON, keyed by interval) ---
    # Lets 5m/15m run a tighter/tuned range window + displacement threshold so
    # they aren't over-sensitive (more candles/day -> needs stricter filtering).
    crt_tf_overrides: str = (
        '{"5min":{"range_window":8,"displacement_k":1.2},'
        '"15min":{"range_window":7,"displacement_k":1.1},'
        '"1h":{"range_window":6,"displacement_k":1.0},'
        '"4h":{"range_window":6,"displacement_k":1.0}}'
    )

    # --- Scheduler ---
    scan_cron_minutes: str = "*/5"  # fetch+scan every 5 min (catches 5m closes promptly)

    # --- DB ---
    database_url: str = f"sqlite:///{(DATA_DIR / 'xauusd.db').as_posix()}"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.zai_api_key)

    @property
    def provider_enabled(self) -> bool:
        return bool(self.twelve_data_api_key)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def timeframes(self) -> list[str]:
        """Parsed list of timeframes the scanner runs on."""
        return [t.strip() for t in self.scan_timeframes.split(",") if t.strip()]

    @property
    def symbols_list(self) -> list[str]:
        """Parsed list of symbols the scanner runs on."""
        return [s.strip() for s in self.symbols.split(",") if s.strip()]

    @property
    def tf_overrides(self) -> dict:
        """Per-timeframe strategy param overrides, parsed from JSON."""
        import json
        try:
            data = json.loads(self.crt_tf_overrides or "{}")
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
