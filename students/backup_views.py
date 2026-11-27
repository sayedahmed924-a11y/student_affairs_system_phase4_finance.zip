import re
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.management import call_command, CommandError
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.conf import settings
from django.utils import timezone


def _superuser(user):
    return user.is_authenticated and user.is_active and user.is_superuser


def _backup_files():
    directory = Path(getattr(settings, "BACKUP_DIR", settings.BASE_DIR / "backups"))
    directory.mkdir(parents=True, exist_ok=True)
    allowed = re.compile(r"^student_affairs_\d{8}_\d{6}\.(?:dump|sqlite3)$")
    files = []
    for path in directory.iterdir():
        if path.is_file() and allowed.fullmatch(path.name):
            files.append({
                "name": path.name,
                "size": path.stat().st_size,
                "created": timezone.datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.get_current_timezone()),
            })
    return sorted(files, key=lambda item: item["created"], reverse=True)


@user_passes_test(_superuser, login_url="login")
def backup_dashboard(request):
    if request.method == "POST":
        try:
            call_command("backup_database")
            messages.success(request, "تم إنشاء نسخة احتياطية بنجاح.")
        except (CommandError, OSError, ValueError) as exc:
            messages.error(request, f"تعذر إنشاء النسخة الاحتياطية: {exc}")
        return redirect("students:backup_dashboard")
    return render(request, "students/backup_dashboard.html", {
        "backup_files": _backup_files(),
        "retention_days": 30,
    })


@user_passes_test(_superuser, login_url="login")
def download_backup(request, filename):
    if not re.fullmatch(r"student_affairs_\d{8}_\d{6}\.(?:dump|sqlite3)", filename):
        raise Http404
    directory = Path(getattr(settings, "BACKUP_DIR", settings.BASE_DIR / "backups")).resolve()
    path = (directory / filename).resolve()
    if path.parent != directory or not path.is_file():
        raise Http404
    return FileResponse(path.open("rb"), as_attachment=True, filename=filename)
