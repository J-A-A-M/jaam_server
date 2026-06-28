import os
import json
import asyncio
import logging
import datetime
import uvicorn

import redis.asyncio as redis

from starlette.applications import Starlette
from starlette.responses import JSONResponse, HTMLResponse
from starlette.routing import Route

debug_level = os.environ.get("LOGGING") or "INFO"
port = int(os.environ.get("PORT") or 8095)

redis_hosts_raw = os.environ.get("REDIS_HOSTS") or ""
redis_host = os.environ.get("REDIS_HOST") or "redis"
redis_port = int(os.environ.get("REDIS_PORT") or 6379)
redis_password = os.environ.get("REDIS_PASSWORD") or "redis"
redis_db = int(os.environ.get("REDIS_DB") or 0)

BUCKET_MINUTES = 15
HISTORY_HOURS = 24

logging.basicConfig(level=debug_level, format="%(asctime)s %(levelname)s : %(message)s")
logger = logging.getLogger(__name__)

redis_clients: list = []
server_configs: list[dict] = []


def parse_redis_hosts() -> list[dict]:
    if redis_hosts_raw:
        try:
            return json.loads(redis_hosts_raw)
        except json.JSONDecodeError:
            logger.error("REDIS_HOSTS is not valid JSON, falling back to single REDIS_HOST")
    return [{"host": redis_host, "port": redis_port, "password": redis_password, "db": redis_db}]


def parse_connect_time(raw: str) -> datetime.datetime | None:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.datetime.strptime(raw, fmt).replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
    return None


async def get_connect_time(client: redis.Redis, key: str) -> str | None:
    key_type = await client.type(key)
    if key_type == "hash":
        return await client.hget(key, "connect_time")
    elif key_type == "string":
        raw = await client.get(key)
        if raw:
            try:
                data = json.loads(raw)
                return data.get("connect_time") if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
    return None


async def scan_redis_clients(client: redis.Redis) -> list[str]:
    connect_times = []
    cursor = 0
    while True:
        cursor, keys = await client.scan(cursor, match="websocket:clients:*", count=100)
        for key in keys:
            try:
                ct = await get_connect_time(client, key)
                if ct:
                    connect_times.append(ct)
            except Exception as e:
                logger.error(f"Error reading key {key}: {e}")
        if cursor == 0:
            break
    return connect_times


def server_name(idx: int) -> str:
    if idx < len(server_configs):
        cfg = server_configs[idx]
        return cfg.get("name") or cfg.get("host", f"сервер {idx + 1}")
    return f"сервер {idx + 1}"


def durations_from_connect_times(connect_times: list[str], now: datetime.datetime) -> list[float]:
    result = []
    for raw in connect_times:
        ct = parse_connect_time(raw)
        if ct:
            m = (now - ct).total_seconds() / 60
            if m >= 0:
                result.append(m)
    return result


def format_duration_label(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    if h == 0:
        return f"{m}хв"
    if m == 0:
        return f"{h}г"
    return f"{h}г {m}хв"


def median_duration_label(durations_minutes: list[float]) -> str:
    if not durations_minutes:
        return "—"
    sorted_d = sorted(durations_minutes)
    n = len(sorted_d)
    mid = n // 2
    median_min = sorted_d[mid] if n % 2 else (sorted_d[mid - 1] + sorted_d[mid]) / 2
    return format_duration_label(int(median_min))


def build_chart_data(connect_times: list[str]) -> dict:
    now = datetime.datetime.now(datetime.timezone.utc)
    total_buckets = (HISTORY_HOURS * 60) // BUCKET_MINUTES

    labels = [format_duration_label((i + 1) * BUCKET_MINUTES) for i in range(total_buckets)]
    counts = [0] * total_buckets
    older_count = 0
    durations: list[float] = []

    for raw in connect_times:
        ct = parse_connect_time(raw)
        if ct is None:
            continue
        online_minutes = (now - ct).total_seconds() / 60
        if online_minutes < 0:
            continue
        durations.append(online_minutes)
        if online_minutes >= HISTORY_HOURS * 60:
            older_count += 1
        else:
            idx = int(online_minutes // BUCKET_MINUTES)
            if 0 <= idx < total_buckets:
                counts[idx] += 1

    if older_count > 0:
        labels[-1] = f">{HISTORY_HOURS}г"
        counts[-1] += older_count

    return {
        "labels": labels,
        "counts": counts,
        "total": len(connect_times),
        "median_online": median_duration_label(durations),
        "updated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


async def data_endpoint(request):
    now = datetime.datetime.now(datetime.timezone.utc)
    tasks = [scan_redis_clients(c) for c in redis_clients]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_connect_times = []
    servers = []

    for i, result in enumerate(results):
        name = server_name(i)
        if isinstance(result, Exception):
            logger.error(f"Error scanning Redis {i}: {result}")
            servers.append({"name": name, "total": 0, "median_online": "—"})
        else:
            durations = durations_from_connect_times(result, now)
            servers.append(
                {
                    "name": name,
                    "total": len(result),
                    "median_online": median_duration_label(durations),
                }
            )
            all_connect_times.extend(result)

    chart_data = build_chart_data(all_connect_times)
    chart_data["servers"] = servers
    return JSONResponse(chart_data)


HTML_PAGE = """<!DOCTYPE html>
<html lang='uk' data-theme='dark'>
<head>
    <meta charset='UTF-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <title>JAAM — Онлайн мапи</title>
    <script>
        (function() {
            var saved = document.cookie.split(';').find(function(c) { return c.trim().startsWith('jaam_theme='); });
            var theme = saved ? saved.split('=')[1].trim() : 'dark';
            document.documentElement.setAttribute('data-theme', theme);
        })();
    </script>
    <script src='https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js'></script>
    <style>
        :root {
            --bg-color: #f0f0f0;
            --container-bg: #ffffff;
            --text-color: #000000;
            --border-color: #dee2e6;
            --panel-bg: #f8f9fa;
            --secondary-text: #6c757d;
        }
        [data-theme='dark'] {
            --bg-color: #1a1a1a;
            --container-bg: #2d2d2d;
            --text-color: #ffffff;
            --border-color: #444444;
            --panel-bg: #3a3a3a;
            --secondary-text: #aaaaaa;
        }
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: var(--bg-color);
            color: var(--text-color);
            transition: background-color 0.3s ease, color 0.3s ease;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
            background-color: var(--container-bg);
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 0 10px rgba(0,0,0,0.3);
        }
        .header-container {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        h1 { margin: 0; font-size: 1.5em; }
        .control-button {
            background: none;
            border: 1px solid var(--border-color);
            cursor: pointer;
            padding: 8px;
            border-radius: 8px;
            transition: background-color 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .control-button:hover { background-color: var(--panel-bg); }
        .control-button svg { width: 18px; height: 18px; fill: var(--text-color); transition: fill 0.3s ease; }
        .panel {
            background: var(--panel-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
            transition: background-color 0.3s ease, border-color 0.3s ease;
        }
        .section-header {
            font-size: 14px;
            font-weight: bold;
            margin-bottom: 15px;
            padding-bottom: 8px;
            border-bottom: 2px solid var(--border-color);
        }
        .stat-row {
            display: flex;
            gap: 20px;
        }
        .stat-box {
            background: var(--container-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px 24px;
            text-align: center;
        }
        .stat-value {
            font-size: 2.2em;
            font-weight: bold;
            color: #007bff;
        }
        .stat-label {
            font-size: 12px;
            color: var(--secondary-text);
            margin-top: 4px;
        }
        .updated-at {
            font-size: 11px;
            color: var(--secondary-text);
            text-align: right;
            margin-top: 10px;
        }
        .server-grid {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin-top: 12px;
        }
        .server-card {
            background: var(--container-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 10px 16px;
            min-width: 140px;
            text-align: center;
        }
        .server-card-name {
            font-size: 11px;
            font-weight: bold;
            color: var(--secondary-text);
            margin-bottom: 6px;
            font-family: monospace;
        }
        .server-card-stat {
            display: flex;
            justify-content: space-between;
            gap: 16px;
        }
        .server-card-item .val {
            font-size: 1.3em;
            font-weight: bold;
            color: #007bff;
        }
        .server-card-item .lbl {
            font-size: 10px;
            color: var(--secondary-text);
        }
    </style>
</head>
<body>
    <div class='container'>
        <div class='header-container'>
            <h1>JAAM — Онлайн мапи</h1>
            <button class='control-button' onclick='toggleTheme()' title='Змінити тему'>
                <svg viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg'>
                    <path d='M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z'/>
                </svg>
            </button>
        </div>
        <div class='panel'>
            <div class='section-header'>Зараз онлайн</div>
            <div class='stat-row'>
                <div class='stat-box'>
                    <div class='stat-value' id='total-count'>—</div>
                    <div class='stat-label'>мап онлайн</div>
                </div>
                <div class='stat-box'>
                    <div class='stat-value' id='median-online'>—</div>
                    <div class='stat-label'>медіана часу онлайн</div>
                </div>
            </div>
        </div>
        <div class='panel' id='servers-panel' style='display:none'>
            <div class='section-header'>По серверах</div>
            <div class='server-grid' id='servers-grid'></div>
        </div>
        <div class='panel'>
            <div class='section-header'>Тривалість онлайн (інтервал 15 хв, макс. 24 год)</div>
            <canvas id='chart'></canvas>
            <div class='updated-at' id='updated-at'></div>
        </div>
    </div>
    <script>
        var chartInstance = null;
        var isDark = document.documentElement.getAttribute('data-theme') === 'dark';

        function getColors() {
            return isDark
                ? { bar: 'rgba(0,123,255,0.55)', border: 'rgba(0,123,255,1)', grid: 'rgba(255,255,255,0.08)', text: '#aaaaaa' }
                : { bar: 'rgba(0,123,255,0.65)', border: 'rgba(0,123,255,1)', grid: 'rgba(0,0,0,0.08)', text: '#6c757d' };
        }

        function buildChart(labels, counts) {
            var ctx = document.getElementById('chart').getContext('2d');
            var c = getColors();
            if (chartInstance) chartInstance.destroy();
            chartInstance = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Кількість мап',
                        data: counts,
                        backgroundColor: c.bar,
                        borderColor: c.border,
                        borderWidth: 1,
                        borderRadius: 3
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                title: function(items) { return 'В онлайні ' + items[0].label; },
                                label: function(item) { return item.raw + ' мап'; }
                            }
                        }
                    },
                    scales: {
                        x: {
                            ticks: { color: c.text, maxTicksLimit: 12, maxRotation: 45 },
                            grid: { color: c.grid }
                        },
                        y: {
                            beginAtZero: true,
                            ticks: { color: c.text, stepSize: 1 },
                            grid: { color: c.grid }
                        }
                    }
                }
            });
        }

        function makeEl(tag, cls, text) {
            var el = document.createElement(tag);
            if (cls) el.className = cls;
            if (text !== undefined) el.textContent = text;
            return el;
        }

        function renderServers(servers) {
            var panel = document.getElementById('servers-panel');
            var grid = document.getElementById('servers-grid');
            if (!servers || servers.length <= 1) { panel.style.display = 'none'; return; }
            panel.style.display = '';
            while (grid.firstChild) grid.removeChild(grid.firstChild);
            servers.forEach(function(s) {
                var card = makeEl('div', 'server-card');
                card.appendChild(makeEl('div', 'server-card-name', s.name));
                var stat = makeEl('div', 'server-card-stat');
                var i1 = makeEl('div', 'server-card-item');
                i1.appendChild(makeEl('div', 'val', String(s.total)));
                i1.appendChild(makeEl('div', 'lbl', 'мап'));
                var i2 = makeEl('div', 'server-card-item');
                i2.appendChild(makeEl('div', 'val', s.median_online));
                i2.appendChild(makeEl('div', 'lbl', 'медіана'));
                stat.appendChild(i1);
                stat.appendChild(i2);
                card.appendChild(stat);
                grid.appendChild(card);
            });
        }

        function loadData() {
            fetch('/data.json')
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    document.getElementById('total-count').textContent = d.total;
                    document.getElementById('median-online').textContent = d.median_online;
                    document.getElementById('updated-at').textContent = 'Оновлено: ' + d.updated_at;
                    renderServers(d.servers);
                    buildChart(d.labels, d.counts);
                })
                .catch(function(e) { console.error('fetch error', e); });
        }

        loadData();
        setInterval(loadData, 30000);

        function toggleTheme() {
            var current = document.documentElement.getAttribute('data-theme');
            var next = current === 'dark' ? 'light' : 'dark';
            isDark = next === 'dark';
            document.documentElement.setAttribute('data-theme', next);
            document.cookie = 'jaam_theme=' + next + '; max-age=31536000; path=/';
            loadData();
        }
    </script>
</body>
</html>"""


async def index(request):
    return HTMLResponse(HTML_PAGE)


app = Starlette(
    routes=[
        Route("/", index),
        Route("/data.json", data_endpoint),
    ]
)


@app.on_event("startup")
async def startup():
    global redis_clients, server_configs
    hosts = parse_redis_hosts()
    server_configs = hosts
    for cfg in hosts:
        client = redis.Redis(
            host=cfg.get("host", "redis"),
            port=int(cfg.get("port", 6379)),
            db=int(cfg.get("db", 0)),
            password=cfg.get("password", "redis"),
            decode_responses=True,
            encoding="utf-8",
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
        )
        redis_clients.append(client)
        logger.info(f"Redis client initialized: {cfg.get('host')}:{cfg.get('port')}")


@app.on_event("shutdown")
async def shutdown():
    for client in redis_clients:
        await client.close()
    logger.info("All Redis clients closed")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips=["*"])
