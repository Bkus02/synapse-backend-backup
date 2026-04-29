# Veritabanı migration'ları

Sırayla çalıştır (pgAdmin **Query Tool** veya `psql`):

1. `001_add_behavior_logs_parameters.sql` — `behavior_logs.parameters` (TEXT, nullable)
2. `002_environments_icons_join_requests.sql` — `environments.icon_key`, `users.avatar_key`, `environment_join_requests` tablosu
3. `003_devices_room.sql` — `devices.room` (TEXT, nullable)

Örnek:

```bash
psql -h localhost -U postgres -d postgres -f migrations/001_add_behavior_logs_parameters.sql
```

Veritabanı adın farklıysa `-d` değiştir.
