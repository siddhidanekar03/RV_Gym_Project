"""
Comprehensive Media Persistence and Storage Contract Test Suite.
Validates:
1. Media directory resolution contract across environments.
2. Successful upload, disk persistence, and static retrieval.
3. Media persistence across application lifecycle recreation with shared volume mount.
4. Path traversal rejection in schemas and static file routes.
5. Upload validation boundaries (roles, CSRF, MIME, magic bytes, file size).
6. Fail-fast behavior when staging/production storage is unusable or inside source tree.
"""
import os
import io
import stat
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from starlette.staticfiles import StaticFiles

from backend.app.main import app
from backend.app.core.config import Settings, validate_production_security, settings
from backend.app.core.auth import create_user_session
from backend.app.core.security import hash_password
from backend.app.models.user import User
from backend.app.schemas.announcement import AnnouncementCreate, validate_safe_image_url


def get_test_png_bytes() -> bytes:
    """Generate minimal valid PNG binary payload (magic bytes: \x89PNG\r\n\x1a\n)."""
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
        b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def get_test_jpeg_bytes() -> bytes:
    """Generate minimal valid JPEG binary payload (magic bytes: \xff\xd8\xff)."""
    return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\xff\xd9"


def setup_test_admin(db_session) -> User:
    """Create or return an authorized org_admin user for upload tests."""
    admin = db_session.query(User).filter(User.email == "admin_media_test@rvfitness.in").first()
    if not admin:
        admin = User(
            id="admin-media-test-uid",
            email="admin_media_test@rvfitness.in",
            name="Media Admin",
            role="org_admin",
            is_active=True,
            hashed_password=hash_password("adminSecret123"),
        )
        db_session.add(admin)
        db_session.commit()
    return admin


def setup_test_member(db_session) -> User:
    """Create or return an unauthorized member user for permission tests."""
    member = db_session.query(User).filter(User.email == "member_media_test@rvfitness.in").first()
    if not member:
        member = User(
            id="member-media-test-uid",
            email="member_media_test@rvfitness.in",
            name="Regular Member",
            role="member",
            is_active=True,
            hashed_password=hash_password("memberSecret123"),
        )
        db_session.add(member)
        db_session.commit()
    return member


# ==============================================================================
# Requirement 1: Consistent Media Directory Resolution
# ==============================================================================

def test_media_directory_resolution_defaults(monkeypatch):
    """Verify default upload directory resolution in development and test environments."""
    s = Settings(ENVIRONMENT="development", UPLOADS_DIR=None)
    resolved = s.get_uploads_dir()
    assert os.path.isabs(resolved)
    assert resolved.endswith(os.path.join("backend", "uploads"))


def test_media_directory_resolution_explicit_custom(tmp_path):
    """Verify explicit custom UPLOADS_DIR resolution."""
    custom_dir = tmp_path / "custom_gym_uploads"
    s = Settings(ENVIRONMENT="development", UPLOADS_DIR=str(custom_dir))
    resolved = s.get_uploads_dir()
    assert resolved == os.path.abspath(str(custom_dir))


def test_media_directory_resolution_whitespace_stripping(tmp_path):
    """Verify whitespace is trimmed when resolving UPLOADS_DIR."""
    custom_dir = tmp_path / "trimmed_uploads"
    s = Settings(ENVIRONMENT="development", UPLOADS_DIR=f"  {str(custom_dir)}  ")
    resolved = s.get_uploads_dir()
    assert resolved == os.path.abspath(str(custom_dir))


# ==============================================================================
# Requirement 2 & 3: Upload, Retrieval & App Lifecycle Recreation Persistence
# ==============================================================================

def test_media_persistence_across_app_lifecycle_recreation(test_engine, db_session, monkeypatch, tmp_path):
    """
    Simulate container creation, image upload, container destruction,
    and subsequent container recreation retaining the same persistent volume directory.
    """
    from sqlalchemy.orm import sessionmaker
    from backend.app.core.database import get_db

    def override_get_db():
        session_factory = sessionmaker(
            bind=test_engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        session = session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    # 1. Simulate Persistent Host Volume Directory
    persistent_volume_dir = tmp_path / "persistent_uploads"
    announcements_dir = persistent_volume_dir / "announcements"
    announcements_dir.mkdir(parents=True, exist_ok=True)

    # Point application upload directory to the persistent volume via settings
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(persistent_volume_dir))

    # Point FastAPI /uploads static mount to the persistent volume
    for route in app.routes:
        if getattr(route, "name", None) == "uploads":
            route.app = StaticFiles(directory=str(persistent_volume_dir))

    # 2. Container Instance 1: Authenticate Admin & Upload Media
    admin_user = setup_test_admin(db_session)
    session, raw_token, csrf_token = create_user_session(db_session, admin_user)
    db_session.commit()

    client1 = TestClient(app)
    client1.cookies.set("rvf_session", raw_token)
    client1.cookies.set("rvf_csrf_token", csrf_token)

    png_data = get_test_png_bytes()
    upload_res = client1.post(
        "/api/announcements/upload-image",
        files={"file": ("banner.png", io.BytesIO(png_data), "image/png")},
        headers={
            "X-CSRF-Token": csrf_token,
            "Cookie": f"rvf_session={raw_token}; rvf_csrf_token={csrf_token}",
        },
    )
    assert upload_res.status_code == 200, f"Upload failed: {upload_res.text}"
    image_url = upload_res.json()["imageUrl"]
    filename = os.path.basename(image_url)

    # Verify physical file existence in persistent volume
    file_on_disk = announcements_dir / filename
    assert file_on_disk.is_file(), "Uploaded file missing from volume"
    assert file_on_disk.read_bytes() == png_data

    # Verify Instance 1 can serve the file
    fetch_res1 = client1.get(image_url)
    assert fetch_res1.status_code == 200
    assert fetch_res1.content == png_data

    # 3. Simulate Container Destruction (Teardown Instance 1)
    del client1

    # 4. Container Instance 2: Brand new TestClient attaching to the SAME persistent volume
    client2 = TestClient(app)

    # Instance 2 must immediately serve the previously uploaded image without re-uploading
    fetch_res2 = client2.get(image_url)
    assert fetch_res2.status_code == 200, "Image failed to survive container recreation"
    assert fetch_res2.content == png_data
    assert fetch_res2.headers["content-type"] in ("image/png", "image/x-png")

    # 5. Negative Test: Simulate Ephemeral Storage Wipe (Volume Deleted)
    file_on_disk.unlink()
    fetch_res3 = client2.get(image_url)
    assert fetch_res3.status_code == 404, "Ephemeral wipe should result in 404"


# ==============================================================================
# Requirement 4: Path Traversal Rejection
# ==============================================================================

def test_path_traversal_rejection_in_schema():
    """Verify that image_url validators strictly reject path traversal sequences and unsafe protocols."""
    # Valid relative URL
    assert validate_safe_image_url("/uploads/announcements/banner.png") == "/uploads/announcements/banner.png"
    # Valid absolute HTTPS URL
    assert validate_safe_image_url("https://cdn.rvfitness.in/banner.webp") == "https://cdn.rvfitness.in/banner.webp"

    # Path traversal attempts
    with pytest.raises(ValueError, match="Path traversal sequences are strictly forbidden"):
        validate_safe_image_url("/uploads/../backend/main.py")

    with pytest.raises(ValueError, match="Path traversal sequences are strictly forbidden"):
        validate_safe_image_url("/uploads/..\\secret.key")

    with pytest.raises(ValueError, match="Path traversal sequences are strictly forbidden"):
        validate_safe_image_url("/uploads/%2e%2e/etc/passwd")

    with pytest.raises(ValueError, match="Path traversal sequences are strictly forbidden"):
        validate_safe_image_url("/uploads/announcements/safe.png\0/etc/passwd")

    # Relative paths outside /uploads/
    with pytest.raises(ValueError, match="Relative image URLs must start with '/uploads/'"):
        validate_safe_image_url("/etc/passwd")

    with pytest.raises(ValueError, match="Relative image URLs must start with '/uploads/'"):
        validate_safe_image_url("/var/log/syslog")

    # Unsafe URI schemes
    with pytest.raises(ValueError, match="Unsafe image URL protocol provided"):
        validate_safe_image_url("javascript:alert('xss')")

    with pytest.raises(ValueError, match="Unsafe image URL protocol provided"):
        validate_safe_image_url("data:text/html;base64,PHNjcmlwdD4=")

    with pytest.raises(ValueError, match="Unsafe image URL protocol provided"):
        validate_safe_image_url("file:///etc/shadow")


def test_path_traversal_rejection_via_static_routes(tmp_path, monkeypatch):
    """Verify that Starlette StaticFiles rejects path traversal outside the mounted upload directory."""
    test_uploads = tmp_path / "static_uploads"
    announcements_dir = test_uploads / "announcements"
    announcements_dir.mkdir(parents=True, exist_ok=True)

    # Place a legitimate file and an external secret outside the uploads mount
    legit_file = announcements_dir / "legit.png"
    legit_file.write_bytes(get_test_png_bytes())

    outside_secret = tmp_path / "secret.env"
    outside_secret.write_text("SUPER_SECRET_KEY=confidential")

    monkeypatch.setattr(settings, "UPLOADS_DIR", str(test_uploads))
    for route in app.routes:
        if getattr(route, "name", None) == "uploads":
            route.app = StaticFiles(directory=str(test_uploads))

    client = TestClient(app)

    # Legitimate retrieval succeeds
    res_ok = client.get("/uploads/announcements/legit.png")
    assert res_ok.status_code == 200

    # Path traversal attempts to read external files must return 404 or reject access
    res_traversal1 = client.get("/uploads/../secret.env")
    assert res_traversal1.status_code in (404, 400)
    assert res_traversal1.text != outside_secret.read_text()

    res_traversal2 = client.get("/uploads/announcements/../../secret.env")
    assert res_traversal2.status_code in (404, 400)
    assert res_traversal2.text != outside_secret.read_text()

    res_traversal3 = client.get("/uploads/%2e%2e/secret.env")
    assert res_traversal3.status_code in (404, 400)
    assert res_traversal3.text != outside_secret.read_text()


# ==============================================================================
# Requirement 5: Upload Validation Boundaries and Access Control
# ==============================================================================

def test_upload_unauthenticated_rejection(client):
    """Verify that unauthenticated upload attempts return 401 Unauthorized."""
    res = client.post(
        "/api/announcements/upload-image",
        files={"file": ("test.png", io.BytesIO(get_test_png_bytes()), "image/png")},
    )
    assert res.status_code == 401


def test_upload_unauthorized_role_rejection(client, db_session):
    """Verify that regular members cannot upload announcement media (403 Forbidden)."""
    member = setup_test_member(db_session)
    session, raw_token, csrf_token = create_user_session(db_session, member)
    db_session.commit()

    res = client.post(
        "/api/announcements/upload-image",
        files={"file": ("test.png", io.BytesIO(get_test_png_bytes()), "image/png")},
        headers={
            "X-CSRF-Token": csrf_token,
            "Cookie": f"rvf_session={raw_token}; rvf_csrf_token={csrf_token}",
        },
    )
    assert res.status_code == 403


def test_upload_missing_csrf_rejection(client, db_session):
    """Verify that uploads without a valid CSRF token return 403 Forbidden."""
    admin = setup_test_admin(db_session)
    session, raw_token, csrf_token = create_user_session(db_session, admin)
    db_session.commit()

    # Omit X-CSRF-Token header
    res = client.post(
        "/api/announcements/upload-image",
        files={"file": ("test.png", io.BytesIO(get_test_png_bytes()), "image/png")},
        headers={
            "Cookie": f"rvf_session={raw_token}; rvf_csrf_token={csrf_token}",
        },
    )
    assert res.status_code == 403


def test_upload_disallowed_mime_type_rejection(client, db_session):
    """Verify that non-image MIME types (e.g. PDF, executable) return 400 Bad Request."""
    admin = setup_test_admin(db_session)
    session, raw_token, csrf_token = create_user_session(db_session, admin)
    db_session.commit()

    res = client.post(
        "/api/announcements/upload-image",
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.5 fake content"), "application/pdf")},
        headers={
            "X-CSRF-Token": csrf_token,
            "Cookie": f"rvf_session={raw_token}; rvf_csrf_token={csrf_token}",
        },
    )
    assert res.status_code == 400
    assert "Unsupported file type" in res.json()["detail"]


def test_upload_magic_bytes_mismatch_rejection(client, db_session):
    """Verify that files claiming to be image/png but lacking valid PNG magic bytes return 400."""
    admin = setup_test_admin(db_session)
    session, raw_token, csrf_token = create_user_session(db_session, admin)
    db_session.commit()

    fake_png = b"THIS IS NOT A PNG HEADER AT ALL, JUST PLAIN TEXT"
    res = client.post(
        "/api/announcements/upload-image",
        files={"file": ("fake.png", io.BytesIO(fake_png), "image/png")},
        headers={
            "X-CSRF-Token": csrf_token,
            "Cookie": f"rvf_session={raw_token}; rvf_csrf_token={csrf_token}",
        },
    )
    assert res.status_code == 400
    assert "does not match claimed image format" in res.json()["detail"]


def test_upload_oversized_file_rejection(client, db_session):
    """Verify that files exceeding MAX_IMAGE_SIZE_BYTES (5 MB) return 413 Content Too Large."""
    admin = setup_test_admin(db_session)
    session, raw_token, csrf_token = create_user_session(db_session, admin)
    db_session.commit()

    # Valid PNG header followed by 5 MB + 100 bytes of padding
    oversized = get_test_png_bytes() + (b"\x00" * (5 * 1024 * 1024 + 100))
    res = client.post(
        "/api/announcements/upload-image",
        files={"file": ("huge.png", io.BytesIO(oversized), "image/png")},
        headers={
            "X-CSRF-Token": csrf_token,
            "Cookie": f"rvf_session={raw_token}; rvf_csrf_token={csrf_token}",
        },
    )
    assert res.status_code == 413
    assert "exceeds maximum allowed size" in res.json()["detail"]


# ==============================================================================
# Requirement 6: Storage Failure Invariants in Staging / Production
# ==============================================================================

def test_staging_storage_inside_source_tree_rejection():
    """Verify that configuring UPLOADS_DIR inside the backend source tree raises a fatal ValueError in staging."""
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    source_tree_uploads = os.path.join(backend_dir, "uploads")

    bad_staging = Settings(
        ENVIRONMENT="staging",
        DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/rvfitness_staging",
        SECRET_KEY="s" * 64,
        QR_SIGNING_KEY="q" * 64,
        CORS_ORIGINS=["https://staging.rvfitness.in"],
        UPLOADS_DIR=source_tree_uploads,
    )
    with pytest.raises(ValueError, match="cannot be located inside the application source tree"):
        validate_production_security(bad_staging)


def test_staging_storage_unwritable_rejection(tmp_path):
    """Verify that pointing UPLOADS_DIR to an unwritable directory raises a fatal ValueError in staging."""
    # Create a regular file that prevents creating a directory with the same name
    blocker_file = tmp_path / "blocker.txt"
    blocker_file.write_text("blocking_file")

    bad_path = str(blocker_file / "unreachable_uploads")
    bad_staging = Settings(
        ENVIRONMENT="staging",
        DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/rvfitness_staging",
        SECRET_KEY="s" * 64,
        QR_SIGNING_KEY="q" * 64,
        CORS_ORIGINS=["https://staging.rvfitness.in"],
        UPLOADS_DIR=bad_path,
    )
    with pytest.raises(ValueError, match="unusable or not writable"):
        validate_production_security(bad_staging)


def test_staging_storage_valid_persistent_directory_succeeds(tmp_path):
    """Verify that a properly configured persistent storage directory passes staging security checks."""
    valid_storage = tmp_path / "valid_persistent_uploads"
    valid_storage.mkdir(parents=True, exist_ok=True)

    good_staging = Settings(
        ENVIRONMENT="staging",
        DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/rvfitness_staging",
        SECRET_KEY="s" * 64,
        QR_SIGNING_KEY="q" * 64,
        CORS_ORIGINS=["https://staging.rvfitness.in"],
        COOKIE_SECURE=True,
        UPLOADS_DIR=str(valid_storage),
        REDIS_URL="redis://127.0.0.1:6379/0",
    )
    validate_production_security(good_staging)
    assert os.path.isdir(os.path.join(str(valid_storage), "announcements"))
