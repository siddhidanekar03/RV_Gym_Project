// RVFitness API Client with HttpOnly Cookie Sessions & CSRF Protection

const API_BASE = '/api';

/**
 * Extract CSRF token from cookie if available.
 */
function getCsrfToken() {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(new RegExp('(^| )rvf_csrf_token=([^;]+)'));
  return match ? decodeURIComponent(match[2]) : null;
}

/**
 * Standardized fetch helper enforcing credentials and CSRF tokens.
 */
async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const headers = { ...options.headers };

  if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  // Attach CSRF token for mutating requests
  const method = (options.method || 'GET').toUpperCase();
  if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      headers['X-CSRF-Token'] = csrfToken;
    }
  }

  // If a legacy token is passed in headers, allow Authorization header as fallback
  const config = {
    ...options,
    headers,
    credentials: 'include', // Automatically send & receive HttpOnly cookies
  };

  const res = await fetch(url, config);
  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    let errorMsg = 'Request failed';
    if (data.field_errors && Object.keys(data.field_errors).length > 0) {
      errorMsg = Object.entries(data.field_errors)
        .map(([field, msg]) => `${field.charAt(0).toUpperCase() + field.slice(1)}: ${msg}`)
        .join('; ');
    } else if (data.details && Array.isArray(data.details) && data.details.length > 0) {
      errorMsg = data.details
        .map((d) => d.replace(/^body\s*->\s*/i, '').replace(/_/g, ' '))
        .join('; ');
    } else if (typeof data.detail === 'string') {
      errorMsg = data.detail;
    } else if (Array.isArray(data.detail)) {
      errorMsg = data.detail
        .map((d) => (d.msg ? `${d.loc?.slice(-1)[0] || 'Field'}: ${d.msg}` : JSON.stringify(d)))
        .join('; ');
    } else if (data.message) {
      errorMsg = data.message;
    } else if (data.error && data.error !== 'Request validation failed') {
      errorMsg = data.error;
    } else if (data.error) {
      errorMsg = data.error;
    }

    const err = new Error(errorMsg);
    err.status = res.status;
    err.data = data;
    err.fieldErrors = data.field_errors || {};

    if (res.status === 401 && typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('rvf:auth_expired', { detail: { message: errorMsg } }));
    }

    throw err;
  }

  return data;
}

export async function fetchGymInfo() {
  return request('/info');
}

export async function fetchPlans() {
  return request('/plans');
}

export async function fetchBranches() {
  return request('/branches');
}

export async function fetchTrainers() {
  return request('/trainers');
}

export async function fetchEquipment() {
  return request('/equipment');
}

export async function fetchEvents() {
  return request('/events');
}

export async function fetchLeaderboard(params = 'all') {
  if (typeof params === 'string') {
    const query = params && params !== 'all' ? `?category=${encodeURIComponent(params)}` : '';
    return request(`/leaderboard${query}`);
  }
  const q = new URLSearchParams();
  if (params.category && params.category !== 'all') q.set('category', params.category);
  if (params.month) q.set('month', params.month);
  if (params.year) q.set('year', params.year);
  if (params.branchId && params.branchId !== 'all') q.set('branch_id', params.branchId);
  if (params.page) q.set('page', params.page);
  if (params.limit) q.set('limit', params.limit);
  const queryString = q.toString() ? `?${q.toString()}` : '';
  return request(`/leaderboard${queryString}`);
}

export async function fetchMyLeaderboardStanding({ month, year } = {}) {
  const q = new URLSearchParams();
  if (month) q.set('month', month);
  if (year) q.set('year', year);
  const queryString = q.toString() ? `?${q.toString()}` : '';
  return request(`/leaderboard/me${queryString}`);
}

export async function updateLeaderboardPreferences(data) {
  return request('/leaderboard/preferences', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function fetchScoringRules() {
  return request('/leaderboard/rules');
}

export async function fetchMyPointHistory({ month, year } = {}) {
  const q = new URLSearchParams();
  if (month) q.set('month', month);
  if (year) q.set('year', year);
  const queryString = q.toString() ? `?${q.toString()}` : '';
  return request(`/leaderboard/history${queryString}`);
}

export async function submitContact(data) {
  return request('/contact', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function submitEnrollment(data) {
  return request('/memberships/enroll', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function loginUser(email, password) {
  return request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export async function registerUser(data) {
  return request('/auth/register', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function fetchCurrentUser() {
  return request('/auth/me');
}

export async function logoutUser() {
  return request('/auth/logout', {
    method: 'POST',
  });
}

export async function memberCheckIn() {
  return request('/attendance/check-in', {
    method: 'POST',
  });
}

export async function fetchAdminOverview() {
  return request('/admin/overview');
}

// Phase 4: Production Attendance, QR, Desk Manual & Reporting APIs

export async function getAttendanceQRToken() {
  return request('/attendance/qr-token');
}

export async function qrCheckIn(qrToken, branchId = 'narsobawadi') {
  return request('/attendance/qr-check-in', {
    method: 'POST',
    body: JSON.stringify({ qrToken, branchId }),
  });
}

export async function manualCheckIn({
  branchId = 'narsobawadi',
  reasonCode,
  memberId,
  phone,
  name,
  notes,
}) {
  return request('/attendance/manual-check-in', {
    method: 'POST',
    body: JSON.stringify({
      branchId,
      reasonCode,
      memberId: memberId || undefined,
      phone: phone || undefined,
      name: name || undefined,
      notes: notes || undefined,
    }),
  });
}

export async function managerOverride({ attemptId, reason }) {
  return request('/attendance/override', {
    method: 'POST',
    body: JSON.stringify({ attemptId, reason }),
  });
}

export async function paperBackfill({
  branchId = 'narsobawadi',
  visitDate,
  entryOperator,
  reason,
  memberId,
  phone,
  name,
}) {
  return request('/attendance/backfill', {
    method: 'POST',
    body: JSON.stringify({
      branchId,
      visitDate,
      entryOperator,
      reason,
      memberId: memberId || undefined,
      phone: phone || undefined,
      name: name || undefined,
    }),
  });
}

export async function lookupMembersForDesk(query, branchId = 'narsobawadi') {
  if (!query || !query.trim()) return { members: [] };
  const encodedQ = encodeURIComponent(query.trim());
  const encodedB = encodeURIComponent(branchId);
  return request(`/attendance/members/lookup?q=${encodedQ}&branch_id=${encodedB}`);
}

export async function fetchBranchMonthlyReport(branchId = 'narsobawadi', year = 2026, month = 10) {
  return request(`/attendance/reports/branch/${encodeURIComponent(branchId)}?year=${year}&month=${month}`);
}

export async function fetchMemberMonthlyReport(userId, year = 2026, month = 10) {
  return request(`/attendance/reports/member/${encodeURIComponent(userId)}?year=${year}&month=${month}`);
}

export function getBranchReportExportUrl(branchId = 'narsobawadi', year = 2026, month = 10, format = 'csv') {
  return `/api/attendance/reports/branch/${encodeURIComponent(branchId)}/export?year=${year}&month=${month}&format=${format}`;
}

export async function downloadBranchReportExport(branchId = 'narsobawadi', year = 2026, month = 10, format = 'csv') {
  const url = getBranchReportExportUrl(branchId, year, month, format);
  const res = await fetch(url, {
    method: 'GET',
    credentials: 'include',
  });
  if (!res.ok) {
    let errText = 'Failed to export report';
    try {
      const errJson = await res.json();
      errText = errJson.detail || errJson.message || errText;
    } catch {
      errText = await res.text();
    }
    throw new Error(errText);
  }
  const blob = await res.blob();
  const downloadUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = downloadUrl;
  a.download = `attendance_report_${branchId}_${year}_${month}.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(downloadUrl);
}

// Phase 3 & 4: Gym Owner Website & Facility Management APIs

export async function fetchWebsiteContent() {
  return request('/owner/website-content');
}

export async function updateWebsiteContent(section, data) {
  return request(`/owner/website-content/${encodeURIComponent(section)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function fetchOwnerEquipment(branchId = null) {
  const q = branchId ? `?branch_id=${encodeURIComponent(branchId)}` : '';
  return request(`/owner/equipment${q}`);
}

export async function createOwnerEquipment(payload) {
  return request('/owner/equipment', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function updateOwnerEquipment(id, payload) {
  return request(`/owner/equipment/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function deleteOwnerEquipment(id) {
  return request(`/owner/equipment/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
}

export async function uploadOwnerEquipmentPhoto(id, file) {
  const formData = new FormData();
  formData.append('file', file);
  return request(`/owner/equipment/${encodeURIComponent(id)}/upload-photo`, {
    method: 'POST',
    body: formData,
  });
}

export async function fetchOwnerGallery(branchId = null) {
  const q = branchId ? `?branch_id=${encodeURIComponent(branchId)}` : '';
  return request(`/owner/gallery${q}`);
}

export async function createOwnerGallery(payload) {
  return request('/owner/gallery', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function updateOwnerGallery(id, payload) {
  return request(`/owner/gallery/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function deleteOwnerGallery(id) {
  return request(`/owner/gallery/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
}

export async function uploadOwnerGalleryPhoto(file) {
  const formData = new FormData();
  formData.append('file', file);
  return request('/owner/gallery/upload-photo', {
    method: 'POST',
    body: formData,
  });
}

export async function fetchOwnerCoaches(branchId = null) {
  const q = branchId ? `?branch_id=${encodeURIComponent(branchId)}` : '';
  return request(`/owner/coaches${q}`);
}

export async function createOwnerCoach(payload) {
  return request('/owner/coaches', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function updateOwnerCoach(id, payload) {
  return request(`/owner/coaches/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function fetchOwnerPlans() {
  return request('/owner/plans');
}

export async function createOwnerPlan(payload) {
  return request('/owner/plans', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function updateOwnerPlan(id, payload) {
  return request(`/owner/plans/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function archiveOwnerPlan(id) {
  return request(`/owner/plans/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
}

export async function uploadOwnerMedia(file) {
  const formData = new FormData();
  formData.append('file', file);
  return request('/owner/upload-media', {
    method: 'POST',
    body: formData,
  });
}

// Enrollment Approval & Verification APIs
export async function fetchOwnerEnrollments(arg1 = 'all', arg2 = '', arg3 = '') {
  let status = 'all';
  let branchId = '';
  let search = '';
  if (typeof arg1 === 'object' && arg1 !== null) {
    status = arg1.status || 'all';
    branchId = arg1.branchId || arg1.branch_id || '';
    search = arg1.search || '';
  } else {
    status = arg1 || 'all';
    branchId = arg2 || '';
    search = arg3 || '';
  }
  const query = new URLSearchParams();
  if (status && status !== 'all') query.append('status', status);
  if (branchId) query.append('branch_id', branchId);
  if (search) query.append('search', search);
  const qStr = query.toString();
  return request(`/owner/enrollments${qStr ? `?${qStr}` : ''}`);
}

export async function fetchOwnerEnrollmentById(id) {
  return request(`/owner/enrollments/${encodeURIComponent(id)}`);
}

export async function approveOwnerEnrollment(id, payload = {}) {
  return request(`/owner/enrollments/${encodeURIComponent(id)}/approve`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function rejectOwnerEnrollment(id, payload = {}) {
  return request(`/owner/enrollments/${encodeURIComponent(id)}/reject`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function fetchMyEnrollment() {
  return request('/memberships/my-enrollment');
}

export async function fetchPublicGallery(branchId = null) {
  const q = branchId ? `?branch_id=${encodeURIComponent(branchId)}` : '';
  return request(`/gallery${q}`);
}

// Phase 6: Announcements and Operational Content APIs

export async function fetchPublicAnnouncements(branchId = null, category = null) {
  const params = new URLSearchParams();
  if (branchId) params.append('branch_id', branchId);
  if (category) params.append('category', category);
  const q = params.toString() ? `?${params.toString()}` : '';
  return request(`/announcements/public${q}`);
}

export async function fetchUserFeedAnnouncements(branchId = null, category = null) {
  const params = new URLSearchParams();
  if (branchId) params.append('branch_id', branchId);
  if (category) params.append('category', category);
  const q = params.toString() ? `?${params.toString()}` : '';
  return request(`/announcements/feed${q}`);
}

export async function fetchAdminAnnouncements(status = null, branchId = null, category = null) {
  const params = new URLSearchParams();
  if (status) params.append('status', status);
  if (branchId) params.append('branch_id', branchId);
  if (category) params.append('category', category);
  const q = params.toString() ? `?${params.toString()}` : '';
  return request(`/announcements/admin/list${q}`);
}

export async function previewAnnouncement(id) {
  return request(`/announcements/${encodeURIComponent(id)}/preview`);
}

export async function createAnnouncement(data) {
  return request('/announcements', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateAnnouncement(id, data) {
  return request(`/announcements/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function publishAnnouncement(id, publishData = {}) {
  return request(`/announcements/${encodeURIComponent(id)}/publish`, {
    method: 'POST',
    body: JSON.stringify(publishData),
  });
}

export async function unpublishAnnouncement(id) {
  return request(`/announcements/${encodeURIComponent(id)}/unpublish`, {
    method: 'POST',
  });
}

export async function archiveAnnouncement(id) {
  return request(`/announcements/${encodeURIComponent(id)}/archive`, {
    method: 'POST',
  });
}

export async function deleteAnnouncement(id) {
  return request(`/announcements/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
}

export async function uploadAnnouncementImage(file) {
  const formData = new FormData();
  formData.append('file', file);
  return request('/announcements/upload-image', {
    method: 'POST',
    body: formData,
  });
}

// ---------------------------------------------------------
// Phase 8: Workout Plans, Sessions, and Progress
// ---------------------------------------------------------

export async function fetchWorkoutPlans(params = {}) {
  const query = new URLSearchParams();
  if (params.branchId) query.append('branch_id', params.branchId);
  if (params.status) query.append('status', params.status);
  const qStr = query.toString();
  return request(`/workouts/plans${qStr ? `?${qStr}` : ''}`);
}

export async function fetchWorkoutPlanById(id) {
  return request(`/workouts/plans/${encodeURIComponent(id)}`);
}

export async function createWorkoutPlan(data) {
  return request('/workouts/plans', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateWorkoutPlan(id, data) {
  return request(`/workouts/plans/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function archiveWorkoutPlan(id) {
  return request(`/workouts/plans/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
}

export async function addPlanExercise(planId, data) {
  return request(`/workouts/plans/${encodeURIComponent(planId)}/exercises`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function deletePlanExercise(planId, exerciseId) {
  return request(`/workouts/plans/${encodeURIComponent(planId)}/exercises/${encodeURIComponent(exerciseId)}`, {
    method: 'DELETE',
  });
}

export async function assignPlanToMember(planId, data) {
  return request(`/workouts/plans/${encodeURIComponent(planId)}/assign`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function unassignPlanFromMember(planId, data) {
  return request(`/workouts/plans/${encodeURIComponent(planId)}/unassign`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function fetchAssignedWorkoutPlans(memberId) {
  const qStr = memberId ? `?member_id=${encodeURIComponent(memberId)}` : '';
  return request(`/workouts/assigned${qStr}`);
}

export async function startWorkoutSession(data) {
  return request('/workouts/sessions', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateWorkoutSession(id, data) {
  return request(`/workouts/sessions/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function fetchWorkoutSessionById(id) {
  return request(`/workouts/sessions/${encodeURIComponent(id)}`);
}

export async function fetchWorkoutSessions(memberId) {
  const qStr = memberId ? `?member_id=${encodeURIComponent(memberId)}` : '';
  return request(`/workouts/sessions${qStr}`);
}

export async function verifyWorkoutSession(id, data = {}) {
  return request(`/workouts/sessions/${encodeURIComponent(id)}/verify`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function recordFitnessProgress(data, memberId) {
  const qStr = memberId ? `?member_id=${encodeURIComponent(memberId)}` : '';
  return request(`/workouts/progress${qStr}`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function fetchFitnessProgress(memberId, recordType) {
  const query = new URLSearchParams();
  if (memberId) query.append('member_id', memberId);
  if (recordType) query.append('record_type', recordType);
  const qStr = query.toString();
  return request(`/workouts/progress${qStr ? `?${qStr}` : ''}`);
}

export async function downloadInvoicePdf(invoiceId) {
  const url = `${API_BASE}/billing/invoices/${encodeURIComponent(invoiceId)}/pdf`;
  const response = await fetch(url, {
    credentials: 'include',
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.error || 'Failed to download invoice PDF');
  }
  const blob = await response.blob();
  const downloadUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = downloadUrl;
  a.download = `RVFitness_Invoice_${invoiceId}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(downloadUrl);
}

export async function fetchInvoices(branchId) {
  const qStr = branchId ? `?branch_id=${encodeURIComponent(branchId)}` : '';
  return request(`/billing/invoices${qStr}`);
}

export async function fetchInvoiceById(invoiceId) {
  return request(`/billing/invoices/${encodeURIComponent(invoiceId)}`);
}

export async function submitPayment(data, idempotencyKey) {
  const headers = {};
  if (idempotencyKey) {
    headers['Idempotency-Key'] = idempotencyKey;
  }
  return request('/billing/payments', {
    method: 'POST',
    headers,
    body: JSON.stringify(data),
  });
}

export async function reversePayment(paymentId, data) {
  return request(`/billing/payments/${encodeURIComponent(paymentId)}/reverse`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function uploadOwnerCoachPhoto(file) {
  const formData = new FormData();
  formData.append('file', file);
  return request('/owner/coaches/upload-photo', {
    method: 'POST',
    body: formData,
  });
}

export async function deleteOwnerCoachPhoto(coachId) {
  return request(`/owner/coaches/${encodeURIComponent(coachId)}/photo`, {
    method: 'DELETE',
  });
}

export async function searchOwnerMembers(query, branchId) {
  const q = new URLSearchParams();
  if (query) q.append('q', query);
  if (branchId && branchId !== 'all') q.append('branch_id', branchId);
  return request(`/owner/members/search?${q.toString()}`);
}

export async function assignMembershipToMember(data) {
  return request('/owner/members/assign-membership', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// -------------------------------------------------------------
// Member Profile & Sensitive Health Data APIs
// -------------------------------------------------------------

export async function fetchMyProfile() {
  return request('/profile/me');
}

export async function updateMyProfile(payload) {
  return request('/profile/me', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function fetchMemberProfile(memberId) {
  return request(`/profile/member/${encodeURIComponent(memberId)}`);
}

export async function updateMemberProfile(memberId, payload) {
  return request(`/profile/member/${encodeURIComponent(memberId)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function logMyMeasurement(payload) {
  return request('/profile/measurements', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function fetchMyMeasurements(limit = 50, offset = 0) {
  return request(`/profile/measurements?limit=${limit}&offset=${offset}`);
}

export async function logMemberMeasurement(memberId, payload) {
  return request(`/profile/member/${encodeURIComponent(memberId)}/measurements`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function fetchMemberMeasurements(memberId, limit = 50, offset = 0) {
  return request(`/profile/member/${encodeURIComponent(memberId)}/measurements?limit=${limit}&offset=${offset}`);
}

// -------------------------------------------------------------
// Fitness Performance Tracker & Coach Progress APIs
// -------------------------------------------------------------

export async function fetchMyPerformanceSummary() {
  return request('/performance/summary');
}

export async function fetchMemberPerformanceSummary(memberId) {
  return request(`/performance/member/${encodeURIComponent(memberId)}/summary`);
}

export async function fetchMyWeightHistory() {
  return request('/performance/weight-history');
}

export async function fetchMemberWeightHistory(memberId) {
  return request(`/performance/member/${encodeURIComponent(memberId)}/weight-history`);
}

export async function fetchMyCompletedWorkouts(limit = 50, offset = 0) {
  return request(`/performance/workouts?limit=${limit}&offset=${offset}`);
}

export async function fetchMemberCompletedWorkouts(memberId, limit = 50, offset = 0) {
  return request(`/performance/member/${encodeURIComponent(memberId)}/workouts?limit=${limit}&offset=${offset}`);
}

export async function recordCompletedWorkout(payload, memberId = null) {
  const query = memberId ? `?memberId=${encodeURIComponent(memberId)}` : '';
  return request(`/performance/workouts/complete${query}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function fetchCoachAssignedMembers() {
  return request('/performance/coach/members');
}

