from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    from apps.licensing.permissions import LicenseWriteDenied

    # This exception is emitted at the permission boundary before the view runs.
    # Keep its clock observation and audit record when writes are denied.
    if isinstance(exc, LicenseWriteDenied):
        return Response(
            {
                "code": "LICENSE_WRITE_DENIED",
                "message": str(exc.detail),
                "details": {"status": exc.state, "feature": exc.feature},
            },
            status=403,
        )
    response = exception_handler(exc, context)
    if response is None:
        return Response(
            {
                "code": "INTERNAL_ERROR",
                "message": "The request could not be completed.",
                "details": {},
            },
            status=500,
        )
    return Response(
        {
            "code": getattr(response, "status_code", "ERROR"),
            "message": "The request could not be completed.",
            "details": response.data,
        },
        status=response.status_code,
    )
