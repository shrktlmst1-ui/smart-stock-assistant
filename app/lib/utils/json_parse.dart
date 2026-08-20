/// Flexible JSON field parsing — handles bool, int, and string encodings.
library;

bool parseJsonBool(
  dynamic value, {
  bool defaultValue = false,
}) {
  if (value == null) return defaultValue;
  if (value is bool) return value;
  if (value is num) return value != 0;
  if (value is String) {
    final normalized = value.trim().toLowerCase();
    if (normalized == 'true' || normalized == '1' || normalized == 'yes') {
      return true;
    }
    if (normalized == 'false' || normalized == '0' || normalized == 'no') {
      return false;
    }
  }
  return defaultValue;
}

bool readJsonBool(
  Map<String, dynamic> json,
  List<String> keys, {
  bool defaultValue = false,
}) {
  for (final key in keys) {
    if (json.containsKey(key)) {
      return parseJsonBool(json[key], defaultValue: defaultValue);
    }
  }
  return defaultValue;
}

int readJsonInt(
  Map<String, dynamic> json,
  List<String> keys, {
  int defaultValue = 0,
}) {
  for (final key in keys) {
    final value = json[key];
    if (value == null) continue;
    if (value is int) return value;
    if (value is num) return value.toInt();
    if (value is String) {
      final parsed = int.tryParse(value.trim());
      if (parsed != null) return parsed;
    }
  }
  return defaultValue;
}

String readJsonString(
  Map<String, dynamic> json,
  List<String> keys, {
  String defaultValue = '',
}) {
  for (final key in keys) {
    final value = json[key];
    if (value == null) continue;
    return value.toString();
  }
  return defaultValue;
}
