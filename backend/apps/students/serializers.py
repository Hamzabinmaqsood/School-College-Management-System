from io import BytesIO

from django.conf import settings
from PIL import Image, ImageOps
from rest_framework import serializers

from apps.academics.access import school

from .models import AdmissionNumberPolicy, Guardian, Student, StudentDocument, StudentGuardian


class StudentFields(serializers.ModelSerializer):
    admission_number = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,47}$", required=False)

    class Meta:
        model = Student
        fields = (
            "id",
            "admission_number",
            "registration_number",
            "first_name",
            "last_name",
            "preferred_name",
            "birth_date",
            "gender",
            "phone",
            "address",
            "city",
            "province",
            "admission_date",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("status",)

    def validate_admission_number(self, number):
        return number.upper()

    def validate(self, attrs):
        birth = attrs.get("birth_date", getattr(self.instance, "birth_date", None))
        admitted = attrs.get("admission_date", getattr(self.instance, "admission_date", None))
        if birth and admitted and birth >= admitted:
            raise serializers.ValidationError({"birth_date": "Birth date must precede admission."})
        if (
            self.instance
            and "admission_date" in attrs
            and self.instance.enrollments.filter(enrollment_date__lt=admitted).exists()
        ):
            raise serializers.ValidationError(
                {"admission_date": "Admission date must precede or match all enrollments."}
            )
        return attrs


class GuardianFields(serializers.ModelSerializer):
    class Meta:
        model = Guardian
        fields = (
            "id",
            "full_name",
            "phone",
            "alternate_phone",
            "email",
            "address",
            "occupation",
            "created_at",
            "updated_at",
        )


class LinkFields(serializers.ModelSerializer):
    name = serializers.CharField(source="guardian.full_name", read_only=True)
    phone = serializers.CharField(source="guardian.phone", read_only=True)

    class Meta:
        model = StudentGuardian
        fields = (
            "id",
            "guardian",
            "name",
            "phone",
            "relationship",
            "primary",
            "emergency",
            "pickup",
        )

    def validate_guardian(self, guardian):
        if guardian.institution_id != school().pk or (
            self.instance and guardian.pk != self.instance.guardian_id
        ):
            raise serializers.ValidationError("Choose an existing guardian for this institution.")
        return guardian


class GuardianChoice(serializers.Serializer):
    guardian = serializers.PrimaryKeyRelatedField(queryset=Guardian.objects.all(), required=False)
    new_guardian = GuardianFields(required=False)
    relationship = serializers.CharField(max_length=64)
    primary = serializers.BooleanField(default=False)
    emergency = serializers.BooleanField(default=False)
    pickup = serializers.BooleanField(default=False)

    def validate(self, values):
        if bool(values.get("guardian")) == bool(values.get("new_guardian")):
            raise serializers.ValidationError(
                "Select an existing guardian or enter one new guardian."
            )
        if values.get("guardian") and values["guardian"].institution_id != school().pk:
            raise serializers.ValidationError("Select a guardian from this institution.")
        return values


class PolicyFields(serializers.ModelSerializer):
    prefix = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9-]{0,15}$", required=False)
    padding = serializers.IntegerField(min_value=1, max_value=12, required=False)

    class Meta:
        model = AdmissionNumberPolicy
        fields = ("prefix", "padding", "allow_unsectioned")

    def validate_prefix(self, prefix):
        return prefix.upper()


class DocumentInput(serializers.Serializer):
    kind = serializers.ChoiceField(choices=[])
    label = serializers.CharField(max_length=120)
    file = serializers.FileField(write_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kind"].choices = settings.STUDENT_DOCUMENT_KINDS

    def validate_file(self, upload):
        limit = settings.STUDENT_DOCUMENT_MAX_BYTES
        if upload.size > limit:
            raise serializers.ValidationError("The file exceeds the configured upload limit.")
        try:
            with Image.open(upload, formats=["PNG", "JPEG", "WEBP"]) as image:
                if image.width * image.height > 10_000_000 or getattr(image, "is_animated", False):
                    raise serializers.ValidationError("Upload a still image under 10 megapixels.")
                image.load()
                image = ImageOps.exif_transpose(image).convert("RGB")
                image.info.clear()
                image.thumbnail((2400, 2400))
                output = BytesIO()
                image.save(output, "PNG", optimize=True)
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise serializers.ValidationError("Upload a valid PNG, JPEG or WebP scan.") from exc
        content = output.getvalue()
        if len(content) > limit:
            raise serializers.ValidationError(
                "The normalized image exceeds the configured storage limit."
            )
        return content


class DocumentFields(serializers.ModelSerializer):
    class Meta:
        model = StudentDocument
        fields = ("id", "kind", "label", "size", "created_at")
