"""
Step 1 of the reasoner search pipeline.
This module is responsible for embedding and storing the call transcript in the Azure Search service.
"""
from azure.search.documents.indexes.models import (
    SimpleField,
    SearchableField,
    SearchField,
    VectorSearch,
    VectorSearchProfile,
    SearchFieldDataType,
    HnswAlgorithmConfiguration,
    HnswParameters,
)
from common_new.logger import get_logger
from common_new.azure_search_service import AzureSearchService
from common_new.azure_embedding_service import AzureEmbeddingService

logger = get_logger("reasoner_search")

class EmbedAndStoreService:
    def __init__(self, index_name: str = "call-reasoner-index"):
        self.search_service = AzureSearchService(index_name=index_name)
        self.embedding_service = AzureEmbeddingService()
        self.vector_field_name = "text_vector"
        self.vector_dimensions = 3072

    async def create_index_if_not_exists(self):
        if not await self.search_service.index_exists():
            logger.info(f"Index '{self.search_service.index_name}' does not exist. Creating now.")
            fields = [
                SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True, sortable=True),
                SearchableField(name="taskId", type=SearchFieldDataType.String, filterable=True, sortable=True),
                SearchableField(name="language", type=SearchFieldDataType.String, filterable=True, sortable=True),
                SearchableField(name="text", type=SearchFieldDataType.String),
                SearchField(
                    name=self.vector_field_name,
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True,
                    vector_search_dimensions=self.vector_dimensions,
                    vector_search_profile_name="vector-profile",
                ),
            ]
            
            vector_search_algorithm = HnswAlgorithmConfiguration(
                name="vector-config",
                parameters=HnswParameters(metric="cosine"),
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
        else:
            logger.info(f"Index '{self.search_service.index_name}' already exists.")

    async def embed_and_upload_document(self, document: dict) -> list[float]:
        text_to_embed = document.get("text")
        if not text_to_embed:
            logger.warning("Document has no 'text' field to embed. Skipping.")
            raise ValueError("Document has no 'text' field")

        logger.info(f"Creating embedding for document id: {document.get('id')}")
        embedding_list = await self.embedding_service.create_embedding(text=text_to_embed)
        
        if not embedding_list:
            logger.error(f"Failed to create embedding for document id: {document.get('id')}")
            raise ValueError("Embedding creation failed")

        embedding = embedding_list[0]
        document[self.vector_field_name] = embedding
        
        await self.search_service.upload_documents([document])
        logger.info(f"Successfully uploaded document id: {document.get('id')}")
        return embedding
