import { useState, useEffect } from 'react';
import {
  Users,
  UserCheck,
  Calendar,
  Shield,
  ArrowLeft,
  RefreshCw,
  AlertCircle,
  QrCode,
  LayoutDashboard,
  Megaphone,
  Dumbbell,
  Check,
  X
} from 'lucide-react';
import { fetchAdminOverview, approveOwnerEnrollment, rejectOwnerEnrollment } from '../api';
import StaffAttendanceDesk from './StaffAttendanceDesk';
import AdminAnnouncements from './AdminAnnouncements';
import AdminWorkouts from './AdminWorkouts';
import GymOwnerPanel from './GymOwnerPanel';

export default function AdminDashboard({ user, token, onClose }) {
  const isOwner = user?.role === 'org_admin' || user?.role === 'admin' || user?.staff_role === 'Gym Owner';
  if (isOwner) {
    return <GymOwnerPanel user={user} onClose={onClose} />;
  }

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionFeedback, setActionFeedback] = useState(null);
  const [currentSection, setCurrentSection] = useState('attendance'); // 'attendance' | 'announcements' | 'workouts' | 'overview'

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchAdminOverview(token);
      setData(res);
    } catch (err) {
      setError(err.message || 'Unable to retrieve administrative data.');
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (enrollmentId) => {
    setError(null);
    setActionFeedback(null);
    try {
      const res = await approveOwnerEnrollment(enrollmentId, { record_payment: false });
      setActionFeedback(res.message || 'Enrollment approved. Awaiting front-desk payment.');
      loadData();
    } catch (err) {
      setError(err.message || 'Failed to approve enrollment.');
    }
  };

  const handleReject = async (enrollmentId) => {
    const reason = prompt('Please enter the reason for rejecting this application:');
    if (!reason || !reason.trim()) return;
    setError(null);
    setActionFeedback(null);
    try {
      const res = await rejectOwnerEnrollment(enrollmentId, { reason: reason.trim() });
      setActionFeedback(res.message || 'Enrollment application rejected.');
      loadData();
    } catch (err) {
      setError(err.message || 'Failed to reject enrollment.');
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  return (
    <div className="dashboard-overlay" role="dialog" aria-modal="true" aria-label="Staff Administration Portal">
      <div className="dashboard-header-bar">
        <div className="dashboard-title-group">
          <button
            type="button"
            className="btn-back-home"
            onClick={onClose}
          >
            <ArrowLeft size={16} />
            <span>Return to Site</span>
          </button>
          <div className="vertical-bar" aria-hidden="true" />
          <h2 className="dashboard-title">Staff & Coaching Operations Desk</h2>
        </div>

        <div className="dashboard-user-badge">
          <Shield size={16} className="gold-text" />
          <span>{user?.name}</span>
          <span className="badge-pill-status">Staff Duty</span>
        </div>
      </div>

      {/* Staff Section Switcher */}
      <div className="admin-subnav-bar">
        <button
          type="button"
          className={`admin-nav-tab ${currentSection === 'attendance' ? 'active' : ''}`}
          onClick={() => setCurrentSection('attendance')}
        >
          <QrCode size={16} />
          <span>Attendance & Check-In Desk</span>
          <span className="subnav-pill-gold">Live</span>
        </button>
        <button
          type="button"
          className={`admin-nav-tab ${currentSection === 'announcements' ? 'active' : ''}`}
          onClick={() => setCurrentSection('announcements')}
        >
          <Megaphone size={16} />
          <span>Announcements & Operations</span>
        </button>
        <button
          type="button"
          className={`admin-nav-tab ${currentSection === 'workouts' ? 'active' : ''}`}
          onClick={() => setCurrentSection('workouts')}
        >
          <Dumbbell size={16} />
          <span>Workout Plans & Coaching</span>
        </button>
        <button
          type="button"
          className={`admin-nav-tab ${currentSection === 'overview' ? 'active' : ''}`}
          onClick={() => setCurrentSection('overview')}
        >
          <LayoutDashboard size={16} />
          <span>Facility Roster & Overview</span>
        </button>
      </div>

      <div className="dashboard-main-content">
        {currentSection === 'attendance' && (
          <StaffAttendanceDesk currentUser={user} branchId={user?.branch_id || 'narsobawadi'} />
        )}
        {currentSection === 'announcements' && (
          <AdminAnnouncements currentUser={user} />
        )}
        {currentSection === 'workouts' && (
          <AdminWorkouts currentUser={user} />
        )}
        {currentSection === 'overview' && (
          <>
            {loading && (
              <div className="status-container" role="status">
                <RefreshCw className="spinner-icon gold-text" size={32} />
                <p>Loading staff overview and active facility records...</p>
              </div>
            )}

            {error && (
              <div className="error-banner" role="alert">
                <AlertCircle size={24} className="danger-text" />
                <p>{error}</p>
              </div>
            )}

            {!loading && !error && data && (
              <div className="admin-content-flow">
            {/* Real-time Metric Cards */}
            <div className="admin-stats-grid">
              <div className="admin-stat-card">
                <div className="stat-icon-wrap" aria-hidden="true">
                  <UserCheck size={24} className="gold-text" />
                </div>
                <div>
                  <span className="stat-label">Active On Floor Right Now</span>
                  <strong className="stat-num">{data.activeTodayInGym} Members</strong>
                  <span className="stat-hint">Floor capacity: 75</span>
                </div>
              </div>

              <div className="admin-stat-card">
                <div className="stat-icon-wrap" aria-hidden="true">
                  <Users size={24} className="gold-text" />
                </div>
                <div>
                  <span className="stat-label">Total Registered Roster</span>
                  <strong className="stat-num">{data.totalMembers} Members</strong>
                  <span className="stat-hint">Active membership status</span>
                </div>
              </div>

              <div className="admin-stat-card">
                <div className="stat-icon-wrap" aria-hidden="true">
                  <Calendar size={24} className="gold-text" />
                </div>
                <div>
                  <span className="stat-label">Staff Duty Roster</span>
                  <strong className="stat-num">Head Coach On-Site</strong>
                  <span className="stat-hint">Shift: 6:00 AM - 2:00 PM</span>
                </div>
              </div>
            </div>

            {actionFeedback && (
              <div className="owner-alert-banner success" role="status">
                <Check size={18} />
                <span>{actionFeedback}</span>
              </div>
            )}

            {/* Recent Enrollments Table */}
            <div className="admin-section-box">
              <div className="admin-box-header">
                <h3 className="admin-box-title">Recent Membership Applications</h3>
                <span className="badge-pill-subtle">
                  {data.recentEnrollments?.length || 0} Pending Desk Actions
                </span>
              </div>

              {(!data.recentEnrollments || data.recentEnrollments.length === 0) ? (
                <div className="empty-sub-state">
                  <p>No new membership applications pending at the reception desk.</p>
                </div>
              ) : (
                <div className="table-responsive">
                  <table className="admin-table">
                    <thead>
                      <tr>
                        <th scope="col">Application ID</th>
                        <th scope="col">Member Name</th>
                        <th scope="col">Plan</th>
                        <th scope="col">Contact Phone</th>
                        <th scope="col">Amount Due</th>
                        <th scope="col">Status</th>
                        <th scope="col" className="text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.recentEnrollments.map((enr) => {
                        const isPending = enr.status === 'pending_verification' || enr.status === 'Pending Verification at Gym Desk';
                        return (
                          <tr key={enr.id}>
                            <td className="font-mono text-muted">{enr.id?.slice(0, 8)}...</td>
                            <td><strong>{enr.name}</strong></td>
                            <td><span className="category-tag-subtle">{enr.planName}</span></td>
                            <td>{enr.phone}</td>
                            <td className="gold-text font-bold">₹{enr.price?.toLocaleString('en-IN')}</td>
                            <td><span className="badge-warning">{enr.status}</span></td>
                            <td className="text-right">
                              {isPending && (
                                <div className="action-buttons-group">
                                  <button
                                    type="button"
                                    className="btn-approve-sm"
                                    onClick={() => handleApprove(enr.id)}
                                    title="Approve membership application"
                                  >
                                    <Check size={14} />
                                    <span>Approve</span>
                                  </button>
                                  <button
                                    type="button"
                                    className="btn-reject-sm"
                                    onClick={() => handleReject(enr.id)}
                                    title="Reject membership application"
                                  >
                                    <X size={14} />
                                    <span>Reject</span>
                                  </button>
                                </div>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Recent Contact Submissions */}
            <div className="admin-section-box">
              <div className="admin-box-header">
                <h3 className="admin-box-title">Recent Facility Inquiries</h3>
                <span className="badge-pill-subtle">
                  {data.recentContacts?.length || 0} Received
                </span>
              </div>

              {(!data.recentContacts || data.recentContacts.length === 0) ? (
                <div className="empty-sub-state">
                  <p>No unanswered inquiries in the front desk queue.</p>
                </div>
              ) : (
                <div className="table-responsive">
                  <table className="admin-table">
                    <thead>
                      <tr>
                        <th scope="col">Date/Time</th>
                        <th scope="col">Sender</th>
                        <th scope="col">Phone</th>
                        <th scope="col">Message / Goal</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.recentContacts.map((c) => (
                        <tr key={c.id}>
                          <td className="text-muted">{new Date(c.submittedAt).toLocaleTimeString()}</td>
                          <td><strong>{c.name}</strong></td>
                          <td>{c.phone}</td>
                          <td className="text-secondary">{c.message || 'General inquiry'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}
      </>
    )}
  </div>
</div>
  );
}
