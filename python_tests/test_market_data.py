from unittest import TestCase

from sentiment.market_data import _eastmoney_secid, _parse_tencent_quotes, quote_symbol


class MarketDataTests(TestCase):
    def test_parses_tencent_quote_fields(self):
        fields = [""] * 33
        fields[1] = "测试股票"
        fields[2] = "600001"
        fields[3] = "10.50"
        fields[4] = "10.00"
        fields[30] = "20260901150000"
        fields[31] = "0.50"
        fields[32] = "5.00"
        payload = f'v_sh600001="{"~".join(fields)}";'
        quote = _parse_tencent_quotes(payload)["600001"]
        self.assertEqual(quote["price"], 10.5)
        self.assertEqual(quote["priceChange"], 5.0)
        self.assertEqual(quote["asOf"], "20260901150000")

    def test_market_index_uses_shanghai_prefix(self):
        target = {"id": "market", "stockCode": "000001", "quoteSymbol": "sh000001"}
        self.assertEqual(quote_symbol(target), "sh000001")
        self.assertEqual(_eastmoney_secid(target), "1.000001")

    def test_shanghai_stock_uses_market_one(self):
        target = {"id": "liquor", "stockCode": "600519"}
        self.assertEqual(_eastmoney_secid(target), "1.600519")
