"""
Repeatable local media persistence test.
Proves that announcement media uploads survive application restart/recreation
when backed by a persistent volume mount, and that ephemeral storage fails.
"""
import os
import io
import pytest
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.main import app
from backend.app.core.auth import create_user_session
from backend.app.models.user import User


def get_test_png_bytes() -> bytes:
    """Generate minimal valid PNG binary payload (magic bytes: \x89PNG\r\n\x1a\n)."""
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
        b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )


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
    from backend.app.core.config import settings
    monkeypatch.setattr(settings, "UPLOADS_DIR", str(persistent_volume_dir))

    # Also point FastAPI /uploads static mount to the persistent volume
    from starlette.staticfiles import StaticFiles
    mount_updated = False
    for route in app.routes:
        if getattr(route, "name", None) == "uploads":
            route.app = StaticFiles(directory=str(persistent_volume_dir))
            mount_updated = True
    if not mount_updated:
        app.mount("/uploads", StaticFiles(directory=str(persistent_volume_dir)), name="uploads")

    # 2. Container Instance 1: Authenticate Admin & Upload Media
    admin_user = db_session.query(User).filter(User.role == "org_admin").first()
    if not admin_user:
        admin_user = User(
            id="admin-persist-test",
            email="admin-persist@rvfitness.in",
            name="Persistence Admin",
            role="org_admin",
            is_active=True,
            hashed_password="hash",
        )
        db_session.add(admin_user)
        db_session.commit()

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
    # Simulates container restart / new deployment pod mounting the existing host volume
    client2 = TestClient(app)

    # Instance 2 must immediately serve the previously uploaded image without re-uploading
    fetch_res2 = client2.get(image_url)
    assert fetch_res2.status_code == 200, "Image failed to survive container recreation"
    assert fetch_res2.content == png_data
    assert fetch_res2.headers["content-type"] in ("image/png", "image/x-png")

    # 5. Negative Test: Simulate Ephemeral Storage Wipe (Volume Deleted)
    file_on_disk.unlink()  # File wiped due to ephemeral container destruction
    fetch_res3 = client2.get(image_url)
    assert fetch_res3.status_code == 404, "Ephemeral wipe should result in 404"
