from common_new.logger import get_logger
from app_reasoner.services.reasoner_search.text_embed_and_store import ReasonerSearchService

logger = get_logger("reasoner_search")

class Pipeline:
    def __init__(self):
        self.reasoner_search_service = ReasonerSearchService()

    async def run(self, message_data: dict):
        # Step 1: Index the incoming message
        await self._index_incoming_message(message_data)

        # Step 2: Search against the dispocode index (placeholder)
        await self._search_dispocode_index()

        # Step 3: Classify with GPT (placeholder)
        await self._classify_with_gpt()

    async def _index_incoming_message(self, message_data: dict):
        logger.info(f"Indexing message id: {message_data.get('id')}")
        await self.reasoner_search_service.create_index_if_not_exists()
        await self.reasoner_search_service.embed_and_upload_document(message_data)
        logger.info(f"Successfully indexed message id: {message_data.get('id')}")

    async def _search_dispocode_index(self):
        # This is a placeholder for the logic to search the dispocode index
        logger.info("Searching dispocode index (placeholder)")
        pass

    async def _classify_with_gpt(self):
        # This is a placeholder for the logic to classify with GPT
        logger.info("Classifying with GPT (placeholder)")
        pass
