from io import BytesIO
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.http import HttpResponse
from PIL import Image, UnidentifiedImageError
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.licensing.models import InstallationIdentity

from .access import authority_lock, permission_codes, require
from .authentication import audit, branding
from .models import Institution


class ManagementView(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.user.password_change_required:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Change your password to continue.")


class InstitutionFields(serializers.ModelSerializer):
    logo = serializers.FileField(write_only=True, required=False)
    currency = serializers.RegexField(r"^[A-Z]{3}$", required=False)

    class Meta:
        model = Institution
        fields = (
            "id",
            "code",
            "name",
            "institution_type",
            "registration_number",
            "principal",
            "email",
            "phone",
            "address",
            "city",
            "province",
            "country",
            "currency",
            "timezone",
            "language",
            "logo",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise serializers.ValidationError("Choose a valid IANA timezone.") from exc
        return value

    def validate_logo(self, value):
        if value.size > 1024 * 1024:
            raise serializers.ValidationError("Logo must be at most 1 MB.")
        try:
            with Image.open(value, formats=["PNG", "JPEG", "WEBP"]) as image:
                if max(image.size) > 2048 or getattr(image, "is_animated", False):
                    raise serializers.ValidationError(
                        "Use a still image up to 2048 by 2048 pixels."
                    )
                output = BytesIO()
                image.load()
                clean = image.convert("RGBA")
                clean.info.clear()
                clean.thumbnail((512, 512))
                clean.save(output, format="PNG")
                return output.getvalue()
        except (OSError, ValueError, Image.DecompressionBombError, UnidentifiedImageError) as exc:
            raise serializers.ValidationError("Upload a valid PNG, JPEG or WebP image.") from exc


class InstitutionView(ManagementView):
    def get(self, request):
        if "accounts.change_institution" not in permission_codes(request.user):
            require(request.user, "accounts.view_institution")
        instance = Institution.objects.first()
        return Response(InstitutionFields(instance).data | branding(instance) if instance else None)

    @transaction.atomic
    def patch(self, request):
        authority_lock()
        require(request.user, "accounts.change_institution")
        instance = Institution.objects.first()
        serializer = InstitutionFields(
            instance=instance, data=request.data, partial=instance is not None
        )
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if "logo" in data:
            data["logo_png"] = data.pop("logo")
        if not instance:
            instance = Institution.objects.create(**data)
            InstallationIdentity.objects.create(institution=instance)
        else:
            for key, value in data.items():
                setattr(instance, key, value)
            instance.save(update_fields=[*data, "updated_at"])
        audit(request, "INSTITUTION_UPDATED", "institution", instance, fields=sorted(data))
        return Response(InstitutionFields(instance).data | branding(instance))


class LogoView(APIView):
    authentication_classes = ()
    permission_classes = ()

    def get(self, request):
        logo = Institution.objects.values_list("logo_png", flat=True).first()
        if not logo:
            return Response(status=404)
        return HttpResponse(
            bytes(logo),
            content_type="image/png",
            headers={
                "Cache-Control": "no-cache",
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": 'inline; filename="institution-logo.png"',
            },
        )
