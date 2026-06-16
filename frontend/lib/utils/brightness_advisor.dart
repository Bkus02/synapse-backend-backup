/// Oda bazli lamba parlakligi onerisi.
///
/// Oda secimi sabit bir katalogdan yapilir (Study Room, Standard Room, Rest Room)
/// boylece yazim hatasi veya eslesme sorunu olmaz.
class BrightnessRecommendation {
  const BrightnessRecommendation({
    required this.percent,
    required this.roomLabel,
  });

  /// Onerilen parlaklik yuzdesi (0-100).
  final int percent;

  /// Kullaniciya gosterilecek oda etiketi.
  final String roomLabel;
}

/// Sabit oda katalogu — DB'ye bu Ingilizce etiketler kaydedilir.
class RoomCatalogOption {
  const RoomCatalogOption({
    required this.label,
    required this.brightnessPercent,
    required this.subtitle,
  });

  final String label;
  final int brightnessPercent;
  final String subtitle;
}

const List<RoomCatalogOption> kRoomCatalogOptions = [
  RoomCatalogOption(
    label: 'Study Room',
    brightnessPercent: 80,
    subtitle: 'Focused work — recommended 80%',
  ),
  RoomCatalogOption(
    label: 'Standard Room',
    brightnessPercent: 60,
    subtitle: 'Living / general — recommended 60%',
  ),
  RoomCatalogOption(
    label: 'Rest Room',
    brightnessPercent: 30,
    subtitle: 'Bedroom / rest — recommended 30%',
  ),
];

/// Eski Turkce veya serbest metin oda adlarini kataloga esler.
RoomCatalogOption? roomCatalogOptionForLabel(String? room) {
  final normalized = (room ?? '').trim();
  if (normalized.isEmpty) return null;

  for (final opt in kRoomCatalogOptions) {
    if (opt.label == normalized) return opt;
  }

  final lower = normalized.toLowerCase();
  if (lower.contains('study') ||
      lower.contains('çalış') ||
      lower.contains('calis') ||
      lower.contains('office') ||
      lower.contains('ofis')) {
    return kRoomCatalogOptions[0];
  }
  if (lower.contains('rest') ||
      lower.contains('dinlen') ||
      lower.contains('yatak') ||
      lower.contains('bedroom') ||
      lower.contains('sleep')) {
    return kRoomCatalogOptions[2];
  }
  if (lower.contains('standard') ||
      lower.contains('normal') ||
      lower.contains('salon') ||
      lower.contains('living')) {
    return kRoomCatalogOptions[1];
  }
  return null;
}

const BrightnessRecommendation _generalDefault = BrightnessRecommendation(
  percent: 60,
  roomLabel: 'Standard Room',
);

/// Verilen oda etiketine gore parlaklik onerisi.
BrightnessRecommendation brightnessRecommendationForRoom(String? room) {
  final opt = roomCatalogOptionForLabel(room);
  if (opt != null) {
    return BrightnessRecommendation(
      percent: opt.brightnessPercent,
      roomLabel: opt.label,
    );
  }
  return _generalDefault;
}
