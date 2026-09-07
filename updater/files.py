"""Синхронізація локальних файлів релізів з GitHub."""

import logging
import os
import asyncio

import httpx

logger = logging.getLogger(__name__)


async def download_file(url, filepath):
    """Завантажує файл з URL та зберігає його локально"""
    try:
        
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url, follow_redirects=True, timeout=60.0) as response:
                response.raise_for_status()
                with open(filepath, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        await asyncio.to_thread(f.write, chunk)
        logger.info(f"✅ Завантажено файл: {os.path.basename(filepath)}")
        return True
    except Exception as e:
        logger.error(f"❌ Помилка завантаження {os.path.basename(filepath)}: {e}")
        return False


async def sync_local_files(files_data, files_path):
    """Синхронізує локальні файли з даними releases"""
    if not files_data:
        return

    # Створюємо директорію якщо не існує
    os.makedirs(files_path, exist_ok=True)

    # Отримуємо список актуальних файлів з GitHub (з урахуванням strip_pattern)
    def _is_safe_name(name):
        return name and os.path.basename(name) == name and not name.startswith(".")

    remote_files = {item["name"]: item["url"] for item in files_data if _is_safe_name(item["name"])}

    # Отримуємо список локальних .bin файлів
    local_files = set()
    if os.path.exists(files_path):
        local_files = {
            f for f in os.listdir(files_path) if os.path.isfile(os.path.join(files_path, f)) and f.endswith(".bin")
        }

    # Знаходимо файли які треба завантажити
    files_to_download = set(remote_files.keys()) - local_files

    # Знаходимо файли які треба видалити
    files_to_delete = local_files - set(remote_files.keys())

    # Видаляємо застарілі файли
    for filename in files_to_delete:
        try:
            filepath = os.path.join(files_path, filename)
            os.remove(filepath)
            logger.info(f"🗑️  Видалено застарілий файл: {filename}")
        except Exception as e:
            logger.error(f"❌ Помилка видалення {filename}: {e}")

    # Завантажуємо нові файли
    if files_to_download:
        failed = []
        logger.info(f"📥 Завантажуємо {len(files_to_download)} нових файлів...")
        for filename in files_to_download:
            url = remote_files[filename]
            filepath = os.path.join(files_path, filename)
            if not await download_file(url, filepath):
                failed.append(filename)
        if failed:
            logger.error(f"❌ Не вдалося завантажити файли: {', '.join(failed)}")

    if not files_to_download and not files_to_delete:
        logger.debug("✅ Локальні файли синхронізовані")
