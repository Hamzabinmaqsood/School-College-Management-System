from typing import ClassVar

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response

from apps.academics.access import RecordsView
from apps.accounts.authentication import audit

from .models import StudentDocument
from .serializers import DocumentFields, DocumentInput, GuardianChoice, LinkFields, PolicyFields
from .service import link_guardian, policy, store_document, student_for


class GuardiansForStudent(RecordsView):
    license_feature = "students"
    permission_map: ClassVar = {
        "list": ["accounts.view_student_details", "students.view_guardian"],
        "create": "accounts.manage_guardian_links",
        "partial_update": ["accounts.manage_guardian_links", "students.view_guardian"],
    }

    def list(self, request, student_id):
        rows = (
            student_for(student_id)
            .guardian_links.select_related("guardian")
            .order_by("-primary", "created_at")
        )
        page = self.paginate_queryset(rows)
        return self.get_paginated_response(LinkFields(page, many=True).data)

    def create(self, request, student_id):
        def save():
            student = student_for(student_id)
            form = GuardianChoice(data=request.data)
            form.is_valid(raise_exception=True)
            link = link_guardian(student, form.validated_data, request)
            return Response(LinkFields(link).data, status=201)

        return self.write(save)

    def partial_update(self, request, student_id, pk):
        def save():
            student = student_for(student_id)
            link = get_object_or_404(student.guardian_links.select_related("guardian"), pk=pk)
            form = LinkFields(link, data=request.data, partial=True)
            form.is_valid(raise_exception=True)
            if form.validated_data.get("primary"):
                student.guardian_links.exclude(pk=link.pk).filter(primary=True).update(
                    primary=False
                )
            form.save()
            audit(
                request,
                "GUARDIAN_LINK_UPDATED",
                "studentguardian",
                link,
                fields=sorted(form.validated_data),
            )
            return Response(form.data)

        return self.write(save)


class Documents(RecordsView):
    license_feature = "students"
    permission_map: ClassVar = {
        "list": "students.view_studentdocument",
        "download": "students.view_studentdocument",
        "preview": "students.view_studentdocument",
        "create": "students.add_studentdocument",
        "archive": "accounts.archive_student_documents",
        "kinds": "students.add_studentdocument",
    }

    def kinds(self, request):
        return Response(
            {
                "kinds": settings.STUDENT_DOCUMENT_KINDS,
                "max_bytes": settings.STUDENT_DOCUMENT_MAX_BYTES,
            }
        )

    def list(self, request, student_id):
        rows = (
            student_for(student_id)
            .documents.filter(archived_at__isnull=True)
            .defer("content")
            .order_by("-created_at")
        )
        page = self.paginate_queryset(rows)
        return self.get_paginated_response(DocumentFields(page, many=True).data)

    def create(self, request, student_id):
        def save():
            form = DocumentInput(data=request.data)
            form.is_valid(raise_exception=True)
            document = store_document(student_for(student_id), form.validated_data, request)
            return Response(DocumentFields(document).data, status=201)

        return self.write(save)

    @staticmethod
    def attachment(student_id, pk, **filters):
        return get_object_or_404(
            StudentDocument,
            pk=pk,
            student=student_for(student_id),
            archived_at__isnull=True,
            **filters,
        )

    def download(self, request, student_id, pk):
        document = self.attachment(student_id, pk)
        audit(request, "STUDENT_DOCUMENT_DOWNLOADED", "studentdocument", document)
        return self.content(document, "attachment")

    def preview(self, request, student_id, pk):
        return self.content(self.attachment(student_id, pk, kind="photo"), "inline")

    @staticmethod
    def content(document, disposition):
        return HttpResponse(
            bytes(document.content),
            content_type="image/png",
            headers={
                "Content-Disposition": f'{disposition}; filename="{document.pk}.png"',
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "sandbox; default-src 'none'",
            },
        )

    def archive(self, request, student_id, pk):
        def save():
            document = self.attachment(student_id, pk)
            document.archived_at = timezone.now()
            document.save(update_fields=["archived_at", "updated_at"])
            audit(request, "STUDENT_DOCUMENT_ARCHIVED", "studentdocument", document)
            return Response(status=204)

        return self.write(save)


class AdmissionPolicy(RecordsView):
    license_feature = "academics"
    permission_map: ClassVar = {
        "retrieve": "accounts.manage_admissions_policy",
        "partial_update": "accounts.manage_admissions_policy",
    }

    def retrieve(self, request):
        return Response(PolicyFields(policy(create=False)).data)

    def partial_update(self, request):
        def save():
            form = PolicyFields(policy(), data=request.data, partial=True)
            form.is_valid(raise_exception=True)
            record = form.save()
            audit(
                request,
                "ADMISSION_POLICY_UPDATED",
                "admissionnumberpolicy",
                record,
                fields=sorted(form.validated_data),
            )
            return Response(form.data)

        return self.write(save)
