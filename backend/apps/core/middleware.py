import logging
import uuid

logger = logging.getLogger("django.request")

SENSITIVE_KEYS = {"password", "token", "secret", "authorization", "license_private_key"}


class RequestAuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = str(uuid.uuid4())
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        logger.info(
            "request method=%s path=%s status=%s request_id=%s",
            request.method,
            request.path,
            response.status_code,
            request.request_id,
        )
        return response
