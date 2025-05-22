# Reasoner Processing Service

## Overview
The Reasoner Processing Service is a specialized microservice that processes call transcripts using Azure OpenAI. It receives transcript data from an Azure Service Bus queue, processes it using AI to generate insights, and delivers the processed results to an output queue.

## Key Features
- **Intelligent Call Transcript Processing**: Uses Azure OpenAI to analyze and categorize call transcripts
- **PII Removal**: Automatically removes personal identifiable information from transcripts
- **Reason Categorization**: Classifies call content using predefined reason categories
- **AI-Generated Reasoning**: Creates additional relevant reasoning beyond predefined categories
- **Message Queue Integration**: Works seamlessly with Azure Service Bus for reliable message processing
- **Robust Error Handling**: Implements comprehensive error handling for all processing steps
- **Rate Limit Management**: Smart retries with backoff when hitting OpenAI API rate limits

## Architecture

### Core Components
1. **Service Bus Handler**: Listens to an input queue and sends processed results to an output queue
   - Uses Azure Identity for authentication
   - Implements robust message handling with lock management
   - Provides graceful startup and shutdown

2. **Data Processor**: Transforms raw input data into processed insights
   - Validates input data using Pydantic models
   - Handles JSON parsing and error conditions
   - Returns structured output data

3. **Call Processor**: The AI-powered call transcript analysis engine
   - Connects to Azure OpenAI using the common service
   - Formats prompts with system and user instructions
   - Processes the call transcripts to extract insights
   - Handles retries when API limits are reached

4. **Prompt Management**: Manages the prompts sent to the AI models
   - Defines system instructions for the AI
   - Creates user prompts with variables
   - Formats reason options for consistent classification

## Technical Details

### Call Transcript Processing Pipeline
1. Service Bus Handler receives a message from the input queue
2. Message is passed to the Data Processor for initial validation
3. Valid data is sent to the Call Processor for AI analysis
4. AI generates a summary, reason classification, and AI-suggested reason
5. Results are formatted and sent to the output queue

### AI Prompt System
- **System Prompt**: Defines the AI's role and tasks (summarize, classify, add reasons)
- **User Prompt**: Contains call transcript and reason options
- **Variables**: Dynamically inserts call transcript and reason options into templates

### Reason Classification
- **Predefined Reasons**: Standard categories like #logical, #empirical, #theoretical
- **AI-Generated Reasons**: Additional relevant reasons created by the AI
- **Reason Descriptions**: Each reason includes a detailed description and examples

### Token Rate Limit Management
- Integrated with the Token Counter service for rate limit management
- Smart retry logic when hitting API rate limits
- Waits for the token window to reset before retrying
- Uses non-blocking async/await for efficient resource usage

### Error Handling and Resilience
- Comprehensive exception handling at each step
- Automatic retries for transient errors
- Graceful degradation with meaningful error messages
- Detailed logging for diagnostics

## Configuration
- `SERVICE_BUS_NAMESPACE`: The fully qualified Azure Service Bus namespace
- `REASONER_IN_QUEUE`: Name of the input queue (default: "reasoner-in")
- `REASONER_OUT_QUEUE`: Name of the output queue (default: "reasoner-out")

## Input/Output Data Models

### Input Model
```json
{
  "id": "reason-123",
  "taskId": "task-456",
  "language": "en",
  "text": "Call transcript goes here"
}
```

### Output Model
```json
{
  "id": "reason-123",
  "taskId": "task-456",
  "reason": "#predefinedCategory",
  "ai_reason": "#aiGeneratedReason",
  "summary": "Concise summary with PII removed",
  "message": "SUCCESS"
}
```

## Service Bus Integration
- Uses Azure Service Bus for reliable message processing
- Implements at-least-once delivery guarantee
- Handles message completion after successful processing
- Supports error handling with retry logic

## Running the Service
```bash
uvicorn apps.app_reasoner.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## API Endpoints

### GET /
Returns basic information about the app.

### GET /health
Health check endpoint that shows service bus connection status.

## Architecture Integration
This service is designed to work alongside the Token Counter service to manage OpenAI API rate limits. It uses the common Azure OpenAI Service for interacting with the AI models, which in turn uses the Token Client to manage token usage. 