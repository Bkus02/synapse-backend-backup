# Synapse — Uçtan uca test rehberi (A)

Bu rehber **login → environment → cihaz → habit → streak** akışını elle doğrular.
Backend ve frontend aynı makinede çalışırken ~15 dakika sürer.

## Önkoşullar

| Bileşen | Komut / URL |
|---------|-------------|
| PostgreSQL | `localhost:5433`, kullanıcı `postgres`, şifre `.env` ile aynı |
| Backend | `cd final_sql1` → `.\venv\Scripts\Activate.ps1` → `python -m uvicorn app.main:app --reload --port 8000` |
| Frontend | `cd frontend` → `flutter run -d web-server --web-port 5050` |
| API docs | http://127.0.0.1:8000/docs |
| Uygulama | http://localhost:5050 |

Migration uygulanmış olmalı:

```powershell
python -m app.ops apply-migrations
```

---

## 1. Kayıt ve giriş

1. Tarayıcıda **Welcome** → **Register**.
2. Yeni kullanıcı oluştur (e-posta + parola).
3. **Login** ile aynı bilgilerle giriş yap.
4. Beklenen: Dashboard açılır; üstte kullanıcı adı görünür.

**API doğrulama (opsiyonel):**

```http
POST /auth/login
→ 200, body içinde access_token ve user
```

---

## 2. Environment (ev) oluştur

1. Alt menüden **Environments**.
2. **Add environment** → isim, konum, ikon seç → kaydet.
3. Listede yeni ev görünmeli; ana sayfada (Main) üstte ev adı çıkmalı.

**API:** `GET /environments` (Bearer) → en az 1 kayıt, `admin_id` = senin `user.id`.

---

## 3. Cihaz ekle (streak için zorunlu)

Streak, `behavior_logs` tablosundaki günlük kayıtlara dayanır; log için **device_id** gerekir.

1. Environments’ta oluşturduğun eve tıkla.
2. **Add device** → örn. tip **Lamp**, isim `Salon`.
3. Cihaz listesinde görünmeli.

---

## 4. Habit oluştur

1. Alt menü **Habits**.
2. **Add habit** → isim (ör. `Evening reading`), recurrence **Daily**, aktif bırak.
3. Kayıt listede görünmeli.

**Dashboard:** Main sekmesinde **Active Advices** altında bu habit kartı görünmeli (statik “Reading Time” yerine).

---

## 5. Streak (günlük aktivite)

1. **Main** sekmesine dön.
2. **Community Progress** altında kendi satırında gene çubukları (çoğu gri = henüz log yok).
3. Bir **Active Advice** kartına dokun → saat + süre (dakika) gir → **Save**.
4. Beklenen:
   - “Saved for …” snackbar
   - Çubukların **son günü** yeşile döner (yeniden yükleme veya kısa bekleme sonrası)
   - `weekly_streak_count` artabilir

**API doğrulama:**

```http
GET /users/{senin_id}/daily-activity?days=10
Authorization: Bearer …
→ days[-1].active == true (bugün için)
```

Log oluşumu: `POST /behavior-logs` (Save sırasında frontend gönderir).

**Cihaz yoksa:** Save öncesi snackbar — önce Environments’ta cihaz ekle.

---

## 6. Synapse önerisi (opsiyonel)

1. Swagger veya sentetik veri ile `behavior_logs` ekle; inference arka planda öneri üretebilir.
2. Main’de **Synapse suggestion** banner veya bildirimlerde öneri görünebilir.
3. **Accept** / **Dismiss** → `POST /recommendations/{id}/accept` veya `reject`.

---

## 7. Join request (opsiyonel, 2. kullanıcı)

1. İkinci hesapla kayıt ol.
2. Birinci hesabın environment ID’si ile **Request join**.
3. Birinci hesapta bildirimler veya Environments → join istekleri → **Approve**.

---

## Sık karşılaşılan sorunlar

| Belirti | Çözüm |
|---------|--------|
| Login 401 | Eski düz metin parola; kullanıcıyı yeniden kaydet veya `password_hash` sıfırla (README) |
| API 401 habits/devices | Token süresi dolmuş; çıkış yapıp tekrar giriş |
| Streak güncellenmiyor | Ortamda cihaz var mı? Save sonrası Main’i yenile (pull / F5) |
| CORS / bağlantı hatası | Backend 8000 açık mı? Web için `127.0.0.1:8000` |
| CI kırmızı | `channel: stable` Flutter + `pytest -m "not benchmark"` (son commit) |

---

## Otomatik API smoke (geliştirici)

```powershell
pytest tests/test_api_auth_smoke.py -v
pytest -q -m "not benchmark"
```

Tam latency benchmark (lokal):

```powershell
pytest -q -m benchmark
```
