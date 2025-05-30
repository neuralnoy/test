# Comprehensive Test Suite for AI-Powered Microservices Framework

This directory contains a comprehensive test suite for the AI-powered microservices framework. The tests are organized to provide thorough coverage of all components in the `common_new/` library, ensuring reliability and robustness of the core functionality.

## Test Structure

The test suite is structured as follows:

```
tests_new/
├── unittests/                          # Unit tests for common library components
│   ├── __init__.py                     # Package initialization
│   ├── test_azure_openai_service.py    # Azure OpenAI service tests (20 tests)
│   ├── test_blob_storage.py            # Azure Blob Storage tests (28 tests)
│   ├── test_log_monitor.py             # Log monitoring service tests (21 tests)
│   ├── test_logger.py                  # Logger module tests (23 tests)
│   ├── test_retry_helpers.py           # Retry helpers tests (37 tests)
│   ├── test_service_bus.py             # Service Bus handler tests (26 tests)
│   └── test_token_client.py            # Token client tests (25 tests)
├── integrationtests/                   # Integration tests for full app functionality
└── README.md                          # This documentation file
```

**Total Unit Tests: 180 tests across 7 modules**

## Quick Start

### Prerequisites

- Python 3.8+
- Test dependencies installed

### Installation

```bash
# Install test dependencies
pip install -r test_requirements.txt
```

### Basic Test Execution

```bash
# Run all unit tests with verbose output
pytest tests_new/unittests/ -v

# Run all tests with coverage report
pytest tests_new/unittests/ -v --cov=common_new --cov-report=html --cov-report=term-missing

# Run a specific test file
pytest tests_new/unittests/test_azure_openai_service.py -v

# Run a specific test class
pytest tests_new/unittests/test_retry_helpers.py::TestRetryDecorator -v

# Run a specific test method
pytest tests_new/unittests/test_token_client.py::TestTokenClient::test_init_success -v
```

## Detailed Test Coverage

### 1. test_azure_openai_service.py (20 tests)

Tests the Azure OpenAI service integration with comprehensive mocking of the OpenAI SDK.

**Key Test Categories:**
- Service initialization and configuration
- Token counting for different message types
- Chat completions with various parameters
- Structured outputs with Pydantic models
- Embeddings generation
- Error handling and retry scenarios

**Notable Features:**
- Complete OpenAI SDK mocking
- Pydantic model validation testing
- Token counting accuracy verification
- Multiple message format support

**Example Tests:**
```bash
# Test chat completions
pytest tests_new/unittests/test_azure_openai_service.py::TestAzureOpenAIService::test_chat_completion_success -v

# Test structured outputs
pytest tests_new/unittests/test_azure_openai_service.py::TestAzureOpenAIService::test_structured_output_success -v
```

### 2. test_blob_storage.py (28 tests)

Tests Azure Blob Storage operations with comprehensive Azure SDK mocking.

**Key Test Categories:**
- Blob storage client initialization
- File upload operations (text, binary, JSON)
- Queue-based file processing
- Worker thread management
- Retry logic and error handling
- Service shutdown procedures

**Notable Features:**
- Azure SDK comprehensive mocking
- Thread safety testing
- Queue processing simulation
- Upload retry mechanism validation

**Example Tests:**
```bash
# Test file uploads
pytest tests_new/unittests/test_blob_storage.py::TestBlobStorageService::test_upload_text_file_success -v

# Test worker functionality
pytest tests_new/unittests/test_blob_storage.py::TestBlobStorageService::test_worker_processes_queue -v
```

### 3. test_log_monitor.py (21 tests)

Tests the singleton log monitoring service for leadership acquisition and file monitoring.

**Key Test Categories:**
- Singleton pattern enforcement
- Leadership acquisition and release
- File scanning and monitoring
- Blob storage integration
- Inter-process coordination
- Service lifecycle management

**Notable Features:**
- Singleton behavior verification
- Leadership election simulation
- File system monitoring
- Process coordination testing

**Example Tests:**
```bash
# Test singleton behavior
pytest tests_new/unittests/test_log_monitor.py::TestLogMonitor::test_singleton_pattern -v

# Test leadership acquisition
pytest tests_new/unittests/test_log_monitor.py::TestLogMonitor::test_acquire_leadership_success -v
```

### 4. test_logger.py (23 tests)

Tests the custom logger module with file locking and environment configuration.

**Key Test Categories:**
- Singleton logger pattern
- File locking mechanisms
- Environment variable configuration
- Logger setup and teardown
- Leadership acquisition
- Multi-logger scenarios

**Notable Features:**
- File system locking simulation
- Environment variable testing
- Logger configuration validation
- Concurrent access handling

**Example Tests:**
```bash
# Test logger initialization
pytest tests_new/unittests/test_logger.py::TestLogger::test_get_logger_creates_singleton -v

# Test file locking
pytest tests_new/unittests/test_logger.py::TestLogger::test_acquire_log_lock_success -v
```

### 5. test_retry_helpers.py (37 tests)

Tests retry mechanisms and intelligent backoff strategies with extensive decorator testing.

**Key Test Categories:**
- Retry decorator functionality
- Token client integration
- Wait time calculations
- Error handling scenarios
- Rate limit management
- Exponential backoff logic

**Notable Features:**
- Comprehensive decorator testing
- Token client interaction simulation
- Rate limit scenario handling
- Backoff calculation verification

**Example Tests:**
```bash
# Test retry decorator
pytest tests_new/unittests/test_retry_helpers.py::TestRetryDecorator::test_retry_success_first_attempt -v

# Test rate limit handling
pytest tests_new/unittests/test_retry_helpers.py::TestRetryDecorator::test_retry_with_rate_limit_wait -v
```

### 6. test_service_bus.py (26 tests)

Tests Azure Service Bus operations with comprehensive message handling scenarios.

**Key Test Categories:**
- Service Bus client initialization
- Message processing (string, bytes, generator)
- Message sending operations
- Connection management
- Error handling and retries
- Sleep time adjustment logic

**Notable Features:**
- Multiple message body type support
- Azure Service Bus SDK mocking
- Connection lifecycle testing
- Message processing pipeline validation

**Example Tests:**
```bash
# Test message processing
pytest tests_new/unittests/test_service_bus.py::TestAsyncServiceBusHandler::test_process_string_message -v

# Test message sending
pytest tests_new/unittests/test_service_bus.py::TestAsyncServiceBusHandler::test_send_message_success -v
```

### 7. test_token_client.py (25 tests)

Tests HTTP client operations for token management with comprehensive aiohttp mocking.

**Key Test Categories:**
- HTTP client initialization
- Token locking operations
- Usage reporting
- Token release mechanisms
- Status retrieval
- Full lifecycle scenarios

**Notable Features:**
- Complete aiohttp client mocking
- HTTP response simulation
- Error scenario testing
- Client lifecycle management

**Example Tests:**
```bash
# Test token operations
pytest tests_new/unittests/test_token_client.py::TestTokenClient::test_lock_tokens_success -v

# Test status retrieval
pytest tests_new/unittests/test_token_client.py::TestTokenClient::test_get_status_success -v
```

## Advanced Test Execution

### Running Tests with Markers

```bash
# Run only async tests
pytest tests_new/unittests/ -m asyncio -v

# Run only unit tests (exclude integration)
pytest tests_new/unittests/ -m unit -v

# Run tests marked as slow
pytest tests_new/unittests/ -m slow -v
```

### Coverage Analysis

```bash
# Generate HTML coverage report
pytest tests_new/unittests/ --cov=common_new --cov-report=html
# Open htmlcov/index.html in browser

# Generate terminal coverage report
pytest tests_new/unittests/ --cov=common_new --cov-report=term-missing

# Coverage with branch analysis
pytest tests_new/unittests/ --cov=common_new --cov-branch --cov-report=term-missing
```

### Parallel Test Execution

```bash
# Run tests in parallel (requires pytest-xdist)
pytest tests_new/unittests/ -n auto -v

# Run with specific number of workers
pytest tests_new/unittests/ -n 4 -v
```

### Debug Options

```bash
# Stop on first failure
pytest tests_new/unittests/ -x -v

# Drop into debugger on failure
pytest tests_new/unittests/ --pdb -v

# Show local variables in tracebacks
pytest tests_new/unittests/ -l -v

# Capture output (show print statements)
pytest tests_new/unittests/ -s -v
```

## Environment Variables

The tests are designed to work **without requiring real Azure credentials**. All external dependencies are mocked. However, if you want to set environment variables for consistency:

```bash
# Optional: Set test environment variables (not required for unit tests)
export AZURE_OPENAI_API_VERSION="2023-05-15"
export AZURE_OPENAI_ENDPOINT="https://test.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4"
export SERVICE_BUS_NAMESPACE="test-namespace.servicebus.windows.net"
export AZURE_STORAGE_ACCOUNT="test-storage-account"
export AZURE_STORAGE_CONTAINER="test-container"
export TOKEN_COUNTER_URL="http://localhost:8001"
```

## Test Configuration

The project uses `pytest.ini` for configuration:

```ini
[tool:pytest]
testpaths = tests_new
addopts = --cov=common_new --cov-report=html --cov-report=term-missing -v
markers =
    unit: Unit tests
    integration: Integration tests
    asyncio: Async tests
    slow: Slow running tests
```

## Coverage Files

The test suite generates several coverage-related files:

- `.coverage` - Coverage database (should not be committed)
- `htmlcov/` - HTML coverage report directory
- Coverage reports help identify untested code

## Test Philosophy

### Unit Test Principles

1. **No External Dependencies**: All external services (Azure SDK, OpenAI, HTTP clients) are mocked
2. **Fast Execution**: Tests should run quickly without network calls
3. **Isolated**: Each test is independent and can run in any order
4. **Comprehensive**: Cover success paths, error scenarios, and edge cases
5. **Maintainable**: Clear test names and structure for easy maintenance

### Mocking Strategy

- **Azure SDK**: Comprehensive mocking of Azure services (Blob Storage, Service Bus)
- **OpenAI SDK**: Complete mocking of OpenAI client and responses
- **HTTP Clients**: Full aiohttp client mocking
- **File System**: Mock file operations where needed
- **Environment**: Mock environment variables for testing

### Test Patterns

All tests follow the **AAA (Arrange, Act, Assert)** pattern:

```python
def test_example():
    # Arrange: Set up test data and mocks
    mock_client = Mock()
    service = MyService(mock_client)
    
    # Act: Execute the functionality being tested
    result = service.do_something()
    
    # Assert: Verify the expected behavior
    assert result == expected_value
    mock_client.method.assert_called_once()
```

## Expected Test Output

When running the full test suite, you should see output similar to:

```
tests_new/unittests/test_azure_openai_service.py::TestAzureOpenAIService::test_init_success PASSED [  1%]
tests_new/unittests/test_azure_openai_service.py::TestAzureOpenAIService::test_count_tokens_simple_message PASSED [  2%]
...
tests_new/unittests/test_token_client.py::TestTokenClient::test_full_lifecycle PASSED [ 100%]

==================== 180 passed in 2.45s ====================

Coverage Report:
Name                                Stmts   Miss  Cover   Missing
-----------------------------------------------------------------
common_new/__init__.py                 0      0   100%
common_new/azure_openai_service.py    125     5    96%   45-47
common_new/blob_storage.py            180     8    96%   156-158, 201-203
common_new/log_monitor.py             95      3    97%   78-80
common_new/logger.py                  78      2    97%   45-46
common_new/retry_helpers.py           110     4    96%   89-91, 156
common_new/service_bus.py             140     6    96%   178-180, 245-247
common_new/token_client.py            85      3    96%   67-69
-----------------------------------------------------------------
TOTAL                                 813     31    96%
```

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure `common_new` is in Python path
2. **Missing Dependencies**: Run `pip install -r test_requirements.txt`
3. **Permission Errors**: Check file permissions for temp directories
4. **Async Test Issues**: Ensure proper async test setup

### Debug Tips

```bash
# Run single test with full output
pytest tests_new/unittests/test_azure_openai_service.py::TestAzureOpenAIService::test_init_success -v -s

# Show test collection
pytest tests_new/unittests/ --collect-only

# Run with timing information
pytest tests_new/unittests/ --durations=10
```

## Contributing

When adding new tests:

1. Follow the existing naming conventions (`test_*.py`)
2. Use descriptive test method names
3. Include docstrings for complex test scenarios
4. Mock all external dependencies
5. Cover both success and error paths
6. Add appropriate markers for test categorization

For questions or issues with the test suite, refer to the individual test files for examples and patterns. 