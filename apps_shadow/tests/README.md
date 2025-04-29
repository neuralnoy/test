# Test Coverage for Forms Project

This directory contains comprehensive test coverage for the Forms project. The tests are organized into unit tests and integration tests to ensure thorough coverage of all functionality.

## Test Structure

The test suite is structured as follows:

```
tests/
├── unittests/            # Unit tests for individual components
│   ├── test_token_counter.py        # Tests for TokenCounter service
│   ├── test_token_client.py         # Tests for TokenClient service
│   ├── test_data_processor.py       # Tests for feedback form data processor
│   ├── test_service_bus.py          # Tests for AsyncServiceBusHandler
│   ├── test_azure_openai_service.py # Tests for AzureOpenAIService
│   ├── test_retry_helpers.py        # Tests for retry helpers
│   └── test_logger.py               # Tests for logger module
├── integrationtests/     # Integration tests for full app functionality
│   ├── test_counter_api.py          # Tests for Token Counter API
│   └── test_feedback_form.py        # Tests for Feedback Form service
└── conftest.py           # Shared pytest fixtures and configuration
```

## Running Tests

To run the tests, you'll need to install the test dependencies first:

```bash
pip install -r test_requirements.txt
```

### Running All Tests

To run all tests:

```bash
pytest
```

### Running Specific Test Categories

To run only unit tests:

```bash
pytest tests/unittests/
```

To run only integration tests:

```bash
pytest tests/integrationtests/
```

To run a specific test file:

```bash
pytest tests/unittests/test_token_counter.py
```

### Running with Coverage Report

To run tests with coverage reporting:

```bash
pytest --cov=apps --cov=common --cov-report=term --cov-report=html
```

This command will generate a terminal report and an HTML report in the `htmlcov` directory.

## Test Categories

### Unit Tests

The unit tests focus on testing individual components in isolation, with dependencies mocked as needed:

- **test_token_counter.py**: Tests for the TokenCounter class that manages token rate limiting
- **test_token_client.py**: Tests for the TokenClient class that interacts with the token counter API
- **test_data_processor.py**: Tests for the feedback form data processing logic
- **test_service_bus.py**: Tests for the service bus handler that processes queue messages
- **test_azure_openai_service.py**: Tests for the Azure OpenAI service wrapper
- **test_retry_helpers.py**: Tests for retry helpers that handle transient errors
- **test_logger.py**: Tests for the custom logger module

### Integration Tests

The integration tests focus on testing the complete functionality of the applications:

- **test_counter_api.py**: Tests for the Token Counter API endpoints and flows
- **test_feedback_form.py**: Tests for the Feedback Form service with the service bus

## Key Test Scenarios

The test suite covers the following key scenarios:

1. Token counter rate limiting and tracking
2. Token request, report, and release flows
3. Concurrent token requests handling
4. Feedback form data processing
5. Service bus message handling
6. Error handling and retry mechanisms
7. OpenAI API integration with token management
8. API endpoint functionality

## Edge Cases Covered

The tests include a wide range of edge cases:

- Invalid input data handling
- Error handling during processing
- Timeout and retry scenarios
- Race conditions in concurrent processing
- Message format validation
- Resource limit handling
- API authentication and authorization
- Token rate limit enforcement
- Service continuity during errors

## Adding New Tests

When adding new functionality to the project, please maintain the same level of test coverage by:

1. Adding unit tests for new components
2. Adding integration tests for new API endpoints or flows
3. Testing edge cases and error conditions
4. Ensuring all branches of code are covered

Follow the existing patterns for mocking dependencies and creating test fixtures. 