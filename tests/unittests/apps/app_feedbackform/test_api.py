import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

class TestFeedbackFormAPI:
    """Unit tests for the Feedback Form API endpoints."""
    
    def test_read_root(self, test_app_client):
        """Test the root endpoint."""
        response = test_app_client.get("/")
        assert response.status_code == 200
        
        # Check response content
        data = response.json()
        assert data["app"] == "Feedback Form Processor"
        assert data["status"] == "running"
        assert data["auth_type"] == "Default Azure Credential"
        assert "queues" in data
        assert "in" in data["queues"]
        assert "out" in data["queues"]
    
    def test_health_check(self, test_app_client):
        """Test the health check endpoint."""
        response = test_app_client.get("/health")
        assert response.status_code == 200
        
        # Check response content
        data = response.json()
        assert data["status"] == "healthy"
        assert "service_bus_running" in data
        assert data["service_bus_running"] == True  # MockedHandler.running is set to True in conftest.py
    
    def test_lifespan_starts_service_bus_handler(self):
        """Test that the lifespan context manager starts the service bus handler."""
        with patch('common.service_bus.AsyncServiceBusHandler') as mock_handler_class, \
             patch('apps.app_feedbackform.services.data_processor.process_data'):
            
            # Configure the mock handler
            mock_handler = mock_handler_class.return_value
            mock_handler.running = False
            mock_handler.listen = AsyncMock()
            mock_handler.stop = AsyncMock()
            
            # Import the app after patching dependencies to trigger lifespan setup
            from apps.app_feedbackform.main import app, lifespan
            
            # Create TestClient which triggers the lifespan
            with TestClient(app) as client:
                # Just make a simple request to ensure app is running
                client.get("/")
            
            # Assert listen was called
            mock_handler.listen.assert_called_once()
    
    def test_lifespan_stops_service_bus_handler(self):
        """Test that the lifespan context manager stops the service bus handler."""
        with patch('common.service_bus.AsyncServiceBusHandler') as mock_handler_class, \
             patch('apps.app_feedbackform.services.data_processor.process_data'):
            
            # Configure the mock handler
            mock_handler = mock_handler_class.return_value
            mock_handler.running = True
            mock_handler.listen = AsyncMock()
            mock_handler.stop = AsyncMock()
            
            # Import the app after patching dependencies to trigger lifespan setup
            from apps.app_feedbackform.main import app
            
            # Create TestClient which triggers the lifespan
            with TestClient(app) as client:
                # Just make a simple request to ensure app is running
                client.get("/")
            
            # Assert stop was called when context manager exits
            mock_handler.stop.assert_called_once() 