# Synapse Mobile (Flutter)

Synapse backend ile konuşan Flutter istemcisi. Welcome → Login/Register →
Dashboard (Main / Environments / Habits) akışı.

## Önkoşullar

- Flutter SDK **3.10+** (Dart 3.10+)
- Backend `http://127.0.0.1:8000` veya LAN IP'sinden erişilebilir
  (bkz. depo kökündeki [README](../README.md)).

## Hızlı başlangıç

```bash
cd frontend
flutter pub get

# Windows / macOS / iOS simülatör (varsayılan 127.0.0.1:8000)
flutter run

# Web (Chrome sorunluysa) — örn. port 5050
flutter run -d web-server --web-port 5050
# Tarayıcı: http://localhost:5050

# Android emulator (otomatik 10.0.2.2 kullanır)
flutter run -d emulator-5554

# Fiziksel cihaz — backend'in LAN IP'sini ver
flutter run --dart-define=API_HOST=192.168.1.10
```

## Yapılandırma

`lib/config/api_config.dart` üzerinden çalışır:

```dart
ApiConfig.baseUrl
```

- `--dart-define=API_HOST=<host>` verilirse `http://<host>:8000` kullanılır.
- Web: `http://127.0.0.1:8000`
- Android emulator: `http://10.0.2.2:8000`
- Diğer platformlar: `http://127.0.0.1:8000`

## Dizin yapısı

```
lib/
  config/           # API_HOST çözümleyici
  models/           # Veri sınıfları (Environment, Habit, JoinRequest, …)
  screens/          # welcome / login / register / dashboard / environments / habits
  services/         # SessionService, *_api.dart (HTTP istemciler)
  utils/            # environment_visuals (ikon eşleme vb.)
  widgets/          # NotificationsModal, ProfileModal, StreakGeneWidget
```

## Lint / analiz

```bash
flutter analyze
```

Ana lint kuralları `analysis_options.yaml` üzerinden alınır.

## Auth durumu (Sprint F)

- Tüm `*_api.dart` istemcileri `SessionService.authHeaders()` ile
  `Authorization: Bearer <jwt>` gönderir.
- Backend route'ları (devices, habits, environments, behavior-logs,
  recommendations) artık `user_id` query parametresi yerine token'dan
  kullanıcıyı okur. Eski parametre gönderilebilir ama token sub'ı ile
  eşleşmek zorundadır.
- Dashboard streak'i `GET /users/{id}/daily-activity` üzerinden gerçek
  davranış loglarından beslenir; "Active Advices" listesi de kullanıcının
  `/habits` listesinden `is_active=true` olanlardan oluşur.

## Öneri yenileme (Sprint E)

- `RecommendationRefreshService` — 30 sn sabit + olay sonrası 3 sn burst (90 sn).
- Tetikleyiciler: cihaz toggle, advice kaydı, uygulama resume, bildirim refresh.
- `RecommendationApi.getActive()` artık `user_id` query göndermez; token yeterli.

## Bilinen sınırlar

- Demo “home tips” kartları `notifications_modal.dart` içinde hâlâ statik örneklerdir.
- Inference veri üretmezse öneri banner’ı görünmeyebilir (normal).
