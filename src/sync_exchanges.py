import logging
import traceback
import re
from typing import List, Dict, Any, Optional
from .api.exchanges.abstract import AbstractAPI
from .api import ApiFacade
from .db.database_facade import DatabaseFacade

logger = logging.getLogger(__name__)


class Exchanges:
    """
    Klasa odpowiedzialna za integrację z giełdami i synchronizację assetów.
    Używa wzorca strategii do obsługi różnych giełd.
    """

    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.api_facade = ApiFacade()
        self.exchanges: List[AbstractAPI] = self.api_facade.get_fabric().get_exchanges_apis()

        if not self.test_mode:
            self.db = DatabaseFacade().get_database_postgresql()
        else:
            self.db = DatabaseFacade().get_test_database_postgresql()

    @staticmethod
    def _clean_asset_code(asset_code: str) -> str:
        """
        Czyści kod assetu z niepożądanych znaków (dla giełd typu Binance).
        Dla Yahoo Finance assety przychodzą już sformatowane i nie wymagają czyszczenia.
        """
        if not asset_code:
            return asset_code
        cleaned = asset_code.upper()
        cleaned = re.sub(r'[^A-Z0-9]', '', cleaned)
        return cleaned.strip()

    @staticmethod
    def _is_rich_metadata(symbol_info: Dict[str, Any]) -> bool:
        """Sprawdza czy symbol_info zawiera metadane kind/country (Yahoo Finance)."""
        return bool(symbol_info.get('kind'))

    async def _get_all_symbols_from_exchanges(self) -> Dict[str, Dict[str, Any]]:
        all_symbols = {}
        for exchange in self.exchanges:
            try:
                logger.info(f"Pobieram symbole z giełdy: {exchange.__class__.__name__}")
                symbols_data = exchange._get_symbols()

                if symbols_data is not None and len(symbols_data) > 0:
                    exchange_name = exchange.__class__.__name__
                    all_symbols[exchange_name] = symbols_data
                    logger.info(f"Pobrano {len(symbols_data)} symboli z {exchange_name}")
                else:
                    logger.warning(f"Brak symboli z giełdy {exchange.__class__.__name__}")
            except Exception as e:
                logger.error(f"Błąd podczas pobierania symboli z giełdy {exchange.__class__.__name__}: {e}")
                logger.error(traceback.format_exc())

        return all_symbols

    async def _sync_exchange_symbols_with_database(
        self, all_exchange_symbols: Dict[str, Dict[str, Any]]
    ) -> Dict[str, int]:
        if not all_exchange_symbols:
            logger.warning("Brak symboli z giełd — nie można synchronizować")
            return {}

        try:
            logger.info("Rozpoczynam synchronizację symboli z giełd z bazą danych")

            # ── KROK 1: Exchanges ──────────────────────────────────────
            logger.info("=== KROK 1: Synchronizacja exchanges ===")
            exchanges_to_create = [
                {'name': name, 'display_name': name, 'is_active': True}
                for name in all_exchange_symbols
            ]
            exchanges_table = self.db.get_factory().get_exchanges_table()
            created_exchanges = await exchanges_table.create_many(exchanges_to_create)
            logger.info(f"Zsynchronizowano {len(created_exchanges)} exchanges")

            # ── KROK 2: Zbierz assety ──────────────────────────────────
            logger.info("=== KROK 2: Przygotowanie assetów ===")

            all_assets: set = set()
            asset_exchange_mapping: Dict[str, List[str]] = {}
            asset_meta: Dict[str, Dict[str, str]] = {}
            total_symbols = 0

            for exchange_name, exchange_data in all_exchange_symbols.items():
                for symbol_info in exchange_data:
                    total_symbols += 1
                    base_asset = symbol_info.get('base_asset')
                    quote_asset = symbol_info.get('quote_asset')

                    if not base_asset or not quote_asset:
                        continue

                    rich = self._is_rich_metadata(symbol_info)

                    if rich:
                        asset_key = base_asset
                        cleaned_asset = base_asset
                        kind = symbol_info.get('kind', '')
                        country = symbol_info.get('country', '')
                    else:
                        if quote_asset != 'USDT':
                            continue
                        cleaned_asset = self._clean_asset_code(base_asset)
                        asset_key = base_asset
                        kind = 'CRYPTO'
                        country = 'CRYPTO'

                    all_assets.add(asset_key)

                    if asset_key not in asset_exchange_mapping:
                        asset_exchange_mapping[asset_key] = []
                    asset_exchange_mapping[asset_key].append(exchange_name)

                    asset_meta[asset_key] = {
                        'cleaned_asset': cleaned_asset,
                        'quote': quote_asset,
                        'kind': kind,
                        'country': country,
                    }

            logger.info(f"Znaleziono {len(all_assets)} unikalnych assetów z {total_symbols} symboli")

            # ── KROK 3: Sprawdź istniejące assety ──────────────────────
            logger.info("=== KROK 3: Sprawdzanie istniejących assetów ===")
            assets_table = self.db.get_factory().get_assets_table()

            assets_to_check = [
                {'asset': meta['cleaned_asset'], 'quote': meta['quote']}
                for meta in asset_meta.values()
            ]
            existing_assets = await assets_table.check_many(assets_to_check)
            logger.info(f"Znaleziono {len(existing_assets)} istniejących assetów")

            # ── KROK 4: Utwórz brakujące assety ───────────────────────
            logger.info("=== KROK 4: Tworzenie nowych assetów ===")
            found_assets: Dict[str, int] = {}
            assets_to_create = []

            for asset_key, meta in asset_meta.items():
                asset_db_key = f"{meta['cleaned_asset']}/{meta['quote']}"
                if asset_db_key in existing_assets:
                    found_assets[asset_key] = existing_assets[asset_db_key]
                else:
                    assets_to_create.append({
                        'asset': meta['cleaned_asset'],
                        'quote': meta['quote'],
                    })

            added_count = 0
            if assets_to_create:
                logger.info(f"Tworzę {len(assets_to_create)} nowych assetów")
                created_assets = await assets_table.create_many(assets_to_create)

                for asset_key, meta in asset_meta.items():
                    asset_db_key = f"{meta['cleaned_asset']}/{meta['quote']}"
                    if asset_db_key in created_assets:
                        found_assets[asset_key] = created_assets[asset_db_key]
                        added_count += 1
            else:
                logger.info("Wszystkie assety już istnieją w bazie")

            # ── KROK 5: Relacje asset-exchange ─────────────────────────
            logger.info("=== KROK 5: Tworzenie relacji asset-exchange ===")
            asset_exchanges_table = self.db.get_factory().get_asset_exchanges_table()
            ae_relations = []

            for asset_key, asset_id in found_assets.items():
                for exchange_name in asset_exchange_mapping.get(asset_key, []):
                    if exchange_name in created_exchanges:
                        ae_relations.append({
                            'asset_id': asset_id,
                            'exchange_id': created_exchanges[exchange_name],
                        })

            added_relations = 0
            if ae_relations:
                created_rels = await asset_exchanges_table.create_many(ae_relations)
                added_relations = len(created_rels)
                logger.info(f"Utworzono {added_relations} relacji asset-exchange")

            # ── KROK 6: Kind + Country (M2M) ──────────────────────────
            logger.info("=== KROK 6: Mapowanie kind i country ===")
            await self._sync_kind_and_country(found_assets, asset_meta)

            logger.info(
                f"Synchronizacja zakończona: {len(found_assets)} assetów, "
                f"{added_count} nowych, {added_relations} relacji"
            )
            return found_assets

        except Exception as e:
            logger.error(f"Błąd synchronizacji symboli: {e}")
            logger.error(traceback.format_exc())
            return {}

    async def _sync_kind_and_country(
        self,
        found_assets: Dict[str, int],
        asset_meta: Dict[str, Dict[str, str]],
    ) -> None:
        """Tworzy rekordy w tabelach M2M: asset_kind_map i asset_country_map."""
        try:
            asset_kinds_table = self.db.get_factory().get_asset_kinds_table()
            countries_table = self.db.get_factory().get_countries_table()
            kind_map_table = self.db.get_factory().get_asset_kind_map_table()
            country_map_table = self.db.get_factory().get_asset_country_map_table()

            kind_cache: Dict[str, int] = {}
            country_cache: Dict[str, int] = {}

            kind_pairs: list = []
            country_pairs: list = []

            for asset_key, asset_id in found_assets.items():
                meta = asset_meta.get(asset_key)
                if not meta:
                    continue

                kind_name = meta.get('kind', '')
                country_code = meta.get('country', '')

                if kind_name:
                    if kind_name not in kind_cache:
                        kind_cache[kind_name] = await asset_kinds_table.get_or_create(kind_name)
                    kind_pairs.append({
                        'asset_id': asset_id,
                        'kind_id': kind_cache[kind_name],
                    })

                if country_code:
                    if country_code not in country_cache:
                        country_cache[country_code] = await countries_table.get_or_create(country_code)
                    country_pairs.append({
                        'asset_id': asset_id,
                        'country_id': country_cache[country_code],
                    })

            if kind_pairs:
                await kind_map_table.create_many(kind_pairs)
                logger.info(f"Utworzono {len(kind_pairs)} mapowań kind")

            if country_pairs:
                await country_map_table.create_many(country_pairs)
                logger.info(f"Utworzono {len(country_pairs)} mapowań country")

        except Exception as e:
            logger.error(f"Błąd mapowania kind/country: {e}", exc_info=True)

    async def sync_assets(self) -> None:
        """
        Synchronizuje assety ze wszystkich giełd z bazą danych.
        Dla Binance: filtruje quote=USDT, kind=CRYPTO.
        Dla Yahoo Finance: akceptuje wszystkie quote_assets, kind/country z registry.
        """
        try:
            if not hasattr(self.db, 'factory') or self.db.factory is None:
                await self.db.init_db()

            logger.info("=== KROK 1: Pobieranie symboli ze wszystkich giełd ===")
            all_exchange_symbols = await self._get_all_symbols_from_exchanges()

            if not all_exchange_symbols:
                logger.warning("Nie udało się pobrać symboli z żadnej giełdy")
                return

            logger.info("=== KROK 2: Synchronizacja symboli z bazą danych ===")
            synced_assets = await self._sync_exchange_symbols_with_database(all_exchange_symbols)
            logger.info(f"Zsynchronizowano {len(synced_assets)} assetów z giełd")

            logger.info("=== Synchronizacja zakończona ===")
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji z bazą danych: {e}", exc_info=True)
            return None
