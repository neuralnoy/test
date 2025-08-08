"""
Azure AI Search Service for vector and text search operations.

Required Environment Variables:
- APP_SEARCH_ENDPOINT: Azure AI Search endpoint URL
"""
import os
from typing import List, Dict, Any, Optional, Union

from azure.identity import DefaultAzureCredential, AzureAuthorityHosts
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    VectorSearch,
    VectorSearchAlgorithmConfiguration,
    VectorSearchAlgorithmKind,
    VectorSearchAlgorithmMetric,
    VectorSearchProfile,
    SearchField,
    SearchFieldDataType,
    HnswAlgorithmConfiguration,
    HnswParameters,
)
from azure.search.documents.models import VectorizedQuery
from azure.core.exceptions import ResourceNotFoundError, HttpResponseError
from dotenv import load_dotenv
from common_new.logger import get_logger

load_dotenv()

logger = get_logger("common")



class AzureSearchService:
    """
    Service for Azure AI Search operations including document indexing and vector search.
    Provides functionality for authentication, document management, and search operations.
    """
    
    def __init__(self, index_name: Optional[str] = None, app_id: str = "default_app"):
        """
        Initialize the Azure AI Search service with credentials from environment variables.
        
        Args:
            index_name: Optional index name. If not specified, defaults to 'default-index'.
            app_id: ID of the application using this service. Used for logging.
        """
        self.search_endpoint = os.getenv("APP_SEARCH_ENDPOINT")
        self.index_name = index_name or "default-index"
        self.app_id = app_id
        
        # Authentication setup (Microsoft's recommended approach)
        authority = AzureAuthorityHosts.AZURE_PUBLIC_CLOUD
        self.credential = DefaultAzureCredential(authority=authority)
        
        if not self.search_endpoint:
            raise ValueError("APP_SEARCH_ENDPOINT must be set in .env file or exported as environment variables")
        
        logger.info(f"Initializing Azure AI Search service with endpoint: {self.search_endpoint}")
        logger.info(f"Using index: {self.index_name}")
        logger.info("Azure Search service configured with Microsoft's recommended approach")
        logger.info("Using DefaultAzureCredential with explicit AZURE_PUBLIC_CLOUD authority")
        
        self.search_client = self._initialize_search_client()
        self.index_client = self._initialize_index_client()
    
    def _initialize_search_client(self) -> SearchClient:
        """
        Initialize the Azure Search client.
        
        Returns:
            SearchClient: An initialized Azure Search client.
        """
        return SearchClient(
            endpoint=self.search_endpoint,
            index_name=self.index_name,
            credential=self.credential
        )
    
    def _initialize_index_client(self) -> SearchIndexClient:
        """
        Initialize the Azure Search Index client for index management.
        
        Returns:
            SearchIndexClient: An initialized Azure Search Index client.
        """
        return SearchIndexClient(
            endpoint=self.search_endpoint,
            credential=self.credential
        )
    
    async def upload_documents(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Upload or update documents in the search index.
        
        Args:
            documents: List of documents to upload. Each document should be a dictionary.
            
        Returns:
            Dict containing upload results
            
        Raises:
            HttpResponseError: If upload fails
        """
        try:
            logger.debug(f"Uploading {len(documents)} documents to index: {self.index_name}")
            
            result = await self.search_client.upload_documents(documents)
            
            logger.info(f"Successfully uploaded {len(documents)} documents")
            return {"success": True, "uploaded_count": len(documents), "results": result}
            
        except Exception as e:
            logger.error(f"Error uploading documents: {str(e)}")
            raise
    
    async def search_documents(
        self,
        search_text: str = "",
        top: int = 10,
        select: Optional[List[str]] = None,
        filter_expression: Optional[str] = None,
        order_by: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform a text search on the index.
        
        Args:
            search_text: Text to search for (empty string for all documents)
            top: Number of results to return
            select: Fields to include in results
            filter_expression: OData filter expression
            order_by: Fields to order by
            
        Returns:
            List of search results
        """
        try:
            logger.debug(f"Searching for: '{search_text}' in index: {self.index_name}")
            
            results = await self.search_client.search(
                search_text=search_text,
                top=top,
                select=select,
                filter=filter_expression,
                orderby=order_by
            )
            
            # Convert results to list of dicts (as in quickstart notebooks)
            search_results = [dict(result) async for result in results]
            
            logger.debug(f"Found {len(search_results)} results")
            return search_results
            
        except Exception as e:
            logger.error(f"Error searching documents: {str(e)}")
            raise
    
    async def vector_search(
        self,
        vector: List[float],
        vector_field: str = "content_vector",
        top: int = 10,
        select: Optional[List[str]] = None,
        filter_expression: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform a vector search on the index.
        
        Args:
            vector: Query vector for similarity search
            vector_field: Name of the vector field in the index
            top: Number of results to return
            select: Fields to include in results
            filter_expression: OData filter expression
            
        Returns:
            List of search results with similarity scores
        """
        try:
            logger.debug(f"Performing vector search in index: {self.index_name}")
            
            vector_query = VectorizedQuery(
                vector=vector,
                k_nearest_neighbors=top,
                fields=vector_field
            )
            
            results = await self.search_client.search(
                search_text="",
                vector_queries=[vector_query],
                select=select,
                filter=filter_expression,
                top=top
            )
            
            # Convert results to list of dicts (as in quickstart notebooks)
            search_results = [dict(result) async for result in results]
            
            logger.debug(f"Found {len(search_results)} vector search results")
            return search_results
            
        except Exception as e:
            logger.error(f"Error performing vector search: {str(e)}")
            raise
    
    async def get_document(self, document_key: str, selected_fields: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Retrieve a single document by its key.
        
        Args:
            document_key: The key/ID of the document
            selected_fields: Optional list of fields to retrieve
            
        Returns:
            The document data
            
        Raises:
            ResourceNotFoundError: If document not found
        """
        try:
            logger.debug(f"Retrieving document with key: {document_key}")
            
            result = await self.search_client.get_document(
                key=document_key,
                selected_fields=selected_fields
            )
            
            logger.debug(f"Successfully retrieved document: {document_key}")
            return result
            
        except ResourceNotFoundError:
            logger.warning(f"Document not found: {document_key}")
            raise
        except Exception as e:
            logger.error(f"Error retrieving document {document_key}: {str(e)}")
            raise
    
    async def delete_documents(self, documents: Union[List[Dict[str, Any]], List[str]]) -> Dict[str, Any]:
        """
        Delete documents from the index.
        
        Args:
            documents: Either a list of document objects with keys, or a list of document keys
            
        Returns:
            Dict containing deletion results
        """
        try:
            # Handle both document objects and key strings
            if documents and isinstance(documents[0], str):
                # Convert keys to document format expected by delete_documents
                documents = [{"@search.action": "delete", "id": key} for key in documents]
            
            logger.debug(f"Deleting {len(documents)} documents from index: {self.index_name}")
            
            result = await self.search_client.delete_documents(documents)
            
            logger.info(f"Successfully deleted {len(documents)} documents")
            return {"success": True, "deleted_count": len(documents), "results": result}
            
        except Exception as e:
            logger.error(f"Error deleting documents: {str(e)}")
            raise
    
    async def get_document_count(self) -> int:
        """
        Get the total number of documents in the index.
        
        Returns:
            Total document count
        """
        try:
            # Use search with count=True to get total count
            results = await self.search_client.search(
                search_text="*",
                include_total_count=True,
                top=0  # We only want the count, not the documents
            )
            
            count = results.get_count()
            logger.debug(f"Total documents in index {self.index_name}: {count}")
            return count
            
        except Exception as e:
            logger.error(f"Error getting document count: {str(e)}")
            raise
    
    async def close(self):
        """
        Close the search client connections.
        """
        try:
            if hasattr(self.search_client, 'close'):
                await self.search_client.close()
            if hasattr(self.index_client, 'close'):
                await self.index_client.close()
            logger.debug("Azure Search service connections closed")
        except Exception as e:
            logger.warning(f"Error closing Azure Search connections: {str(e)}")

    async def create_index(
        self,
        fields: List[SearchField],
        vector_search: Optional[VectorSearch] = None,
        vector_field_name: str = "content_vector",
        vector_dimensions: int = 3072
    ) -> None:
        """
        Create a new search index with custom fields and optional vector search capabilities.
        
        Args:
            fields: List of SearchField objects defining the index schema
            vector_search: Optional VectorSearch configuration. If not provided, a default HNSW configuration will be used
            vector_field_name: Name of the vector field if vector search is enabled
            vector_dimensions: Dimensions of the vector field (default: 1536 for OpenAI embeddings)
            
        Raises:
            HttpResponseError: If index creation fails
            ValueError: If vector search is enabled but vector field is not found in fields
        """
        try:
            # Check if index already exists
            if await self.index_exists():
                logger.info(f"Index {self.index_name} already exists")
                return

            # If vector search is enabled but not provided, create default configuration
            if vector_search is None:
                vector_search = VectorSearch(
                    algorithms=[
                        HnswAlgorithmConfiguration(
                            name="vector-config",
                            parameters=HnswParameters(metric="cosine"),
                        )
                    ],
                    profiles=[
                        VectorSearchProfile(
                            name="vector-profile",
                            algorithm_configuration_name="vector-config",
                        )
                    ],
                )

            # Verify vector field exists if vector search is enabled
            if vector_search and not any(field.name == vector_field_name for field in fields):
                raise ValueError(f"Vector field '{vector_field_name}' not found in provided fields")

            # Create the index
            index = SearchIndex(
                name=self.index_name,
                fields=fields,
                vector_search=vector_search
            )

            logger.info(f"Creating index: {self.index_name}")
            await self.index_client.create_index(index)
            logger.info(f"Successfully created index: {self.index_name}")

        except Exception as e:
            logger.error(f"Error creating index: {str(e)}")
            raise

    async def delete_index(self) -> None:
        """
        Delete the search index.
        
        Raises:
            HttpResponseError: If index deletion fails
        """
        try:
            if not await self.index_exists():
                logger.info(f"Index {self.index_name} does not exist")
                return

            logger.info(f"Deleting index: {self.index_name}")
            await self.index_client.delete_index(self.index_name)
            logger.info(f"Successfully deleted index: {self.index_name}")

        except Exception as e:
            logger.error(f"Error deleting index: {str(e)}")
            raise

    async def index_exists(self) -> bool:
        """
        Check if the index exists.
        
        Returns:
            bool: True if the index exists, False otherwise
        """
        try:
            await self.index_client.get_index(self.index_name)
            return True
        except ResourceNotFoundError:
            return False
        except Exception as e:
            logger.error(f"Error checking if index exists: {str(e)}")
            raise 