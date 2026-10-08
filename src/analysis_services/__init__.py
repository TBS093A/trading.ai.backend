"""
Serwisy analizy technicznej wydzielone z TechnicalAnalysis (src/sync_technical_analysis.py):

- KlinesSource              - wybór giełdy assetu i pobieranie świec (jedno miejsce dla wszystkich ścieżek)
- PatternStore              - zapis formacji harmonicznych (upsert po kluczu punktów, wersja silnika)
- ConfluencePostProcessor   - konfluencje liczone po zapisie (Fib cluster, wyższe TF)
- HarmonicScanService       - skan zakresów na żądanie (GET /harmonics) i okna pokrycia
- SetupTrackingService      - setupy XABCD i ich wyniki (src/harmonic_setups.py), zdarzenia do alertów
- StrengthService           - model siły formacji (src/pattern_strength.py): uczenie i cache

TechnicalAnalysis zostaje orkiestratorem nocnego syncu i fasadą dla zadań Celery / kontrolerów.
"""

from .klines_source import KlinesSource, ResolvedAsset
from .pattern_store import PatternStore
from .confluence_postprocessor import ConfluencePostProcessor
from .harmonic_scan_service import HarmonicScanService
from .setup_tracking_service import SetupTrackingService
from .strength_service import StrengthService

__all__ = [
    "KlinesSource", "ResolvedAsset", "PatternStore", "ConfluencePostProcessor",
    "HarmonicScanService", "SetupTrackingService", "StrengthService",
]
