import os
import sqlite3
import subprocess
import tarfile
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone


class Command(BaseCommand):
    help = "Create verified database and media backups and prune expired files."

    def handle(self, *args, **options):
        backup_dir = Path(getattr(settings, "BACKUP_DIR", settings.BASE_DIR / "backups"))
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
        engine = connection.settings_dict["ENGINE"]
        db_target = None
        media_target = backup_dir / f"student_affairs_{stamp}_media.tar.gz"
        created = []

        try:
            if engine.endswith("postgresql"):
                db_target = backup_dir / f"student_affairs_{stamp}.dump"
                db = connection.settings_dict
                env = os.environ.copy()
                env["PGPASSWORD"] = db.get("PASSWORD", "")
                subprocess.run([
                    "pg_dump", "--format=custom", "--no-owner", "--no-privileges",
                    "--host", str(db.get("HOST") or "localhost"),
                    "--port", str(db.get("PORT") or "5432"),
                    "--username", str(db.get("USER") or ""),
                    "--dbname", str(db["NAME"]),
                    "--file", str(db_target),
                ], env=env, check=True, capture_output=True, text=True)
            elif engine.endswith("sqlite3"):
                source = connection.settings_dict["NAME"]
                if str(source) == ":memory:":
                    raise CommandError("لا يمكن إنشاء نسخة دائمة من قاعدة SQLite الموجودة في الذاكرة.")
                db_target = backup_dir / f"student_affairs_{stamp}.sqlite3"
                connection.ensure_connection()
                destination = sqlite3.connect(str(db_target))
                try:
                    connection.connection.backup(destination)
                finally:
                    destination.close()
            else:
                raise CommandError(f"محرك قاعدة البيانات غير مدعوم: {engine}")

            created.append(db_target)
            if not db_target.exists() or db_target.stat().st_size == 0:
                raise CommandError("ملف قاعدة البيانات الاحتياطي فارغ.")
            os.chmod(db_target, 0o600)

            if engine.endswith("postgresql"):
                subprocess.run(
                    ["pg_restore", "--list", str(db_target)],
                    check=True, capture_output=True, text=True,
                )
            else:
                check_db = sqlite3.connect(str(db_target))
                try:
                    integrity = check_db.execute("PRAGMA integrity_check").fetchone()[0]
                finally:
                    check_db.close()
                if integrity != "ok":
                    raise CommandError(f"فشل فحص سلامة نسخة SQLite: {integrity}")

            media_root = Path(settings.MEDIA_ROOT)
            media_root.mkdir(parents=True, exist_ok=True)
            with tarfile.open(media_target, "w:gz", compresslevel=6) as archive:
                for item in sorted(media_root.rglob("*")):
                    if item.is_symlink():
                        raise CommandError(f"يوجد رابط رمزي داخل مجلد media ولا يمكن نسخه بأمان: {item}")
                    archive.add(
                        item,
                        arcname=item.relative_to(media_root).as_posix(),
                        recursive=False,
                    )
            created.append(media_target)
            os.chmod(media_target, 0o600)

            with tarfile.open(media_target, "r:gz") as archive:
                for member in archive.getmembers():
                    if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                        raise CommandError("أرشيف ملفات media يحتوي على نوع ملف غير مسموح.")
                    if member.isfile():
                        stream = archive.extractfile(member)
                        if stream is None:
                            raise CommandError("تعذر قراءة أحد ملفات أرشيف media.")
                        with stream:
                            while stream.read(1024 * 1024):
                                pass

            retention_days = max(1, int(os.getenv("BACKUP_RETENTION_DAYS", "30")))
            cutoff = timezone.now() - timedelta(days=retention_days)
            removed = 0
            for old in backup_dir.iterdir():
                if old.is_file() and old.name.startswith("student_affairs_"):
                    if timezone.datetime.fromtimestamp(
                        old.stat().st_mtime, tz=timezone.get_current_timezone()
                    ) < cutoff:
                        old.unlink()
                        removed += 1

            self.stdout.write(self.style.SUCCESS(
                f"تم إنشاء نسخة قاعدة البيانات {db_target.name} ونسخة الملفات {media_target.name}. "
                f"النسخ القديمة المحذوفة: {removed}"
            ))
        except FileNotFoundError as exc:
            for path in created:
                path.unlink(missing_ok=True)
            if db_target and db_target.exists():
                db_target.unlink(missing_ok=True)
            media_target.unlink(missing_ok=True)
            raise CommandError("أداة pg_dump أو pg_restore غير موجودة. ثبّت postgresql-client-16 داخل صورة الخادم.") from exc
        except subprocess.CalledProcessError as exc:
            for path in created:
                path.unlink(missing_ok=True)
            if db_target and db_target.exists():
                db_target.unlink(missing_ok=True)
            media_target.unlink(missing_ok=True)
            raise CommandError(f"فشل إنشاء أو فحص نسخة PostgreSQL: {exc.stderr or exc}") from exc
        except Exception:
            for path in created:
                path.unlink(missing_ok=True)
            if db_target and db_target.exists():
                db_target.unlink(missing_ok=True)
            media_target.unlink(missing_ok=True)
            raise
