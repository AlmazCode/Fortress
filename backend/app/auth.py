"""One configured operator key protects all API data, not individual users."""
import hmac
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse


class ApiKeyAuth:
    def __init__(self, key: str):
        if not isinstance(key, str) or len(key) < 16 or not key.isascii() or any(c.isspace() for c in key):
            raise ValueError('Configure a nonempty ASCII operator key of at least 16 characters')
        self._key = key.encode('ascii')

    def __call__(self, request: Request):
        values = request.headers.getlist('x-api-key')
        supplied = values[0].encode('utf-8') if len(values) == 1 else b''
        if not hmac.compare_digest(supplied, self._key):
            raise HTTPException(401, 'Missing or invalid operator key.')


class ApiKeyMiddleware:
    """Runs before routing, body parsing, file access and dependency lookup."""
    def __init__(self, app, auth: ApiKeyAuth):
        self.app, self.auth = app, auth

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http' and scope.get('path', '').startswith('/api/'):
            try:
                self.auth(Request(scope))
            except HTTPException:
                response = JSONResponse({'error': {'code': 'invalid_key', 'message': 'Missing or invalid operator key.', 'status': 401}}, status_code=401, headers={'Cache-Control': 'private, no-store'})
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
