---
name: firebase
description: |
  Firebase Management API integration with managed OAuth. Manage Firebase projects, web apps, Android apps, and iOS apps.
  Use this skill when users want to list Firebase projects, create or manage apps, get app configurations, or link Google Analytics.
  For other third party apps, use the api-gateway skill (https://clawhub.ai/byungkyu/api-gateway).
compatibility: Requires network access and valid Maton API key
metadata:
  author: maton
  version: "1.0"
  clawdbot:
    emoji: 🧠
    homepage: "https://maton.ai"
    requires:
      env:
        - MATON_API_KEY
---

# Firebase

Access the Firebase Management API with managed OAuth authentication. Manage Firebase projects and apps (Web, Android, iOS) with full CRUD operations.

## Quick Start

```bash
# List Firebase projects
python <<'EOF'
import urllib.request, os, json
req = urllib.request.Request('https://gateway.maton.ai/firebase/v1beta1/projects')
req.add_header('Authorization', f'Bearer {os.environ["MATON_API_KEY"]}')
print(json.dumps(json.load(urllib.request.urlopen(req)), indent=2))
EOF
```

## Base URL

```
https://gateway.maton.ai/firebase/{native-api-path}
```

Replace `{native-api-path}` with the actual Firebase Management API endpoint path. The gateway proxies requests to `firebase.googleapis.com` and automatically injects your OAuth token.

## Authentication

All requests require the Maton API key in the Authorization header:

```
Authorization: Bearer $MATON_API_KEY
```

**Environment Variable:** Set your API key as `MATON_API_KEY`:

```bash
export MATON_API_KEY="YOUR_API_KEY"
```

### Getting Your API Key

1. Sign in or create an account at [maton.ai](https://maton.ai)
2. Go to [maton.ai/settings](https://maton.ai/settings)
3. Copy your API key

## Connection Management

Manage your Firebase OAuth connections at `https://ctrl.maton.ai`.

### List Connections

```bash
python <<'EOF'
import urllib.request, os, json
req = urllib.request.Request('https://ctrl.maton.ai/connections?app=firebase&status=ACTIVE')
req.add_header('Authorization', f'Bearer {os.environ["MATON_API_KEY"]}')
print(json.dumps(json.load(urllib.request.urlopen(req)), indent=2))
EOF
```

### Create Connection

```bash
python <<'EOF'
import urllib.request, os, json
data = json.dumps({'app': 'firebase'}).encode()
req = urllib.request.Request('https://ctrl.maton.ai/connections', data=data, method='POST')
req.add_header('Authorization', f'Bearer {os.environ["MATON_API_KEY"]}')
req.add_header('Content-Type', 'application/json')
print(json.dumps(json.load(urllib.request.urlopen(req)), indent=2))
EOF
```

### Get Connection

```bash
python <<'EOF'
import urllib.request, os, json
req = urllib.request.Request('https://ctrl.maton.ai/connections/{connection_id}')
req.add_header('Authorization', f'Bearer {os.environ["MATON_API_KEY"]}')
print(json.dumps(json.load(urllib.request.urlopen(req)), indent=2))
EOF
```

**Response:**
```json
{
  "connection": {
    "connection_id": "21fd90f9-5935-43cd-b6c8-bde9d915ca80",
    "status": "ACTIVE",
    "creation_time": "2025-12-08T07:20:53.488460Z",
    "last_updated_time": "2026-01-31T20:03:32.593153Z",
    "url": "https://connect.maton.ai/?session_token=...",
    "app": "firebase",
    "metadata": {}
  }
}
```

Open the returned `url` in a browser to complete OAuth authorization.

### Delete Connection

```bash
python <<'EOF'
import urllib.request, os, json
req = urllib.request.Request('https://ctrl.maton.ai/connections/{connection_id}', method='DELETE')
req.add_header('Authorization', f'Bearer {os.environ["MATON_API_KEY"]}')
print(json.dumps(json.load(urllib.request.urlopen(req)), indent=2))
EOF
```

### Specifying Connection

If you have multiple Firebase connections, specify which one to use with the `Maton-Connection` header:

```bash
python <<'EOF'
import urllib.request, os, json
req = urllib.request.Request('https://gateway.maton.ai/firebase/v1beta1/projects')
req.add_header('Authorization', f'Bearer {os.environ["MATON_API_KEY"]}')
req.add_header('Maton-Connection', '21fd90f9-5935-43cd-b6c8-bde9d915ca80')
print(json.dumps(json.load(urllib.request.urlopen(req)), indent=2))
EOF
```

If omitted, the gateway uses the default (oldest) active connection.

## API Reference

### Project Operations

#### List Projects

List all Firebase projects accessible to the authenticated user.

```bash
GET /firebase/v1beta1/projects
```

**Response:**
```json
{
  "results": [
    {
      "projectId": "my-firebase-project",
      "projectNumber": "123456789",
      "displayName": "My Firebase Project",
      "name": "projects/my-firebase-project",
      "resources": {
        "hostingSite": "my-firebase-project"
      },
      "state": "ACTIVE",
      "etag": "1_bc06d94f-cf77-4689-be01-576702b23f6a"
    }
  ]
}
```

#### Get Project

```bash
GET /firebase/v1beta1/projects/{projectId}
```

#### Update Project

```bash
PATCH /firebase/v1beta1/projects/{projectId}?updateMask=displayName
Content-Type: application/json

{
  "displayName": "Updated Project Name"
}
```

#### List Available Projects

List Google Cloud projects that can have Firebase added.

```bash
GET /firebase/v1beta1/availableProjects
```

#### Add Firebase to Project

Add Firebase services to an existing Google Cloud project.

```bash
POST /firebase/v1beta1/projects/{projectId}:addFirebase
Content-Type: application/json

{}
```

This returns a long-running operation. Check the operation status with:

```bash
GET /firebase/v1beta1/operations/{operationId}
```

#### Get Admin SDK Config

```bash
GET /firebase/v1beta1/projects/{projectId}/adminSdkConfig
```

### Web App Operations

#### List Web Apps

```bash
GET /firebase/v1beta1/projects/{projectId}/webApps
```

#### Get Web App

```bash
GET /firebase/v1beta1/projects/{projectId}/webApps/{appId}
```

#### Create Web App

```bash
POST /firebase/v1beta1/projects/{projectId}/webApps
Content-Type: application/json

{
  "displayName": "My Web App"
}
```

#### Update Web App

```bash
PATCH /firebase/v1beta1/projects/{projectId}/webApps/{appId}?updateMask=displayName
Content-Type: application/json

{
  "displayName": "Updated Web App Name"
}
```

#### Get Web App Config

```bash
GET /firebase/v1beta1/projects/{projectId}/webApps/{appId}/config
```

**Response:**
```json
{
  "projectId": "my-firebase-project",
  "appId": "1:123456789:web:abc123",
  "apiKey": "AIzaSy...",
  "authDomain": "my-firebase-project.firebaseapp.com",
  "storageBucket": "my-firebase-project.firebasestorage.app",
  "messagingSenderId": "123456789",
  "measurementId": "G-XXXXXXXXXX",
  "projectNumber": "123456789"
}
```

#### Delete Web App

```bash
POST /firebase/v1beta1/projects/{projectId}/webApps/{appId}:remove
Content-Type: application/json

{
  "immediate": true
}
```

#### Undelete Web App

```bash
POST /firebase/v1beta1/projects/{projectId}/webApps/{appId}:undelete
Content-Type: application/json

{}
```

### Android App Operations

#### List Android Apps

```bash
GET /firebase/v1beta1/projects/{projectId}/androidApps
```

#### Get Android App

```bash
GET /firebase/v1beta1/projects/{projectId}/androidApps/{appId}
```

#### Create Android App

```bash
POST /firebase/v1beta1/projects/{projectId}/androidApps
Content-Type: application/json

{
  "displayName": "My Android App",
  "packageName": "com.example.myapp"
}
```

#### Update Android App

```bash
PATCH /firebase/v1beta1/projects/{projectId}/androidApps/{appId}?updateMask=displayName
Content-Type: application/json

{
  "displayName": "Updated Android App Name"
}
```

#### Get Android App Config

Returns the google-services.json configuration.

```bash
GET /firebase/v1beta1/projects/{projectId}/androidApps/{appId}/config
```

#### Delete Android App

```bash
POST /firebase/v1beta1/projects/{projectId}/androidApps/{appId}:remove
Content-Type: application/json

{
  "immediate": true
}
```

#### List SHA Certificates

```bash
GET /firebase/v1beta1/projects/{projectId}/androidApps/{appId}/sha
```

#### Add SHA Certificate

```bash
POST /firebase/v1beta1/projects/{projectId}/androidApps/{appId}/sha
Content-Type: application/json

{
  "shaHash": "1234567890ABCDEF1234567890ABCDEF12345678",
  "certType": "SHA_1"
}
```

#### Delete SHA Certificate

```bash
DELETE /firebase/v1beta1/projects/{projectId}/androidApps/{appId}/sha/{shaId}
```

### iOS App Operations

#### List iOS Apps

```bash
GET /firebase/v1beta1/projects/{projectId}/iosApps
```

#### Get iOS App

```bash
GET /firebase/v1beta1/projects/{projectId}/iosApps/{appId}
```

#### Create iOS App

```bash
POST /firebase/v1beta1/projects/{projectId}/iosApps
Content-Type: application/json

{
  "displayName": "My iOS App",
  "bundleId": "com.example.myapp"
}
```

#### Update iOS App

```bash
PATCH /firebase/v1beta1/projects/{projectId}/iosApps/{appId}?updateMask=displayName
Content-Type: application/json

{
  "displayName": "Updated iOS App Name"
}
```

#### Get iOS App Config

Returns the GoogleService-Info.plist configuration.

```bash
GET /firebase/v1beta1/projects/{projectId}/iosApps/{appId}/config
```

#### Delete iOS App

```bash
POST /firebase/v1beta1/projects/{projectId}/iosApps/{appId}:remove
Content-Type: application/json

{
  "immediate": true
}
```

### Google Analytics Operations

#### Get Analytics Details

```bash
GET /firebase/v1beta1/projects/{projectId}/analyticsDetails
```

#### Add Google Analytics

```bash
POST /firebase/v1beta1/projects/{projectId}:addGoogleAnalytics
Content-Type: application/json

{
  "analyticsAccountId": "123456789"
}
```

#### Remove Google Analytics

```bash
POST /firebase/v1beta1/projects/{projectId}:removeAnalytics
Content-Type: application/json

{
  "analyticsPropertyId": "properties/123456789"
}
```

### Available Locations

#### List Available Locations

```bash
GET /firebase/v1beta1/projects/{projectId}/availableLocations
```

## Pagination

Use `pageSize` and `pageToken` for pagination:

```bash
GET /firebase/v1beta1/projects?pageSize=10&pageToken={nextPageToken}
```

Response includes `nextPageToken` when more results exist:

```json
{
  "results": [...],
  "nextPageToken": "..."
}
```

## Code Examples

### JavaScript

```javascript
const response = await fetch(
  'https://gateway.maton.ai/firebase/v1beta1/projects',
  {
    headers: {
      'Authorization': `Bearer ${process.env.MATON_API_KEY}`
    }
  }
);
const data = await response.json();
```

### Python

```python
import os
import requests

response = requests.get(
    'https://gateway.maton.ai/firebase/v1beta1/projects',
    headers={'Authorization': f'Bearer {os.environ["MATON_API_KEY"]}'}
)
data = response.json()
```

### Create a Web App

```python
import os
import requests

response = requests.post(
    'https://gateway.maton.ai/firebase/v1beta1/projects/my-project/webApps',
    headers={
        'Authorization': f'Bearer {os.environ["MATON_API_KEY"]}',
        'Content-Type': 'application/json'
    },
    json={'displayName': 'My New Web App'}
)
data = response.json()
```

## Notes

- Project IDs are globally unique identifiers for Firebase projects
- App IDs follow the format `1:PROJECT_NUMBER:PLATFORM:HASH`
- PATCH requests require an `updateMask` query parameter specifying which fields to update (e.g., `?updateMask=displayName`)
- Create operations are asynchronous and return an Operation object
- Check operation status at `/firebase/v1beta1/operations/{operationId}`
- Deleted apps can be restored within 30 days using the undelete endpoint
- IMPORTANT: When using curl commands, use `curl -g` when URLs contain brackets to disable glob parsing
- IMPORTANT: When piping curl output to `jq` or other commands, environment variables like `$MATON_API_KEY` may not expand correctly in some shell environments

## Error Handling

| Status | Meaning |
|--------|---------|
| 400 | Missing Firebase connection |
| 401 | Invalid or missing Maton API key |
| 403 | Insufficient permissions for the requested operation |
| 404 | Project or app not found |
| 429 | Rate limited |
| 4xx/5xx | Passthrough error from Firebase API |

## Resources

- [Firebase Management API Overview](https://firebase.google.com/docs/projects/api/workflow_set-up-and-manage-project)
- [Firebase Management REST API Reference](https://firebase.google.com/docs/reference/firebase-management/rest)
- [Projects Resource](https://firebase.google.com/docs/reference/firebase-management/rest/v1beta1/projects)
- [Web Apps Resource](https://firebase.google.com/docs/reference/firebase-management/rest/v1beta1/projects.webApps)
- [Android Apps Resource](https://firebase.google.com/docs/reference/firebase-management/rest/v1beta1/projects.androidApps)
- [iOS Apps Resource](https://firebase.google.com/docs/reference/firebase-management/rest/v1beta1/projects.iosApps)
- [Maton Community](https://discord.com/invite/dBfFAcefs2)
- [Maton Support](mailto:support@maton.ai)
