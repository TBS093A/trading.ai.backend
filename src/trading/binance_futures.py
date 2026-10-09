"""
Adapter Binance USDT-M Futures (najpierw testnet) - ten sam przepływ co PaperExchange: zlecenie wejścia limit,
po wypełnieniu SL (STOP_MARKET, reduceOnly) i TP (LIMIT albo TAKE_PROFIT_MARKET, reduceOnly), anulowanie,
stan zleceń i pozycji.

- Klient REST z podpisem HMAC-SHA256; transport HTTP wstrzykiwany (testy - atrapa giełdy, bez sieci).
  Klucz i sekret nie trafiają do logów, wyjątków ani repr - w błędach jest tylko metoda, ścieżka i kod Binance.
- Idempotencja: każde zlecenie ma client order id z trading_orders.client_order_id. Gdy nie wiadomo, czy
  zlecenie doszło (timeout, błąd sieci), następny przebieg pyta giełdę o ten id zamiast wystawiać drugie.
- Zlecenia warunkowe (STOP_MARKET, TAKE_PROFIT_MARKET) od 2025-12 idą przez Algo Order API
  (/fapi/v1/algoOrder, clientAlgoId); LIMIT i MARKET - zwykłe /fapi/v1/order.
- Filtry symbolu (tickSize, stepSize, minQty, min notional) z exchangeInfo; margin isolated, dźwignia 1-2x,
  tryb one-way (pozycja netto na symbolu - hedge mode jest odrzucany).
"""

import asyncio
import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

BASE_URLS = {
    "binance_futures_testnet": "https://testnet.binancefuture.com",
    "binance_futures": "https://fapi.binance.com",
}
# Zmienne środowiskowe z kluczem trade-only (SealedSecret w cloud.config).
CREDENTIAL_ENV = {
    "binance_futures_testnet": ("BINANCE_FUTURES_TESTNET_API_KEY", "BINANCE_FUTURES_TESTNET_API_SECRET"),
    "binance_futures": ("BINANCE_FUTURES_API_KEY", "BINANCE_FUTURES_API_SECRET"),
}
LIVE_EXCHANGES = tuple(BASE_URLS)

ALGO_TYPES = {"STOP_MARKET", "TAKE_PROFIT_MARKET"}
ORDER_TYPES = {"limit": "LIMIT", "market": "MARKET", "stop_market": "STOP_MARKET",
               "take_profit_market": "TAKE_PROFIT_MARKET"}
ORDER_STATUS = {"NEW": "open", "PARTIALLY_FILLED": "partially_filled", "FILLED": "filled", "CANCELED": "cancelled",
                "EXPIRED": "expired", "EXPIRED_IN_MATCH": "expired", "REJECTED": "rejected"}
ALGO_OPEN = {"NEW", "TRIGGERING"}
ALGO_TERMINAL = {"CANCELED": "cancelled", "EXPIRED": "expired", "REJECTED": "rejected"}
# "Order does not exist" / "Unknown order sent" - zlecenia nie ma (nie doszło albo już nieaktywne).
# Inny kod przy zapytaniu = wyjątek: lepiej przerwać przebieg niż wystawić zlecenie drugi raz.
NOT_FOUND_CODES = {-2013, -2011}
NO_CHANGE_CODES = {-4046}          # "No need to change margin type."
WOULD_TRIGGER_CODE = -2021         # "Order would immediately trigger."
TIME_CODE = -1021                  # znacznik czasu poza recvWindow

Transport = Callable[[str, str, Dict[str, str]], Awaitable[Tuple[int, Any]]]


class BinanceError(Exception):
    """Giełda odpowiedziała błędem (zlecenie na pewno nie zostało przyjęte w tym wywołaniu)."""

    def __init__(self, status: int, code: Optional[int], msg: str, method: str, path: str):
        self.status, self.code, self.msg = status, code, msg
        super().__init__(f"Binance {method} {path}: HTTP {status}, kod {code}: {msg}")


def requests_transport(timeout: float = 10.0) -> Transport:
    """Domyślny transport: requests w wątku (silnik jest asynchroniczny, requests jest już w zależnościach)."""
    import requests

    session = requests.Session()

    def call(method: str, url: str, headers: Dict[str, str]) -> Tuple[int, Any]:
        response = session.request(method, url, headers=headers, timeout=timeout)
        try:
            body = response.json()
        except ValueError:
            body = {"code": None, "msg": response.text[:200]}
        return response.status_code, body

    async def transport(method: str, url: str, headers: Dict[str, str]) -> Tuple[int, Any]:
        return await asyncio.to_thread(call, method, url, headers)

    return transport


class BinanceFuturesClient:
    """Podpisany klient REST /fapi. Sekret tylko w atrybucie prywatnym, nigdy w logach ani wyjątkach."""

    def __init__(self, api_key: str, api_secret: str, base_url: str, transport: Optional[Transport] = None,
                 recv_window: int = 10_000, clock: Callable[[], float] = time.time):
        if not api_key or not api_secret:
            raise ValueError("Binance Futures: brak klucza API lub sekretu")
        self.__api_key = api_key
        self.__api_secret = api_secret.encode()
        self.base_url = base_url.rstrip("/")
        self.transport = transport or requests_transport()
        self.recv_window = recv_window
        self.clock = clock
        self.time_offset_ms = 0

    def __repr__(self) -> str:
        return f"BinanceFuturesClient(base_url={self.base_url!r}, api_key=***)"

    def _sign(self, query: str) -> str:
        return hmac.new(self.__api_secret, query.encode(), hashlib.sha256).hexdigest()

    async def request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None,
                      signed: bool = True, _retry_time: bool = True) -> Any:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        headers = {}
        if signed:
            params["recvWindow"] = self.recv_window
            params["timestamp"] = int(self.clock() * 1000) + self.time_offset_ms
            query = urlencode(params)
            query += "&signature=" + self._sign(query)
            headers["X-MBX-APIKEY"] = self.__api_key
        else:
            query = urlencode(params)
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        status, body = await self.transport(method, url, headers)
        if status >= 400 or (isinstance(body, dict) and isinstance(body.get("code"), int) and body["code"] < 0):
            code = body.get("code") if isinstance(body, dict) else None
            msg = str(body.get("msg") if isinstance(body, dict) else body)[:300]
            if code == TIME_CODE and signed and _retry_time:
                await self.sync_time()
                params.pop("timestamp", None)
                params.pop("recvWindow", None)
                return await self.request(method, path, params, signed, _retry_time=False)
            raise BinanceError(status, code, msg, method, path)
        return body

    async def sync_time(self) -> None:
        body = await self.request("GET", "/fapi/v1/time", signed=False)
        self.time_offset_ms = int(body["serverTime"]) - int(self.clock() * 1000)


# ─────────────────────────── filtry symbolu ───────────────────────────

@dataclass(frozen=True)
class SymbolRules:
    symbol: str
    tick_size: Decimal
    step_size: Decimal
    min_qty: Decimal
    max_qty: Decimal
    min_notional: Decimal

    @staticmethod
    def _round(value: float, step: Decimal, mode) -> Decimal:
        return (Decimal(str(value)) / step).to_integral_value(rounding=mode) * step

    def price(self, value: float, mode: str = "nearest") -> Decimal:
        rounding = {"nearest": ROUND_HALF_UP, "down": ROUND_DOWN, "up": ROUND_UP}[mode]
        return self._round(value, self.tick_size, rounding).quantize(self.tick_size)

    def qty(self, value: float) -> Decimal:
        return self._round(value, self.step_size, ROUND_DOWN).quantize(self.step_size)

    def check(self, qty: Decimal, price: Decimal) -> Optional[str]:
        """Powód odrzucenia przez filtry albo None."""
        if qty < self.min_qty:
            return f"ilość {qty} < minQty {self.min_qty}"
        if qty > self.max_qty:
            return f"ilość {qty} > maxQty {self.max_qty}"
        if qty * price < self.min_notional:
            return f"wartość {qty * price:.4f} < min notional {self.min_notional}"
        return None


def futures_symbol(symbol: str) -> str:
    """'BTC/USDT' -> 'BTCUSDT'."""
    return symbol.replace("/", "").replace("-", "").upper()


def _fmt(value) -> str:
    return format(Decimal(str(value)).normalize(), "f")


@dataclass
class OrderState:
    """Stan zlecenia z giełdy w słowniku silnika (open | partially_filled | filled | cancelled | expired | rejected)."""
    client_order_id: str
    exchange_order_id: Optional[str]
    status: str
    filled_qty: float
    avg_price: float
    update_time: int
    fill_order_id: Optional[str] = None     # zwykłe orderId z wypełnieniami (dla algo - actualOrderId)


@dataclass
class PositionState:
    amount: float          # ze znakiem: + long, - short (tryb one-way)
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    leverage: int
    margin_type: str


class BinanceFuturesExchange:
    """Operacje silnika na Binance USDT-M Futures. Zlecenia opisane wierszami trading_orders."""

    def __init__(self, client: BinanceFuturesClient, quote_asset: str = "USDT"):
        self.client = client
        self.quote_asset = quote_asset
        self._rules: Optional[Dict[str, SymbolRules]] = None
        self._prepared: Dict[str, int] = {}
        self._one_way_checked = False

    # ─────────── symbol i konto ───────────

    async def rules(self, symbol: str) -> Optional[SymbolRules]:
        if self._rules is None:
            info = await self.client.request("GET", "/fapi/v1/exchangeInfo", signed=False)
            self._rules = {}
            for s in info.get("symbols", []):
                if s.get("status") != "TRADING" or s.get("contractType") != "PERPETUAL":
                    continue
                f = {x["filterType"]: x for x in s.get("filters", [])}
                if "PRICE_FILTER" not in f or "LOT_SIZE" not in f:
                    continue
                self._rules[s["symbol"]] = SymbolRules(
                    s["symbol"], Decimal(f["PRICE_FILTER"]["tickSize"]).normalize(),
                    Decimal(f["LOT_SIZE"]["stepSize"]).normalize(), Decimal(f["LOT_SIZE"]["minQty"]),
                    Decimal(f["LOT_SIZE"]["maxQty"]), Decimal(f.get("MIN_NOTIONAL", {}).get("notional", "0")),
                )
        return self._rules.get(futures_symbol(symbol))

    async def balance(self) -> float:
        """Saldo portfela (wallet balance) w walucie rozliczenia - bez niezrealizowanego wyniku."""
        for row in await self.client.request("GET", "/fapi/v2/balance"):
            if row.get("asset") == self.quote_asset:
                return float(row["balance"])
        return 0.0

    async def position(self, symbol: str) -> PositionState:
        rows = await self.client.request("GET", "/fapi/v2/positionRisk", {"symbol": futures_symbol(symbol)})
        row = next((r for r in rows if r.get("positionSide", "BOTH") == "BOTH"), rows[0] if rows else {})
        return PositionState(float(row.get("positionAmt", 0)), float(row.get("entryPrice", 0)),
                             float(row.get("markPrice", 0)), float(row.get("unRealizedProfit", 0)),
                             int(float(row.get("leverage", 0) or 0)), str(row.get("marginType", "")).lower())

    async def prepare(self, symbol: str, leverage: int) -> None:
        """One-way mode, margin isolated i dźwignia przed pierwszym wejściem na symbolu (raz na przebieg)."""
        sym = futures_symbol(symbol)
        if not self._one_way_checked:
            mode = await self.client.request("GET", "/fapi/v1/positionSide/dual")
            if mode.get("dualSidePosition"):
                raise RuntimeError("konto Binance Futures w trybie hedge - silnik wymaga trybu one-way")
            self._one_way_checked = True
        if self._prepared.get(sym) == leverage:
            return
        pos = await self.position(symbol)
        if pos.margin_type != "isolated":
            try:
                await self.client.request("POST", "/fapi/v1/marginType", {"symbol": sym, "marginType": "ISOLATED"})
            except BinanceError as e:
                if e.code not in NO_CHANGE_CODES:
                    raise
        if pos.leverage != leverage:
            await self.client.request("POST", "/fapi/v1/leverage", {"symbol": sym, "leverage": leverage})
        self._prepared[sym] = leverage

    # ─────────── zlecenia ───────────

    @staticmethod
    def is_algo(order: Dict[str, Any]) -> bool:
        return ORDER_TYPES[order["order_type"]] in ALGO_TYPES

    async def place(self, order: Dict[str, Any], rules: SymbolRules) -> OrderState:
        """Wystawia zlecenie z wiersza trading_orders. Wyjście (purpose != entry) zawsze reduceOnly."""
        btype = ORDER_TYPES[order["order_type"]]
        sym = futures_symbol(order["symbol"])
        params: Dict[str, Any] = {"symbol": sym, "side": order["side"].upper(), "type": btype,
                                  "quantity": _fmt(rules.qty(order["qty"]))}
        if order["purpose"] != "entry":
            params["reduceOnly"] = "true"
        if btype in ALGO_TYPES:
            params.update(algoType="CONDITIONAL", triggerPrice=_fmt(rules.price(order["price"])),
                          workingType="MARK_PRICE", clientAlgoId=order["client_order_id"])
            body = await self.client.request("POST", "/fapi/v1/algoOrder", params)
            return self._algo_state(body)
        params["newClientOrderId"] = order["client_order_id"]
        params["newOrderRespType"] = "RESULT"
        if btype == "LIMIT":
            params.update(timeInForce="GTC", price=_fmt(rules.price(order["price"])))
        return self._order_state(await self.client.request("POST", "/fapi/v1/order", params))

    async def get(self, order: Dict[str, Any]) -> Optional[OrderState]:
        """Stan po client order id; None = giełda nie zna zlecenia."""
        sym = futures_symbol(order["symbol"])
        try:
            if self.is_algo(order):
                body = await self.client.request("GET", "/fapi/v1/algoOrder", {"clientAlgoId": order["client_order_id"]})
                state = self._algo_state(body)
                if state.fill_order_id:
                    inner = self._order_state(await self.client.request(
                        "GET", "/fapi/v1/order", {"symbol": sym, "orderId": state.fill_order_id}))
                    state.status, state.filled_qty, state.avg_price = inner.status, inner.filled_qty, inner.avg_price
                    state.update_time = inner.update_time
                return state
            return self._order_state(await self.client.request(
                "GET", "/fapi/v1/order", {"symbol": sym, "origClientOrderId": order["client_order_id"]}))
        except BinanceError as e:
            if e.code in NOT_FOUND_CODES:
                return None
            raise

    async def cancel(self, order: Dict[str, Any]) -> Optional[OrderState]:
        """Anuluje i zwraca stan po anulowaniu (mogło się wypełnić w międzyczasie)."""
        try:
            if self.is_algo(order):
                await self.client.request("DELETE", "/fapi/v1/algoOrder", {"clientAlgoId": order["client_order_id"]})
            else:
                await self.client.request("DELETE", "/fapi/v1/order", {"symbol": futures_symbol(order["symbol"]),
                                                                       "origClientOrderId": order["client_order_id"]})
        except BinanceError as e:
            if e.code not in NOT_FOUND_CODES:
                raise
        return await self.get(order)

    async def open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """Otwarte zlecenia na symbolu (zwykłe i algo): client_order_id, algo."""
        sym = futures_symbol(symbol)
        regular = await self.client.request("GET", "/fapi/v1/openOrders", {"symbol": sym})
        algo = await self.client.request("GET", "/fapi/v1/openAlgoOrders", {"symbol": sym})
        if isinstance(algo, dict):
            algo = algo.get("orders", [])
        return ([{"client_order_id": o["clientOrderId"], "algo": False} for o in regular] +
                [{"client_order_id": o["clientAlgoId"], "algo": True} for o in algo])

    async def cancel_by_client_id(self, symbol: str, client_order_id: str, algo: bool) -> None:
        try:
            if algo:
                await self.client.request("DELETE", "/fapi/v1/algoOrder", {"clientAlgoId": client_order_id})
            else:
                await self.client.request("DELETE", "/fapi/v1/order", {"symbol": futures_symbol(symbol),
                                                                       "origClientOrderId": client_order_id})
        except BinanceError as e:
            if e.code not in NOT_FOUND_CODES:
                raise

    async def commission(self, symbol: str, order_id: Optional[str]) -> Optional[float]:
        """Suma prowizji z wypełnień zlecenia (w walucie rozliczenia); None = nieznana (inna waluta, brak)."""
        if not order_id:
            return None
        trades = await self.client.request("GET", "/fapi/v1/userTrades",
                                           {"symbol": futures_symbol(symbol), "orderId": order_id})
        if not trades or any(t.get("commissionAsset") != self.quote_asset for t in trades):
            return None
        return sum(float(t["commission"]) for t in trades)

    # ─────────── odpowiedzi -> stan ───────────

    @staticmethod
    def _order_state(body: Dict[str, Any]) -> OrderState:
        return OrderState(body["clientOrderId"], str(body["orderId"]), ORDER_STATUS.get(body["status"], "open"),
                          float(body.get("executedQty") or 0), float(body.get("avgPrice") or 0),
                          int(body.get("updateTime") or body.get("time") or 0), str(body["orderId"]))

    @staticmethod
    def _algo_state(body: Dict[str, Any]) -> OrderState:
        status = body.get("algoStatus", "NEW")
        actual = str(body.get("actualOrderId") or "") or None
        if actual:
            mapped = "open"   # wyzwolone - wynik w zwykłym zleceniu (get() dopytuje)
        elif status in ALGO_OPEN:
            mapped = "open"
        else:
            mapped = ALGO_TERMINAL.get(status, "cancelled")
        return OrderState(body["clientAlgoId"], str(body["algoId"]), mapped, 0.0, 0.0,
                          int(body.get("updateTime") or 0), actual)


def credentials_configured(exchange: str) -> bool:
    names = CREDENTIAL_ENV.get(exchange)
    return bool(names and os.getenv(names[0]) and os.getenv(names[1]))


def from_env(exchange: str, transport: Optional[Transport] = None) -> BinanceFuturesExchange:
    if exchange not in BASE_URLS:
        raise ValueError(f"nieznana giełda: {exchange}")
    key_env, secret_env = CREDENTIAL_ENV[exchange]
    if not credentials_configured(exchange):
        raise RuntimeError(f"{exchange}: brak {key_env} / {secret_env} w środowisku")
    client = BinanceFuturesClient(os.environ[key_env], os.environ[secret_env], BASE_URLS[exchange], transport)
    return BinanceFuturesExchange(client)
