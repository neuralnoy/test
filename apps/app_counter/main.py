import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from common.service_bus import AsyncServiceBusHandler
from common.logger import get_logger
from apps.app_counter.services.data_processor import process_data

logger = get_logger("counter_app")

# Get service bus connection details from environment variables
FULLY_QUALIFIED_NAMESPACE = os.getenv("SERVICE_BUS_NAMESPACE")
IN_QUEUE_NAME = os.getenv("COUNTER_IN_QUEUE", "counter-in")
OUT_QUEUE_NAME = os.getenv("COUNTER_OUT_QUEUE", "counter-out")

# Initialize service bus handler with DefaultAzureCredential
logger.info(f"Using DefaultAzureCredential for Service Bus authentication with namespace: {FULLY_QUALIFIED_NAMESPACE}")
service_bus_handler = AsyncServiceBusHandler(
    processor_function=process_data,
    in_queue_name=IN_QUEUE_NAME,
    out_queue_name=OUT_QUEUE_NAME,
    fully_qualified_namespace=FULLY_QUALIFIED_NAMESPACE
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for the FastAPI app.
    Handles startup and shutdown events for the service bus handler.
    """
    # Startup logic
    logger.info("Starting Counter Processor app")
    listener_task = asyncio.create_task(service_bus_handler.listen())
    logger.info("Service bus handler started")
    
    yield  # This is where the app runs
    
    # Shutdown logic
    logger.info("Shutting down Counter Processor app")
    await service_bus_handler.stop()
    logger.info("Service bus handler stopped")

app = FastAPI(title="Counter Processor", lifespan=lifespan)

@app.get("/")
def read_root():
    return {
        "app": "Counter Processor",
        "status": "running",
        "auth_type": "Default Azure Credential",
        "queues": {
            "in": IN_QUEUE_NAME,
            "out": OUT_QUEUE_NAME
        }
    }

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service_bus_running": service_bus_handler.running} 