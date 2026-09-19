import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("jobsync_worker")

def main():
    logger.info("JobSync Copilot background worker initialized.")
    while True:
        try:
            logger.info("Worker heartbeat: idle, awaiting scheduled pipeline tasks...")
            time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Worker shutting down.")
            break

if __name__ == "__main__":
    main()
