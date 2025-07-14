import asyncio
import json
import os
from pathlib import Path
import aiohttp
from filelock import FileLock, Timeout
from common_new.logger import get_logger

logger = get_logger("dispocode_service")

class DispocodeService:
    def __init__(self, endpoint_url: str, interval_hours: int = 2, max_retries: int = 3):
        if not endpoint_url:
            raise ValueError("Endpoint URL cannot be empty.")
        self.endpoint_url = endpoint_url
        self.interval_seconds = interval_hours * 3600
        self.max_retries = max_retries
        self._task = None
        self._is_running = False

        # Define paths
        self.project_root = Path(__file__).resolve().parent.parent
        self.json_path = self.project_root / "dispocodes.json"
        self.lock_path = self.project_root / "dispocodes.json.lock"

    async def start(self):
        if self._is_running:
            logger.warning("DispocodeService is already running.")
            return

        self._is_running = True
        self._task = asyncio.create_task(self._fetch_and_update_task())
        logger.info("DispocodeService started.")

    async def stop(self):
        if not self._is_running or not self._task:
            logger.warning("DispocodeService is not running.")
            return

        self._is_running = False
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            logger.info("DispocodeService task cancelled successfully.")
        finally:
            self._task = None
            logger.info("DispocodeService stopped.")

    async def _fetch_and_update_task(self):
        while self._is_running:
            await self._fetch_and_process_dispocodes()
            try:
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break

    async def _fetch_and_process_dispocodes(self):
        logger.info("Starting to fetch and process dispocodes.")
        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(self.endpoint_url) as response:
                        response.raise_for_status()
                        data = await response.json()
                        logger.info("Successfully fetched data from the endpoint.")
                        await self._write_to_file(data)
                        return
            except aiohttp.ClientError as e:
                logger.error(f"Attempt {attempt + 1} failed with network error: {e}")
            except json.JSONDecodeError as e:
                logger.error(f"Attempt {attempt + 1} failed to decode JSON: {e}")
            except Exception as e:
                logger.error(f"An unexpected error occurred on attempt {attempt + 1}: {e}")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(5)  # Wait before retrying
        
        logger.error(f"All {self.max_retries} attempts to fetch dispocodes failed.")

    async def _write_to_file(self, data):
        if "dispoCodes" not in data or not isinstance(data["dispoCodes"], list):
            logger.error("Invalid data format received: 'dispoCodes' key missing or not a list.")
            return

        new_content = {"dispoCodes": data["dispoCodes"]}
        lock = FileLock(self.lock_path)

        try:
            with lock.acquire(timeout=10):
                logger.info("Acquired lock for dispocodes.json.")
                
                existing_content = []
                if self.json_path.exists():
                    try:
                        with open(self.json_path, "r") as f:
                            existing_content = json.load(f)
                    except (json.JSONDecodeError, IOError) as e:
                        logger.warning(f"Could not read or parse existing dispocodes.json: {e}")

                if new_content != existing_content:
                    with open(self.json_path, "w") as f:
                        json.dump(new_content, f, indent=4)
                    logger.info("dispocodes.json has been updated.")
                else:
                    logger.info("No changes detected in dispocodes.json. File not updated.")
        
        except Timeout:
            logger.error("Could not acquire lock on dispocodes.json. Another process may be holding it.")
        except Exception as e:
            logger.error(f"An error occurred during file write: {e}")
        finally:
            if lock.is_locked:
                lock.release()
                logger.info("Released lock for dispocodes.json.")

def get_dispocode_service():
    endpoint_url = os.getenv("DISPOCODE_ENDPOINT_URL")
    if not endpoint_url:
        logger.error("DISPOCODE_ENDPOINT_URL environment variable is not set. DispocodeService cannot be started.")
        return None
    return DispocodeService(endpoint_url=endpoint_url)
