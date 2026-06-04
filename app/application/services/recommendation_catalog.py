"""Personalized cold-start advice catalog (BMI x age curated).

Picks exactly 4 advice items for a user based on:
  - BMI category (under, normal, over, obese)
  - Age category (young, adult, middle, senior)

Independent from the CSV peer-group `ColdStartEngine`; this is a simple,
explainable rule layer used to populate the dashboard's "Active Advices"
section right after signup (and to filter recommendations forever, not just
at cold start).
"""

from __future__ import annotations

from typing import Literal, TypedDict

BmiCategory = Literal["under", "normal", "over", "obese"]
AgeCategory = Literal["young", "adult", "middle", "senior"]


class AdviceItem(TypedDict):
    key: str
    title: str
    summary: str
    icon: str  # Material icon name (rendered on the Flutter side)


ADVICE_CATALOG: dict[str, AdviceItem] = {
    "reading_time": {
        "key": "reading_time",
        "title": "Reading Time",
        "summary": "Wind down with a focused session; Synapse aligns lighting with your routine.",
        "icon": "menu_book",
    },
    "hydration": {
        "key": "hydration",
        "title": "Hydration Check",
        "summary": "Aim for 8 glasses of water across the day — your home reminds you on time.",
        "icon": "local_drink",
    },
    "sleep_routine": {
        "key": "sleep_routine",
        "title": "Sleep Routine",
        "summary": "Same bedtime every night helps your body lock in 7–8 hours of recovery.",
        "icon": "bedtime",
    },
    "morning_sunlight": {
        "key": "morning_sunlight",
        "title": "Morning Sunlight",
        "summary": "Ten minutes outdoors after waking boosts mood and vitamin D.",
        "icon": "wb_sunny",
    },
    "screen_curfew": {
        "key": "screen_curfew",
        "title": "Screen Curfew",
        "summary": "Drop the phone 30 minutes before bed to fall asleep faster.",
        "icon": "phonelink_off",
    },
    "posture_break": {
        "key": "posture_break",
        "title": "Posture Break",
        "summary": "Stand up and stretch every two hours to protect your back.",
        "icon": "accessibility_new",
    },
    "light_walk": {
        "key": "light_walk",
        "title": "Light Walk",
        "summary": "A 15 minute walk after meals helps digestion and energy.",
        "icon": "directions_walk",
    },
    "brisk_walk": {
        "key": "brisk_walk",
        "title": "Brisk Walk",
        "summary": "Thirty minutes of brisk cardio supports a healthy heart and weight.",
        "icon": "directions_run",
    },
    "strength_training": {
        "key": "strength_training",
        "title": "Strength Training",
        "summary": "Body-weight strength work 3x a week builds lean muscle and bone density.",
        "icon": "fitness_center",
    },
    "low_impact_mobility": {
        "key": "low_impact_mobility",
        "title": "Low-Impact Mobility",
        "summary": "Yoga, swimming, or stationary cycling keep joints happy.",
        "icon": "self_improvement",
    },
    "fruit_break": {
        "key": "fruit_break",
        "title": "Fruit Break",
        "summary": "One small portion of fruit gives a steady energy curve.",
        "icon": "restaurant",
    },
    "high_protein_snack": {
        "key": "high_protein_snack",
        "title": "High-Protein Snack",
        "summary": "Egg, yoghurt, or cheese keep you full and steady between meals.",
        "icon": "egg_alt",
    },
    "calorie_dense_meal": {
        "key": "calorie_dense_meal",
        "title": "Calorie-Dense Meal",
        "summary": "Add nuts, avocado, and olive oil to grow muscle and reach a healthier weight.",
        "icon": "set_meal",
    },
    "portion_control": {
        "key": "portion_control",
        "title": "Portion Control",
        "summary": "Use a smaller plate to enjoy meals while keeping portions in check.",
        "icon": "restaurant_menu",
    },
    "reduce_sugar": {
        "key": "reduce_sugar",
        "title": "Reduce Added Sugar",
        "summary": "Skip sugary drinks and snacks today — your energy will stay smoother.",
        "icon": "no_food",
    },
}


# ---- BMI / age helpers --------------------------------------------------


def bmi_value(height_cm: float | int, weight_kg: float | int) -> float | None:
    """Return BMI rounded to 2 digits, or None when inputs are invalid."""
    try:
        h_m = float(height_cm) / 100.0
        w = float(weight_kg)
    except (TypeError, ValueError):
        return None
    if h_m <= 0 or w <= 0:
        return None
    return round(w / (h_m * h_m), 2)


def bmi_category(bmi: float | None) -> BmiCategory:
    """Map a BMI value to one of the 4 cold-start buckets."""
    if bmi is None:
        return "normal"
    if bmi < 18.5:
        return "under"
    if bmi < 25.0:
        return "normal"
    if bmi < 30.0:
        return "over"
    return "obese"


def age_category(age: int | None) -> AgeCategory:
    if age is None:
        return "adult"
    a = int(age)
    if a < 30:
        return "young"
    if a < 45:
        return "adult"
    if a < 60:
        return "middle"
    return "senior"


# ---- Curated 4 picks per (bmi x age) cell -------------------------------

# Each tuple lists 4 advice keys ordered by display priority.
_PICKS: dict[tuple[BmiCategory, AgeCategory], tuple[str, str, str, str]] = {
    # Underweight — focus on calories, protein, gentle activity
    ("under", "young"): ("calorie_dense_meal", "high_protein_snack", "strength_training", "reading_time"),
    ("under", "adult"): ("calorie_dense_meal", "high_protein_snack", "strength_training", "hydration"),
    ("under", "middle"): ("calorie_dense_meal", "high_protein_snack", "morning_sunlight", "posture_break"),
    ("under", "senior"): ("high_protein_snack", "morning_sunlight", "posture_break", "hydration"),
    # Normal — maintain and build healthy routines
    ("normal", "young"): ("strength_training", "light_walk", "reading_time", "hydration"),
    ("normal", "adult"): ("light_walk", "strength_training", "sleep_routine", "posture_break"),
    ("normal", "middle"): ("light_walk", "posture_break", "morning_sunlight", "sleep_routine"),
    ("normal", "senior"): ("morning_sunlight", "light_walk", "posture_break", "hydration"),
    # Overweight — gradual cardio + nutrition guardrails
    ("over", "young"): ("brisk_walk", "strength_training", "portion_control", "reduce_sugar"),
    ("over", "adult"): ("brisk_walk", "strength_training", "portion_control", "reduce_sugar"),
    ("over", "middle"): ("brisk_walk", "posture_break", "portion_control", "reduce_sugar"),
    ("over", "senior"): ("light_walk", "posture_break", "portion_control", "reduce_sugar"),
    # Obese — joint-friendly movement + portion/sugar focus
    ("obese", "young"): ("brisk_walk", "portion_control", "reduce_sugar", "high_protein_snack"),
    ("obese", "adult"): ("brisk_walk", "portion_control", "reduce_sugar", "high_protein_snack"),
    ("obese", "middle"): ("low_impact_mobility", "portion_control", "reduce_sugar", "hydration"),
    ("obese", "senior"): ("low_impact_mobility", "morning_sunlight", "portion_control", "hydration"),
}


def pick_advice_keys(bmi: float | None, age: int | None) -> list[str]:
    """Return the curated 4 advice keys for the given profile."""
    cell = (bmi_category(bmi), age_category(age))
    keys = _PICKS.get(cell)
    if keys is None:
        # Safe fallback that always renders something useful.
        keys = ("hydration", "sleep_routine", "light_walk", "reading_time")
    return list(keys)


def pick_advices(bmi: float | None, age: int | None) -> list[AdviceItem]:
    return [ADVICE_CATALOG[k] for k in pick_advice_keys(bmi, age) if k in ADVICE_CATALOG]


def describe_profile(
    *, height_cm: int | None, weight_kg: int | None, age: int | None
) -> dict[str, object]:
    """Return BMI value + category + age category for explainability."""
    bmi = bmi_value(height_cm or 0, weight_kg or 0) if height_cm and weight_kg else None
    return {
        "bmi": bmi,
        "bmi_category": bmi_category(bmi),
        "age_category": age_category(age),
    }
