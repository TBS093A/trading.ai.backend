"""Wybór giełdy dla assetu i pobieranie świec - wspólne dla skanu zakresu, setupów i nocnego syncu."""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .. import harmonic_scan

logger = logging.getLogger(__name__)


@dataclass
class ResolvedAsset:
    asset: Dict[str, Any]
    exchange: Optional[str]          # BINANCE | YAHOO | None (giełda spoza harmonic_scan.EXCHANGE_PRIORITY)
    api: Any                         # klient z _get_klines albo None

    @property
    def symbol(self) -> str:
        return f"{self.asset['asset']}/{self.asset['quote']}"


class KlinesSource:
    def __init__(self, api_facade, factory):
        self.api_facade = api_facade
        self.factory = factory
        self._all_apis = None

    def all_apis(self) -> List[Any]:
        if self._all_apis is None:
            self._all_apis = self.api_facade.get_fabric().get_exchanges_apis()
        return self._all_apis

    async def resolve(self, asset_id: int) -> ResolvedAsset:
        """Asset i klient giełdy w tej samej kolejności co GET /exchanges/klines (wykres)."""
        asset = await self.factory.get_assets_table().get_by_id(asset_id)
        if not asset:
            raise ValueError(f"Asset {asset_id} not found")
        asset_exchanges = await self.factory.get_asset_exchanges_table().get_by_asset_id(asset_id)
        exchange = harmonic_scan.pick_exchange(e.get('exchange_name', '') for e in asset_exchanges)
        fabric = self.api_facade.get_fabric()
        getters = {'BINANCE': fabric.get_binance_api, 'YAHOO': fabric.get_yahoofinance_api}
        api = getters[exchange]() if exchange in getters else None
        return ResolvedAsset(asset=asset, exchange=exchange if api else None, api=api)

    @staticmethod
    def require_api(resolved: ResolvedAsset) -> None:
        if resolved.api is None:
            raise ValueError(f"Brak obsługiwanej giełdy dla assetu {resolved.asset['asset']}")

    def fetch_range(self, resolved: ResolvedAsset, interval: str, start: int, end: int) -> List[Dict[str, Any]]:
        """Wszystkie świece z [start, end] z giełdy assetu (stronicowanie w obie strony)."""
        self.require_api(resolved)
        return harmonic_scan.fetch_klines_range(
            resolved.api._get_klines, resolved.asset['asset'], resolved.asset['quote'], interval, start, end
        )

    def fetch_recent(self, resolved: ResolvedAsset, interval: str, start: int, end: int,
                     limit: int) -> List[Dict[str, Any]]:
        """Nocny sync: najpierw giełda assetu, a gdy jej nie ma albo nic nie zwróci - pozostałe
        giełdy po kolei (dotychczasowe zachowanie syncu dla assetów spoza Binance / Yahoo)."""
        candidates = ([resolved.api] if resolved.api is not None else []) + [
            api for api in self.all_apis()
            if resolved.api is None or type(api) is not type(resolved.api)
        ]
        for api in candidates:
            name = api.__class__.__name__
            try:
                klines = api._get_klines(
                    base_currency=resolved.asset['asset'], quote_currency=resolved.asset['quote'],
                    interval=interval, start_time=start, end_time=end, limit=limit,
                )
            except Exception as e:
                logger.error(f"Błąd podczas pobierania klines z {name}: {e}")
                continue
            if klines:
                logger.info(f"Pobrano {len(klines)} klines z {name} dla {resolved.symbol} [{interval}]")
                return klines
            logger.warning(f"Brak klines z {name} dla {resolved.symbol} [{interval}]")
        return []
