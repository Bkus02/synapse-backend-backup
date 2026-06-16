# Sprint D — Cihaz simülasyonu (aç/kapa)

Cihaz kartındaki **On/Off** anahtarı artık yalnızca yerel state değiştirmiyor; backend’e yazar ve öğrenme hattını tetikler.

## API

`PATCH /devices/{device_id}` (Bearer zorunlu)

```json
{ "status": true }
```

Opsiyonel: `current_value` (sayısal sensör değeri).

**Akış:**

1. Cihaz `status` güncellenir.
2. `behavior_logs` tablosuna `TurnOn` veya `TurnOff` kaydı eklenir (`parameters.source = device_toggle`).
3. Arka planda `run_inference_for_behavior_log` çalışır (öneri üretimi).

## Frontend

- `DeviceApi.setStatus(deviceId, status)`
- `EnvironmentDevicesPage` — switch → `PATCH`, snackbar: *"… turned on/off — Synapse is learning."*

## Manuel test

1. Backend + frontend çalışsın (`docs/E2E_TEST.md`).
2. Giriş yap → **Environments** → bir ortam → **Devices**.
3. Bir lambanın switch’ini aç/kapa.
4. **Main** sekmesine geçip tekrar **Environments** → aynı ortam: switch **On** kalmalı (DB’den yeniden yüklenir).
5. Swagger veya `GET /behavior-logs` ile `TurnOn`/`TurnOff` kayıtlarını doğrula.

## Otomatik test

`tests/test_e2e_api_flow.py` — register akışında `PATCH /devices/{id}` + `TurnOn` log kontrolü.

```bash
pytest -q tests/test_e2e_api_flow.py -m "not benchmark"
```
