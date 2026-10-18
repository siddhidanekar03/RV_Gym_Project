# Membership Enrollment Approval and Activation Workflow

## 1. Executive Summary

This document details the architecture, design decisions, data model, state transitions, security controls, and automated verification for the Membership Enrollment Approval and Activation Workflow in RVFitness.

The workflow provides complete end-to-end synchronization between member self-service enrollment, gym owner and branch manager queue management, front-desk offline payment processing, invoice generation, member audit logging, and dynamic member keycard visualization.

---

## 2. Root Cause Analysis

Prior to this implementation, when a prospective or registered member selected a membership plan and submitted an enrollment application:

1. **Missing Management Queue**: The application was inserted into the `enrollments` table with status `pending_verification`, but no queue or moderation dashboard existed for the gym owner (`org_admin`) or branch managers (`manager`). The frontend only displayed an administrative placeholder without any approval actions.
2. **Missing Approval/Rejection Endpoints**: The backend provided no API routes or service functions to review, approve, or reject enrollment applications.
3. **Decoupled User Identity**: The `enrollments` table lacked a `user_id` foreign key. It stored only raw strings (`name`, `email`, `phone`). Without a relational link between `enrollments` and `users`, the system could not reliably determine which member account to update when an application was approved.
4. **Static Keycard State**: The `/auth/me` endpoint evaluated member status solely from `User.membership_status` and `User.membership_plan_id`. Because the enrollment was never processed, `User.membership_status` remained `pending` and `User.membership_plan_id` remained `None`, causing the 3D member keycard to display `Trial / Awaiting Activation` indefinitely.
5. **Decoupled Invoice and Billing Lifecycle**: An invoice was generated with `balance_due = price`, but there was no mechanism linking payment recording on that invoice back to enrollment status activation.

---

## 3. Architecture and Data Model Changes

### 3.1 Database Migration (009_enrollment_workflow.py)

Alembic migration [009_enrollment_workflow.py](file:///d:/RV_Gym_Project/backend/alembic/versions/009_enrollment_workflow.py) was implemented and applied to the database schema:

- **`enrollments.user_id`**: Added `String(36)`, foreign key to `users.id` with `ondelete="SET NULL"`, indexed for lookup performance.
- **`enrollments.rejection_reason`**: Added `Text`, nullable, storing the mandatory reason provided by the owner or manager upon application rejection.
- **Data Backfill**: Existing historical enrollment rows were backfilled by linking `enrollments.user_id` to `users.id` using case-insensitive matching on `enrollments.email == users.email`, and secondary correlation via `invoices.user_id`.

### 3.2 SQLAlchemy Model Enhancements

In [backend/app/models/membership.py](file:///d:/RV_Gym_Project/backend/app/models/membership.py):
- `Enrollment.user_id`: Defined as `Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)`.
- `Enrollment.rejection_reason`: Defined as `Mapped[Optional[str]] = mapped_column(Text, nullable=True)`.
- `Enrollment.user`: Established `relationship("User", foreign_keys=[user_id])`.
- `Enrollment.initial_invoice`: Established `relationship("Invoice", back_populates="enrollment", uselist=False)`.

---

## 4. Enrollment State Machine

The workflow enforces a strict four-state finite state machine:

```
                  [ Member Submits Enrollment ]
                                |
                                v
                     +----------------------+
                     | pending_verification |
                     +----------------------+
                                |
             +------------------+------------------+
             |                                     |
    [ Owner Approves                      [ Owner Approves
      WITHOUT Payment ]                     WITH Full Payment ]
             |                                     |
             v                                     v
    +-----------------+                     +-------------+
    | payment_pending |                     |   active    |
    +-----------------+                     +-------------+
             |                                     ^
             | [ Desk Payment Recorded via         |
             |   Billing or Second Approval ]      |
             +-------------------------------------+
             |
             +--------> [ Owner Rejects ] --------> +------------+
                                                    |  rejected  |
                                                    +------------+
```

### 4.1 State Definitions

| State | Enrollment Status | User Membership Status | Invoice Status | Keycard Plan Label | Keycard Expiration Date |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Initial Registration | None | `pending` | None | `Trial / Awaiting Activation` | `Pending Activation` |
| Application Submitted | `pending_verification` | `pending` | `unpaid` | `<Plan Name> (Pending Verification)` | `Pending Desk Verification` |
| Approved (No Payment) | `payment_pending` | `approved` | `unpaid` | `<Plan Name> (Awaiting Payment)` | `Awaiting Desk Payment` |
| Approved (Full Payment) | `active` | `active` | `paid` | `<Plan Name>` | Actual Expiration Date (e.g. `January 14, 2027`) |
| Rejected | `rejected` | `rejected` | `void` | `<Plan Name> (Rejected)` | `Application Rejected` |

### 4.2 Idempotency and State Transition Invariants

1. **Active Guard**: An application in `active` status cannot be approved or rejected again. Subsequent approval requests return HTTP 400 Bad Request (`Enrollment application is already approved and activated.`).
2. **Rejection Guard**: An application in `rejected` status cannot be approved or activated. It returns HTTP 400 Bad Request (`Cannot approve a rejected enrollment application. The member must submit a new request.`).
3. **Payment Pending Idempotency**: An application in `payment_pending` status cannot be re-approved without payment. Calling approve with `record_payment=False` returns HTTP 400 Bad Request (`Enrollment application is already approved and awaiting payment.`). Calling approve with `record_payment=True` completes payment and transitions the application to `active`.
4. **Concurrency and Row Locking**: All approval and rejection operations acquire row locks via `.with_for_update()` on both the `Enrollment` record and the associated `Invoice` record before evaluating state and applying mutations.
5. **Invoice Voiding on Rejection**: When an application is rejected, its unpaid initial invoice is transitioned to `void`, preventing phantom accounts receivable from appearing in financial reports.
6. **Automatic Activation on External Invoice Payment**: If a member application is in `payment_pending` status and the front desk records payment directly via the Billing module (`record_offline_payment`), a post-payment hook automatically activates the enrollment, sets user status to `active`, and records the `MembershipChange` audit log.

---

## 5. API Reference

### 5.1 Owner and Manager Endpoints

#### GET `/api/v1/owner/enrollments`
Lists enrollment requests scoped by caller permissions and optional query parameters.
- **Authorization**: `org_admin`, `admin`, `branch_manager`, `manager`.
- **Query Parameters**:
  - `status`: `all` | `pending` | `payment_pending` | `active` | `rejected` (default: `pending`).
  - `branch_id`: Branch filter (ignored for branch managers; automatically enforced).
  - `search`: Case-insensitive search on member name, email, or phone.
- **Response**: `EnrollmentListResponse` containing `enrollments`, `totalCount`, `pendingCount`, `paymentPendingCount`.

#### GET `/api/v1/owner/enrollments/{enrollment_id}`
Retrieves detailed metadata for a single enrollment request.
- **Authorization**: `org_admin`, `admin`, `branch_manager`, `manager`.
- **Branch Scope**: Enforces branch isolation for branch managers. Returns HTTP 403 if unauthorized.
- **Response**: `EnrollmentResponse`.

#### POST `/api/v1/owner/enrollments/{enrollment_id}/approve`
Approves an enrollment request with optional immediate front-desk payment recording.
- **Authorization**: `org_admin`, `admin`, `branch_manager`, `manager`.
- **Headers**: Requires valid session cookie (`rvf_session`) and CSRF token (`x-csrf-token`).
- **Request Body**:
  ```json
  {
    "recordPayment": true,
    "paymentMethod": "cash",
    "paymentAmount": 4000.00,
    "referenceNumber": "DESK-CASH-001",
    "notes": "Full fee received at Narsobawadi desk"
  }
  ```
- **Response**: `EnrollmentResponse` with updated status (`active` or `payment_pending`).

#### POST `/api/v1/owner/enrollments/{enrollment_id}/reject`
Rejects an enrollment application with mandatory audit reason.
- **Authorization**: `org_admin`, `admin`, `branch_manager`, `manager`.
- **Headers**: Requires valid session cookie (`rvf_session`) and CSRF token (`x-csrf-token`).
- **Request Body**:
  ```json
  {
    "reason": "Doctor medical certificate required prior to heavy training enrollment.",
    "notes": "Applicant notified by phone."
  }
  ```
- **Response**: `EnrollmentResponse` with status `rejected` and voided invoice.

### 5.2 Member Self-Service Endpoints

#### POST `/api/v1/memberships/enroll`
Submits a new membership enrollment request. Automatically associates `user_id` when submitted by an authenticated member, and sets `branch_id` to the requested gym location.
- **Status Code**: HTTP 201 Created.
- **Response**: `EnrollmentResponse` with initial invoice metadata.

#### GET `/api/v1/memberships/my-enrollment`
Returns the caller's most recent enrollment application with real-time status and balance.
- **Authorization**: Authenticated member.
- **Response**: `MyEnrollmentResponse`.

#### GET `/api/v1/auth/me`
Returns the authenticated user's authoritative profile, dynamic keycard status, plan label, and validUntil timestamp.

---

## 6. Authorization and Branch Isolation Rules

The system enforces multi-tier access control:

1. **Platform Admin and Gym Owner (`org_admin`, `admin`)**:
   - Access to all enrollment applications across all branches.
   - Authorized to approve, reject, and record payments for any branch.
2. **Branch Managers (`branch_manager`, `manager`)**:
   - Queue is strictly scoped to the manager's assigned branch (`Branch.id == manager.branch_id`).
   - Cross-branch approval attempts are rejected with HTTP 403 Forbidden (`Access denied: You are not authorized to approve applications for branch '<branch_id>'.`).
   - Cross-branch rejection attempts are rejected with HTTP 403 Forbidden (`Access denied: You are not authorized to reject applications for branch '<branch_id>'.`).
3. **Trainers (`trainer`) and Members (`member`)**:
   - Access to owner enrollment queue returns HTTP 403 Forbidden.
   - Approval and rejection mutation endpoints return HTTP 403 Forbidden.
4. **Unauthenticated Callers**:
   - Return HTTP 401 Unauthorized (`Authentication required. Missing session credentials.`).

---

## 7. Frontend User Experience

### 7.1 Owner Management Desk (`GymOwnerPanel.jsx`)
- **Membership Requests Tab**: Dedicated queue table displaying reference ID, applicant name, contact details, requested plan, branch, enrollment timestamp, balance due, and status badge.
- **Queue Filters**: Quick filter buttons for `Pending Verification`, `Payment Pending`, `Active`, `Rejected`, and `All Applications`.
- **Search Bar**: Real-time filtering by applicant name, email, or telephone.
- **Overview Card and Shortcut**: Owner dashboard displays a pending enrollment stat badge with one-click navigation to the queue.
- **Approval Modal**: Allows owner/manager to either approve directly with immediate payment (cash, UPI, POS card) or approve without payment awaiting desk collection.
- **Rejection Modal**: Requires explicit rejection reason (minimum 2 characters, maximum 500 characters) before submission.
- **Application Detail Modal**: Complete breakdown of application timeline, branch location, invoice details, and audit history.

### 7.2 Member Dashboard and 3D Keycard (`MemberDashboard.jsx`)
- **Authoritative Status Banner**: Dynamically informs the member of their exact enrollment stage:
  - `pending_verification`: Displays pending notice with reference ID and front-desk verification instructions.
  - `payment_pending`: Displays payment instructions with amount due and accepted desk payment methods.
  - `active`: Displays confirmed membership banner with expiration date and renewal countdown.
  - `rejected`: Displays rejection notice with the specific reason recorded by management.
- **3D Member Keycard (`MembershipCard3D.jsx`)**: Synchronized in real time with backend authoritative state, eliminating the stale `Trial / Awaiting Activation` view without requiring browser re-login.

---

## 8. Verification and Test Results

### 8.1 Automated Test Suite (`backend/tests/test_enrollment_workflow.py`)

A comprehensive 13-test automated test suite was developed and verified:

```
backend/tests/test_enrollment_workflow.py::test_member_enrollment_creation_and_persistence PASSED
backend/tests/test_enrollment_workflow.py::test_owner_queue_returns_pending_request PASSED
backend/tests/test_enrollment_workflow.py::test_request_visibility_across_branches PASSED
backend/tests/test_unauthorized_users_receive_401_or_403 PASSED
backend/tests/test_enrollment_workflow.py::test_successful_approval_with_desk_payment_activates_membership PASSED
backend/tests/test_enrollment_workflow.py::test_rejection_preserves_history_and_does_not_activate PASSED
backend/tests/test_enrollment_workflow.py::test_approval_without_payment_leaves_membership_inactive PASSED
backend/tests/test_offline_payment_confirmation_activates_membership PASSED
backend/tests/test_repeated_approval_rejected PASSED
backend/tests/test_concurrent_approval_idempotency_protection PASSED
backend/tests/test_member_portal_reflects_authoritative_status_and_expiration PASSED
backend/tests/test_member_keycard_reflects_authoritative_status_and_expiration PASSED
backend/tests/test_branch_manager_cross_branch_approval_prevented PASSED

====================== 13 passed, 38 warnings in 22.76s =======================
```

### 8.2 Regression Test Suite

All existing authentication, billing, and owner management tests were executed to ensure zero regressions:

```
backend/tests/test_auth.py: 5 tests PASSED
backend/tests/test_billing.py: 5 tests PASSED
backend/tests/test_owner_management_and_auth_fixes.py: 15 tests PASSED

====================== 25 passed, 17 warnings in 21.19s =======================
```

### 8.3 Live Staging Verification (`http://127.0.0.1:18000`)

The entire lifecycle was verified directly against the live staging container (`rvfitness_staging_app` backed by PostgreSQL and Redis):

1. **Member Enrollment**: Prospective member registered and submitted enrollment request for the Monthly plan. Keycard updated immediately from `Trial / Awaiting Activation` to `Monthly (Pending Verification)` with status `Pending Desk Verification`.
2. **Owner Queue**: Logged in as `owner@rvfitness.in`. Verified submitted application appeared in `GET /api/owner/enrollments?status=pending` with full member details.
3. **Approval with Desk Payment**: Owner approved request with cash payment. Enrollment transitioned to `active` with zero balance. Member keycard updated immediately to `Monthly` with validity date `November 15, 2026` and status `Active`.
4. **Idempotency Guard**: Repeat approval call on the active enrollment returned HTTP 400 Bad Request (`Enrollment application is already approved and activated.`).
5. **Rejection Lifecycle**: Second candidate submitted application. Owner rejected application with reason: `Doctor medical clearance required before joining`. Enrollment transitioned to `rejected`, invoice was voided, keycard displayed `Monthly (Rejected) | Application Rejected`, and attempt to approve returned HTTP 400 Bad Request.
6. **Payment Pending to Active Lifecycle**: Third candidate submitted application. Owner approved without payment. Application transitioned to `payment_pending`. Keycard showed `Monthly (Awaiting Payment) | Awaiting Desk Payment`. Front desk recorded UPI payment; enrollment and member status immediately transitioned to `active`.

---

## 9. Conclusion

The Membership Enrollment Approval and Activation Workflow is completely resolved, securely isolated by branch, fully audited, covered by 13 automated tests, and validated in live staging at `http://127.0.0.1:18000`.
