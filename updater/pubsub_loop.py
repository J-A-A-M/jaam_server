"""Generic Redis Pub/Sub-цикл — прибирає ~15 копій однакового boilerplate.

Покриває обидва варіанти, що були в updater.py:
- простий: підписка -> get_message -> await on_message(channel) -> sleep;
- throttled+initial: опційний `initial()` до циклу, `throttler` для wait/cancel
  (сам виклик через throttler робить `on_message`), опційний фільтр `accepted_channels`.
"""

import asyncio


async def run_pubsub_loop(
    redis_client,
    channels,
    on_message,
    name,
    logger,
    run_once=False,
    initial=None,
    sleep=0.1,
    throttler=None,
    accepted_channels=None,
):
    """
    :param on_message: async fn(channel) — реакція на повідомлення (може викликати throttler.call).
    :param initial: async fn() — початковий виклик після підписки (напр. fusion alerts).
    :param throttler: якщо задано — у run_once робимо `await throttler.wait()`, у finally `cancel()`.
    :param accepted_channels: якщо задано — обробляти лише канали з цієї множини.
    """
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(*channels)
    logger.info(f"📡 Підписано на канали: {', '.join(channels)}")

    try:
        if initial is not None:
            await initial()

        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                channel = message["channel"]
                if accepted_channels is None or channel in accepted_channels:
                    logger.info(f"📬 Отримано повідомлення з каналу: {channel} ({name})")
                    await on_message(channel)

            if run_once:
                if throttler is not None:
                    await throttler.wait()
                break

            if sleep:
                await asyncio.sleep(sleep)  # Коротка пауза для зменшення навантаження на CPU

    except Exception as e:
        logger.error(f"❌ {name}: {str(e)}")
        logger.debug("❌ Повний стек помилки:", exc_info=True)
    finally:
        if throttler is not None:
            throttler.cancel()
        await pubsub.unsubscribe(*channels)
        await pubsub.aclose()
        logger.info(f"📡 Відписано від каналів: {', '.join(channels)}")
