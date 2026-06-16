/// Oda bazli lamba parlakligi onerisi.
///
/// Standart aydinlatma kilavuzlarina gore her oda tipinin onerilen parlaklik
/// yuzdesi farklidir (calisma odasi yuksek, yatak odasi dusuk vb.). Cihazin
/// `room` alanindaki serbest metni anahtar kelimelerle eslestirip uygun
/// yuzdeyi doneriz. Eslesme yoksa `null` doner (oneri gosterilmez).
class BrightnessRecommendation {
  const BrightnessRecommendation({
    required this.percent,
    required this.roomLabel,
  });

  /// Onerilen parlaklik yuzdesi (0-100).
  final int percent;

  /// Kullaniciya gosterilecek oda etiketi (orn. "calisma odasi").
  final String roomLabel;
}

class _RoomRule {
  const _RoomRule(this.keywords, this.percent, this.label);
  final List<String> keywords;
  final int percent;
  final String label;
}

// Siralama onemli: daha ozel odalar (calisma, yemek) genel odalardan (oda)
// once gelmeli.
const List<_RoomRule> _rules = [
  _RoomRule(
    ['calisma', 'çalışma', 'study', 'office', 'ofis', 'work', 'desk', 'ders'],
    80,
    'çalışma odası',
  ),
  _RoomRule(
    ['mutfak', 'kitchen'],
    75,
    'mutfak',
  ),
  _RoomRule(
    ['banyo', 'bathroom', 'tuvalet', 'wc', 'lavabo'],
    70,
    'banyo',
  ),
  _RoomRule(
    ['yemek', 'dining'],
    70,
    'yemek odası',
  ),
  _RoomRule(
    ['cocuk', 'çocuk', 'kids', 'nursery', 'bebek', 'oyun'],
    60,
    'çocuk odası',
  ),
  _RoomRule(
    ['salon', 'oturma', 'living', 'lounge', 'misafir'],
    60,
    'salon',
  ),
  _RoomRule(
    ['koridor', 'hol', 'antre', 'hallway', 'corridor', 'giris', 'giriş'],
    45,
    'koridor',
  ),
  _RoomRule(
    [
      'yatak',
      'uyku',
      'dinlenme',
      'bedroom',
      'rest',
      'sleep',
      'yatma',
    ],
    30,
    'yatak / dinlenme odası',
  ),
];

/// Taninmayan veya bos oda icin varsayilan genel ic mekan aydinlatmasi.
const BrightnessRecommendation _generalDefault = BrightnessRecommendation(
  percent: 60,
  roomLabel: 'genel ortam',
);

/// Verilen oda adina gore parlaklik onerisi.
///
/// Oda tanidik bir tipe (calisma/salon/yatak vb.) eslesirse ona ozel deger,
/// aksi halde genel ic mekan varsayilani (%60) doner. Boylece her lambada
/// kullaniciya bir oneri gosterilir.
BrightnessRecommendation brightnessRecommendationForRoom(String? room) {
  final normalized = (room ?? '').trim().toLowerCase();
  if (normalized.isNotEmpty) {
    for (final rule in _rules) {
      if (rule.keywords.any(normalized.contains)) {
        return BrightnessRecommendation(
          percent: rule.percent,
          roomLabel: rule.label,
        );
      }
    }
  }
  return _generalDefault;
}
