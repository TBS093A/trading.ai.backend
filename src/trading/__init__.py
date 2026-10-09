"""
Trading z sygnałów setupów XABCD.

- risk.py           - ustawienia ryzyka (pola z opisem, warianty, wielkość pozycji, podgląd na historii)
- paper_exchange.py - giełda symulowana: wypełnienia zleceń na prawdziwych świecach (te same reguły co
                      symulator setupów), opłaty i poślizg
- engine.py         - sygnały z setupów -> kontrola ryzyka -> zlecenia -> pozycje -> wynik, z dziennikiem
- binance_futures.py - adapter Binance USDT-M Futures (testnet / live): podpisany REST, filtry symbolu,
                      zlecenia po client order id, margin isolated, dźwignia
- live.py           - przepływ konta na giełdzie: te same kroki co paper, wypełnienia z giełdy,
                      rekoncyliacja w każdym przebiegu (giełda wygrywa, rozbieżności w trading_events)
"""
