#!/usr/bin/env python3
"""
Test runner dla projektu telegram.pump.bot
Umożliwia uruchamianie testów z katalogu tests z możliwością wyboru konkretnego zestawu testów.
"""

import sys
import os
import argparse
import unittest
from pathlib import Path

# Dodaj katalog główny projektu do ścieżki Python
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def get_available_testsets():
    """Zwraca listę dostępnych zestawów testów"""
    tests_dir = project_root / "tests"
    testsets = []
    
    if tests_dir.exists():
        for file in tests_dir.glob("*.py"):
            if file.name.startswith("test.") and file.name != "__init__.py":
                testset_name = file.stem  # nazwa bez rozszerzenia
                testsets.append(testset_name)
    
    return testsets

def run_tests(testset=None):
    """Uruchamia testy"""
    tests_dir = project_root / "tests"
    
    if not tests_dir.exists():
        print(f"❌ Katalog tests nie istnieje: {tests_dir}")
        return False
    
    # Konfiguracja discover
    loader = unittest.TestLoader()
    start_dir = str(tests_dir)
    
    if testset:
        # Uruchom konkretny zestaw testów
        testset_file = tests_dir / f"{testset}.py"
        if not testset_file.exists():
            print(f"❌ Plik testowy nie istnieje: {testset_file}")
            return False
        
        # Załaduj testy z konkretnego pliku
        suite = loader.discover(start_dir, pattern=f"{testset}.py")
    else:
        # Uruchom wszystkie testy
        suite = loader.discover(start_dir, pattern="test*.py")
    
    # Uruchom testy
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()

def main():
    parser = argparse.ArgumentParser(
        description="Test runner dla projektu telegram.pump.bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Przykłady użycia:
  python tests.py                           # Uruchom wszystkie testy
  python tests.py --set-testset test.ai.analysis  # Uruchom konkretny zestaw testów
  python tests.py --list-testsets          # Pokaż dostępne zestawy testów
        """
    )
    
    parser.add_argument(
        "--set-testset",
        help="Nazwa konkretnego zestawu testów do uruchomienia (np. test.ai.analysis)"
    )
    
    parser.add_argument(
        "--list-testsets",
        action="store_true",
        help="Pokaż listę dostępnych zestawów testów"
    )
    
    args = parser.parse_args()
    
    if args.list_testsets:
        testsets = get_available_testsets()
        if testsets:
            print("📋 Dostępne zestawy testów:")
            for testset in sorted(testsets):
                print(f"  • {testset}")
        else:
            print("❌ Nie znaleziono żadnych zestawów testów")
        return
    
    print("🚀 Uruchamianie testów...")
    print(f"📁 Katalog projektu: {project_root}")
    print(f"📁 Katalog testów: {project_root / 'tests'}")
    
    if args.set_testset:
        print(f"🎯 Uruchamiam zestaw testów: {args.set_testset}")
    else:
        print("🎯 Uruchamiam wszystkie testy")
    
    success = run_tests(args.set_testset)
    
    if success:
        print("✅ Wszystkie testy zakończone sukcesem!")
        sys.exit(0)
    else:
        print("❌ Niektóre testy zakończone niepowodzeniem!")
        sys.exit(1)

if __name__ == "__main__":
    main() 