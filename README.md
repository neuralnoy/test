# Async Service Bus Handler for FastAPI Applications

A robust, async service bus handler implementation for FastAPI applications that process data from dedicated input queues and send processed results to output queues.

## Features

- Asynchronous message handling
- Robust error handling with try-except blocks
- Automatic message locking during processing
- Message lock renewal for long-running processes
- Graceful startup and shutdown
- Health check endpoints
- Retries with exponential backoff
- Comprehensive logging
- Azure Default Credentials authentication for secure and flexible authentication

## Project Structure

```
├── apps/
│   ├── app_feedbackform/
│   │   ├── models/
│   │   │   └── schemas.py
│   │   ├── services/
│   │   │   └── data_processor.py
│   │   └── main.py
│   └── app_counter/
│       ├── models/
│       │   └── schemas.py
│       ├── services/
│       │   └── data_processor.py
│       └── main.py
├── common/
│   ├── logger.py
│   └── service_bus.py
├── requirements.txt
└── README.md
```

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Set up environment variables:

```bash
# Service Bus Namespace
export SERVICE_BUS_NAMESPACE="your-servicebus-namespace.servicebus.windows.net"

# Queue names for the feedback form app
export FEEDBACK_FORM_IN_QUEUE="feedback-form-in"
export FEEDBACK_FORM_OUT_QUEUE="feedback-form-out"

# Queue names for the counter app
export COUNTER_IN_QUEUE="counter-in"
export COUNTER_OUT_QUEUE="counter-out"
```

## Authentication

The service bus handler uses Azure Identity library's DefaultAzureCredential, which supports:
- Environment variables (AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_CLIENT_SECRET)
- Managed Identity
- Azure CLI credentials
- Visual Studio Code credentials
- Azure PowerShell credentials
- Interactive browser authentication

Ensure your identity has appropriate permissions to the Service Bus namespace and queues.

## Running the Applications

To run the Feedback Form app:

```bash
uvicorn apps.app_feedbackform.main:app --host 0.0.0.0 --port 8000 --workers 4
```

To run the Counter app:

```bash
uvicorn apps.app_counter.main:app --host 0.0.0.0 --port 8001 --workers 4
```

## Creating a New App

1. Create the app directory structure:

```bash
mkdir -p apps/app_name/models apps/app_name/services
```

2. Create schema models in `apps/app_name/models/schemas.py`.

3. Create a data processor in `apps/app_name/services/data_processor.py` that implements an async `process_data` function.

4. Create the FastAPI app in `apps/app_name/main.py` using the AsyncServiceBusHandler.

5. Set the environment variables for your app's queues.

## How It Works

1. When the FastAPI app starts up, the service bus handler begins listening to the input queue.
2. When a message arrives, it's locked, and the lock is renewed periodically during processing.
3. The message is processed by the app-specific data processor function.
4. If processing is successful, the result is sent to the output queue, and the input message is completed.
5. If an error occurs, the message is abandoned for retry.
6. The handler includes comprehensive error handling and logging.

## Best Practices

- Always include thorough error handling in your data processors.
- Make data processors as fast as possible to minimize lock time.
- Use environment variables for configuration.
- Set up proper logging.
- Use health check endpoints for monitoring.
- Scale by adding more workers, not by running multiple instances.
- For production environments, prefer using Managed Identity with Default Azure Credentials.
- When running locally, authenticate via Azure CLI (`az login`) or environment variables.

## Monitoring

Each app exposes a `/health` endpoint that returns the status of the service bus handler. 