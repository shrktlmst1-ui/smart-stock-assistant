import 'package:smart_stock_assistant/services/api_config.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('production API base URL has no trailing slash', () {
    expect(ApiConfig.productionApiBaseUrl,
        'https://smart-stock-assistant-api.onrender.com');
    expect(ApiConfig.productionApiBaseUrl.endsWith('/'), isFalse);
  });

  test('baseUrl default is localhost for VM tests', () {
    expect(ApiConfig.baseUrl, 'http://localhost:8000');
  });
}
