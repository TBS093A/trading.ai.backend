"""
Trading z sygnałów setupów XABCD.

- risk.py           - ustawienia ryzyka (pola z opisem, warianty, wielkość pozycji, podgląd na historii)
- paper_exchange.py - giełda symulowana: wypełnienia zleceń na prawdziwych świecach (te same reguły co
                      symulator setupów), opłaty i poślizg
- engine.py         - sygnały z setupów -> kontrola ryzyka -> zlecenia -> pozycje -> wynik, z dziennikiem

Adaptery prawdziwych giełd (Binance USDT-M Futures, najpierw testnet) mają ten sam interfejs co
PaperExchange: submit / cancel / sync zleceń - dochodzą w osobnym PR.
"""
