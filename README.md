# Synapse — Akıllı Ev Davranış Öneri Sistemi

Synapse, kullanıcı davranış loglarından örüntü çıkararak proaktif öneriler üreten
bir akıllı ev platformudur. Backend tarafında **FastAPI + SQLModel + PostgreSQL**
hexagonal mimarisi, analytics tarafında **pandas + scikit-learn** ile sequence
mining, cold‑start (peer‑profil) motoru ve anomali tespiti vardır. Mobil istemci
**Flutter** ile yazılmıştır.

```
┌──────────────┐   HTTP/JSON   ┌────────────────────────────────────────┐
│  Flutter UI  │ ───────────▶ │  FastAPI (app/api/routes)              │
└──────────────┘               │   │                                    │
                               │   ▼                                    │
                               │  Application services (use cases)      │
                               │   │                                    │
                               │   ▼                                    │
                               │  Domain (core/domain, core/ports)      │
                               │   │                                    │
                               │   ▼                                    │
                               │  Infrastructure (SQLModel, events)     │
                               └────────────────┬───────────────────────┘
                                                │
                                       ┌────────▼─────────┐
                                       │  PostgreSQL      │
                                       └──────────────────┘
```

## İçerik

- [Hızlı başlangıç](#hızlı-başlangıç)
- [Ortam değişkenleri](#ortam-değişkenleri)
- [Veritabanı şeması](#veritabanı-şeması)
- [Backend'i çalıştırma](#backendi-çalıştırma)
- [Docker (compose)](#docker-compose)
- [Continuous Integration](#continuous-integration)
- [Test](#test)
- [Frontend (Flutter)](#frontend-flutter)
- [Analitik araçlar](#analitik-araçlar)
- [Operasyonel komutlar](#operasyonel-komutlar)
- [Dizin yapısı](#dizin-yapısı)
- [Mimari notlar](#mimari-notlar)

## Hızlı başlangıç

> Gereklilikler: **Python 3.11+**, **PostgreSQL 14+**, **Flutter 3.10+** (frontend için).

```powershell
# 1) Bağımlılıkları kur
python -m venv venv
.\venv\Scripts\Activate.ps1            # Windows PowerShell
# kaynak venv/bin/activate              # macOS / Linux

pip install -r requirements-dev.txt    # dev araçları + prod paketleri

# 2) Konfigürasyon
copy .env.example .env                  # Windows
# cp .env.example .env                  # macOS / Linux
# .env içindeki DATABASE_URL'i kendi PG kurulumuna göre düzenle

# 3) Veritabanı şemasını kur (migrationlar idempotent)
python -m app.ops apply-migrations

# 4) (Opsiyonel) Sentetik veri üret
python -m app.ops generate-synthetic-data --to-db

# 5) Backend'i başlat
uvicorn app.main:app --reload --port 8000

# 6) Sağlık kontrolü
# http://127.0.0.1:8000/healthz   -> "ok"
# http://127.0.0.1:8000/readyz    -> "ready"  (DB'ye bağlanır)
# http://127.0.0.1:8000/docs      -> OpenAPI Swagger UI
```

## Ortam değişkenleri

Tüm ayarlar `app/core/settings.py` içindeki tek `Settings` sınıfı üzerinden
okunur (Pydantic `BaseSettings`). `.env` dosyası ve OS ortam değişkenleri
desteklenir. Örnek değerler için [`.env.example`](.env.example) bakın.

| Değişken | Varsayılan | Açıklama |
|----------|------------|----------|
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5433/postgres` | SQLAlchemy bağlantı dizesi |
| `APP_NAME` | `Synapse Backend` | OpenAPI başlığı |
| `APP_ENV` | `dev` | `dev` / `test` / `prod` |
| `LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR`/`CRITICAL` |
| `CORS_ORIGINS` | *(boş)* | Virgül ayrılmış kesin origin listesi; boşsa localhost regex'i |
| `SEQUENCE_DECAY_LAMBDA` | `0.0077` | Sequence miner zaman çürümesi |
| `SUNRISE_HOUR` / `SUNSET_HOUR` | `6` / `19` | Decision engine gündüz/gece kontrolü |
| `PRE_SUNSET_LIGHT_PENALTY` | `0.65` | Gün doğumu‑gün batımı arasında ışık önerisi indirimi |
| `RECOMMENDATION_MAX_AGE_MINUTES` | `5` | Pending recommendation expire süresi |
| `HABIT_MATRIX_REBUILD_HOUR` | `3` | Gece habit matrix yenileme saati |
| `JWT_SECRET_KEY` | *(dev placeholder)* | JWT imza anahtarı — **prod'da mutlaka değiştirin** |
| `JWT_ALGORITHM` | `HS256` | JWT imza algoritması |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Access token ömrü (dakika) |

## Veritabanı şeması

Migration'lar `migrations/` altındadır ve **sırayla** çalıştırılmalıdır.
Tek komutla:

```powershell
python -m app.ops apply-migrations
```

| Sıra | Dosya | İçerik |
|------|-------|--------|
| 000 | `000_init_schema.sql` | ENUM tipleri + temel tablolar (users, environments, devices, behavior_logs, habits, positive_advices, user_environments, user_streaks) |
| 001 | `001_add_behavior_logs_parameters.sql` | `behavior_logs.parameters` |
| 002 | `002_create_recommendations.sql` | `recommendations` + `recommendation_status` |
| 003 | `003_create_habit_matrix.sql` | `habit_matrix` |
| 004 | `004_add_recommendation_type_context.sql` | `recommendation_type`, `context` |
| 005 | `005_environment_membership_ui_fields.sql` | `icon_key`, `avatar_key`, `environment_join_requests` |
| 006 | `006_add_devices_room.sql` | `devices.room` |

Tüm dosyalar idempotent (`IF NOT EXISTS` / `DO $$`).

**SQLite (test) için fallback:**

```powershell
python -m app.ops bootstrap-db
```

`SQLModel.metadata.create_all` ile model‑tabanlı oluşturma yapar (ENUM'lar
SQLite'ta `TEXT`'e düşer; PG'de migration'ı tercih edin).

## Backend'i çalıştırma

```powershell
uvicorn app.main:app --reload --port 8000
```

Açılışta:
- `app/core/logging_config.py` ile structured logging devreye girer.
- `lifespan` DB bağlantısını doğrular ve gece habit matrix scheduler'ını başlatır.
- `/docs` üzerinden Swagger UI, `/redoc` üzerinden ReDoc kullanılabilir.

### Önemli endpoint'ler (özet)

| Yol | Metod | Amaç |
|-----|-------|------|
| `/auth/login` | POST | Email/parola → `{access_token, token_type, expires_in, user}` (bcrypt + JWT) |
| `/auth/me` | GET | Geçerli `Authorization: Bearer <token>` → aktif kullanıcı |
| `/users` | GET/POST/PATCH | Kullanıcı yönetimi |
| `/environments` | GET/POST/DELETE | Ev / ortam yönetimi |
| `/environments/{id}/members` | GET | Üye listesi |
| `/environments/{id}/join-requests` | GET/POST/approve/reject | Katılma istekleri |
| `/devices` | GET/POST/DELETE | Cihaz CRUD (environment scope) |
| `/behavior-logs` | GET/POST/DELETE | Davranış logları (POST sonrası inference) |
| `/behavior-logs/sequences` | GET | Canlı sequence mining |
| `/behavior-logs/rebuild-habit-matrix` | POST | Habit matrix rebuild |
| `/habits` | GET/POST/PATCH/DELETE | Habit kayıtları |
| `/recommendations/active` | GET | En güncel pending öneri |
| `/recommendations/{id}/accept` ve `/reject` | POST | Onay/ret |

> **Auth durumu (Sprint B sonrası):**
> - Parolalar bcrypt ile hashlenir; `/auth/login` JWT access token döndürür.
> - `GET /auth/me` token doğrulama uç noktasıdır.
> - `PATCH /users/{id}` token gönderiliyorsa yalnız kendi profili güncellenir.
> - **Sprint F (tam):** Aşağıdaki route'larda **Bearer token zorunludur**:
>   `/habits`, `/devices`, `/environments` (write/list), `/behavior-logs`,
>   `/recommendations`. `user_id` query parametresi artık token'dan okunur;
>   gönderilirse token sub'ı ile eşleşmek zorundadır (uyuşmazlıkta 403).
> - `GET /users/{id}/daily-activity?days=N`: kullanıcının son N gününde
>   BehaviorLog bulunduğu günlerin listesi (dashboard streak için).
>   Sahiplik kontrolü: yalnız kendi log'unu okuyabilirsiniz.
>
> **Migration uyarısı:** Sprint B öncesi PG'de düz metin parolayla kaydedilmiş
> kullanıcılar artık login olamaz. Aşağıdaki SQL ile parolaları sıfırlayın
> veya kullanıcıyı yeniden oluşturun:
>
> ```sql
> UPDATE public.users SET password_hash = NULL WHERE password_hash IS NOT NULL
>   AND password_hash NOT LIKE '$2a$%'
>   AND password_hash NOT LIKE '$2b$%'
>   AND password_hash NOT LIKE '$2y$%';
> ```
>
> Sonra `PATCH /users/{id}` ile yeni parola ayarlanabilir (token gerekir).

## Docker (compose)

Tüm yığını tek komutla ayağa kaldırmak için `docker-compose.yml` sağlanmıştır:
PostgreSQL 16 + migrations one-shot + FastAPI servisi.

```powershell
# Önce .env dosyasını hazırla (POSTGRES_PASSWORD ve JWT_SECRET_KEY zorunlu).
copy .env.example .env

docker compose up --build
# API: http://127.0.0.1:8000/docs
# DB:  localhost:5433 (compose içinden db:5432)
```

Compose servisleri:

| Servis | Açıklama |
|--------|----------|
| `db` | PostgreSQL 16 (named volume `synapse-db-data`); healthcheck `pg_isready` |
| `migrate` | `python -m app.ops apply-migrations` çalıştırır, sonra durur |
| `api` | Uvicorn — `db` healthy + `migrate` tamamlandıktan sonra başlar; `/healthz` healthcheck |

Yeni migration eklediğinde sadece `docker compose up migrate` tekrar çalıştır,
ardından `docker compose restart api`. Tüm `JWT_*`, `CORS_ORIGINS` ve analytics
ayarları `.env` üzerinden compose'a aktarılır.

`JWT_SECRET_KEY` set edilmezse compose `?Set JWT_SECRET_KEY` hatası verir —
bu, prod sırlarının yanlışlıkla default ile gizlenmesini engeller.

## Continuous Integration

`.github/workflows/ci.yml` üç paralel iş yürütür:

1. **Backend** — Python 3.12 kurulumu, `ruff check app tests`, `pytest -q`.
   `JWT_SECRET_KEY` CI ortamında test placeholder ile set edilir.
2. **Frontend** — `subosito/flutter-action@v2` (3.24.x), `flutter pub get`,
   `flutter analyze`.
3. **Docker** — `docker/build-push-action@v6` ile imajın derlenebildiğini
   doğrular (push edilmez).

Lokal olarak benzer doğrulamayı çalıştırmak için:

```powershell
.\venv\Scripts\Activate.ps1
ruff check app tests
pytest -q

cd frontend
flutter analyze
```

## Test

```powershell
pytest -q
```

`tests/`:

- `test_anomaly_detection.py` — duration anomaly + `AnomalyDetected` event
- `test_api_auth_smoke.py` — Sprint B/F: register/login/me, route token kilidi,
  daily-activity sahiplik kontrolü, environment admin token enjeksiyonu
- `test_cold_start.py` — cold start motoru
- `test_cold_start_user_provisioning.py` — yeni kullanıcı varsayılan öneri ekleme
- `test_decision_engine_rules.py` — gündüz ışık bloğu, çakışma çözümü
- `test_habit_latency_benchmark.py` — runtime mining vs habit matrix latency
- `chapter6_report_tables.py` — rapor için tablo üreteci (CLI)

Rapor tablolarını yeniden üretmek için:

```powershell
python -m tests.chapter6_report_tables
```

## Frontend (Flutter)

```powershell
cd frontend
flutter pub get

# Yerel makinede backend 127.0.0.1:8000'de çalışıyor olmalı
flutter run --dart-define=API_HOST=127.0.0.1     # iOS sim, macOS, Windows
# Android emulator için 10.0.2.2 otomatik kullanılır
```

`frontend/lib/config/api_config.dart` platform algılama yapar; fiziksel
cihaz için `--dart-define=API_HOST=<LAN IP>` parametresi yeterlidir.

## Analitik araçlar

| Komut | Açıklama |
|-------|----------|
| `python -m app.analytics.cold_start_engine --age 22 --gender Erkek --city İzmir --bmi 23.1` | Peer‑profil cold start önerisi |
| `python -m app.analytics.peer_profile_recommend --age 24 --gender Erkek --city izmir --height 180 --weight 80` | Çok‑sorulu peer öneri |
| `python -m app.analytics.heating_cohort --age 24 --gender Erkek --city izmir --height 192 --weight 95` | Kış ısıtma kohort modu + RF |
| `python -m app.analytics.random_forest_train --save-model` | RF eğitimi + joblib bundle kaydet |
| `python -m app.analytics.preprocess --from-url <google_sheets_csv>` | Anket ön işleme |

Üretilen `app/analytics/processed_synapse_data.csv` cold start akışları
(`cold_start_provisioning.py`) tarafından okunur.

## Operasyonel komutlar

```powershell
python -m app.ops apply-migrations            # SQL migration sırasını uygula
python -m app.ops bootstrap-db                # SQLModel ile tabloları kur (dev/test)
python -m app.ops rebuild-habit-matrix        # Habit Matrix'i baştan kur
python -m app.ops generate-synthetic-data --to-db   # Sentetik davranış logu
```

## Dizin yapısı

```
app/
  api/
    routes/        # FastAPI router'ları (inbound adapter)
    schemas.py     # Request/Response DTO'ları
  application/
    services/      # Use case orkestrasyonu (smart_home_service, cold_start_provisioning)
  core/
    domain/        # Domain entity & event (anomaly_detection, events)
    ports/         # Soyut arayüzler (EventPublisher Protocol)
    models.py      # SQLModel tablo modelleri (PG şemasına 1:1 eşlenir)
    settings.py    # Pydantic Settings (tek kaynak konfigürasyon)
    logging_config.py
  infrastructure/
    events/        # InMemoryEventPublisher vb.
  analytics/       # Sequence miner, cold start, RF, peer profile, time utils, preprocess
  models/          # HabitMatrix gibi yardımcı persistance modelleri
  db/database.py   # Engine + session factory
  ops.py           # CLI: migration / bootstrap / habit matrix / synthetic
  main.py          # FastAPI app + lifespan
migrations/        # *.sql (000 init + 001..006 incremental)
tests/             # pytest
frontend/          # Flutter mobile app
data/              # Sentetik veri (ignore edilebilir, küçük örnek)
```

## Mimari notlar

- **Hexagonal yaklaşım:** API katmanı domain'e bağlıdır, domain altyapıya bağlı
  değildir. `EventPublisher` Protocol (`app/core/ports/`) — `InMemoryEventPublisher`
  (`app/infrastructure/events/`) test ortamında AnomalyDetected event'lerini
  toplar.
- **Decision Engine:** İki kaynak birleştirir — *sequence mining* (runtime ya
  da kalıcı `habit_matrix` tablosu) ve *cold start* (peer‑profil) sinyali.
  Log sayısı eşiği aştığında ağırlık otomatik sequence'a kayar. Gündüz LIGHT_ON
  önerileri context‑guard ile susturulur, çakışmalar tek aksiyona indirgenir.
- **Habit Matrix:** Geceleri `HABIT_MATRIX_REBUILD_HOUR` saatinde scheduler tüm
  kullanıcılar için kuralları yeniden hesaplar; canlı mining'e göre ~10×‑20×
  daha hızlı okuma sağlar (bkz. `tests/test_habit_latency_benchmark.py`).
- **Cold Start:** Yeni kullanıcı kayıt olunca `provision_cold_start_defaults`
  yaş+cinsiyet+şehir+BMI ile peer grubunu seçer ve anketten gelen çoğunluk
  cevaplarını **COLD_START_DEFAULT** tipli recommendation olarak yazar.
- **Anomaly Detection:** Cihaz açık kalma süresi k × ortalamayı aştığında
  `SAFETY_ANOMALY` recommendation üretilir ve `AnomalyDetected` domain event
  yayılır (test edilebilir bir yan etki noktası).

---

Geliştirici notları, todo'lar ve sprint planı için `tests/chapter6_report_tables.py`
çıktısına ve depo kökündeki sprint takibine bakın.
