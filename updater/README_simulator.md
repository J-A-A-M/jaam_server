# Симулятор fusion-тривог (`simulator.py`)

Скрипт підміняє реальні API-джерела для локального тестування двох обробників
`updater.py`:

- `update_websocket_fusion_v1_alerts`
- `update_websocket_fusion_v1_etryvoga`

Замість запитів у зовнішні API він прокручує заздалегідь заданий сценарій
`SIMULATION_STEPS` і на кожному кроці пише дані в Redis + публікує події, на які
підписаний updater.

## Що пише в Redis

| kind           | ключ                        | подія                     |
|----------------|-----------------------------|---------------------------|
| `alert`        | `alerts:api:data`           | `alerts:api:updated`      |
|                | `alerts:api:last_call`      | —                         |
| `notification` | `alerts:etryvoga:full:data` | `alerts:etryvoga:updated` |

`alerts:api:data` — список записів регіонів у форматі ukrainealarm v3
(`regionId`, `regionType`, `regionName`, `regionEngName`, `lastUpdate`,
`activeAlerts[]`).

`alerts:etryvoga:full:data` — `[{"regionId", "type", "id"}]`; `id` монотонно
зростає між кроками (гарантія: кожен новий id більший за максимальний з
попереднього кроку).

Регіони резолвяться за назвою з `data/uaapi.json` (області + райони).

## Сценарій

`SIMULATION_STEPS` — 9 кроків по районах Київської області: наростання тривог
(AIR) + нотіфікації (`DRONE`, `RECON_DRONE`, `ROCKET`, `KAB`, `BALLISTIC`,
`EXPLOSION`), останній крок — повний відбій (порожні дані). AIR тут дефолтно
Red-рівня (біт 12).

`SIMULATION_STEPS_2` — по черзі кожна область з `AIR`: спершу прохід Red
(біт 12), потім прохід Yellow (біт 11), далі відбій (у циклі `main` не
використовується; для ручного перемикання).

Рівень AIR задається суфіксом у типі: `"AIR"` або `"AIR:Red"` → Red,
`"AIR:Yellow"` → Yellow. `make_region_record` для AIR завжди генерує
`activeAlertLevels`, тож біти 11/12 відтворюються локально.

Цикл: `run_step` → `sleep(SIMULATION_PAUSE)` → наступний крок по колу.

## Запуск

```bash
python3 simulator.py
```

## Змінні середовища

| змінна             | замовчування | опис                       |
|--------------------|--------------|----------------------------|
| `REDIS_HOST`       | `redis`      | хост Redis                 |
| `REDIS_PORT`       | `6379`       | порт Redis                 |
| `REDIS_PASSWORD`   | `redis`      | пароль Redis               |
| `REDIS_DB`         | `0`          | номер БД Redis             |
| `SIMULATION_PAUSE` | `60`         | пауза між кроками, секунди |
| `LOGGING`          | `INFO`       | рівень логування           |

## Fusion flags16 (вихід `build_fusion_alerts_state`)

Бітова маска на регіон у payload `websocket:v1:fusion:payload:alerts`
(2 байти `regionId` + 2 байти `flags16`):

- Біт 0: AIR Legacy (повітряна тривога без рівнів)
- Біт 1: ARTILLERY (артилерійська загроза)
- Біт 2: URBAN_FIGHTS (міські бої)
- Біт 3: CHEMICAL (хімічна загроза)
- Біт 4: NUCLEAR (ядерна загроза)
- Біт 5: Drones (дрони, з `alerts:http:reasons:data`)
- Біт 6: Missile (ракети, з `alerts:http:reasons:data`)
- Біт 7: Ballistic (балістика) — зарезервовано
- Біт 8: KAB (керовані авіабомби) — зарезервовано
- Біт 9: Explosion (вибухи) — зарезервовано
- Біт 10: Recon Drones (дрони-розвідники) — зарезервовано
- Біт 11: AIR Yellow (повітряна тривога жовтого рівня)
- Біт 12: AIR Red (повітряна тривога червоного рівня)
