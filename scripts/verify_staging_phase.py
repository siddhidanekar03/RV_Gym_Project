"""
Live staging end-to-end verification script using session cookies and CSRF tokens.
Verifies:
1. QR Attendance Repair and Security Hardening
2. Member Profile, Least-Privilege Scoping, Dynamic Age, and Measurements
3. Performance Tracking, Weight History, PRs, and Coach Dashboard
"""
import sys
import uuid
import requests
from datetime import date

BASE_URL = "http://127.0.0.1:18000/api/v1"

def print_step(title):
    print(f"\n--- {title} ---")

def run():
    import subprocess
    subprocess.run(["docker", "exec", "rvfitness_staging_redis", "redis-cli", "flushall"], capture_output=True)

    admin_session = requests.Session()
    member_session = requests.Session()
    staff_session = requests.Session()
    coach_session = requests.Session()

    # 1. Login as Admin
    print_step("Step 1: Admin Authentication")
    admin_res = admin_session.post(f"{BASE_URL}/auth/login", json={
        "email": "admin@rvfitness.in",
        "password": "StagingAdminPass123!"
    })
    assert admin_res.status_code == 200, f"Admin login failed: {admin_res.text}"
    admin_csrf = admin_res.json().get("csrfToken")
    admin_headers = {"X-CSRF-Token": admin_csrf} if admin_csrf else {}
    print(f"Admin authenticated successfully. CSRF: {admin_csrf[:8] if admin_csrf else 'None'}...")

    # 2. Register Member, Staff, Coach
    print_step("Step 2: User Creation")
    unique_suffix = uuid.uuid4().hex[:6]
    import random
    m_digits = str(random.randint(10000000, 99999999))
    s_digits = str(random.randint(10000000, 99999999))
    c_digits = str(random.randint(10000000, 99999999))
    member_email = f"staging_member_{unique_suffix}@rvfitness.com"
    staff_email = f"staging_staff_{unique_suffix}@rvfitness.com"
    coach_email = f"staging_coach_{unique_suffix}@rvfitness.com"

    # Register member
    m_reg = member_session.post(f"{BASE_URL}/auth/register", json={
        "name": f"Pooja Patil {unique_suffix}",
        "email": member_email,
        "phone": f"+9198{m_digits}",
        "password": "Password123!",
        "role": "member",
        "branch_id": "narsobawadi",
        "acceptedTerms": True
    })
    assert m_reg.status_code == 201, f"Member reg failed: {m_reg.text}"
    member_data = m_reg.json()["user"]
    member_id = member_data["id"]
    member_csrf = m_reg.json().get("csrfToken")
    member_headers = {"X-CSRF-Token": member_csrf} if member_csrf else {}
    print(f"Member created: {member_id} ({member_email})")

    # Register staff
    s_reg = staff_session.post(f"{BASE_URL}/auth/register", json={
        "name": f"Desk Staff {unique_suffix}",
        "email": staff_email,
        "phone": f"+9197{s_digits}",
        "password": "Password123!",
        "role": "front_desk",
        "branch_id": "narsobawadi",
        "acceptedTerms": True
    })
    assert s_reg.status_code == 201, f"Staff reg failed: {s_reg.text}"
    staff_data = s_reg.json()["user"]
    staff_id = staff_data["id"]
    staff_csrf = s_reg.json().get("csrfToken")
    staff_headers = {"X-CSRF-Token": staff_csrf} if staff_csrf else {}
    print(f"Staff created: {staff_id} ({staff_email})")

    # Register coach
    c_reg = coach_session.post(f"{BASE_URL}/auth/register", json={
        "name": f"Coach Vikram {unique_suffix}",
        "email": coach_email,
        "phone": f"+9196{c_digits}",
        "password": "Password123!",
        "role": "trainer",
        "branch_id": "narsobawadi",
        "acceptedTerms": True
    })
    assert c_reg.status_code == 201, f"Coach reg failed: {c_reg.text}"
    coach_data = c_reg.json()["user"]
    coach_id = coach_data["id"]
    coach_csrf = c_reg.json().get("csrfToken")
    coach_headers = {"X-CSRF-Token": coach_csrf} if coach_csrf else {}
    print(f"Coach created: {coach_id} ({coach_email})")

    # Admin assigns membership plan to member
    assign_res = admin_session.post(
        f"{BASE_URL}/owner/members/assign-membership",
        json={
            "userId": member_id,
            "planId": "plan_quarterly",
            "branchId": "narsobawadi",
            "recordPayment": True,
            "paymentMethod": "cash",
            "notes": "Staging test enrollment"
        },
        headers=admin_headers
    )
    assert assign_res.status_code == 200, f"Plan assign failed: {assign_res.text}"
    print("Membership plan assigned successfully.")

    # Configure staff and coach roles and link assigned trainer
    import subprocess
    setup_code = (
        "from backend.app.core.database import SessionLocal\n"
        "from backend.app.models.user import User\n"
        "db = SessionLocal()\n"
        f"s = db.query(User).filter(User.id == '{staff_id}').first()\n"
        "if s:\n"
        "    s.role = 'front_desk'\n"
        "    s.staff_role = 'Receptionist'\n"
        f"c = db.query(User).filter(User.id == '{coach_id}').first()\n"
        "if c:\n"
        "    c.role = 'trainer'\n"
        "    c.staff_role = 'Strength Coach'\n"
        f"m = db.query(User).filter(User.id == '{member_id}').first()\n"
        "if m:\n"
        f"    m.assigned_trainer_id = '{coach_id}'\n"
        "    m.membership_status = 'active'\n"
        "db.commit()\n"
    )
    subprocess.run(["docker", "exec", "rvfitness_staging_app", "python", "-c", setup_code], check=True)
    print("Elevated staff/coach roles and trainer linkage configured.")

    # Re-login staff and coach to refresh sessions with updated roles
    staff_session = requests.Session()
    s_login = staff_session.post(f"{BASE_URL}/auth/login", json={"email": staff_email, "password": "Password123!"})
    assert s_login.status_code == 200
    staff_csrf = s_login.json().get("csrfToken")
    staff_headers = {"X-CSRF-Token": staff_csrf} if staff_csrf else {}

    coach_session = requests.Session()
    c_login = coach_session.post(f"{BASE_URL}/auth/login", json={"email": coach_email, "password": "Password123!"})
    assert c_login.status_code == 200
    coach_csrf = c_login.json().get("csrfToken")
    coach_headers = {"X-CSRF-Token": coach_csrf} if coach_csrf else {}

    # 3. VERIFY OUTCOME 1: QR Attendance Repair and Security Hardening
    print_step("Step 3: Outcome 1 - QR Attendance Verification")
    qr_res = member_session.get(f"{BASE_URL}/attendance/qr-token")
    assert qr_res.status_code == 200, f"QR token fetch failed: {qr_res.text}"
    qr_data = qr_res.json()
    qr_token = qr_data.get("qrToken") or qr_data.get("qr_token")
    print(f"Member retrieved active dynamic QR entry token (Length: {len(qr_token)}).")

    # 3a. Member attempts self-check-in remotely -> MUST BE 403 Forbidden
    self_res = member_session.post(f"{BASE_URL}/attendance/qr-check-in", json={
        "qrToken": qr_token,
        "branchId": "narsobawadi"
    }, headers=member_headers)
    assert self_res.status_code == 403, f"Expected 403 for member self-checkin, got {self_res.status_code}: {self_res.text}"
    print("Security check passed: Member remote self-checkin rejected with HTTP 403 Forbidden.")

    # 3b. Authorized front-desk staff scans QR token -> MUST BE 200 OK
    scan_res = staff_session.post(f"{BASE_URL}/attendance/qr-check-in", json={
        "qrToken": qr_token,
        "branchId": "narsobawadi"
    }, headers=staff_headers)
    assert scan_res.status_code == 200, f"Staff scan failed: {scan_res.status_code} {scan_res.text}"
    scan_body = scan_res.json()
    print(f"Staff scan succeeded: {scan_body['message']} (Streak: {scan_body.get('streakDays', scan_body.get('streak_days'))})")

    # 3c. Replay attack with same QR token -> MUST BE 400 Bad Request
    replay_res = staff_session.post(f"{BASE_URL}/attendance/qr-check-in", json={
        "qrToken": qr_token,
        "branchId": "narsobawadi"
    }, headers=staff_headers)
    assert replay_res.status_code == 400, f"Expected 400 for replay, got {replay_res.status_code}: {replay_res.text}"
    print(f"Replay prevention passed: Reused QR token rejected with HTTP 400 Bad Request ({replay_res.json()['detail']}).")

    # 4. VERIFY OUTCOME 2: Member Health Profile and Least-Privilege Scoping
    print_step("Step 4: Outcome 2 - Member Health Profile and Scoping")
    profile_payload = {
        "personal": {
            "date_of_birth": "1996-05-15",
            "gender": "female",
            "address": "Flat 302, Krishna Valley Residency, Narsobawadi",
            "emergency_contact_name": "Ramesh Patil",
            "emergency_contact_phone": "+919822001122",
        },
        "health": {
            "health_conditions": "Mild asthma on high-humidity days",
            "past_injuries": "Right knee meniscus repair in 2022",
            "exercise_restrictions": "Avoid heavy impact box jumps; squat depth to parallel",
            "health_notes": "Cleared for strength training with proper warmups",
            "has_medication_consent": True,
        },
        "targets": {
            "height_cm": 165.0,
            "target_weight_kg": 58.0,
            "primary_goal": "strength"
        }
    }
    prof_update = member_session.put(f"{BASE_URL}/profile/me", json=profile_payload, headers=member_headers)
    assert prof_update.status_code == 200, f"Profile update failed: {prof_update.text}"
    my_prof = prof_update.json()
    print(f"Profile updated. Dynamic age: {my_prof['calculatedAge']} years (DOB: {my_prof['dateOfBirth']})")
    assert my_prof["calculatedAge"] is not None and my_prof["calculatedAge"] >= 28

    # 4b. Member logs initial body measurements
    m1_res = member_session.post(f"{BASE_URL}/profile/measurements", json={
        "recorded_date": "2026-09-01",
        "weight_kg": 64.5,
        "height_cm": 165.0,
        "body_fat_pct": 24.5,
        "chest_cm": 88.0,
        "waist_cm": 74.0,
        "hips_cm": 96.0,
        "arms_cm": 27.5,
        "notes": "Baseline intake measurements"
    }, headers=member_headers)
    assert m1_res.status_code == 200, f"Measurement 1 failed: {m1_res.text}"

    # Log second measurement (progress)
    m2_res = member_session.post(f"{BASE_URL}/profile/measurements", json={
        "recorded_date": "2026-10-15",
        "weight_kg": 61.2,
        "height_cm": 165.0,
        "body_fat_pct": 22.0,
        "chest_cm": 86.5,
        "waist_cm": 71.0,
        "hips_cm": 93.5,
        "arms_cm": 28.0,
        "notes": "Midway progress check-in"
    }, headers=member_headers)
    assert m2_res.status_code == 200, f"Measurement 2 failed: {m2_res.text}"
    print("Time-series measurements logged (Baseline: 64.5kg, Latest: 61.2kg).")

    # 4c. Coach views member profile -> Scoped least-privilege (restrictions visible, medical conditions redacted)
    coach_view_res = coach_session.get(f"{BASE_URL}/profile/member/{member_id}")
    assert coach_view_res.status_code == 200, f"Coach view failed: {coach_view_res.text}"
    coach_view = coach_view_res.json()
    print("Coach view scoping verification:")
    print(f"  Physical restrictions: {coach_view['exerciseRestrictions']}")
    print(f"  Medical conditions (scoped): {coach_view['healthConditions']}")
    print(f"  Health notes (scoped): {coach_view['healthNotes']}")
    assert coach_view["exerciseRestrictions"] == "Avoid heavy impact box jumps; squat depth to parallel"
    assert coach_view["healthConditions"] is None, "Medical conditions must be redacted for coach"
    assert coach_view["healthNotes"] is None, "Health notes must be redacted for coach"

    # 4d. Front-desk views member profile -> Full medical redaction, contact & emergency info visible
    staff_view_res = staff_session.get(f"{BASE_URL}/profile/member/{member_id}")
    assert staff_view_res.status_code == 200, f"Staff view failed: {staff_view_res.text}"
    staff_view = staff_view_res.json()
    print("Front-desk view scoping verification:")
    print(f"  Emergency contact: {staff_view['emergencyContactName']} ({staff_view['emergencyContactPhone']})")
    print(f"  Physical restrictions (scoped): {staff_view['exerciseRestrictions']}")
    print(f"  Medical conditions (scoped): {staff_view['healthConditions']}")
    assert staff_view["emergencyContactName"] == "Ramesh Patil"
    assert staff_view["exerciseRestrictions"] is None, "Physical restrictions must be redacted for front-desk"
    assert staff_view["healthConditions"] is None, "Medical conditions must be redacted for front-desk"

    # 5. VERIFY OUTCOME 3: Fitness Performance Tracker & Weight Calculations
    print_step("Step 5: Outcome 3 - Performance Tracker and Weight History")
    
    # 5a. Performance Summary calculation
    perf_res = member_session.get(f"{BASE_URL}/performance/summary")
    assert perf_res.status_code == 200, f"Summary failed: {perf_res.text}"
    perf = perf_res.json()
    print("Performance Summary metrics:")
    print(f"  Baseline Weight: {perf['baselineWeightKg']} kg")
    print(f"  Current Weight: {perf['currentWeightKg']} kg")
    print(f"  Net Weight Change: {perf['netWeightChangeKg']} kg")
    print(f"  Goal Weight: {perf['goalWeightKg']} kg")
    print(f"  Goal Progress: {perf['goalProgressPct']}%")
    print(f"  Goal Status: {perf['goalStatusMessage']}")
    assert perf["baselineWeightKg"] == 64.5
    assert perf["currentWeightKg"] == 61.2
    assert perf["netWeightChangeKg"] == -3.3
    assert perf["goalProgressPct"] is not None and perf["goalProgressPct"] > 0

    # 5b. Weight History chronological array
    wh_res = member_session.get(f"{BASE_URL}/performance/weight-history")
    assert wh_res.status_code == 200
    weight_hist = wh_res.json()
    assert len(weight_hist) == 2
    assert weight_hist[0]["weightKg"] == 64.5
    assert weight_hist[1]["weightKg"] == 61.2
    print(f"Weight history returned {len(weight_hist)} dated records for SVG chart rendering.")

    # 5c. Log completed workout session with exercise performance & automatic PR detection
    workout_res = member_session.post(f"{BASE_URL}/performance/workouts/complete", json={
        "sessionName": "Lower Body Strength and Hip Mobility",
        "sessionDate": date.today().isoformat(),
        "durationMinutes": 55,
        "rpe": 8,
        "notes": "Controlled tempo, parallel depth maintained",
        "exercises": [
            {"exerciseName": "Barbell Back Squat", "sets": 4, "reps": 6, "weightKg": 85.0},
            {"exerciseName": "Romanian Deadlift", "sets": 3, "reps": 10, "weightKg": 70.0},
            {"exerciseName": "Seated Calf Raise", "sets": 3, "reps": 15, "weightKg": 40.0}
        ]
    }, headers=member_headers)
    assert workout_res.status_code == 200, f"Workout complete failed: {workout_res.text}"
    workout_data = workout_res.json()
    print(f"Workout session logged: {workout_data['id']} (Status: {workout_data['status']}, Exercises: {len(workout_data['exercises'])})")
    assert workout_data["status"] == "completed"
    assert len(workout_data["exercises"]) == 3

    # Check updated summary for new PR
    perf_res2 = member_session.get(f"{BASE_URL}/performance/summary")
    perf2 = perf_res2.json()
    assert len(perf2["recentPRs"]) >= 3
    print(f"Personal records recognized automatically: {[pr['exerciseName'] + ': ' + str(pr['value']) + 'kg' for pr in perf2['recentPRs']]}")

    # 5d. Coach Dashboard: assigned members overview
    coach_roster_res = coach_session.get(f"{BASE_URL}/performance/coach/members")
    assert coach_roster_res.status_code == 200, f"Coach roster failed: {coach_roster_res.text}"
    roster = coach_roster_res.json()
    assert len(roster) >= 1
    assigned_entry = next((r for r in roster if r.get("memberId") == member_id or r.get("userId") == member_id), None)
    assert assigned_entry is not None
    m_name = assigned_entry.get("memberName") or assigned_entry.get("userName")
    print(f"Coach roster overview: Member {m_name} (Goal: {assigned_entry['primaryGoal']}, Workouts: {assigned_entry['workoutsCompletedThisMonth']}, Movement restrictions: {assigned_entry['movementRestrictions']})")

    print("\nALL 3 OUTCOMES VERIFIED END-TO-END ON LOCAL STAGING ENVIRONMENT WITH ZERO ERRORS!")

if __name__ == "__main__":
    run()
