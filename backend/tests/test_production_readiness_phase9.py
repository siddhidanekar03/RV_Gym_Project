import os
import re
import pytest
from decimal import Decimal
from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.core.config import Settings, validate_production_security, settings
from backend.app.core.logging import StructuredFormatter, correlation_id_ctx
from backend.app.core.auth import get_client_ip
from backend.app.models.user import User
from backend.app.models.membership import Enrollment, MembershipPlan
from backend.app.models.billing import Invoice, Payment
from backend.app.services.billing_service import create_invoice_for_enrollment, generate_invoice_pdf
from backend.app.services.attendance_service import generate_member_qr_token, process_qr_checkin


# ==============================================================================
# 1. Production Configuration & Secrets Validation
# ==============================================================================

def test_production_secret_key_rejection():
    """Verify that placeholder or weak secret keys are rejected in production."""
    insecure_settings = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/rvfitness_prod",
        SECRET_KEY="change-this-to-a-secure-random-64-character-hex-string-in-production",
    )
    with pytest.raises(ValueError, match="SECRET_KEY must be a cryptographically secure random string"):
        validate_production_security(insecure_settings)


def test_production_sqlite_rejection():
    """Verify that SQLite database URL is strictly rejected in production."""
    with pytest.raises(ValueError, match="SQLite is strictly forbidden in production"):
        Settings(
            ENVIRONMENT="production",
            DATABASE_URL="sqlite:///./rvfitness_prod.db",
            SECRET_KEY="a" * 64,
        )


def test_production_wildcard_cors_rejection():
    """Verify that wildcard CORS origins are rejected in production."""
    wildcard_settings = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/rvfitness_prod",
        SECRET_KEY="a" * 64,
        CORS_ORIGINS=["*"],
    )
    with pytest.raises(ValueError, match="Wildcard CORS origin"):
        validate_production_security(wildcard_settings)


def test_production_weak_qr_key_rejection():
    """Verify that weak or placeholder dedicated QR signing keys are rejected in production."""
    weak_qr_settings = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/rvfitness_prod",
        SECRET_KEY="a" * 64,
        QR_SIGNING_KEY="change-this-short",
    )
    with pytest.raises(ValueError, match="QR_SIGNING_KEY must be a secure string"):
        validate_production_security(weak_qr_settings)


def test_production_disabled_cookie_secure_rejection():
    """Verify that explicitly disabling secure cookies in production raises a configuration error."""
    insecure_cookie_settings = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/rvfitness_prod",
        SECRET_KEY="a" * 64,
        COOKIE_SECURE=False,
    )
    with pytest.raises(ValueError, match="COOKIE_SECURE cannot be explicitly disabled"):
        validate_production_security(insecure_cookie_settings)


def test_valid_production_configuration_passes():
    """Verify that a compliant production configuration passes all security checks."""
    valid_settings = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/rvfitness_prod",
        SECRET_KEY="f" * 64,
        QR_SIGNING_KEY="e" * 64,
        CORS_ORIGINS=["https://rvfitness.in", "https://app.rvfitness.in"],
        COOKIE_SECURE=True,
    )
    validate_production_security(valid_settings)  # Should not raise


def test_staging_enforces_production_grade_security():
    """Verify that staging environment enforces the exact same strict security invariants."""
    # 1. Staging rejects SQLite
    with pytest.raises(ValueError, match="SQLite is strictly forbidden"):
        Settings(
            ENVIRONMENT="staging",
            DATABASE_URL="sqlite:///./rvfitness_staging.db",
            SECRET_KEY="a" * 64,
        )

    # 2. Staging rejects placeholder secret key
    weak_staging = Settings(
        ENVIRONMENT="staging",
        DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/rvfitness_staging",
        SECRET_KEY="change-this-placeholder-secret-key-that-is-long-enough",
    )
    with pytest.raises(ValueError, match="SECRET_KEY must be a cryptographically secure random string"):
        validate_production_security(weak_staging)

    # 3. Staging rejects wildcard CORS
    wildcard_staging = Settings(
        ENVIRONMENT="staging",
        DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/rvfitness_staging",
        SECRET_KEY="a" * 64,
        CORS_ORIGINS=["*"],
    )
    with pytest.raises(ValueError, match="Wildcard CORS origin"):
        validate_production_security(wildcard_staging)

    # 4. Valid staging passes and auto-enables secure cookies
    valid_staging = Settings(
        ENVIRONMENT="staging",
        DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/rvfitness_staging",
        SECRET_KEY="b" * 64,
        CORS_ORIGINS=["https://staging.rvfitness.in"],
    )
    validate_production_security(valid_staging)
    assert valid_staging.is_cookie_secure() is True


def test_csrf_cookie_name_divergence_rejected():
    """Verify that configuring a CSRF cookie name differing from rvf_csrf_token fails fast."""
    divergent_settings = Settings(
        ENVIRONMENT="staging",
        DATABASE_URL="postgresql://user:pass@127.0.0.1:5432/rvfitness_staging",
        SECRET_KEY="c" * 64,
        CSRF_COOKIE_NAME="custom_csrf_name",
    )
    with pytest.raises(ValueError, match="CSRF_COOKIE_NAME is configured as 'custom_csrf_name'"):
        validate_production_security(divergent_settings)


# ==============================================================================
# 2. HTTP Security Headers & Content Security Policy
# ==============================================================================

def test_production_http_security_headers(client: TestClient):
    """Verify defensive HTTP security headers are present on all API responses."""
    res = client.get("/api/health")
    assert res.status_code == 200
    headers = res.headers

    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"
    assert headers.get("x-xss-protection") == "1; mode=block"
    assert headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "default-src 'self'" in headers.get("content-security-policy", "")
    assert "frame-ancestors 'none'" in headers.get("content-security-policy", "")


def test_hsts_header_in_production(client: TestClient, monkeypatch):
    """Verify Strict-Transport-Security (HSTS) is attached in production environment."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    res = client.get("/api/health")
    assert "strict-transport-security" in res.headers
    assert "max-age=31536000" in res.headers["strict-transport-security"]


# ==============================================================================
# 3. Request Correlation IDs & Sensitive Data Redaction
# ==============================================================================

def test_correlation_id_middleware_generated(client: TestClient):
    """Verify incoming requests receive a correlation ID if none is supplied."""
    res = client.get("/api/health")
    assert res.status_code == 200
    corr_id = res.headers.get("x-correlation-id")
    assert corr_id is not None
    assert len(corr_id) >= 8


def test_correlation_id_middleware_preserved(client: TestClient):
    """Verify client-supplied correlation ID is propagated and reflected in the response."""
    custom_id = "test-corr-abc-12345"
    res = client.get("/api/health", headers={"X-Correlation-ID": custom_id})
    assert res.status_code == 200
    assert res.headers.get("x-correlation-id") == custom_id


def test_structured_log_sensitive_data_redaction():
    """Verify that credentials, tokens, session cookies, and sensitive metrics are redacted from logs."""
    formatter = StructuredFormatter()

    sample_log = (
        'User auth attempt with password="SuperSecretPassword123" and secret_key: MySuperSecretKey. '
        'Session token is session_token=token_abc_xyz. Cookie: rvf_session=session_cookie_secret; '
        'Recorded metrics: weight_kg=78.5 and body_fat_percentage=14.2'
    )
    redacted = formatter.redact(sample_log)

    assert "SuperSecretPassword123" not in redacted
    assert "[REDACTED]" in redacted
    assert "MySuperSecretKey" not in redacted
    assert "token_abc_xyz" not in redacted
    assert "session_cookie_secret" not in redacted
    assert "78.5" not in redacted
    assert "14.2" not in redacted


# ==============================================================================
# 4. Health and Readiness Endpoints
# ==============================================================================

def test_root_and_api_health_endpoints(client: TestClient):
    """Verify both /health and /api/health report 200 OK with connected database."""
    res_root = client.get("/health")
    assert res_root.status_code == 200
    assert res_root.json()["status"] == "healthy"
    assert res_root.json()["database"]["status"] == "connected"

    res_api = client.get("/api/health")
    assert res_api.status_code == 200
    assert res_api.json()["status"] == "healthy"


def test_root_and_api_readiness_probes(client: TestClient):
    """Verify both /ready and /api/ready report 200 OK for load balancers and orchestrators."""
    res_root = client.get("/ready")
    assert res_root.status_code == 200
    assert res_root.json()["status"] == "ready"

    res_api = client.get("/api/ready")
    assert res_api.status_code == 200
    assert res_api.json()["status"] == "ready"


# ==============================================================================
# 5. Reverse Proxy Client IP Resolution
# ==============================================================================

class DummyRequest:
    def __init__(self, client_host, forwarded_for=None):
        self.client = type("Client", (), {"host": client_host})()
        self.headers = {"x-forwarded-for": forwarded_for} if forwarded_for else {}


def test_client_ip_resolution_trusted_proxy(monkeypatch):
    """Verify that X-Forwarded-For is trusted when the request comes from a configured trusted proxy."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", ["127.0.0.1", "10.0.0.1"])

    req = DummyRequest(client_host="10.0.0.1", forwarded_for="203.0.113.45, 10.0.0.1")
    ip = get_client_ip(req)
    assert ip == "203.0.113.45"


def test_client_ip_resolution_untrusted_peer_ignored_in_production(monkeypatch):
    """Verify that X-Forwarded-For is ignored in production if the direct peer is not in TRUSTED_PROXIES."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", ["10.0.0.1"])

    # Malicious client connects directly from 198.51.100.22 with a spoofed X-Forwarded-For header
    req = DummyRequest(client_host="198.51.100.22", forwarded_for="1.1.1.1")
    ip = get_client_ip(req)
    assert ip == "198.51.100.22"  # Direct peer IP is retained; spoofed header is ignored


# ==============================================================================
# 6. Safe Error Responses
# ==============================================================================

def test_safe_404_error_response(client: TestClient):
    """Verify 404 responses return clean JSON without leaking stack traces or internal configuration."""
    res = client.get("/api/non-existent-endpoint-abc")
    assert res.status_code == 404
    data = res.json()
    assert "error" in data or "detail" in data
    assert "traceback" not in data
    assert "SELECT" not in str(data)


def test_safe_422_validation_error_response(client: TestClient):
    """Verify 422 validation errors provide field guidance without server internals."""
    res = client.post("/api/auth/register", json={"email": "invalid-email"})
    assert res.status_code == 422
    data = res.json()
    assert data["status_code"] == 422
    assert "details" in data
    assert "traceback" not in data


# ==============================================================================
# 7. Billing Invoice PDF Generation & Authorization
# ==============================================================================

def test_invoice_pdf_generation_content_and_format(db_session: Session):
    """Verify generate_invoice_pdf outputs a valid PDF starting with %PDF- and containing black-gold tokens."""
    # Create test member
    member = User(
        id="pdf_test_member",
        email="pdf_member@rvfitness.in",
        name="Prithviraj S.",
        phone="9876543210",
        role="member",
        branch_id="narsobawadi",
        membership_id="RV-2026-PDF",
        membership_status="active",
        hashed_password="dummy_password_hash",
        is_active=True,
    )
    plan = MembershipPlan(
        id="pdf_plan",
        name="Annual Championship",
        price=Decimal("12000.00"),
        billing_cycle="annually",
        duration_days=365,
        is_active=True,
    )
    enrollment = Enrollment(
        id="pdf_enrollment",
        branch_id="narsobawadi",
        name="Prithviraj S.",
        phone="9876543210",
        plan_id=plan.id,
        price=Decimal("12000.00"),
        status="approved",
        accepted_terms=True,
    )
    db_session.add_all([member, plan, enrollment])
    db_session.commit()

    invoice = create_invoice_for_enrollment(
        db=db_session,
        enrollment=enrollment,
        plan=plan,
        user_id=member.id,
        branch_id="narsobawadi",
    )
    db_session.commit()

    pdf_bytes = generate_invoice_pdf(invoice, db_session)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 500  # Non-trivial document generated


def test_invoice_pdf_download_endpoint_authorization(client: TestClient, db_session: Session):
    """Verify invoice PDF download endpoint enforces ownership and branch authorization."""
    # Create Member A and Member B
    member_a = User(
        id="pdf_user_a",
        email="user_a@rvfitness.in",
        name="Member Alpha",
        role="member",
        branch_id="narsobawadi",
        membership_status="active",
        hashed_password="hash",
        is_active=True,
    )
    member_b = User(
        id="pdf_user_b",
        email="user_b@rvfitness.in",
        name="Member Beta",
        role="member",
        branch_id="sangli",
        membership_status="active",
        hashed_password="hash",
        is_active=True,
    )
    plan = db_session.query(MembershipPlan).first()
    enrollment_a = Enrollment(
        id="pdf_enroll_a",
        branch_id="narsobawadi",
        name="Member Alpha",
        phone="9870000001",
        plan_id=plan.id if plan else "plan_1",
        price=Decimal("5000.00"),
        status="approved",
        accepted_terms=True,
    )
    db_session.add_all([member_a, member_b, enrollment_a])
    db_session.commit()

    invoice_a = Invoice(
        id="inv_pdf_a",
        invoice_number="INV-2026-99991",
        user_id=member_a.id,
        branch_id="narsobawadi",
        enrollment_id=enrollment_a.id,
        status="paid",
        subtotal=Decimal("5000.00"),
        tax=Decimal("0.00"),
        total_amount=Decimal("5000.00"),
        amount_paid=Decimal("5000.00"),
        balance_due=Decimal("0.00"),
        due_date=date.today() + timedelta(days=7),
    )
    db_session.add(invoice_a)
    db_session.commit()

    # 1. Unauthenticated request must return 401
    res_unauth = client.get(f"/api/billing/invoices/{invoice_a.id}/pdf")
    assert res_unauth.status_code == 401

    # 2. Member A (owner) can download their invoice PDF
    from backend.app.core.auth import create_user_session
    _, token_a, _ = create_user_session(db_session, member_a)
    client.cookies.set("rvf_session", token_a)

    res_owner = client.get(f"/api/billing/invoices/{invoice_a.id}/pdf")
    assert res_owner.status_code == 200
    assert res_owner.headers.get("content-type") == "application/pdf"
    assert res_owner.content.startswith(b"%PDF-")

    # 3. Member B attempting to download Member A's invoice PDF must return 403 Forbidden
    _, token_b, _ = create_user_session(db_session, member_b)
    client.cookies.set("rvf_session", token_b)

    res_cross = client.get(f"/api/billing/invoices/{invoice_a.id}/pdf")
    assert res_cross.status_code == 403
    assert "Access denied" in res_cross.json()["detail"]


# ==============================================================================
# 8. QR Token Dedicated Signing Key Configuration
# ==============================================================================

def test_qr_signing_key_dedicated_configuration(monkeypatch, db_session: Session):
    """Verify that setting QR_SIGNING_KEY signs and validates tokens with that dedicated key."""
    dedicated_key = "d" * 64
    monkeypatch.setattr(settings, "QR_SIGNING_KEY", dedicated_key)

    member = User(
        id="qr_key_member",
        email="qr_key@rvfitness.in",
        name="Key Test Member",
        role="member",
        branch_id="narsobawadi",
        membership_id="RV-QR-KEY",
        membership_status="active",
        valid_until=date.today() + timedelta(days=30),
        hashed_password="hash",
        is_active=True,
    )
    db_session.add(member)
    db_session.commit()

    # Generate token using dedicated key
    token, _, _ = generate_member_qr_token(member)

    # Process QR checkin successfully with dedicated key
    rec = process_qr_checkin(db=db_session, qr_token=token, branch_id="narsobawadi")
    assert rec is not None
    assert rec.user_id == member.id
