import getpass
import sys
import warnings

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.access import ADMIN, administrators, authority_lock, seed_roles
from apps.accounts.models import Role, User
from apps.audit.models import AuditEvent


class Command(BaseCommand):
    help = "Interactively create the installation's initial administrator."

    def handle(self, **options):
        if administrators().exists():
            self.stdout.write("An active administrator already exists.")
            return
        if not sys.stdin.isatty():
            raise CommandError("Run setup_admin in an interactive local terminal.")
        try:
            username = User.normalize_username(input("Administrator username: ").strip())
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                password = getpass.getpass("Password: ")
                confirmed = getpass.getpass("Confirm password: ")
        except (EOFError, KeyboardInterrupt, getpass.GetPassWarning) as exc:
            raise CommandError("Administrator setup canceled.") from exc
        if password != confirmed or not password or len(password) > 256:
            raise CommandError("Passwords must match and contain 1 to 256 characters.")
        user = User(username=username)
        try:
            user.full_clean(exclude=["password"])
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        with transaction.atomic():
            authority_lock()
            if administrators().exists():
                raise CommandError("An active administrator already exists.")
            if User.objects.filter(username=username).exists():
                raise CommandError("This username is already in use.")
            seed_roles()
            user.set_password(password)
            user.save()
            user.groups.add(Role.objects.get(key=ADMIN).group)
            AuditEvent.objects.create(
                acting_user=user,
                action="ADMIN_BOOTSTRAPPED",
                resource_type="user",
                resource_id=str(user.pk),
            )
        self.stdout.write(
            self.style.SUCCESS("Administrator created. Sign in to configure the institution.")
        )
