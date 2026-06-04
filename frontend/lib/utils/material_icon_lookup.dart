import 'package:flutter/material.dart';

/// Lookup table for Material icons referenced by name from the backend.
const Map<String, IconData> kMaterialIconLookup = <String, IconData>{
  'menu_book': Icons.menu_book,
  'local_drink': Icons.local_drink,
  'bedtime': Icons.bedtime,
  'wb_sunny': Icons.wb_sunny,
  'phonelink_off': Icons.phonelink_off,
  'accessibility_new': Icons.accessibility_new,
  'directions_walk': Icons.directions_walk,
  'directions_run': Icons.directions_run,
  'fitness_center': Icons.fitness_center,
  'self_improvement': Icons.self_improvement,
  'restaurant': Icons.restaurant,
  'egg_alt': Icons.egg_alt,
  'set_meal': Icons.set_meal,
  'restaurant_menu': Icons.restaurant_menu,
  'no_food': Icons.no_food,
  'lightbulb_outline': Icons.lightbulb_outline,
};

IconData iconForName(String name) =>
    kMaterialIconLookup[name] ?? Icons.lightbulb_outline;
