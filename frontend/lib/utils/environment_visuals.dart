import 'package:flutter/material.dart';

/// Environment card icons (keys match backend `icon_key`).
IconData environmentIconForKey(String? key) {
  switch (key) {
    case 'home':
      return Icons.home_rounded;
    case 'office':
      return Icons.business_rounded;
    case 'car':
      return Icons.directions_car_rounded;
    case 'gym':
      return Icons.fitness_center_rounded;
    case 'beach':
      return Icons.beach_access_rounded;
    case 'shop':
      return Icons.storefront_rounded;
    case 'cafe':
      return Icons.local_cafe_rounded;
    case 'cottage':
      return Icons.cabin_rounded;
    case 'school':
      return Icons.school_rounded;
    case 'warehouse':
      return Icons.warehouse_rounded;
    default:
      return Icons.domain_rounded;
  }
}

const List<MapEntry<String, String>> kEnvironmentIconChoices = [
  MapEntry('home', 'Home'),
  MapEntry('office', 'Office'),
  MapEntry('car', 'Car'),
  MapEntry('gym', 'Gym'),
  MapEntry('beach', 'Vacation'),
  MapEntry('shop', 'Shop'),
  MapEntry('cafe', 'Cafe'),
  MapEntry('cottage', 'Cottage'),
  MapEntry('school', 'School'),
  MapEntry('warehouse', 'Warehouse'),
];

IconData? userAvatarIconForKey(String? key) {
  switch (key) {
    case 'person':
      return Icons.person_rounded;
    case 'face':
      return Icons.face_rounded;
    case 'face_3':
      return Icons.face_3_rounded;
    case 'woman':
      return Icons.woman_rounded;
    case 'man':
      return Icons.man_rounded;
    case 'boy':
      return Icons.boy_rounded;
    case 'girl':
      return Icons.girl_rounded;
    case 'sports':
      return Icons.sports_handball_rounded;
    default:
      return null;
  }
}

const List<MapEntry<String, String>> kUserAvatarChoices = [
  MapEntry('person', 'Person'),
  MapEntry('face', 'Face'),
  MapEntry('face_3', 'Portrait'),
  MapEntry('woman', 'Woman'),
  MapEntry('man', 'Man'),
  MapEntry('boy', 'Boy'),
  MapEntry('girl', 'Girl'),
  MapEntry('sports', 'Sports'),
];

/// Member row avatar: icon from `avatar_key`, else first letter of name.
Widget memberAvatar({
  required String? avatarKey,
  required String? fullName,
  double radius = 22,
}) {
  final icon = userAvatarIconForKey(avatarKey);
  final trimmed = fullName?.trim() ?? '';
  final initial = trimmed.isNotEmpty
      ? trimmed[0].toUpperCase()
      : '?';

  return CircleAvatar(
    radius: radius,
    backgroundColor: const Color(0xFF2A3148),
    child: icon != null
        ? Icon(icon, color: Colors.white, size: radius * 1.1)
        : Text(
            initial,
            style: TextStyle(
              color: Colors.white,
              fontSize: radius * 0.95,
              fontWeight: FontWeight.w700,
            ),
          ),
  );
}
