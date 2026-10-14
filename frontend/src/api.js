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

export async function fetchTrainers() {
  return request('/trainers');
}

export async function fetchEquipment() {
  return request('/equipment');
}

export async function fetchEvents() {
  return request('/events');
}

export async function fetchLeaderboard(category = 'all') {
  const query = category && category !== 'all' ? `?category=${encodeURIComponent(category)}` : '';
  return request(`/leaderboard${query}`);
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
