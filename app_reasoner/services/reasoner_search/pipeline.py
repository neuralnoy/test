from common_new.logger import get_logger
from app_reasoner.services.reasoner_search.step1_embed_and_store import EmbedAndStoreService

logger = get_logger("reasoner_search")

class Pipeline:
    def __init__(self):
        self.embed_and_store_service = EmbedAndStoreService()

    async def run(self, message_data: dict):
        # Step 1: Index the incoming message and get the embedding vector
        embedding_vector = await self._index_incoming_message(message_data)

        # The final result is returned from the last step of the pipeline.
        pass


    async def _index_incoming_message(self, message_data: dict) -> list[float]:
        logger.info(f"Indexing message id: {message_data.get('id')}")
        await self.embed_and_store_service.create_index_if_not_exists()
        embedding = await self.embed_and_store_service.embed_and_upload_document(message_data)
        logger.info(f"Successfully indexed message id: {message_data.get('id')}")
        return embedding

    async def _search_next_index(self, embedding: list[float]):
        # This is a placeholder for the logic to search the next index.
        # It will eventually return the final output of the pipeline.
        logger.info(f"Ready for next step with embedding of dimension {len(embedding)}")
        pass # Returning None for now.

