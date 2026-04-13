from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QObject, Signal

from sentinel.market.prep.chart_payload_builder import CandleChartPayloadBuilder
from sentinel.market.query import HistoricalBarsQuery, Timeframe
from sentinel.market.services.equities_service import EquitiesService


class EquityChartViewModel(QObject):
    loading_changed = Signal(bool)
    payload_ready = Signal(object)
    error_changed = Signal(str)
    empty_changed = Signal(bool)

    def __init__(self, service: EquitiesService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._payload_builder = CandleChartPayloadBuilder()
        self._last_request_id = 0
        self._active_task: asyncio.Task | None = None

    def request_symbol(self, symbol: str, timeframe: Timeframe, *, days: int = 30) -> None:
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
        self._last_request_id += 1
        request_id = self._last_request_id
        self.loading_changed.emit(True)
        self.error_changed.emit("")
        self._active_task = asyncio.create_task(
            self._load(request_id=request_id, symbol=symbol, timeframe=timeframe, days=days)
        )

    async def _load(self, *, request_id: int, symbol: str, timeframe: Timeframe, days: int) -> None:
        try:
            now = datetime.now(timezone.utc)
            query = HistoricalBarsQuery(
                symbol=symbol,
                interval=timeframe,
                start=now - timedelta(days=days),
                end=now,
            )
            bars = await self._service.get_historical_bars(query)
            actions = await self._service.get_corporate_actions(symbol, start=query.start, end=query.end)
            payload = self._payload_builder.build(bars, actions)

            if request_id != self._last_request_id:
                return

            self.empty_changed.emit(len(payload.x) == 0)
            self.payload_ready.emit(payload)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            if request_id == self._last_request_id:
                self.error_changed.emit(str(exc))
        finally:
            if request_id == self._last_request_id:
                self.loading_changed.emit(False)
