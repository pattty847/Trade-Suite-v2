from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from sentinel.market.models import Bar, BarSeries, CorporateAction, CorporateActionType


OHLC_RENAME_MAP = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
}


class EquityNormalizer:
    def normalize_bars(
        self,
        *,
        symbol: str,
        interval: str,
        timezone_name: str,
        raw_history: pd.DataFrame,
        adjusted: bool,
        include_extended_hours: bool,
    ) -> BarSeries:
        if raw_history.empty:
            return BarSeries(
                symbol=symbol,
                interval=interval,
                timezone=timezone_name,
                bars=tuple(),
                adjusted=adjusted,
                include_extended_hours=include_extended_hours,
            )

        df = raw_history.rename(columns=OHLC_RENAME_MAP).copy()
        df = df[~df.index.duplicated(keep="last")]
        df = df.sort_index()

        for column in ("open", "high", "low", "close"):
            df[column] = pd.to_numeric(df[column], errors="coerce")
        if "volume" in df.columns:
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce")

        df = df.dropna(subset=["open", "high", "low", "close"])

        bars: list[Bar] = []
        for index, row in df.iterrows():
            ts = self._as_datetime(index)
            close_value = row["adj_close"] if adjusted and "adj_close" in row and pd.notna(row["adj_close"]) else row["close"]
            bars.append(
                Bar(
                    ts=ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(close_value),
                    volume=float(row["volume"]) if "volume" in row and pd.notna(row["volume"]) else None,
                )
            )

        return BarSeries(
            symbol=symbol,
            interval=interval,
            timezone=timezone_name,
            bars=tuple(bars),
            adjusted=adjusted,
            include_extended_hours=include_extended_hours,
        )

    def normalize_actions(
        self,
        *,
        symbol: str,
        dividends: pd.Series | None,
        splits: pd.Series | None,
    ) -> list[CorporateAction]:
        actions: list[CorporateAction] = []
        if dividends is not None and not dividends.empty:
            for idx, value in dividends.items():
                actions.append(
                    CorporateAction(
                        symbol=symbol,
                        action_type=CorporateActionType.DIVIDEND,
                        ex_date=self._as_datetime(idx),
                        value=float(value),
                    )
                )

        if splits is not None and not splits.empty:
            for idx, value in splits.items():
                ratio_from, ratio_to = self._split_ratio(float(value))
                actions.append(
                    CorporateAction(
                        symbol=symbol,
                        action_type=CorporateActionType.SPLIT,
                        ex_date=self._as_datetime(idx),
                        ratio_from=ratio_from,
                        ratio_to=ratio_to,
                        value=float(value),
                    )
                )

        return sorted(actions, key=lambda x: x.ex_date)

    @staticmethod
    def _as_datetime(value: Any) -> datetime:
        ts = pd.Timestamp(value)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return ts.to_pydatetime()

    @staticmethod
    def _split_ratio(ratio: float) -> tuple[float, float]:
        if ratio <= 0:
            return (1.0, 1.0)
        return (1.0, ratio)
