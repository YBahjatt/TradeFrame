from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.entities import Setting
from app.schemas.dto import PricingProfile, TradeFrameSettings, TradeFrameSettingsUpdate


DEFAULT_SETTINGS = {
    "pricing.sell.price_source": "no",
    "pricing.sell.calculation_method": "low",
    "pricing.sell.margin": "0",
    "pricing.sell.rounding": "nearest",
    "pricing.buy.price_source": "no",
    "pricing.buy.calculation_method": "low",
    "pricing.buy.margin": "0",
    "pricing.buy.rounding": "nearest",
    "pricing.tf_calculations.price_source": "market_sell",
    "pricing.tf_calculations.calculation_method": "low",
    "pricing.tf_calculations.margin": "0",
    "pricing.tf_calculations.rounding": "nearest",
    "warframe_chat.max_length": "180",
    "warframe_chat.margin": "10",
}


class SettingsService:
    def __init__(self, db: Session):
        self.db = db

    def get(self) -> TradeFrameSettings:
        app_settings = get_settings()
        aleca_data_dir, aleca_valid, aleca_status = self._resolve_aleca_data_dir(app_settings.aleca_data_dir)
        return TradeFrameSettings(
            sell=self._profile("sell", allow_no=True),
            buy=self._profile("buy", allow_no=True),
            tf_calculations=self._profile("tf_calculations", allow_no=False),
            warframe_chat_max_length=self._int("warframe_chat.max_length", 180),
            warframe_chat_margin=self._int("warframe_chat.margin", 10),
            aleca_data_dir=str(aleca_data_dir),
            aleca_data_dir_valid=aleca_valid,
            aleca_data_dir_status=aleca_status,
        )

    def update(self, update: TradeFrameSettingsUpdate) -> TradeFrameSettings:
        if update.sell is not None:
            self._save_profile("sell", update.sell, allow_no=True)
        if update.buy is not None:
            self._save_profile("buy", update.buy, allow_no=True)
        if update.tf_calculations is not None:
            self._save_profile("tf_calculations", update.tf_calculations, allow_no=False)
        if update.warframe_chat_max_length is not None:
            self._set("warframe_chat.max_length", str(max(50, min(500, update.warframe_chat_max_length))))
        if update.warframe_chat_margin is not None:
            self._set("warframe_chat.margin", str(max(0, min(100, update.warframe_chat_margin))))
        if update.aleca_data_dir is not None:
            self._set("paths.aleca_data_dir", update.aleca_data_dir)
        self.db.commit()
        return self.get()

    def price_for_value(self, market_value: float) -> float:
        return self.apply_pricing(market_value, self.get().tf_calculations)

    def apply_pricing(self, market_value: float, profile: PricingProfile) -> float:
        if profile.price_source == "no":
            return 0
        value = float(market_value or 0)
        value = self._apply_margin(value, profile.margin)
        return self._round(value, profile.rounding)

    def _profile(self, name: str, allow_no: bool) -> PricingProfile:
        source = self._str(f"pricing.{name}.price_source", DEFAULT_SETTINGS[f"pricing.{name}.price_source"])
        if not allow_no and source == "no":
            source = "market_sell"
        if source not in {"no", "market_sell", "market_buy"}:
            source = "no" if allow_no else "market_sell"
        method = self._str(f"pricing.{name}.calculation_method", DEFAULT_SETTINGS[f"pricing.{name}.calculation_method"])
        if method not in {"high", "low", "average", "median"}:
            method = "low"
        rounding = self._str(f"pricing.{name}.rounding", DEFAULT_SETTINGS[f"pricing.{name}.rounding"])
        if rounding not in {"nearest", "up", "down"}:
            rounding = "nearest"
        return PricingProfile(
            price_source=source,
            calculation_method=method,
            margin=self._str(f"pricing.{name}.margin", DEFAULT_SETTINGS[f"pricing.{name}.margin"]),
            rounding=rounding,
        )

    def _save_profile(self, name: str, profile: PricingProfile, allow_no: bool) -> None:
        source = profile.price_source
        if source not in {"no", "market_sell", "market_buy"}:
            source = "no" if allow_no else "market_sell"
        if not allow_no and source == "no":
            source = "market_sell"
        method = profile.calculation_method if profile.calculation_method in {"high", "low", "average", "median"} else "low"
        rounding = profile.rounding if profile.rounding in {"nearest", "up", "down"} else "nearest"
        self._set(f"pricing.{name}.price_source", source)
        self._set(f"pricing.{name}.calculation_method", method)
        self._set(f"pricing.{name}.margin", profile.margin)
        self._set(f"pricing.{name}.rounding", rounding)

    def _str(self, key: str, default: str) -> str:
        row = self.db.get(Setting, key)
        return row.value if row else default

    def _int(self, key: str, default: int) -> int:
        try:
            return int(self._str(key, str(default)))
        except ValueError:
            return default

    def _set(self, key: str, value: str) -> None:
        row = self.db.get(Setting, key)
        if row is None:
            self.db.add(Setting(key=key, value=value))
        else:
            row.value = value

    def _resolve_aleca_data_dir(self, env_path: Path | None) -> tuple[Path, bool, str]:
        configured = self.db.get(Setting, "paths.aleca_data_dir")
        if configured and configured.value.strip():
            path = Path(configured.value)
            if self._is_aleca_data_dir(path):
                return path, True, "AlecaFrame data folder found."
            return path, False, "This folder does not look like AlecaFrame user data. Expected lastData.dat inside it."

        if env_path:
            path = Path(env_path)
            if self._is_aleca_data_dir(path):
                self._set("paths.aleca_data_dir", str(path))
                self.db.commit()
                return path, True, "AlecaFrame data folder detected from TradeFrame environment."
            return path, False, "Configured TradeFrame AlecaFrame path does not contain lastData.dat."

        candidates = self._aleca_data_dir_candidates()
        valid = [path for path in candidates if self._is_aleca_data_dir(path)]
        if len(valid) == 1:
            self._set("paths.aleca_data_dir", str(valid[0]))
            self.db.commit()
            return valid[0], True, "AlecaFrame data folder detected automatically."
        if len(valid) > 1:
            return valid[0], True, "Multiple AlecaFrame data folders were found. Confirm this is the one you want."

        fallback = candidates[0]
        return fallback, False, "AlecaFrame data folder was not found automatically. Select the folder containing lastData.dat."

    @staticmethod
    def _aleca_data_dir_candidates() -> list[Path]:
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        roaming = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        candidates = [local / "AlecaFrame", roaming / "AlecaFrame"]
        seen: set[str] = set()
        unique: list[Path] = []
        for path in candidates:
            key = str(path).lower()
            if key not in seen:
                seen.add(key)
                unique.append(path)
        return unique

    @staticmethod
    def _is_aleca_data_dir(path: Path) -> bool:
        return path.is_dir() and (path / "lastData.dat").is_file()

    @staticmethod
    def _apply_margin(value: float, margin: str) -> float:
        text = (margin or "0").strip()
        if not text:
            return value
        try:
            if text.endswith("%"):
                return value * (1 + float(text[:-1]) / 100)
            return value + float(text)
        except ValueError:
            return value

    @staticmethod
    def _round(value: float, rounding: str) -> float:
        import math

        if rounding == "up":
            return float(math.ceil(value))
        if rounding == "down":
            return float(math.floor(value))
        return float(round(value))
