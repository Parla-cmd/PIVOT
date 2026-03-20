# PIVOT Remote Control API Implementation Plan

## Overview
Add a REST API server to PIVOT that allows remote clients to trigger intelligence modules programmatically with API key authentication.

## Scope
- Build REST endpoints for each PIVOT module (person_lookup, company_lookup, phone_lookup, etc.)
- Implement API key-based authentication
- Return results in JSON format
- Support async long-running scans
- Integrate with existing PIVOT CLI infrastructure

## Implementation Steps

### Phase 1: Core API Server Setup
1. **Create API framework**
   - Add FastAPI server (`api_server.py`) as alternative to Flask GUI
   - Implement standardized endpoint structure
   - Add request/response validation with Pydantic models

2. **Implement Authentication**
   - Create API key management system
   - Add key generation and validation logic
   - Store keys in `.env` or secure config
   - Implement Bearer token validation middleware

3. **Design API Endpoints**
   - `POST /api/v1/auth/generate-key` - Generate new API key
   - `POST /api/v1/scan/<module>` - Trigger a scan (person, company, phone, etc.)
   - `GET /api/v1/scans/<scan_id>` - Get scan status/results
   - `GET /api/v1/modules` - List available modules
   - `GET /api/v1/health` - Health check endpoint

### Phase 2: Module Integration
4. **Create API wrapper for modules**
   - Add `api_helpers.py` to adapt CLI modules for API use
   - Ensure consistent error handling across APIs
   - Support streaming long-running scans via Server-Sent Events (SSE)

5. **Handle async operations**
   - Implement scan job queue with unique IDs
   - Allow clients to poll for results via `GET /api/v1/scans/<scan_id>`
   - Return partial results for long-running operations

### Phase 3: Security & Documentation
6. **Add comprehensive documentation**
   - Write API documentation with examples
   - Document endpoint parameters and response formats
   - Add authentication setup instructions

7. **Add tests**
   - Test authenticated endpoint access
   - Test invalid API keys return 401
   - Test module execution through API

### Phase 4: Integration & Deployment
8. **Integrate with existing CLI**
   - Add `--api-mode` flag to main.py to start API server
   - Support both CLI and API modes
   - Keep existing GUI functional

9. **Configuration management**
   - Store API keys in `.env.api` or similar
   - Add startup scripts for API server
   - Document deployment setup

## Key Design Decisions
- **Framework**: FastAPI (async, better for APIs than Flask)
- **Authentication**: API keys in Authorization header (Bearer token)
- **Response format**: JSON with consistent structure
- **Error handling**: HTTP status codes + error messages
- **Async jobs**: Scan ID based polling for long operations

## Critical Files to Create/Modify
- `api_server.py` - Main FastAPI application
- `api_helpers.py` - Adapter functions for modules
- `api_auth.py` - Authentication and key management
- `requirements.txt` - Add FastAPI + uvicorn
- `.env.example` - Document API key format
- Main entry point update to support `--api` flag

## Success Criteria
✓ Remote client can authenticate with API key
✓ Can trigger any PIVOT module via API endpoint
✓ Results returned in JSON format
✓ Invalid keys rejected with 401 Unauthorized
✓ Long-running scans return immediately with scan ID
✓ Client can poll for results using scan ID
✓ All existing CLI/GUI functionality preserved
