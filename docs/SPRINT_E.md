# Sprint E — Öneri polling ve otomatik yenileme

Dashboard ve bildirimler, backend’de üretilen **pending** önerileri otomatik takip eder.

## Backend

- `GET /recommendations/active` — **Bearer zorunlu** (token `sub` → kullanıcı)
- Süresi dolmuş pending kayıtlar `RECOMMENDATION_MAX_AGE_MINUTES` ile elenir

## Frontend — `RecommendationRefreshService`

| Davranış | Aralık |
|----------|--------|
| Sabit polling | 30 sn |
| Olay sonrası “burst” | 3 sn × 90 sn |

**Burst tetikleyiciler:**

- Uygulama ön plana dönünce (`AppLifecycleState.resumed`)
- Cihaz aç/kapa (`PATCH /devices`)
- Dashboard’da advice **Save** → `POST /behavior-logs`
- Bildirim çekmecesinde **Refresh**

Servis `main()` içinde `attach()` ile oturum dinler; token yokken durur.

## UI

- **Main** sekmesi: pending öneri banner’ı (Accept / Dismiss)
- **Bildirim zili** rozeti: join istekleri + aktif öneri
- **Notifications** sheet: aynı öneri kartı (paylaşımlı servis)

## Test

```bash
pytest -q tests/test_api_auth_smoke.py::test_protected_routes_require_bearer_token
pytest -q tests/test_recommendations_smoke.py
```

## Manuel

1. Giriş yap, ortamda cihaz aç/kapa veya advice kaydet.
2. ~3–30 sn içinde Main’de mavi öneri banner’ı veya bildirim rozeti görünmeli.
3. Inference veri üretmezse banner çıkmayabilir — bu beklenen davranıştır.
