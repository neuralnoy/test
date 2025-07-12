import os
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI
from common_new.service_bus import AsyncServiceBusHandler
from common_new.logger import get_logger
from common_new.pom_reader import get_pom_version
from app_feedbackform.services.data_processor import process_data

logger = get_logger("feedback_form_app")

start_time = datetime.now(timezone.utc)

# Get service bus connection details from environment variables
FULLY_QUALIFIED_NAMESPACE = os.getenv("SERVICE_BUS_NAMESPACE")
IN_QUEUE_NAME = os.getenv("APP_SB_IN_QUEUE", "form-iq")
OUT_QUEUE_NAME = os.getenv("APP_SB_OUT_QUEUE", "form-oq")

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
    logger.info("Starting Feedback Form Processor app")
    
    # Initialize log monitoring service if configured
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
    account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
    container_name = os.getenv("AZURE_LOGS_CONTAINER_NAME", "application-logs")
    scan_interval = int(os.getenv("LOG_SCAN_INTERVAL", "60"))
    app_name = os.getenv("APP_NAME")  # Get app name from environment variables
    
    # Only initialize if blob storage is configured (either by URL or account name)
    if account_url or account_name:
        from common_new.log_monitor import LogMonitorService
        
        storage_endpoint = account_url or f"https://{account_name}.blob.core.windows.net"
        logger.info(f"Initializing log monitor service to upload to {storage_endpoint}/{container_name}")
        
        log_monitor = LogMonitorService(
            logs_dir=logs_dir,
            account_name=account_name,
            account_url=account_url,
            container_name=container_name,
            app_name=app_name,  # Pass app_name to the LogMonitorService
            scan_interval=scan_interval
        )
        
        monitor_initialized = await log_monitor.initialize()
        if monitor_initialized:
            logger.info("Log monitor service initialized successfully")
            app.state.log_monitor = log_monitor
        else:
            logger.warning("Failed to initialize log monitor service")
    else:
        logger.info("Azure Blob Storage not configured - log uploads disabled")
    
    # Start service bus handler
    listener_task = asyncio.create_task(service_bus_handler.listen())
    logger.info("Service bus handler started")
    
    yield  # This is where the app runs
    
    # Shutdown logic
    logger.info("Shutting down Feedback Form Processor app")
    
    # Shut down the log monitor if it was initialized
    if hasattr(app.state, "log_monitor"):
        logger.info("Shutting down log monitor service")
        await app.state.log_monitor.shutdown()
    
    # Stop the service bus handler
    await service_bus_handler.stop()
    logger.info("Service bus handler stopped")

app = FastAPI(title="Feedback Form Processor", lifespan=lifespan)

@app.get("/")
def read_root():
    return {
        "app": "Feedback Form Processor",
        "version": get_pom_version(),
        "status": "running",
        "start_time": start_time.isoformat(),
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