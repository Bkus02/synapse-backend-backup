import 'brightness_advisor.dart';

/// AC / thermostat temperature recommendation for a city + room.
class TemperatureRecommendation {
  const TemperatureRecommendation({
    required this.celsius,
    required this.roomLabel,
    required this.city,
    this.peerMedianCelsius,
    this.peerCount = 0,
  });

  final int celsius;
  final String roomLabel;
  final String city;
  final int? peerMedianCelsius;
  final int peerCount;
}

/// Local fallback when the API is unreachable (matches backend tables).
const Map<String, Map<String, int>> kCityRoomTemps = {
  'Izmir': {'Study Room': 24, 'Standard Room': 25, 'Rest Room': 26},
  'Istanbul': {'Study Room': 23, 'Standard Room': 24, 'Rest Room': 25},
  'Ankara': {'Study Room': 26, 'Standard Room': 27, 'Rest Room': 28},
};

String _asciiFoldTr(String text) {
  return text
      .replaceAll('İ', 'i')
      .replaceAll('I', 'i')
      .replaceAll('ı', 'i')
      .replaceAll('Ş', 's')
      .replaceAll('ş', 's')
      .replaceAll('Ç', 'c')
      .replaceAll('ç', 'c')
      .replaceAll('Ö', 'o')
      .replaceAll('ö', 'o')
      .replaceAll('Ü', 'u')
      .replaceAll('ü', 'u')
      .replaceAll('Ğ', 'g')
      .replaceAll('ğ', 'g');
}

String normalizeCityKey(String? location) {
  if (location == null || location.trim().isEmpty) return 'Istanbul';
  final key = _asciiFoldTr(location.trim()).toLowerCase();
  if (key.contains('izmir')) return 'Izmir';
  if (key.contains('ankara')) return 'Ankara';
  if (key.contains('istanbul')) return 'Istanbul';
  return 'Istanbul';
}

TemperatureRecommendation temperatureRecommendationForRoom({
  required String? room,
  required String? userLocation,
  Map<String, int>? apiCelsiusByRoom,
  int? peerMedianCelsius,
  int peerCount = 0,
  String? apiCity,
}) {
  final roomLabel =
      roomCatalogOptionForLabel(room)?.label ?? 'Standard Room';
  final city = apiCity ?? normalizeCityKey(userLocation);

  if (apiCelsiusByRoom != null && apiCelsiusByRoom.containsKey(roomLabel)) {
    return TemperatureRecommendation(
      celsius: apiCelsiusByRoom[roomLabel]!,
      roomLabel: roomLabel,
      city: city,
      peerMedianCelsius: peerMedianCelsius,
      peerCount: peerCount,
    );
  }

  final table = kCityRoomTemps[city] ?? kCityRoomTemps['Istanbul']!;
  return TemperatureRecommendation(
    celsius: table[roomLabel] ?? table['Standard Room']!,
    roomLabel: roomLabel,
    city: city,
    peerMedianCelsius: peerMedianCelsius,
    peerCount: peerCount,
  );
}
