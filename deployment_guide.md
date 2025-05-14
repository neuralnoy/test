# Azure App Authentication Guide

This guide explains how to configure authentication between your Feedback Form and Counter apps when deployed to Azure Web Apps.

## Prerequisites

1. Two Azure Web Apps deployed (one for Feedback Form, one for Counter)
2. Azure AD Application registrations for both apps
3. Azure CLI or Azure Portal access

## Step 1: Register Azure AD Apps

For each app (Feedback Form and Counter), you need to create an Azure AD application registration:

```bash
# For Counter app (API)
az ad app create --display-name "Counter-App" --sign-in-audience AzureADMyOrg

# For Feedback Form app (Client)
az ad app create --display-name "Feedback-Form-App" --sign-in-audience AzureADMyOrg
```

Note down the Application (client) IDs for both applications.

## Step 2: Configure API Permissions

The Feedback Form app needs permission to access the Counter app:

1. In Azure Portal, go to App Registrations > Feedback-Form-App
2. Go to API Permissions > Add a permission > My APIs
3. Select Counter-App
4. Select Application permissions
5. Add the appropriate permissions (e.g., "read" and "write")
6. Click "Grant admin consent"

## Step 3: Create App ID URI for Counter App

This URI will be used as the resource identifier:

1. In Azure Portal, go to App Registrations > Counter-App
2. Go to Expose an API
3. Set the Application ID URI (e.g., `api://counter-app-id`)
4. Save the changes

## Step 4: Assign Managed Identities to Web Apps

1. Go to each Azure Web App in the Azure Portal
2. Navigate to Settings > Identity
3. Enable System assigned managed identity
4. Save the changes

## Step 5: Update Application Code

### 1. Update app initialization code:

```python
# In your Feedback Form app
from common.azure_openai_service import AzureOpenAIService

# Initialize with authentication
azure_service = AzureOpenAIService(
    app_id="feedbackform", 
    token_counter_url="https://your-counter-app.azurewebsites.net",
    token_counter_resource_uri="api://counter-app-id"  # App ID URI from Step 3
)
```

### 2. Install required packages:

Add these to your requirements.txt:
```
azure-identity>=1.12.0
azure-core>=1.26.0
```

## Troubleshooting

### Common Issues

1. **Authentication failures**: Check that the managed identity has been assigned and that proper permissions are granted.

2. **Scope errors**: Ensure you're using the correct resource URI format (`api://application-id`).

3. **Deployment issues**: Restart the web apps after updating identities to ensure changes take effect.

### Logging

The TokenClient logs authentication errors. Check your application logs for:
- "Authentication error" messages 
- Failed HTTP requests with 401 or 403 status codes

## Local Development

For local development, you can authenticate using environment variables:

```bash
# Set environment variables for local testing
export AZURE_CLIENT_ID=<your-client-id>
export AZURE_TENANT_ID=<your-tenant-id>
export AZURE_CLIENT_SECRET=<your-client-secret>
```

The DefaultAzureCredential will automatically use these for authentication when running locally. 