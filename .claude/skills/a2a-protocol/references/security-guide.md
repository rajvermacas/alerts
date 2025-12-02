# A2A Protocol: Security Guide

## Table of Contents
1. [Authentication Methods](#authentication-methods)
2. [Authorization Patterns](#authorization-patterns)
3. [Security Best Practices](#security-best-practices)
4. [Production Checklist](#production-checklist)

## Authentication Methods

### Option 1: API Key (Simplest)

**Use when**: Internal agents, development, POC

```python
# Server side
@app.post("/a2a/message/send")
async def send_message(request: dict, x_api_key: str = Header(...)):
    if x_api_key != os.getenv("AGENT_API_KEY"):
        raise HTTPException(status_code=401, detail="Invalid API key")
    # Process request

# Client side
headers = {"x-api-key": "your-api-key-here"}
response = await client.post(endpoint, headers=headers, json=request)
```

**Best practices**:
- Store keys in environment variables, never in code
- Rotate keys regularly (every 90 days minimum)
- Use different keys per environment (dev/staging/prod)
- Implement rate limiting per key
- Log all authentication attempts

### Option 2: OAuth 2.0 (Recommended for Production)

**Use when**: External agents, multi-org collaboration, production systems

#### Client Credentials Flow (Service-to-Service)

```python
import httpx

async def get_access_token(client_id: str, client_secret: str, token_url: str):
    """Get OAuth 2.0 access token"""
    response = await httpx.AsyncClient().post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "agents:call"
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    response.raise_for_status()
    return response.json()["access_token"]

# Use token
access_token = await get_access_token(client_id, client_secret, token_url)
headers = {"Authorization": f"Bearer {access_token}"}
```

**Server-side token validation**:

```python
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Verify JWT bearer token"""
    try:
        token = credentials.credentials

        # Verify token signature and expiration
        payload = jwt.decode(
            token,
            os.getenv("JWT_PUBLIC_KEY"),
            algorithms=["RS256"],
            audience="your-api"
        )

        # Check scopes
        if "agents:call" not in payload.get("scope", "").split():
            raise HTTPException(status_code=403, detail="Insufficient scope")

        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/a2a/message/send")
async def send_message(request: dict, token_payload = Depends(verify_token)):
    # Process authenticated request
    pass
```

**Best practices**:
- **Token expiration**: < 15 minutes (best practice)
- **Refresh tokens**: Only if agents have persistent state
- **Scopes**: Use fine-grained scopes (agents:read, agents:write, agents:admin)
- **Key rotation**: Rotate JWT signing keys regularly

### Option 3: Mutual TLS (mTLS)

**Use when**: Highest security requirements, regulated environments

```python
import ssl
import httpx

# Create SSL context with client certificates
ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
ssl_context.load_cert_chain(
    certfile="client-cert.pem",
    keyfile="client-key.pem"
)
ssl_context.load_verify_locations("ca-cert.pem")

# Use with httpx
async with httpx.AsyncClient(verify=ssl_context) as client:
    response = await client.post(endpoint, json=request)
```

**Server configuration** (example with FastAPI + uvicorn):

```bash
uvicorn app:app \
    --ssl-keyfile=server-key.pem \
    --ssl-certfile=server-cert.pem \
    --ssl-ca-certs=ca-cert.pem \
    --ssl-cert-reqs=2  # Require client cert
```

**Best practices**:
- Use certificate pinning for known agents
- Automated certificate rotation (Let's Encrypt, cert-manager)
- Monitor certificate expiration
- Implement certificate revocation checking (CRL/OCSP)

## Authorization Patterns

### Role-Based Access Control (RBAC)

```python
from enum import Enum
from typing import Set

class AgentRole(Enum):
    ADMIN = "admin"
    ANALYST = "analyst"
    READ_ONLY = "read_only"

ROLE_PERMISSIONS = {
    AgentRole.ADMIN: {"agents:read", "agents:write", "agents:delete", "agents:admin"},
    AgentRole.ANALYST: {"agents:read", "agents:write"},
    AgentRole.READ_ONLY: {"agents:read"}
}

def check_permission(token_payload: dict, required_permission: str):
    """Check if token has required permission"""
    role = AgentRole(token_payload.get("role"))
    permissions = ROLE_PERMISSIONS.get(role, set())

    if required_permission not in permissions:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

@app.post("/a2a/message/send")
async def send_message(request: dict, token_payload = Depends(verify_token)):
    check_permission(token_payload, "agents:write")
    # Process request
```

### Attribute-Based Access Control (ABAC)

```python
def check_access(token_payload: dict, resource: dict, action: str):
    """
    More fine-grained access control based on attributes
    """
    # Agent can only access resources in their organization
    if token_payload.get("org_id") != resource.get("org_id"):
        raise HTTPException(status_code=403, detail="Cross-org access denied")

    # Agent can only perform actions during business hours
    from datetime import datetime
    hour = datetime.now().hour
    if not (9 <= hour < 18):
        raise HTTPException(status_code=403, detail="Outside business hours")

    # Additional attribute checks...
```

## Security Best Practices

### 1. Transport Security

**Always use HTTPS/TLS 1.3+**:

```python
# Force HTTPS in production
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

if os.getenv("ENVIRONMENT") == "production":
    app.add_middleware(HTTPSRedirectMiddleware)
```

**Strong cipher suites**:
- TLS_AES_256_GCM_SHA384
- TLS_CHACHA20_POLY1305_SHA256
- TLS_AES_128_GCM_SHA256

**Disable weak protocols**:
- No TLS 1.0, TLS 1.1
- No SSL 3.0, SSL 2.0

### 2. Input Validation

**Validate all incoming A2A messages**:

```python
from pydantic import BaseModel, validator

class A2AMessage(BaseModel):
    role: str
    parts: list

    @validator('role')
    def validate_role(cls, v):
        if v not in ['user', 'agent']:
            raise ValueError('Invalid role')
        return v

    @validator('parts')
    def validate_parts(cls, v):
        if not v or len(v) > 100:  # Prevent DoS
            raise ValueError('Invalid parts length')
        return v

@app.post("/a2a/message/send")
async def send_message(request: dict):
    try:
        message = A2AMessage(**request["params"]["message"])
    except ValidationError:
        raise HTTPException(status_code=400, detail="Invalid message format")
```

### 3. Rate Limiting

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/a2a/message/send")
@limiter.limit("100/minute")  # 100 requests per minute per IP
async def send_message(request: Request):
    # Process request
    pass
```

### 4. SSRF Protection

**Validate webhook URLs**:

```python
from urllib.parse import urlparse
import ipaddress

BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),      # Private
    ipaddress.ip_network("172.16.0.0/12"),   # Private
    ipaddress.ip_network("192.168.0.0/16"),  # Private
    ipaddress.ip_network("127.0.0.0/8"),     # Loopback
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
]

def validate_webhook_url(url: str):
    """Prevent SSRF attacks via webhook URLs"""
    parsed = urlparse(url)

    # Must be HTTPS
    if parsed.scheme != "https":
        raise ValueError("Webhook must use HTTPS")

    # Resolve IP
    import socket
    ip = socket.gethostbyname(parsed.hostname)
    ip_addr = ipaddress.ip_address(ip)

    # Check against blocked networks
    for network in BLOCKED_NETWORKS:
        if ip_addr in network:
            raise ValueError(f"Webhook URL resolves to blocked network: {network}")

    return url
```

### 5. Audit Logging

```python
import logging
import json
from datetime import datetime

audit_logger = logging.getLogger("audit")

def log_agent_call(
    caller_id: str,
    callee_id: str,
    action: str,
    success: bool,
    metadata: dict = None
):
    """Log all inter-agent communications for audit"""
    audit_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "caller": caller_id,
        "callee": callee_id,
        "action": action,
        "success": success,
        "metadata": metadata or {}
    }
    audit_logger.info(json.dumps(audit_entry))

@app.post("/a2a/message/send")
async def send_message(request: dict, token_payload = Depends(verify_token)):
    try:
        # Process request
        result = await process(request)

        # Log success
        log_agent_call(
            caller_id=token_payload["agent_id"],
            callee_id="self",
            action="message/send",
            success=True,
            metadata={"message_id": request.get("id")}
        )
        return result

    except Exception as e:
        # Log failure
        log_agent_call(
            caller_id=token_payload["agent_id"],
            callee_id="self",
            action="message/send",
            success=False,
            metadata={"error": str(e)}
        )
        raise
```

## Production Checklist

### Security Requirements

**Authentication & Authorization**:
- [ ] Implement OAuth 2.0 or mTLS (not just API keys)
- [ ] Token expiration < 15 minutes
- [ ] Implement proper scope/permission checking
- [ ] Rotate credentials regularly (90 days max)

**Transport Security**:
- [ ] HTTPS/TLS 1.3+ enforced
- [ ] Strong cipher suites only
- [ ] Valid SSL certificates (not self-signed in prod)
- [ ] HSTS headers enabled

**Input Validation**:
- [ ] Validate all incoming A2A messages
- [ ] Reject oversized payloads (prevent DoS)
- [ ] Sanitize all text inputs
- [ ] Validate webhook URLs (prevent SSRF)

**Rate Limiting & DoS Protection**:
- [ ] Rate limiting per API key/token (100-1000 req/min)
- [ ] Request size limits (< 10MB typically)
- [ ] Timeout limits (< 60s per request)
- [ ] Circuit breakers for cascading failure prevention

**Monitoring & Logging**:
- [ ] Audit log all agent-to-agent calls
- [ ] Log authentication failures
- [ ] Monitor for unusual access patterns
- [ ] Alert on repeated auth failures

**Data Protection**:
- [ ] Encrypt sensitive data at rest
- [ ] Never log credentials or tokens
- [ ] Implement data retention policies
- [ ] Comply with GDPR/CCPA if applicable

**Incident Response**:
- [ ] Have credential rotation playbook ready
- [ ] Monitor for security advisories
- [ ] Regular security audits
- [ ] Penetration testing before production

### Security Testing

```python
# Example security tests
import pytest

@pytest.mark.security
def test_rejects_expired_token(client):
    """Test that expired tokens are rejected"""
    expired_token = generate_expired_token()
    response = client.post(
        "/a2a/message/send",
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert response.status_code == 401

@pytest.mark.security
def test_rate_limiting(client):
    """Test rate limiting works"""
    for _ in range(150):  # Over limit
        response = client.post("/a2a/message/send", ...)

    assert response.status_code == 429  # Too Many Requests

@pytest.mark.security
def test_ssrf_protection(client):
    """Test SSRF protection on webhook URLs"""
    malicious_webhook = "http://127.0.0.1:6379/SET%20foo%20bar"

    response = client.post(
        "/a2a/message/send",
        json={"webhook": malicious_webhook}
    )
    assert response.status_code == 400  # Blocked
```

## Common Security Pitfalls

1. **Using API keys in production** - Use OAuth 2.0 or mTLS instead
2. **Long-lived tokens** - Keep expiration < 15 minutes
3. **No rate limiting** - Always implement rate limiting
4. **Accepting HTTP** - Force HTTPS in production
5. **Not validating webhook URLs** - Prevent SSRF attacks
6. **Logging sensitive data** - Never log tokens or credentials
7. **Weak RBAC** - Implement least-privilege access
8. **No audit trail** - Log all inter-agent communications
