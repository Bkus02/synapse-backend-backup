# Veritabanı migration'ları

Sırayla çalıştır (pgAdmin **Query Tool**, `psql` veya `python -m app.ops apply-migrations`):

| Sıra | Dosya | Amaç |
|------|-------|------|
| 000 | `000_init_schema.sql` | Boş veritabanı için ENUM tipleri (`device_type`, `habit_recurrence`, `advice_category`, `recommendation_status`) ve temel tablolar (`users`, `environments`, `devices`, `behavior_logs`, `habits`, `positive_advices`, `user_environments`, `user_streaks`). User/Environment id CHECK kuralları. |
| 001 | `001_add_behavior_logs_parameters.sql` | `behavior_logs.parameters` (TEXT, nullable). |
| 002 | `002_create_recommendations.sql` | `recommendations` tablosu + `recommendation_status` ENUM (idempotent). |
| 003 | `003_create_habit_matrix.sql` | `habit_matrix` tablosu + indeksler. |
| 004 | `004_add_recommendation_type_context.sql` | `recommendations.recommendation_type`, `recommendations.context`. |
| 005 | `005_environment_membership_ui_fields.sql` | `environments.icon_key`, `users.avatar_key`, `environment_join_requests`. |
| 006 | `006_add_devices_room.sql` | `devices.room`. |

Tüm dosyalar idempotent (`IF NOT EXISTS` veya `DO $$`); tekrar çalıştırmak güvenlidir.

## Hızlı kurulum

```bash
# 1) .env kopyala ve DATABASE_URL'i kendi PG'ne göre düzenle
cp .env.example .env

# 2) Migration'ları sırayla uygula
python -m app.ops apply-migrations
```

veya manuel:

```bash
psql -h localhost -U postgres -d postgres -f migrations/000_init_schema.sql
psql -h localhost -U postgres -d postgres -f migrations/001_add_behavior_logs_parameters.sql
# … 002..006
```

Veritabanı adın farklıysa `-d` parametresini değiştir.
