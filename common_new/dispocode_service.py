import asyncio
import json
import os
import random
from pathlib import Path
import aiohttp
from filelock import FileLock, Timeout

from azure.search.documents.indexes.models import (
    SimpleField,
    SearchableField,
    SearchField,
    VectorSearch,
    VectorSearchAlgorithmConfiguration,
    VectorSearchProfile,
    VectorSearchAlgorithmKind,
    VectorSearchAlgorithmMetric,
)

from common_new.logger import get_logger
from common_new.azure_search_service import AzureSearchService
from common_new.azure_embedding_service import AzureEmbeddingService

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

        # Initialize Azure services
        self.search_service = AzureSearchService(index_name="dispo_test")
        self.embedding_service = AzureEmbeddingService()
        self.vector_field_name = "description_vector"
        self.vector_dimensions = 3072

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
                # Add a random jitter to the sleep interval to prevent thundering herd
                jitter = random.uniform(0, 60)  # 0 to 60 seconds
                sleep_duration = self.interval_seconds + jitter
                logger.debug(f"Sleeping for {sleep_duration:.2f} seconds (interval + jitter).")
                await asyncio.sleep(sleep_duration)
            except asyncio.CancelledError:
                break

    async def _fetch_and_process_dispocodes(self):
        logger.info("Starting to fetch and process dispocodes.")
        remote_data = None
        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(self.endpoint_url) as response:
                        response.raise_for_status()
                        remote_data = await response.json()
                        logger.info("Successfully fetched data from the endpoint.")
                        break
            except aiohttp.ClientError as e:
                logger.error(f"Attempt {attempt + 1} failed with network error: {e}")
            except json.JSONDecodeError as e:
                logger.error(f"Attempt {attempt + 1} failed to decode JSON: {e}")
            except Exception as e:
                logger.error(f"An unexpected error occurred on attempt {attempt + 1}: {e}")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(5)
        
        await self._process_and_store_data(remote_data)

    async def _process_and_store_data(self, remote_data: dict | None):
        lock = FileLock(self.lock_path)
        try:
            with lock.acquire(timeout=20):
                logger.info("Acquired lock for dispocodes.json.")

                local_dispocodes = []
                if self.json_path.exists():
                    try:
                        with open(self.json_path, "r") as f:
                            local_dispocodes = json.load(f)
                    except (json.JSONDecodeError, IOError) as e:
                        logger.warning(f"Could not read or parse existing dispocodes.json: {e}")

                source_data = []
                if remote_data and "dispoCodes" in remote_data:
                    logger.info("Using fresh data from remote endpoint.")
                    new_dispocodes = remote_data["dispoCodes"]
                    if new_dispocodes != local_dispocodes:
                        with open(self.json_path, "w") as f:
                            json.dump(new_dispocodes, f, indent=4)
                        logger.info("dispocodes.json has been updated with new remote data.")
                        source_data = new_dispocodes
                    else:
                        logger.info("No changes detected between remote and local data.")
                        source_data = local_dispocodes
                else:
                    logger.warning("Remote data not available. Using local dispocodes.json as fallback.")
                    source_data = local_dispocodes

                if not source_data:
                    logger.error("No dispocode data available from remote or local sources.")
                    return

                is_first_run = not await self.search_service.index_exists()
                if is_first_run:
                    logger.info(f"Index '{self.search_service.index_name}' does not exist. Creating and indexing all documents.")
                    await self._create_search_index()
                    docs_to_index = source_data
                else:
                    logger.info("Index exists. Checking for new documents to add.")
                    search_results = await self.search_service.search_documents(search_text="*", select=["id"])
                    existing_ids = {doc['id'] for doc in search_results}
                    docs_to_index = [item for item in source_data if item['id'] not in existing_ids]

                if docs_to_index:
                    logger.info(f"Found {len(docs_to_index)} new documents to index.")
                    await self._embed_and_upload_documents(docs_to_index)
                else:
                    logger.info("No new documents to index.")

        except Timeout:
            logger.error("Could not acquire lock on dispocodes.json. Another process may be holding it.")
        except Exception as e:
            logger.error(f"An error occurred during data processing or indexing: {e}", exc_info=True)
        finally:
            if lock.is_locked:
                lock.release()
                logger.info("Released lock for dispocodes.json.")

    async def _create_search_index(self):
        fields = [
            SimpleField(name="id", type="Edm.String", key=True, filterable=True, sortable=True),
            SearchableField(name="category", type="Edm.String", filterable=True, sortable=True),
            SearchableField(name="typeName", type="Edm.String", filterable=True, sortable=True),
            SearchableField(name="typeValue", type="Edm.String", filterable=True, sortable=True),
            SearchableField(name="hashtags", type="Collection(Edm.String)", filterable=True),
            SearchableField(name="description", type="Edm.String"),
            SearchField(
                name=self.vector_field_name,
                type="Collection(Edm.Single)",
                searchable=True,
                vector_search_dimensions=self.vector_dimensions,
                vector_search_profile_name="vector-profile",
            ),
        ]
        
        vector_search_algorithm = VectorSearchAlgorithmConfiguration(
            name="vector-config",
            kind="hnsw",
            parameters={
                "metric": "cosine"
            },
        )

        vector_search = VectorSearch(
            profiles=[VectorSearchProfile(name="vector-profile", algorithm_configuration_name="vector-config")],
            algorithms=[vector_search_algorithm]
        )
        
        await self.search_service.create_index(
            fields=fields,
            vector_search=vector_search,
            vector_field_name=self.vector_field_name,
            vector_dimensions=self.vector_dimensions
        )

    async def _embed_and_upload_documents(self, documents: list):
        descriptions = [doc["description"] for doc in documents]
        
        if not descriptions:
            return

        logger.info(f"Creating embeddings for {len(descriptions)} descriptions...")
        embeddings = await self.embedding_service.create_embedding_batch(texts=descriptions)
        
        for i, doc in enumerate(documents):
            doc[self.vector_field_name] = embeddings[i]

        logger.info("Uploading documents to Azure AI Search...")
        await self.search_service.upload_documents(documents)
        logger.info(f"Successfully uploaded {len(documents)} documents.")

def get_dispocode_service():
    endpoint_url = os.getenv("DISPOCODE_ENDPOINT_URL")
    if not endpoint_url:
        logger.error("DISPOCODE_ENDPOINT_URL environment variable is not set. DispocodeService cannot be started.")
        return None
    return DispocodeService(endpoint_url=endpoint_url)
