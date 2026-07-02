class StockAlert {
  final String id;
  final String symbol;
  final String name;
  final double targetPrice;
  final String condition; // 'above' | 'below'
  final bool isActive;
  final DateTime createdAt;

  StockAlert({
    required this.id,
    required this.symbol,
    required this.name,
    required this.targetPrice,
    required this.condition,
    this.isActive = true,
    required this.createdAt,
  });

  Map<String, dynamic> toJson() => {
        'id': id,
        'symbol': symbol,
        'name': name,
        'target_price': targetPrice,
        'condition': condition,
        'is_active': isActive,
        'created_at': createdAt.toIso8601String(),
      };

  factory StockAlert.fromJson(Map<String, dynamic> json) {
    return StockAlert(
      id: json['id'] as String,
      symbol: json['symbol'] as String,
      name: json['name'] as String,
      targetPrice: (json['target_price'] as num).toDouble(),
      condition: json['condition'] as String,
      isActive: json['is_active'] as bool? ?? true,
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }

  StockAlert copyWith({
    bool? isActive,
    double? targetPrice,
    String? condition,
  }) {
    return StockAlert(
      id: id,
      symbol: symbol,
      name: name,
      targetPrice: targetPrice ?? this.targetPrice,
      condition: condition ?? this.condition,
      isActive: isActive ?? this.isActive,
      createdAt: createdAt,
    );
  }
}

class WatchlistItem {
  final String symbol;
  final String name;
  final DateTime addedAt;

  WatchlistItem({
    required this.symbol,
    required this.name,
    required this.addedAt,
  });

  Map<String, dynamic> toJson() => {
        'symbol': symbol,
        'name': name,
        'added_at': addedAt.toIso8601String(),
      };

  factory WatchlistItem.fromJson(Map<String, dynamic> json) {
    return WatchlistItem(
      symbol: json['symbol'] as String,
      name: json['name'] as String,
      addedAt: DateTime.parse(json['added_at'] as String),
    );
  }
}
