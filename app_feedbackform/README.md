# Feedback Form Processing Service

## Overview
The Feedback Form Processing Service is a specialized microservice that processes customer feedback using Azure OpenAI. It receives feedback data from an Azure Service Bus queue, processes it using AI to generate insights, and delivers the processed results to an output queue.

## Key Features
- **Intelligent Feedback Processing**: Uses Azure OpenAI to analyze and categorize customer feedback
- **PII Removal**: Automatically removes personal identifiable information from feedback
- **Feedback Categorization**: Classifies feedback using predefined hashtags
- **AI-Generated Tags**: Creates additional relevant hashtags beyond predefined categories
- **Message Queue Integration**: Works seamlessly with Azure Service Bus for reliable message processing
- **Robust Error Handling**: Implements comprehensive error handling for all processing steps
- **Rate Limit Management**: Smart retries with backoff when hitting OpenAI API rate limits

## Architecture

### Core Components
1. **Service Bus Handler**: Listens to an input queue and sends processed results to an output queue
   - Uses Azure Identity for authentication
   - Implements robust message handling with lock management
   - Provides graceful startup and shutdown

2. **Data Processor**: Transforms raw feedback data into processed insights
   - Validates input data using Pydantic models
   - Handles JSON parsing and error conditions
   - Returns structured output data

3. **Feedback Processor**: The AI-powered feedback analysis engine
   - Connects to Azure OpenAI using the common service
   - Formats prompts with system and user instructions
   - Processes the feedback to extract insights
   - Handles retries when API limits are reached

4. **Prompt Management**: Manages the prompts sent to the AI models
   - Defines system instructions for the AI
   - Creates user prompts with variables
   - Formats hashtag options for consistent classification

## Technical Details

### Feedback Processing Pipeline
1. Service Bus Handler receives a message from the input queue
2. Message is passed to the Data Processor for initial validation
3. Valid data is sent to the Feedback Processor for AI analysis
4. AI generates a summary, hashtag classification, and AI-suggested hashtag
5. Results are formatted and sent to the output queue

### AI Prompt System
- **System Prompt**: Defines the AI's role and tasks (summarize, classify, add hashtags)
- **User Prompt**: Contains feedback text and hashtag options
- **Variables**: Dynamically inserts feedback text and hashtag options into templates

### Hashtag Classification
- **Predefined Hashtags**: Standard categories like #product, #service, #usability
- **AI-Generated Hashtags**: Additional relevant hashtags created by the AI
- **Hashtag Descriptions**: Each hashtag includes a detailed description and examples

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
- `FEEDBACK_FORM_IN_QUEUE`: Name of the input queue (default: "feedback-form-in")
- `FEEDBACK_FORM_OUT_QUEUE`: Name of the output queue (default: "feedback-form-out")

## Input/Output Data Models

### Input Model
```json
{
  "id": "feedback-123",
  "taskId": "task-456",
  "language": "en",
  "text": "Customer feedback text goes here"
}
```

### Output Model
```json
{
  "id": "feedback-123",
  "taskId": "task-456",
  "hashtag": "#predefinedCategory",
  "ai_hashtag": "#aiGeneratedTag",
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
uvicorn apps.app_feedbackform.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## API Endpoints

### GET /
Returns basic information about the app.

### GET /health
Health check endpoint that shows service bus connection status.

## Architecture Integration
This service is designed to work alongside the Token Counter service to manage OpenAI API rate limits. It uses the common Azure OpenAI Service for interacting with the AI models, which in turn uses the Token Client to manage token usage. 