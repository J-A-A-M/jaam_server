import os
import uvicorn
import logging
import json
import asyncio
import httpx
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.responses import JSONResponse, FileResponse, HTMLResponse, RedirectResponse
from starlette.routing import Route
from starlette.exceptions import HTTPException
from starlette.requests import Request

import redis.asyncio as redis
import sys
from pathlib import Path

try:
    from utils import (
        get_redis_data,
        set_redis_data,
        run_with_restart,
        beta_filter,
        release_filter,
        get_file_names,
        touch_beta_filter,
        touch_release_filter,
        verify_device_auth,
        DEVICE_AUTH_MASTER_SECRET,
    )
except ImportError:
    parent_dir = Path(__file__).resolve().parent.parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))

    from utils import (
        get_redis_data,
        set_redis_data,
        run_with_restart,
        beta_filter,
        release_filter,
        get_file_names,
        touch_beta_filter,
        touch_release_filter,
        verify_device_auth,
        DEVICE_AUTH_MASTER_SECRET,
    )

debug_level = os.environ.get("LOGGING") or "INFO"
debug = os.environ.get("DEBUG") or False
port = int(os.environ.get("PORT") or 8090)
redis_host = os.environ.get("REDIS_HOST") or "redis"
redis_port = int(os.environ.get("REDIS_PORT", 6379))
redis_password = os.environ.get("REDIS_PASSWORD") or "redis"
redis_db = int(os.environ.get("REDIS_DB", 0))
shared_path = os.environ.get("SHARED_PATH") or "/shared_data/releases"
shared_path_beta = os.environ.get("SHARED_PATH_BETA") or "/shared_data/beta"
update_loop_time = int(os.environ.get("UPDATE_PERIOD", 3600))
github_token = os.environ.get("GITHUB_TOKEN")  # Optional: для підвищення ліміту API

# jaam_touch — повністю окремий пайплайн від jaam_fusion вище: власний приватний репозиторій,
# власні шляхи/диск/Redis-ключі. Читання приватних релізів потребує github_token з repo-scope.
github_repo_touch = os.environ.get("GITHUB_REPO_TOUCH") or "J-A-A-M/jaam_touch"
shared_path_touch = os.environ.get("SHARED_PATH_TOUCH") or "/shared_data/releases_touch"
shared_path_touch_beta = os.environ.get("SHARED_PATH_TOUCH_BETA") or "/shared_data/beta_touch"


if not isinstance(port, int) or not (1024 <= port <= 65535):
    raise ValueError(f"PORT має бути цілим числом між 1024 та 65535: {port}")

logging.basicConfig(level=debug_level, format="%(asctime)s %(levelname)s : %(message)s")
logger = logging.getLogger(__name__)

# Кеш для списку релізів
releases_cache = {"data": None, "timestamp": None, "ttl": timedelta(minutes=60)}  # Кешуємо на 60 хвилин

# Кеш для списку бета-версій
beta_releases_cache = {"data": None, "timestamp": None, "ttl": timedelta(minutes=60)}  # Кешуємо на 60 хвилин

HTML_404_PAGE = """page not found"""
HTML_500_PAGE = """request error"""


async def not_found(request: Request, exc: HTTPException):
    logger.debug(f"Request time: {exc.args}")
    return HTMLResponse(content=HTML_404_PAGE, status_code=404)


async def server_error(request: Request, exc: HTTPException):
    logger.debug(f"Request time: {exc.args}")
    return HTMLResponse(content=HTML_500_PAGE, status_code=500)


exception_handlers = {404: not_found, 500: server_error}


def bin_sort(bin):
    try:
        if bin.startswith("latest"):
            return (100, 0, 0, 0)
        version = bin.removesuffix(".bin")
        fw_beta = version.split("-")
        fw = fw_beta[0]
        if len(fw_beta) == 1:
            beta = 10000
        else:
            beta = int(fw_beta[1].removeprefix("b"))

        major_minor_patch = fw.split(".")
        major = int(major_minor_patch[0])
        if len(major_minor_patch) == 1:
            minor = 0
            patch = 0
        elif len(major_minor_patch) == 2:
            minor = int(major_minor_patch[1])
            patch = 0
        else:
            minor = int(major_minor_patch[1])
            patch = int(major_minor_patch[2])

        return (major, minor, patch, beta)
    except (ValueError, AttributeError, IndexError) as e:
        # Якщо не вдається розпарсити версію, повертаємо мінімальний пріоритет
        logger.debug(f"Cannot parse version from '{bin}': {e}")
        return (0, 0, 0, 0)


async def main(request):
    response = """
    <!DOCTYPE html>
    <html lang='en'>
    </html>
    """
    return HTMLResponse(response)


async def fetch_github_releases():
    """Отримує релізи з GitHub та фільтрує .bin файли"""
    try:
        headers = {"Accept": "application/vnd.github+json"}
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"

        async with httpx.AsyncClient() as client:
            # Отримуємо всі релізи з пагінацією (до 100 на сторінку)
            response = await client.get(
                "https://api.github.com/repos/J-A-A-M/jaam_fusion/releases",
                headers=headers,
                params={"per_page": 100},  # Максимум релізів на запит
                timeout=10.0,
            )
            response.raise_for_status()
            releases = response.json()

            # Логуємо інформацію про ліміти та кількість релізів
            if "X-RateLimit-Remaining" in response.headers:
                logger.info(
                    f"GitHub API rate limit remaining: {response.headers['X-RateLimit-Remaining']}/{response.headers.get('X-RateLimit-Limit', 'unknown')}"
                )
            logger.info(f"Fetched {len(releases)} releases from GitHub")

            files_with_urls = []
            for release in releases:
                # Пропускаємо драфт релізи
                if release.get("draft", False):
                    logger.debug(f"Skipping draft release: {release.get('tag_name', 'unknown')}")
                    continue

                if "assets" in release:
                    for asset in release["assets"]:
                        name = asset["name"]
                        if name.endswith(".bin"):  # and filter_func(name):
                            files_with_urls.append(
                                {
                                    "name": name,
                                    "tag": release["tag_name"],
                                    "prerelease": release["prerelease"],
                                    "url": asset["browser_download_url"],
                                }
                            )

            logger.info(f"Filtered {len(files_with_urls)} .bin files")
            # Сортуємо за версією у зворотному порядку (новіші спочатку)
            return files_with_urls
    except Exception as e:
        logger.error(f"Error fetching releases from GitHub: {e}")
        return None


async def fetch_github_releases_touch():
    """Те саме, що fetch_github_releases, але для приватного репозиторію jaam_touch.
    Потребує github_token з repo-scope (приватний репозиторій)."""
    try:
        headers = {"Accept": "application/vnd.github+json"}
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{github_repo_touch}/releases",
                headers=headers,
                params={"per_page": 100},
                timeout=10.0,
            )
            response.raise_for_status()
            releases = response.json()

            if "X-RateLimit-Remaining" in response.headers:
                logger.info(
                    f"GitHub API (touch) rate limit remaining: {response.headers['X-RateLimit-Remaining']}/{response.headers.get('X-RateLimit-Limit', 'unknown')}"
                )
            logger.info(f"Fetched {len(releases)} touch releases from GitHub")

            files_with_urls = []
            for release in releases:
                if release.get("draft", False):
                    logger.debug(f"Skipping draft touch release: {release.get('tag_name', 'unknown')}")
                    continue

                if "assets" in release:
                    for asset in release["assets"]:
                        name = asset["name"]
                        if name.endswith(".bin"):
                            files_with_urls.append(
                                {
                                    "name": name,
                                    "tag": release["tag_name"],
                                    "prerelease": release["prerelease"],
                                    "url": asset["browser_download_url"],
                                }
                            )

            logger.info(f"Filtered {len(files_with_urls)} touch .bin files")
            return files_with_urls
    except Exception as e:
        logger.error(f"Error fetching touch releases from GitHub: {e}")
        return None


async def list(request):
    redis_client = request.app.state.redis_client

    releases_cache = await get_redis_data(logger, redis_client, "releases:data", default_response=[])

    files_data = get_file_names(logger, releases_cache, release_filter, strip_pattern="JAAM_")

    # Обмежуємо до 5 найновіших релізів
    files_data = files_data[:5]

    # Повертаємо тільки назви файлів
    return JSONResponse([f["name"] for f in files_data])


async def list_beta(request):
    redis_client = request.app.state.redis_client

    releases_cache = await get_redis_data(logger, redis_client, "releases:data", default_response=[])

    files_data = get_file_names(logger, releases_cache, beta_filter, strip_pattern="JAAM_")

    # Обмежуємо до 10 найновіших бета-версій
    files_data = files_data[:10]

    # Повертаємо тільки назви файлів
    return JSONResponse([f["name"] for f in files_data])


async def update(request):
    redis_client = request.app.state.redis_client

    filename = request.path_params["filename"]

    files_data = await get_redis_data(logger, redis_client, "releases:production", default_response=[])

    if filename == "latest" or filename == "jaam":
        # Повертаємо перший (найновіший) файл
        if files_data:
            return FileResponse(f"{shared_path}/{files_data[0]['name']}")
        raise HTTPException(status_code=404, detail="No releases found")
    else:
        # Шукаємо конкретний файл в кеші
        target_filename = f"{filename}.bin"
        for file_info in files_data:
            if file_info["name"] == target_filename:
                return FileResponse(f"{shared_path}/{file_info['name']}")
        raise HTTPException(status_code=404, detail=f"File {target_filename} not found")


async def update_fusion(request):
    redis_client = request.app.state.redis_client

    filename = request.path_params["filename"]

    files_data = await get_redis_data(logger, redis_client, "releases:data", default_response=[])

    if filename == "latest" or filename == "jaam":
        # Повертаємо перший (найновіший) файл
        if files_data:
            return RedirectResponse(url=files_data[0]["url"])
        raise HTTPException(status_code=404, detail="No releases found")
    else:
        # Шукаємо конкретний файл в кеші
        target_filename = f"{filename}.bin"
        for file_info in files_data:
            if file_info["name"] == target_filename:
                return RedirectResponse(url=file_info["url"])
        raise HTTPException(status_code=404, detail=f"File {target_filename} not found")


async def update_beta(request):
    redis_client = request.app.state.redis_client

    filename = request.path_params["filename"]

    files_data = await get_redis_data(logger, redis_client, "releases:beta", default_response=[])

    if filename == "latest_beta" or filename == "jaam_beta":
        # Повертаємо перший (найновіший) файл
        if files_data:
            return FileResponse(f"{shared_path_beta}/{files_data[0]['name']}")
        raise HTTPException(status_code=404, detail="No releases found")
    else:
        # Шукаємо конкретний файл в кеші
        target_filename = f"{filename}.bin"
        for file_info in files_data:
            if file_info["name"] == target_filename:
                return FileResponse(f"{shared_path_beta}/{file_info['name']}")
        raise HTTPException(status_code=404, detail=f"File {target_filename} not found")


async def update_fusion_beta(request):
    redis_client = request.app.state.redis_client

    filename = request.path_params["filename"]

    files_data = await get_redis_data(logger, redis_client, "releases:data", default_response=[])

    if filename == "latest_beta" or filename == "jaam_beta":
        # Повертаємо перший (найновіший) файл
        if files_data:
            return RedirectResponse(url=files_data[0]["url"])
        raise HTTPException(status_code=404, detail="No releases found")
    else:
        # Шукаємо конкретний файл в кеші
        target_filename = f"{filename}.bin"
        for file_info in files_data:
            if file_info["name"] == target_filename:
                return RedirectResponse(url=file_info["url"])
        raise HTTPException(status_code=404, detail=f"File {target_filename} not found")


async def _check_touch_auth(request, filename: str):
    """chip_id + HMAC(secret, 'OTA:<filename>:chip_id:ts') — domain включає ім'я файлу,
    щоб захоплений токен для однієї версії був непридатний для іншої."""
    redis_client = request.app.state.redis_client
    qs = request.query_params
    ok, reason = await verify_device_auth(
        redis_client,
        qs.get("chip_id"),
        qs.get("ts"),
        qs.get("mac"),
        domain=f"OTA:{filename}",
    )
    if not ok:
        raise HTTPException(status_code=401, detail=f"unauthorized: {reason}")


async def update_touch(request):
    filename = request.path_params["filename"]
    await _check_touch_auth(request, filename)

    redis_client = request.app.state.redis_client
    files_data = await get_redis_data(logger, redis_client, "releases:touch:production", default_response=[])

    target_filename = f"{filename}.bin"
    for file_info in files_data:
        if file_info["name"] == target_filename:
            return FileResponse(f"{shared_path_touch}/{file_info['name']}")
    raise HTTPException(status_code=404, detail=f"File {target_filename} not found")


async def update_touch_beta(request):
    filename = request.path_params["filename"]
    await _check_touch_auth(request, filename)

    redis_client = request.app.state.redis_client
    files_data = await get_redis_data(logger, redis_client, "releases:touch:beta", default_response=[])

    target_filename = f"{filename}.bin"
    for file_info in files_data:
        if file_info["name"] == target_filename:
            return FileResponse(f"{shared_path_touch_beta}/{file_info['name']}")
    raise HTTPException(status_code=404, detail=f"File {target_filename} not found")


# Legacy function - disabled (shared_path not defined)
# async def update_board(request):
#     return FileResponse(f'{shared_path}/{request.path_params["board"]}/{request.path_params["filename"]}.bin')


# Legacy functions - disabled (shared_path and shared_beta_path not defined)
# async def update(request):
#     if request.path_params["filename"] == "latest" or request.path_params["filename"] == "jaam":
#         filenames = sorted(
#             [
#                 file
#                 for file in os.listdir(shared_path_beta)
#                 if (os.path.isfile(os.path.join(shared_path_beta, file)) and file.endswith(".bin"))
#             ],
#             key=bin_sort,
#             reverse=True,
#         )
#         filenames = [filename for filename in filenames if not filename.startswith("4.")]
#         return FileResponse(f"{shared_path_beta}/{filenames[0]}")
#     if request.path_params["filename"] == "jaam_beta":
#         filenames = sorted(
#             [
#                 file
#                 for file in os.listdir(shared_path_beta)
#                 if (os.path.isfile(os.path.join(shared_path_beta, file)) and file.endswith(".bin"))
#             ],
#             key=bin_sort,
#             reverse=True,
#         )
#         return FileResponse(f"{shared_path_beta}/{filenames[0]}")
#     return FileResponse(f'{shared_path_beta}/{request.path_params["filename"]}.bin')


# async def update_beta_board(request):
#     return FileResponse(f'{shared_beta_path}/{request.path_params["board"]}/{request.path_params["filename"]}.bin')


async def update_cache(redis_client):
    while True:
        try:
            logger.debug("start update_cache")

            old_data = await get_redis_data(logger, redis_client, "releases:data", default_response=[])

            releases = await fetch_github_releases()
            if releases:
                if releases != old_data:

                    await set_redis_data(logger, redis_client, "releases:data", releases)
                    await redis_client.publish("releases:data:updated", "1")
                    logger.info(f"✅ Оновлені дані releases:data {len(releases)} збережено в Redis")
                else:
                    logger.debug("⏭️  Дані не змінилися, пропускаємо збереження")
            else:
                logger.debug("❌  Дані відсутні, пропускаємо збереження")
            logger.debug("end update_cache")
            await asyncio.sleep(update_loop_time)
        except asyncio.CancelledError:
            logger.error("❌ update_cache: task canceled. Shutting down...")
            await redis_client.close()
            break
        except Exception as e:
            logger.error(f"❌ Error in update_cache: {e}")
            logger.debug(f"❌ Повний стек помилки:", exc_info=True)
            await asyncio.sleep(update_loop_time)


async def update_cache_touch(redis_client):
    """Аналог update_cache, але для окремого приватного репозиторію jaam_touch
    (releases:touch:data, а не releases:data — не перетинається з jaam_fusion)."""
    while True:
        try:
            logger.debug("start update_cache_touch")

            old_data = await get_redis_data(logger, redis_client, "releases:touch:data", default_response=[])

            releases = await fetch_github_releases_touch()
            if releases:
                if releases != old_data:
                    await set_redis_data(logger, redis_client, "releases:touch:data", releases)
                    await redis_client.publish("releases:touch:data:updated", "1")
                    logger.info(f"✅ Оновлені дані releases:touch:data {len(releases)} збережено в Redis")
                else:
                    logger.debug("⏭️  Дані touch не змінилися, пропускаємо збереження")
            else:
                logger.debug("❌  Дані touch відсутні, пропускаємо збереження")
            logger.debug("end update_cache_touch")
            await asyncio.sleep(update_loop_time)
        except asyncio.CancelledError:
            logger.error("❌ update_cache_touch: task canceled. Shutting down...")
            await redis_client.close()
            break
        except Exception as e:
            logger.error(f"❌ Error in update_cache_touch: {e}")
            logger.debug(f"❌ Повний стек помилки:", exc_info=True)
            await asyncio.sleep(update_loop_time)


@asynccontextmanager
async def lifespan(app: Starlette):
    # Startup: create Redis connection
    redis_client = redis.Redis(
        host=redis_host,
        port=redis_port,
        db=redis_db,
        password=redis_password,
        decode_responses=True,
        encoding="utf-8",
        socket_connect_timeout=5,
        socket_keepalive=True,
        health_check_interval=30,
    )

    try:
        await redis_client.ping()
        logger.info(f"✅ Successfully connected to Redis at {redis_host}:{redis_port}")

        # Store redis_client in app state
        app.state.redis_client = redis_client

        # Start background tasks
        update_cache_task = asyncio.create_task(run_with_restart(logger, update_cache, redis_client, "update_cache"))
        update_cache_touch_task = asyncio.create_task(
            run_with_restart(logger, update_cache_touch, redis_client, "update_cache_touch")
        )

        yield

        # Shutdown: cleanup
        logger.info("⏹️  Shutting down...")
        update_cache_task.cancel()
        update_cache_touch_task.cancel()
        for task in (update_cache_task, update_cache_touch_task):
            try:
                await task
            except asyncio.CancelledError:
                pass

    except redis.ConnectionError as e:
        logger.error(f"❌ Failed to connect to Redis: {e}")
        raise
    finally:
        await redis_client.aclose()
        logger.info("🔌 Redis connection closed")


async def home(request):
    response = """
    <!DOCTYPE html>
    <html lang='en'>
    </html>
    """
    return HTMLResponse(response)


app = Starlette(
    debug=debug,
    exception_handlers=exception_handlers,
    lifespan=lifespan,
    routes=[
        Route("/", home),
        Route("/list", list),
        Route("/betalist", list_beta),
        Route("/{filename}.bin", update),
        Route("/beta/{filename}.bin", update_beta),
        Route("/fusion/{filename}.bin", update_fusion),
        Route("/fusion/beta/{filename}.bin", update_fusion_beta),
        # jaam_touch: окремий, auth-gated пайплайн (див. _check_touch_auth) — ізольований
        # від /fusion/*.bin вище.
        Route("/touch/{filename}.bin", update_touch),
        Route("/touch/beta/{filename}.bin", update_touch_beta),
        # Route("/{board}/{filename}.bin", update_board),
        # Route("/beta/{board}/{filename}.bin", update_beta_board),
    ],
)

if __name__ == "__main__":
    if DEVICE_AUTH_MASTER_SECRET == b"change-me-in-production":
        raise RuntimeError(
            "DEVICE_AUTH_MASTER_SECRET не змінено! Виставте змінну оточення DEVICE_AUTH_MASTER_SECRET "
            "перед запуском — інакше auth-токени OTA-завантаження /touch/*.bin тривіально підробні."
        )
    uvicorn.run(app, host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips=["*"])
