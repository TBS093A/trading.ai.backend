import logging
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from .api.news_services.abstract_service import AbstractService
from .api.exchanges.abstract import AbstractAPI
from .api import ApiFacade
from .db.database_facade import DatabaseFacade
from .config import config

logger = logging.getLogger(__name__)


class FundamentalAnalysis:
    """
    Klasa odpowiedzialna za integrację serwisów wiadomości, giełd i bazy danych.
    Używa wzorca strategii do obsługi różnych serwisów wiadomości.
    """
    
    def __init__(self, test_mode: bool = False):
        """
        Inicjalizacja klasy FundamentalAnalysis
        
        Args:
            test_mode: Czy uruchamiać w trybie testowym
        """
        self.test_mode = test_mode
        self.api_facade = ApiFacade()
        self.news_services: List[AbstractService] = self.api_facade.get_news_services_apis()
        
        # Inicjalizacja bazy danych
        if not self.test_mode:
            self.db = DatabaseFacade().get_database_postgresql()
        else:
            self.db = DatabaseFacade().get_test_database_postgresql()
    
    def add_news_service(self, service: AbstractService) -> None:
        """
        Dodaje serwis wiadomości do listy
        
        Args:
            service: Serwis wiadomości implementujący AbstractService
        """
        self.news_services.append(service)
        logger.info(f"Dodano serwis wiadomości: {service.__class__.__name__}")

    async def sync_news(self, limit: int = 100, offset: int = 0) -> None:
        """
        Dodaje nowe newsy (na podstawie assetów z bazy danych) do bazy danych używając wzorca strategii na puli dostępnych serwisów.

        liczba limit definiuje ilość zapytań do pojedynczego serwisu. (max 100 aby nie wyczerpać darmowego limitu API)

        Args:
            limit: liczba assetów z bazy - która będzie przetwarzana do pobrania newsów (domyślnie 100)
            offset: offset dla pobierania assetów z bazy (domyślnie 0)

        Returns:
            None
        """
        try:
            # Inicjalizuj bazę danych jeśli nie została zainicjalizowana
            if not hasattr(self.db, 'factory') or self.db.factory is None:
                await self.db.init_db()
            
            # KROK 1: Pobierz assety z bazy danych
            logger.info("=== KROK 1: Pobieranie assety z bazy danych ===")
            assets = await self.db.get_factory().get_assets_table().get_all(
                limit=limit, 
                offset=offset
            )
            logger.info(f"Pobrano {len(assets)} assetów z bazy danych")
            
            if not assets:
                logger.warning("Brak assetów w bazie danych - nie można pobrać wiadomości")
                return None
            
            # KROK 2: Przetwórz każdy serwis wiadomości (wzorzec strategii)
            logger.info("=== KROK 2: Przetwarzanie serwisów wiadomości ===")
            
            for service in self.news_services:
                service_name = getattr(service, 'SERVICE_NAME', service.__class__.__name__)
                logger.info(f"Przetwarzam serwis: {service_name}")
                
                try:
                    for asset in assets:
                        # Pobierz wiadomości z API dla konkretnego assetu
                        news_data = service._get_news_request(
                            currencies=[asset['asset']]
                        )

                        if 'results' not in news_data:
                            logger.warning(f"Brak wyników w odpowiedzi API dla serwisu {service_name} i assetu {asset['asset']}")
                            continue
                        
                        # Przetwórz wiadomości (tylko te z assetami istniejącymi w bazie)
                        saved_count = 0
                        updated_count = 0
                        skipped_count = 0
                        logger.info(f"Rozpoczynam przetwarzanie {len(news_data['results'])} wiadomości z serwisu {service_name} dla assetu {asset['asset']}")
                        
                        for news_item in news_data['results']:
                            try:
                                # Sprawdź czy wiadomość już istnieje w bazie (po JSON content)
                                fundamental_analysis_table = self.db.get_factory().get_fundamental_analysis_table()
                                
                                # Konwertuj published_at na timestamp
                                published_at = news_item.get('published_at')
                                if published_at:
                                    # Konwertuj ISO 8601 na Unix timestamp
                                    dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                                    timestamp = int(dt.timestamp())
                                else:
                                    # Użyj aktualnego czasu jeśli brak published_at
                                    timestamp = int(datetime.now().timestamp())
                                
                                # Sprawdź czy wiadomość już istnieje dla tego timestamp i service
                                existing_analyses = await fundamental_analysis_table.get_by_timestamp_and_service(
                                    timestamp=timestamp,
                                    service=service_name,
                                    limit=1
                                )
                                
                                if existing_analyses:
                                    # Analiza już istnieje - dodaj asset do istniejącej analizy
                                    existing_analysis = existing_analyses[0]
                                    existing_analysis_id = existing_analysis['id']
                                    
                                    # Sprawdź czy asset już jest powiązany z tą analizą
                                    analysis_assets = await fundamental_analysis_table.get_analysis_assets(existing_analysis_id)
                                    asset_ids_in_analysis = [asset_info['id'] for asset_info in analysis_assets]
                                    
                                    if asset['id'] not in asset_ids_in_analysis:
                                        # Dodaj asset do istniejącej analizy
                                        success = await fundamental_analysis_table.add_asset_to_analysis(
                                            analysis_id=existing_analysis_id,
                                            asset_id=asset['id']
                                        )
                                        
                                        if success:
                                            updated_count += 1
                                            logger.debug(f"Dodano asset {asset['asset']} do istniejącej analizy {existing_analysis_id}")
                                        else:
                                            logger.error(f"Nie udało się dodać assetu {asset['asset']} do analizy {existing_analysis_id}")
                                    else:
                                        skipped_count += 1
                                        logger.debug(f"Asset {asset['asset']} już jest powiązany z analizą {existing_analysis_id}")
                                else:
                                    # Analiza nie istnieje - utwórz nową
                                    analysis_id = await fundamental_analysis_table.create(
                                        asset_ids=[asset['id']],
                                        timestamp=timestamp,
                                        content=news_item,  # Cały JSON jako content
                                        link=news_item.get('url'),  # URL z results
                                        service=service_name
                                    )
                                    
                                    if analysis_id:
                                        saved_count += 1
                                        logger.debug(f"Utworzono nową analizę {analysis_id} dla assetu {asset['asset']}")
                                    else:
                                        logger.error(f"Nie udało się utworzyć analizy dla assetu {asset['asset']}")
                                
                            except Exception as e:
                                logger.error(f"Błąd podczas przetwarzania wiadomości: {e}")
                                continue
                        
                        logger.info(f"Serwis {service_name}, Asset {asset['asset']}: utworzono {saved_count} nowych analiz, zaktualizowano {updated_count}, pominięto {skipped_count}")
                    
                except Exception as e:
                    logger.error(f"Błąd podczas przetwarzania serwisu {service_name}: {e}")
                    continue

            logger.info("=== Synchronizacja wiadomości zakończona ===")
            return None
            
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji wiadomości: {e}", exc_info=True)
            return None
