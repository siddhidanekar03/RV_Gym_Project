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
    const errorMsg = data.detail || data.error || (data.details ? data.details.join(', ') : 'Request failed');
    throw new Error(errorMsg);
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
  return request('/attendance/qr-checkin', {
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
  return request('/attendance/manual-checkin', {
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
