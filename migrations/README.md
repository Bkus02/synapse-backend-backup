# Veritabanı migration'ları

Sırayla çalıştır (pgAdmin **Query Tool** veya `psql`):

1. `001_add_behavior_logs_parameters.sql` — `behavior_logs.parameters` (TEXT, nullable)

Örnek:

```bash
psql -h localhost -U postgres -d postgres -f migrations/001_add_behavior_logs_parameters.sql
```

Veritabanı adın farklıysa `-d` değiştir.
