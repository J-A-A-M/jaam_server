# JAAM Design — TE-style UI + low-poly UA map

Дизайн-прототипи UI пристрою JAAM у стилі Teenage Engineering (K.O. Sidekick / EP-133)
+ низькополігональна мапа України для підсвітки тривог по районах/областях.

Усе — статичні файли, без білда. Дивитись через `serve.py` (LAN-сервер для мобільних).

---

## Файли

| Файл | Що |
|---|---|
| `jaam_te_design.html` | **Основний** прототип UI. 4 теми, контроли, системна панель, меню, grid/pad приклад. Self-contained (CSS+JS inline, без залежностей). |
| `jaam_te_design_map.html` | Варіант основного з **вбудованою мапою** замість grid. Мапа всередині `alertsWrap` (над списком тривог), ховається/показується разом з ними. **Генерується з основного — не редагувати руками, перегенеровувати.** |
| `ukraine_lowpoly.svg` | Низькополігональна мапа: 124 райони + Крим + occupied, межі областей. viewBox `0 0 260 175`. |
| `ukraine_lowpoly_preview.html` | Демо мапи (підсвітка по raion id / oblast id, теми, клік). |
| `tools/lowpoly.py` | Конвертер SVG-контурів → low-poly. Відтворюваність мапи. |
| `serve.py` | LAN http-сервер (роздає папку на `0.0.0.0:8000`, друкує IP). |
| `device.png`, `green.jpg` | Референси стилю (TE-пристрій, радар «єРадар»). |

VS Code: `Demo: serve design (LAN)` у `.vscode/launch.json` (F5 → http на LAN).

---

## Теми (jaam_te_design*.html)

4 теми, перемикач ◐ у шапці циклить, стан у `localStorage['jaam-theme']`.
Реалізація: CSS-токени в `:root` + override через `[data-theme="..."]`.

| Тема | data-theme | Опис | Акцент |
|---|---|---|---|
| Light | `''` | TE off-white (device.png) | `#F5601A` помаранч |
| Dark | `dark` | темний корпус | `#FF6A2B` |
| Mil | `mil` | радар/олива (green.jpg) | червоний + бурштин `--amber` |
| Pip | `fall` | Fallout Pip-Boy CRT (фосфор, scanlines, glow) | `#7DFF52` зелений |

Токени: `--case --panel --graphite --grey --grey-lt --ink --accent --accent-dk --line` (+ `--amber` у mil, `--glow` у fall).

---

## Структура UI

- **Шапка**: brand + icon-кнопки `.icobtn` (◉ system, △ alerts, ⟨⟩ api, ◐ theme) — однаковий вигляд.
  Кнопки `data-target` згортають секції (`.collapse` / `.collapsed`), кожна persist окремо в localStorage.
- **Системна панель** `.sys`: inline pill-chips (flex-wrap), рендериться JS з масиву `SYS` (count-agnostic).
  Метрики + SVG-іконки взяті з пристрою JAAM (ендпоінт `/system-info`, див. нижче).
- **Меню** MAP/LIST/API/SET — лишилось як highlight-перемикач, **SET активна за замовч.** (єдиний pane).
- **SET pane**: Активні тривоги (collapse) → WebSocket API (collapse) → Налаштування → [grid/pad приклад АБО мапа].

### Контроли (TE-стиль, всі teми)
`.te-input` (text/textarea, h30), `select.te` (h30), `.radio`, `.check`, `.switch` (pill з рухомим `.sk`),
`.hslider` (горизонт., значення зліва), color-picker (`.swatch-btn` + `.presets`), `.banner` (інфо, варіанти amber/grey).

### Збережені компоненти (для подальшого)
`.pad` + `.grid` — TE-кнопки регіонів. У основному файлі = приклад 4-в-ряд. Стилі лишені.

---

## Мапа України (low-poly)

### Джерело
`map.ukrainealarm.com` вантажить SVG-шари: `states.svg` (області), `districts.svg` (райони),
`names.svg`, `rf.svg`. Кожен path має `id` = **regionId з Ukraine Alarm API**.
Завантаження (якщо треба перегенерувати):
```
curl -s --compressed https://map.ukrainealarm.com/states.svg    -o /tmp/states.svg
curl -s --compressed https://map.ukrainealarm.com/districts.svg -o /tmp/districts.svg
```

### Пайплайн (`tools/lowpoly.py`)
1. `svgpathtools` парсить bezier-path → семпли точок (`BEZIER_SAMPLES=10`).
2. `shapely` будує геометрії районів (union кілець).
3. **Occupied/Крим** (області без районів) = `oblast − raion_union` на повній роздільності.
4. Райони + occupied → **один шар** у `mapshaper` (`-snap interval=SNAP -simplify SIMPLIFY_PCT% weighted -clean`).
   Спільний шар = сусіди ділять **один arc на межу** → кордони співпадають, спрощуються однаково.
5. **Області** виводяться dissolve-ом спрощених районів + occupied → межі точно співпадають, контури повні (Крим включно).
6. Recovery: дрібні райони, що mapshaper дропнув → легке незалежне спрощення.

**Ключове знання (через advisor):** не змішувати райони й області в одному mapshaper-шарі —
області ПОВНІСТЮ перекривають райони, `-clean` тоді видаляє райони. Тому occupied рахуються окремо
як gap і додаються до шару районів; межі областей деривуються, не симпліфаюцца напряму.
Метрика успіху спільних меж — **кількість arc** (мають бути сотні, не тисячі) + тест на темному фоні (нуль щілин).

### Параметри тюнінгу (вгорі `lowpoly.py`)
- `SIMPLIFY_PCT = 4` — % вершин лишити (нижче = простіше). Поточний avg ~70 верт/район.
- `SNAP = 0.18` — інтервал злиття вершин (вище = агресивніше зливає спільні межі, але вбиває дрібні райони).
- `BEZIER_SAMPLES = 10`.

### Регенерація
```
.venv/bin/python design/tools/lowpoly.py     # читає /tmp/*.svg, пише ukraine_lowpoly.svg
```
Залежності (у .venv): `svgpathtools shapely topojson cairosvg` (cairosvg лише для прев'ю-рендеру),
CLI `mapshaper` (`npm i -g mapshaper`).

### Структура SVG + підсвітка
```
<svg id="uaLowpoly" viewBox="0 0 260 175">
  <g id="raions"> <g class="raion" id="raion-{regionId}" data-id="{id}" data-oblast="{oblastId}"> <polygon/> </g> ...
  <g id="oblasts"><g class="oblast" id="oblast-{id}"> <polygon/> </g> ...
```
Кольори через CSS-змінні: `--ua-fill --ua-line --ua-border --ua-alert --ua-alert-line`
(у jaam_te_design_map.html прив'язані до активної теми).

Підсвітка:
```js
// район
document.querySelector('#raion-140').classList.add('alert');
// ціла область = всі її райони
document.querySelectorAll('.raion[data-oblast="14"]').forEach(g=>g.classList.add('alert'));
```
- Крим = `regionId 9999` (валідний id, НЕ сміття; не дропати).
- Occupied (Донецька/Луганська ч.) — заливні регіони з ключем = oblast id (1–31, не колізує з районами 32+).

---

## Регенерація map-версії UI
`jaam_te_design_map.html` будується з `jaam_te_design.html`:
видалити grid/pad приклад → вставити inline `ukraine_lowpoly.svg` усередину `alertsWrap` (над `#alertsList`)
→ додати map CSS + per-theme `--ua-*` токени → додати JS click-handler (`#uamap` .raion toggle).
**Оригінал `jaam_te_design.html` не міняти.**

---

## Дані пристрою JAAM (референс)
Системна панель рендеритьсяз ендпоінта `/system-info` (JSON: масив `system_models` типів рядків + масив `system` метрик).
Типи рядків: `bar` (used/total), `number` (value+unit), `text`, `time` (seconds).
Метрики: memory, cpuTemp, version, uptime, wifiSignal, wifiUptime, websocketUptime,
localTemp/Humidity/Light, apiClients. SVG-іконки вшиті в `SYS`/`ICON` у JS прототипу.
