"""Private upload retention, independent from Mongo TTL cleanup."""
import asyncio
import logging
import time

log = logging.getLogger(__name__)
CLEANUP_INTERVAL_SECONDS = 600


def cleanup_expired_files(settings):
    cutoff = time.time() - settings.retention_hours * 3600
    for path in settings.upload_dir.glob('*.h5ad'):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            log.exception('Could not remove expired upload')


async def cleanup_loop(settings):
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            cleanup_expired_files(settings)
        except Exception:
            log.exception('Retention sweep failed')
