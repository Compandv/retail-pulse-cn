from unittest import TestCase
from unittest.mock import MagicMock, patch
from sentiment.collectors import request_text

class DataNetworkTests(TestCase):
    def test_domestic_direct_only_and_explicit_system_override(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{}'
        response.__enter__.return_value.headers.get_content_charset.return_value = 'utf-8'
        with patch.dict('os.environ', {}, clear=True), patch('sentiment.collectors.urllib.request.build_opener') as build, patch('sentiment.collectors.urllib.request.urlopen', return_value=response) as system:
            build.return_value.open.return_value = response
            self.assertEqual(request_text('https://gbapi.eastmoney.com/test', ''), '{}')
            self.assertEqual(build.call_args.args[0].proxies, {})
            system.assert_not_called()
            request_text('https://api.openai.com/test', '')
            system.assert_called_once()
            with patch.dict('os.environ', {'RETAIL_DATA_PROXY_MODE': 'system'}):
                request_text('https://gbapi.eastmoney.com/test', '')
            self.assertEqual(system.call_count, 2)
            request_text('https://eastmoney.com.example.org/test', '')
            self.assertEqual(system.call_count, 3)
