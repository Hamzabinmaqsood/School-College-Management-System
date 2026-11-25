from rest_framework.exceptions import APIException
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .service import license_status


class LicenseWriteDenied(APIException):
    status_code = 403

    def __init__(self, state, feature=None):
        self.state = state
        self.feature = feature
        super().__init__("This operation requires a current subscription and a licensed feature.")


class LicensedBusinessWrites(BasePermission):
    """Add after RBAC on business views; keep export and recovery actions outside this gate."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        features = (
            view.get_license_features()
            if hasattr(view, "get_license_features")
            else (getattr(view, "license_feature", None),)
        )
        if not features or any(not feature for feature in features):
            raise LicenseWriteDenied("FEATURE_NOT_CONFIGURED")
        status = license_status(request)
        if not status["write_allowed"]:
            raise LicenseWriteDenied(status["status"])
        for feature in features:
            if feature not in status["license"]["features"]:
                raise LicenseWriteDenied("FEATURE_NOT_LICENSED", feature)
        return True
