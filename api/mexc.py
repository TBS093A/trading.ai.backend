from pymexc import spot
from .abstract import AbstractAPI


class MexcAPI(
    AbstractAPI
):

    def __init__(self, api_key: str, api_secret: str) -> None:
        self.__api_key = api_key
        self.__api_secret = api_secret

        self.__spot_client = spot.HTTP(
            api_key = self.__api_key,
            api_secret = self.__api_secret
        )

        self.__buy_transaction = {}
        self.__actual_size = 0.0
        self.__actual_price = 0.0
        self.__sell_transactions = {}

    def _market_order_request(self, transaction_side: str, coin: str, currency_size: float, used_currency: str):
        return self.__spot_client.new_order(
            symbol = f"{ coin }{ used_currency }",
            side = transaction_side,
            order_type = "MARKET",
            quantity = currency_size
        )

    def _limit_order_request(self, transaction_side: str, coin: str, coin_size: float, coin_price: float, used_currency: str):
        return self.__spot_client.new_order(
            symbol = f"{ coin }{ used_currency }",
            side = transaction_side,
            order_type = "LIMIT",
            quantity = coin_size,
            price = coin_price,
        )

    def __truncate_float(self, value: float, precision: float) -> float:
        if precision > 1 and type(precision) == int:
            precision = float("0." + (precision - 1) * "0" + "1")
        factor = int(1 / precision)
        return int(value * factor) / factor

    def __truncate_to_four_significant_digits(self, number: float, mode: str = "truncate") -> float:
        full_number = format(number, '.16f')
        num_str = full_number.split('.')

        if len(num_str) > 1:
            integer_part = num_str[0]
            decimal_part = num_str[1]

            non_zero_start = 0
            for i, digit in enumerate(decimal_part):
                if digit != '0':
                    non_zero_start = i
                    break

            truncated_decimal_part = decimal_part[non_zero_start:non_zero_start + 4]

            truncated_number_str = integer_part + '.' + decimal_part[:non_zero_start] + truncated_decimal_part

            return float(truncated_number_str)

        return number

    def get_available_currency_percent_price(self, percent_size: float, currency: str = None, asset_type: str = "SPOT"):
        available_assets = self.__spot_client.account_information()

        if available_assets["accountType"] == asset_type:
            for asset in available_assets["balances"]:
                if asset["asset"] == currency:
                    return str(
                        float(asset["free"]) * float(percent_size)
                    )
        return 0.0

    def get_lot_size(self, base_currency: str = "BTC", quote_currency: str = "USDT"):
        symbol_info = self.__spot_client.exchange_info(
            symbol = f"{ base_currency }{ quote_currency }"
        )

        for symbol in symbol_info["symbols"]:
            if symbol["baseAsset"] == base_currency:
                if symbol["quoteAsset"] == quote_currency:

                    base_size_precision = float(symbol["baseSizePrecision"])

                    if base_size_precision == 0:
                        base_size_precision = 1

                    return {
                        "base_asset_precision": symbol["baseAssetPrecision"],
                        "base_commission_precision": symbol["baseCommissionPrecision"],
                        "base_size_precision": str(base_size_precision),

                        "quote_precision": symbol["quotePrecision"],
                        "quote_asset_precision": symbol["quoteAssetPrecision"],
                        "quote_commission_precision": symbol["quoteCommissionPrecision"],
                        "quote_amount_precision": symbol["quoteAmountPrecision"],
                        "quote_max_amount": symbol["maxQuoteAmount"],
                        "is_spot_trading_allowed": str(symbol["isSpotTradingAllowed"]).lower() == "true",
                        "is_margin_trading_allowed": str(symbol["isMarginTradingAllowed"]).lower() == "true"
                    }

    def get_bid_and_ask_prices(self, base_currency: str = "BTC", quote_currency: str = "USDT"):
        """
            bid - best available buy price (the lowest)
            ask - best available sell price (the highest)
        """
        symbol = self.__spot_client.ticker_book_price(
            symbol = f"{ base_currency }{ quote_currency }"
        )

        if symbol["symbol"] == f"{ base_currency }{ quote_currency }":
            return {
                "bid_price": symbol["bidPrice"],
                "bid_size": symbol["bidQty"],
                "ask_price": symbol["askPrice"],
                "ask_size": symbol["askQty"]
            }

    def get_ticker(self, base_currency: str = "BTC", quote_currency: str = "USDT"):
        return self.__spot_client.ticker_price(
            symbol = f"{ base_currency }{ quote_currency }"
        )

    def buy(self, coin: str, currency_percent_size_to_buy: float, used_currency: str = "USDT", price_buy_balance_percent: float = 0.1):

        symbol_lot_size = self.get_lot_size(
            base_currency = coin,
            quote_currency = used_currency
        )

        ticker_data = self.get_ticker(
            base_currency = coin,
            quote_currency = used_currency
        )

        best_ticker_data = self.get_bid_and_ask_prices(
            base_currency = coin,
            quote_currency = used_currency
        )

        available_currency_assets = self.get_available_currency_percent_price(
            percent_size = currency_percent_size_to_buy,
            currency = used_currency
        )

        coin_buy_proportion = (float(available_currency_assets) / float(ticker_data["price"]))

        self.__actual_price = float(ticker_data["price"])

        print("pre-buy:")
        print(f"\tcoin_buy_size / coin_buy_proportion ({coin_buy_proportion}) = (available_currency_assets ({available_currency_assets}) / ticker_data['price'] ({ticker_data['price']}))")


        coin_size_to_buy = self.__truncate_float(
            value = coin_buy_proportion,
            precision = int(symbol_lot_size["base_asset_precision"])
        )

        self.__actual_size = coin_size_to_buy

        approach = "market"

        print()
        print(f"buy ({approach}):")
        print(f"\tcoin: {coin}")
        print(f"\tcoin buy quantity (size): {coin_size_to_buy}")
        print(f"\tused currency: {used_currency}")

        transaction_dict = self._market_order_request(
            transaction_side = "BUY",
            coin = coin,
            currency_size = coin_size_to_buy,
            used_currency = used_currency
        )

        bought_asset_size = self.get_available_currency_percent_price(
            percent_size = 100,
            currency = coin
        )

        if bought_asset_size == 0:

            print()
            print("market price no available!")

            price_one_houndred_percent = float(best_ticker_data["ask_price"])
            price_percent_balance = float(
                format(
                    price_one_houndred_percent * float(price_buy_balance_percent),
                    f".{len(str(price_one_houndred_percent))}f"
                )
            )

            self.__actual_price = float(ticker_data["price"])

            coin_high_limit_price = float(
                format(
                    price_one_houndred_percent + price_percent_balance,
                    f".{len(str(price_one_houndred_percent))}f"
                )
            )

            coin_low_limit_price = float(best_ticker_data["bid_price"])

            print(f"\tcoin_low_limit_price ({coin_low_limit_price})")

            print(f"\tcoin_high_limit_price ({coin_high_limit_price})")

            coin_buy_proportion = (float(available_currency_assets) / float(coin_high_limit_price))

            self.__actual_price = float(best_ticker_data["ask_price"])

            print()
            print("pre-buy:")
            print(f"\tcoin_buy_size / coin_buy_proportion ({coin_buy_proportion}) = (available_currency_assets ({available_currency_assets}) / best_ticker_data['ask_price'] ({best_ticker_data['ask_price']}))")


            coin_size_to_buy = self.__truncate_float(
                value = coin_buy_proportion,
                precision = int(symbol_lot_size["base_asset_precision"])
            )

            self.__actual_size = coin_size_to_buy

            coin_price = coin_high_limit_price

            approach = "limit"

            print()
            print(f"buy ({approach}):")
            print(f"\tcoin: {coin}")
            print(f"\tcoin buy quantity (size): {coin_size_to_buy}")
            print(f"\tused currency: {used_currency}")

            transaction_dict = self._limit_order_request(
                transaction_side = "BUY",
                coin = coin,
                coin_size = coin_size_to_buy,
                coin_price = coin_price,
                used_currency = used_currency,
            )

        transaction_dict = dict(
            {
                "side": "buy",
                "approach": approach,
                "coin": coin,
                "coin_price_at_buy": ticker_data["price"],
                "coin_buy_size": coin_size_to_buy,
                "currency_used_to_buy_percent": float(currency_percent_size_to_buy) * 100,
                "currency_used_to_buy": available_currency_assets,
                "used_currency": used_currency,
            },
            **transaction_dict
        )

        return transaction_dict

    def sell(self, coin: str, coin_percent_size_to_sell: float, used_currency: str = "USDT", price_sell_balance_percent: float = 0.1):

        symbol_lot_size = self.get_lot_size(
            base_currency = coin,
            quote_currency = used_currency,
        )

        available_coin_assets = self.get_available_currency_percent_price(
            percent_size = coin_percent_size_to_sell,
            currency = coin
        )

        coin_sell_proportion = float(available_coin_assets)

        print()
        print("pre-sell")
        print(f"\tcoin_sell_size / coin_sell_proportion ({coin_sell_proportion}) = available_coin_assets ({available_coin_assets})")

        coin_sell_size = self.__truncate_float(
            value = coin_sell_proportion,
            precision = int(symbol_lot_size["base_asset_precision"])
        )

        self.__actual_size = float(available_coin_assets) - float(coin_sell_size)

        ticker_data = self.get_ticker(
            base_currency = coin,
            quote_currency = used_currency
        )

        best_ticker_data = self.get_bid_and_ask_prices(
            base_currency = coin,
            quote_currency = used_currency
        )

        price_one_houndred_percent = float(best_ticker_data["bid_price"])
        price_percent_balance = float(
            format(
                price_one_houndred_percent * float(price_sell_balance_percent),
                f".{len(str(price_one_houndred_percent))}f"
            )
        )

        self.__actual_price = float(ticker_data["price"])

        coin_low_limit_price = float(
            format(
                price_one_houndred_percent - price_percent_balance,
                f".{len(str(price_one_houndred_percent))}f"
            )
        )

        coin_high_limit_price = float(best_ticker_data["ask_price"])

        print(f"\tcoin_low_limit_price ({coin_low_limit_price})")

        print(f"\tcoin_high_limit_price ({coin_high_limit_price})")

        coin_price = coin_low_limit_price

        approach = "limit"

        print()
        print("sell ({approach}):")
        print(f"\tcoin: {coin}")
        print(f"\tcoin sell quantity (size): {coin_sell_size}")
        print(f"\tcoin price: {coin_price}")
        print(f"\tused currency: {used_currency}")

        transaction_dict = self._limit_order_request(
            transaction_side = "SELL",
            coin = coin,
            coin_size = coin_sell_size,
            coin_price = coin_price,
            used_currency = used_currency,
        )

        pretty_coin_sell_size = format(
            coin_sell_size,
            f".{len(str(int(1 / float(symbol_lot_size['base_size_precision']))))}f"
        )

        pretty_coin_sell_percent = float(coin_percent_size_to_sell) * 100

        pretty_price_sell_balance_percent = float(price_sell_balance_percent) * 100

        pretty_sell_profit = float(best_ticker_data["ask_price"]) * coin_sell_size

        pretty_coin_size_availability_after_sell = format(
            float(
                self.get_available_currency_percent_price(
                    percent_size = 1.0,
                    currency = coin
                )
            ),
            f".{len(str(int(1 / float(symbol_lot_size['base_size_precision']))))}f"
        )

        transaction_dict = dict(
            {
                "side": "sell",
                "approach": approach,
                "coin": coin,
                "coin_price_at_sell": ticker_data["price"],
                "coin_used_price_at_sell": coin_price,
                "coin_sell_size": pretty_coin_sell_size,
                "coin_sell_percent": pretty_coin_sell_percent,
                "coin_size_availability_after_sell": pretty_coin_size_availability_after_sell,
                "sell_profit": pretty_sell_profit,
                "used_currency": used_currency,
            },
            **transaction_dict
        )

        return transaction_dict

