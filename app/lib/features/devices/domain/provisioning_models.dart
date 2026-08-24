class ProvisioningAccessPoint {
  const ProvisioningAccessPoint({
    required this.ssid,
    required this.rssi,
    required this.authMode,
  });

  factory ProvisioningAccessPoint.fromJson(Map<String, dynamic> json) {
    return ProvisioningAccessPoint(
      ssid: json['ssid'] as String? ?? '',
      rssi: (json['rssi'] as num?)?.toInt() ?? -100,
      authMode: (json['authmode'] as num?)?.toInt() ?? 0,
    );
  }

  final String ssid;
  final int rssi;
  final int authMode;

  bool get isOpen => authMode == 0;
}

class ProvisioningScanResult {
  const ProvisioningScanResult({
    required this.accessPoints,
    required this.supports5G,
  });

  factory ProvisioningScanResult.fromJson(Map<String, dynamic> json) {
    final raw = json['aps'];
    return ProvisioningScanResult(
      supports5G: json['support_5g'] == true,
      accessPoints: raw is List
          ? raw
                .whereType<Map>()
                .map(
                  (item) => ProvisioningAccessPoint.fromJson(
                    Map<String, dynamic>.from(item),
                  ),
                )
                .where((item) => item.ssid.isNotEmpty)
                .toList(growable: false)
          : const <ProvisioningAccessPoint>[],
    );
  }

  final List<ProvisioningAccessPoint> accessPoints;
  final bool supports5G;
}

enum ProvisioningPhase {
  idle,
  connectingHotspot,
  scanning,
  submitting,
  waiting,
  success,
  failure,
}
