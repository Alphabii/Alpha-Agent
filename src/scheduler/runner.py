import time

from loguru import logger

from src.pipeline import Pipeline


class Scanner:
    """Runs the pipeline on a recurring interval."""

    def __init__(self, pipeline: Pipeline):
        self._pipeline = pipeline
        self._paused = False
        self._running = True

    def run_forever(self, interval_minutes: int = 30):
        """Main loop: scrape, analyze, apply. Runs until stopped."""
        logger.info(f"Scanner started (interval: {interval_minutes} min)")

        while self._running:
            if not self._paused:
                try:
                    results = self._pipeline.run_cycle()
                    logger.info(
                        f"Cycle done: {results['new_jobs']} new, "
                        f"{results['applied']} applied"
                    )
                except Exception as e:
                    logger.error(f"Scan cycle failed: {e}")

            time.sleep(interval_minutes * 60)

    def pause(self):
        """Pause scanning."""
        self._paused = True
        logger.info("Scanner paused")

    def resume(self):
        """Resume scanning."""
        self._paused = False
        logger.info("Scanner resumed")

    def stop(self):
        """Stop the scanner loop."""
        self._running = False
        logger.info("Scanner stopped")

    @property
    def is_paused(self) -> bool:
        return self._paused
