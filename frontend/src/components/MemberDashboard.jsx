import { useState, useEffect } from 'react';
import {
  Calendar,
  Flame,
  Dumbbell,
  CheckCircle2,
  AlertCircle,
  Sparkles,
  User,
  ArrowLeft,
  QrCode,
  Megaphone,
  Trophy,
  Eye,
  EyeOff,
  Edit2,
  Check,
  Play,
  CheckSquare,
  Lock,
  Unlock,
  Award,
  Plus,
  TrendingUp
} from 'lucide-react';
import confetti from 'canvas-confetti';
import MembershipCard3D from './MembershipCard3D';
import MemberQRModal from './MemberQRModal';
import MemberProfileView from './MemberProfileView';
import FitnessPerformanceTracker from './FitnessPerformanceTracker';
import {
  fetchUserFeedAnnouncements,
  fetchMyLeaderboardStanding,
  updateLeaderboardPreferences,
  fetchMyPointHistory,
  fetchAssignedWorkoutPlans,
  startWorkoutSession,
  updateWorkoutSession,
  fetchWorkoutSessions,
  recordFitnessProgress,
  fetchFitnessProgress,
  fetchMyEnrollment,
  fetchCurrentUser,
} from '../api';

export default function MemberDashboard({
  user,
  token,
  onUserUpdate,
  onClose
}) {
  const [dashboardSection, setDashboardSection] = useState('access'); // 'access' | 'profile' | 'performance'
  const [showQRModal, setShowQRModal] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [error, setError] = useState(null);
  const [notices, setNotices] = useState([]);
  const [standing, setStanding] = useState({
    points: 0,
    distinctDays: 0,
    rank: null,
    totalMembers: 0,
    alias: '',
    isLeaderboardVisible: true,
    tier: 'Bronze',
  });
  const [aliasInput, setAliasInput] = useState('');
  const [isEditingAlias, setIsEditingAlias] = useState(false);
  const [savingPrefs, setSavingPrefs] = useState(false);
  const [prefsFeedback, setPrefsFeedback] = useState(null);
  const [recentLedger, setRecentLedger] = useState([]);

  // Phase 8: Workout plans, active session & fitness progress
  const [assignedPlans, setAssignedPlans] = useState([]);
  const [workoutSessions, setWorkoutSessions] = useState([]);
  const [activeSession, setActiveSession] = useState(null);
  const [sessionExercises, setSessionExercises] = useState([]);
  const [sessionNotes, setSessionNotes] = useState('');
  const [completingSession, setCompletingSession] = useState(false);
  const [progressRecords, setProgressRecords] = useState([]);
  const [showProgressModal, setShowProgressModal] = useState(false);
  const [progressForm, setProgressForm] = useState({
    record_type: 'body_weight',
    value: '',
    unit: 'kg',
    text_value: '',
    notes: '',
    is_private: true,
  });

  // Latest Membership Enrollment application state
  const [myEnrollment, setMyEnrollment] = useState(null);

  useEffect(() => {
    let ignore = false;

    // Refresh current user data to ensure latest plan and activation status
    fetchCurrentUser()
      .then((res) => {
        if (!ignore && res && res.user && onUserUpdate) {
          onUserUpdate(res.user);
        }
      })
      .catch(() => {});

    // Fetch member's latest enrollment record
    fetchMyEnrollment()
      .then((res) => {
        if (!ignore && res && res.enrollment) {
          setMyEnrollment(res.enrollment);
        }
      })
      .catch(() => {});

    fetchUserFeedAnnouncements()
      .then((res) => {
        if (!ignore) setNotices(res.announcements || []);
      })
      .catch(() => {
        if (!ignore) setNotices([]);
      });

    fetchMyLeaderboardStanding()
      .then((res) => {
        if (!ignore) {
          setStanding({
            points: res.points || 0,
            distinctDays: res.distinctDays || 0,
            rank: res.rank,
            totalMembers: res.totalMembers || 0,
            alias: res.alias || '',
            isLeaderboardVisible: res.isLeaderboardVisible,
            tier: res.tier || 'Bronze',
          });
          setAliasInput(res.alias || '');
        }
      })
      .catch(() => {});

    fetchMyPointHistory()
      .then((res) => {
        if (!ignore) setRecentLedger(res.entries ? res.entries.slice(0, 5) : []);
      })
      .catch(() => {});

    fetchAssignedWorkoutPlans()
      .then((res) => {
        if (!ignore) setAssignedPlans(res || []);
      })
      .catch(() => {});

    fetchWorkoutSessions()
      .then((res) => {
        if (!ignore) {
          setWorkoutSessions(res || []);
          const ongoing = (res || []).find((s) => s.status === 'in_progress');
          if (ongoing) {
            setActiveSession(ongoing);
            setSessionExercises(ongoing.exercises || []);
          }
        }
      })
      .catch(() => {});

    fetchFitnessProgress()
      .then((res) => {
        if (!ignore) setProgressRecords(res || []);
      })
      .catch(() => {});

    return () => {
      ignore = true;
    };
  }, []);

  const handleStartWorkout = async (plan) => {
    setError(null);
    try {
      const res = await startWorkoutSession({
        workout_plan_id: plan ? plan.id : undefined,
        session_name: plan ? `${plan.name} Workout` : 'Free Training Session',
      });
      setActiveSession(res);
      setSessionExercises(res.exercises || []);
      setFeedback('Workout session started. Log your sets and reps below.');
    } catch (err) {
      setError(err.message || 'Unable to start workout session.');
    }
  };

  const handleUpdateExerciseRow = (idx, field, val) => {
    const updated = [...sessionExercises];
    updated[idx] = { ...updated[idx], [field]: val };
    setSessionExercises(updated);
  };

  const handleCompleteWorkout = async () => {
    if (!activeSession) return;
    setCompletingSession(true);
    setError(null);
    try {
      await updateWorkoutSession(activeSession.id, {
        status: 'completed',
        notes: sessionNotes || undefined,
        exercises: sessionExercises,
      });
      setActiveSession(null);
      setSessionExercises([]);
      setSessionNotes('');
      setFeedback('Workout completed! +5 points awarded to your fitness standing.');
      confetti({ particleCount: 75, spread: 60, origin: { y: 0.7 } });

      fetchWorkoutSessions().then((s) => setWorkoutSessions(s || [])).catch(() => {});
      fetchMyLeaderboardStanding().then((st) => {
        if (st) setStanding((prev) => ({ ...prev, points: st.points }));
      }).catch(() => {});
    } catch (err) {
      setError(err.message || 'Failed to complete session.');
    } finally {
      setCompletingSession(false);
    }
  };

  const handleSaveProgress = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      await recordFitnessProgress({
        record_type: progressForm.record_type,
        value: progressForm.value ? parseFloat(progressForm.value) : undefined,
        unit: progressForm.unit || undefined,
        text_value: progressForm.text_value || undefined,
        notes: progressForm.notes || undefined,
        is_private: progressForm.is_private,
      });
      setShowProgressModal(false);
      setProgressForm({
        record_type: 'body_weight',
        value: '',
        unit: 'kg',
        text_value: '',
        notes: '',
        is_private: true,
      });
      setFeedback('Fitness progress recorded securely.');
      fetchFitnessProgress().then((r) => setProgressRecords(r || [])).catch(() => {});
    } catch (err) {
      setError(err.message || 'Failed to record progress.');
    }
  };

  const handleSaveAlias = async (e) => {
    e.preventDefault();
    if (!aliasInput || aliasInput.trim().length < 3) {
      setError('Gaming alias must be at least 3 characters in length.');
      return;
    }
    setSavingPrefs(true);
    setError(null);
    try {
      const res = await updateLeaderboardPreferences({ alias: aliasInput.trim() });
      setStanding((prev) => ({ ...prev, alias: res.alias }));
      setIsEditingAlias(false);
      setPrefsFeedback('Gaming alias saved successfully.');
      setTimeout(() => setPrefsFeedback(null), 4000);
    } catch (err) {
      setError(err.message || 'Unable to update alias.');
    } finally {
      setSavingPrefs(false);
    }
  };

  const handleToggleVisibility = async () => {
    setSavingPrefs(true);
    setError(null);
    try {
      const newVisibility = !standing.isLeaderboardVisible;
      const res = await updateLeaderboardPreferences({ isLeaderboardVisible: newVisibility });
      setStanding((prev) => ({ ...prev, isLeaderboardVisible: res.isLeaderboardVisible }));
      setPrefsFeedback(
        res.isLeaderboardVisible
          ? 'Public leaderboard visibility enabled.'
          : 'Public leaderboard visibility disabled. You are hidden from public rankings.'
      );
      setTimeout(() => setPrefsFeedback(null), 4000);
    } catch (err) {
      setError(err.message || 'Unable to update visibility.');
    } finally {
      setSavingPrefs(false);
    }
  };

  // Calendar dates generation for current month
  const currentMonthDays = Array.from({ length: 30 }, (_, i) => {
    const day = i + 1;
    const dateStr = `2026-10-${day < 10 ? '0' + day : day}`;
    const isAttended = user?.attendanceHistory?.includes(dateStr);
    const isToday = day === 14;
    return { day, isAttended, isToday };
  });

  return (
    <div className="dashboard-overlay" role="dialog" aria-modal="true" aria-label="Member Portal">
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
          <h2 className="dashboard-title">Member Training Portal</h2>
        </div>

        {/* Portal Section Navigation Tabs */}
        <div className="dashboard-portal-nav">
          <button
            type="button"
            className={`portal-nav-btn ${dashboardSection === 'access' ? 'active' : ''}`}
            onClick={() => setDashboardSection('access')}
          >
            <QrCode size={15} /> Keycard & Routine
          </button>
          <button
            type="button"
            className={`portal-nav-btn ${dashboardSection === 'profile' ? 'active' : ''}`}
            onClick={() => setDashboardSection('profile')}
          >
            <User size={15} /> Health Profile
          </button>
          <button
            type="button"
            className={`portal-nav-btn ${dashboardSection === 'performance' ? 'active' : ''}`}
            onClick={() => setDashboardSection('performance')}
          >
            <TrendingUp size={15} /> Performance & Progress
          </button>
        </div>

        <div className="dashboard-user-badge">
          <User size={16} className="gold-text" />
          <span>{user?.name}</span>
          <span className="badge-pill-status">{user?.status || 'Active'}</span>
        </div>
      </div>

      <div className="dashboard-main-content">
        {/* Top Notification / Alerts */}
        {feedback && (
          <div className="feedback-alert success" role="status">
            <CheckCircle2 size={18} />
            <span>{feedback}</span>
          </div>
        )}
        {prefsFeedback && (
          <div className="feedback-alert success" role="status">
            <CheckCircle2 size={18} />
            <span>{prefsFeedback}</span>
          </div>
        )}
        {error && (
          <div className="feedback-alert danger" role="alert">
            <AlertCircle size={18} />
            <span>{error}</span>
          </div>
        )}

        {dashboardSection === 'access' && (
          <div className="dashboard-grid">
          {/* Left Column: 3D Digital Card & Fast Check-In */}
          <div className="dashboard-col left-col">
            {/* Membership Application / Activation Status Banner */}
            {myEnrollment && myEnrollment.status !== 'active' && (
              <div className={`enrollment-status-card ${myEnrollment.status === 'rejected' ? 'status-rejected' : 'status-pending'}`}>
                <div className="enrollment-status-header">
                  <div className="status-badge-title">
                    {myEnrollment.status === 'pending_verification' || myEnrollment.status === 'Pending Verification at Gym Desk' ? (
                      <span className="badge-warning">Application Under Review</span>
                    ) : myEnrollment.status === 'payment_pending' ? (
                      <span className="badge-gold">Approved: Payment Pending</span>
                    ) : (
                      <span className="badge-danger">Application Rejected</span>
                    )}
                    <h4 className="enrollment-plan-title">{myEnrollment.planName}</h4>
                  </div>
                  <span className="enrollment-ref-tag font-mono">Ref: {myEnrollment.id?.slice(0, 8)}...</span>
                </div>

                <div className="enrollment-status-body">
                  <div className="enrollment-details-grid">
                    <div>
                      <span className="stat-label">Facility</span>
                      <strong className="stat-val">{myEnrollment.branchId || 'Narsobawadi'}</strong>
                    </div>
                    <div>
                      <span className="stat-label">Amount Due</span>
                      <strong className="stat-val gold-text">
                        ₹{(myEnrollment.balanceDue !== undefined ? myEnrollment.balanceDue : myEnrollment.price)?.toLocaleString('en-IN')}
                      </strong>
                    </div>
                    {myEnrollment.invoiceNumber && (
                      <div>
                        <span className="stat-label">Invoice</span>
                        <strong className="stat-val font-mono">{myEnrollment.invoiceNumber}</strong>
                      </div>
                    )}
                  </div>

                  {myEnrollment.status === 'rejected' ? (
                    <div className="enrollment-next-steps rejection-note">
                      <p><strong>Reason:</strong> {myEnrollment.rejectionReason || 'Application details could not be verified.'}</p>
                      <p>Please contact our reception desk or choose a different membership tier.</p>
                    </div>
                  ) : (
                    <div className="enrollment-next-steps">
                      <p className="next-steps-instruction">
                        <strong>Next Step:</strong> {myEnrollment.status === 'payment_pending'
                          ? 'Your plan application was approved by the gym administrator. Please visit the reception desk at Narsobawadi to complete payment (Cash / UPI / Card POS) to activate your keycard access.'
                          : 'Your enrollment request is pending administrator review. Please visit the front reception desk at Narsobawadi to complete verification, finalize payment, and receive your personalized RFID keycard.'}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}

            <MembershipCard3D member={user} onOpenQR={() => setShowQRModal(true)} />

            {/* Daily Check-In Widget */}
            <div className="checkin-widget-card">
              <div className="checkin-header">
                <div>
                  <h3 className="widget-title">Daily Floor Check-In</h3>
                  <p className="widget-sub">Record today&apos;s workout session at RVFitness.</p>
                </div>
                <div className="streak-counter-pill">
                  <Flame size={18} className="gold-text" />
                  <strong>{user?.streakDays || 0} Day Streak</strong>
                </div>
              </div>

              <div className="checkin-action-area">
                {user?.todayCheckedIn ? (
                  <div className="checked-in-banner">
                    <CheckCircle2 size={24} className="gold-text" />
                    <div>
                      <strong>Checked In for Today!</strong>
                      <p>Session recorded. Have an effective training workout.</p>
                    </div>
                  </div>
                ) : (
                  <div className="checkin-secure-flow">
                    <div className="checkin-instruction-banner" style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '12px', background: 'rgba(212, 175, 55, 0.08)', border: '1px solid rgba(212, 175, 55, 0.25)', borderRadius: '6px', marginBottom: '14px' }}>
                      <QrCode size={20} className="gold-text" style={{ flexShrink: 0, marginTop: '2px' }} />
                      <div style={{ fontSize: '13px', lineHeight: '1.4' }}>
                        <strong style={{ color: 'var(--text-primary)', display: 'block', marginBottom: '2px' }}>Physical Attendance Required</strong>
                        <span style={{ color: 'var(--text-secondary)' }}>Remote web check-in has been disabled. Open your dynamic Entry Pass QR code and present it to the gym scanner or reception desk.</span>
                      </div>
                    </div>
                    <button
                      type="button"
                      className="btn-gold-large"
                      style={{ width: '100%', justifyContent: 'center' }}
                      onClick={() => setShowQRModal(true)}
                    >
                      <QrCode size={18} />
                      <span>Open Dynamic Entry Pass QR</span>
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Operational & Facility Notices */}
            {notices.length > 0 && (
              <div className="member-notices-card">
                <div className="routine-header">
                  <Megaphone size={18} className="gold-text" />
                  <h3 className="widget-title">Facility & Operational Notices</h3>
                </div>
                <div className="notices-list-compact">
                  {notices.slice(0, 3).map((n) => (
                    <div key={n.id} className="notice-item-compact">
                      <div className="notice-meta-line">
                        <span className="badge-cat-pill">{n.category}</span>
                        {n.priority === 'urgent' && <span className="badge-priority-urgent">Urgent</span>}
                        {n.priority === 'high' && <span className="badge-priority-high">High</span>}
                        <span className="notice-date-text">{n.publishedAt ? new Date(n.publishedAt).toLocaleDateString() : ''}</span>
                      </div>
                      <strong className="notice-item-title">{n.title}</strong>
                      <p className="notice-item-snippet">{n.body}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Phase 8: Assigned Workout Plans & Live Session Execution */}
            <div className="workout-routine-card">
              <div className="routine-header">
                <Dumbbell size={18} className="gold-text" />
                <h3 className="widget-title">Prescribed Training Routines</h3>
              </div>

              {/* If an active session is currently underway */}
              {activeSession ? (
                <div className="active-session-box">
                  <div className="active-session-header">
                    <span className="live-pulsing-dot" />
                    <strong>Active Workout Session: {activeSession.session_name}</strong>
                    <span className="active-session-time">Started {new Date(activeSession.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                  </div>

                  <p className="active-session-hint">Log your actual performance for each prescribed movement below:</p>

                  <div className="session-exercises-list">
                    {sessionExercises.map((ex, idx) => (
                      <div key={idx} className="session-exercise-row">
                        <div className="ex-info">
                          <strong>{ex.exercise_name}</strong>
                        </div>
                        <div className="ex-inputs-row">
                          <div className="input-with-label">
                            <span className="tiny-label">Sets</span>
                            <input
                              type="number"
                              min="0"
                              max="20"
                              placeholder="Sets"
                              value={ex.sets_completed ?? ''}
                              onChange={(e) => handleUpdateExerciseRow(idx, 'sets_completed', parseInt(e.target.value) || 0)}
                            />
                          </div>
                          <div className="input-with-label">
                            <span className="tiny-label">Reps</span>
                            <input
                              type="number"
                              min="0"
                              max="200"
                              placeholder="Reps"
                              value={ex.reps_completed ?? ''}
                              onChange={(e) => handleUpdateExerciseRow(idx, 'reps_completed', parseInt(e.target.value) || 0)}
                            />
                          </div>
                          <div className="input-with-label">
                            <span className="tiny-label">kg</span>
                            <input
                              type="number"
                              step="0.5"
                              placeholder="kg"
                              value={ex.weight_kg ?? ''}
                              onChange={(e) => handleUpdateExerciseRow(idx, 'weight_kg', parseFloat(e.target.value) || 0)}
                            />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="session-notes-box">
                    <input
                      type="text"
                      placeholder="Session notes (e.g. Energy level, RPE, tempo)"
                      value={sessionNotes}
                      onChange={(e) => setSessionNotes(e.target.value)}
                      className="session-notes-input"
                    />
                  </div>

                  <div className="active-session-actions">
                    <button
                      type="button"
                      className="btn-complete-workout"
                      disabled={completingSession}
                      onClick={handleCompleteWorkout}
                    >
                      <CheckSquare size={16} />
                      <span>{completingSession ? 'Saving Session...' : 'Complete Workout (+5 Pts)'}</span>
                    </button>
                  </div>
                </div>
              ) : (
                /* Assigned Plans List */
                <div className="assigned-plans-list">
                  {assignedPlans.length === 0 ? (
                    <div className="empty-assigned-box">
                      <p className="coach-assignment">
                        No customized routine assigned yet by your strength coach.
                      </p>
                      <button
                        type="button"
                        className="btn-start-free-session"
                        onClick={() => handleStartWorkout(null)}
                      >
                        <Play size={14} />
                        <span>Start Free Training Session</span>
                      </button>
                    </div>
                  ) : (
                    assignedPlans.map((assignment) => {
                      const p = assignment.plan;
                      if (!p) return null;
                      return (
                        <div key={assignment.id} className="assigned-plan-item">
                          <div className="plan-item-header">
                            <div>
                              <strong className="plan-item-name">{p.name}</strong>
                              <span className="plan-coach-sub">Coach: {p.trainer_name || 'Staff Coach'}</span>
                            </div>
                            <span className="badge-cat-pill">{p.difficulty}</span>
                          </div>

                          <p className="plan-item-desc">{p.description || 'Targeted multi-week progression protocol.'}</p>

                          {p.exercises && p.exercises.length > 0 && (
                            <div className="prescribed-routine-preview">
                              <span className="routine-subheading">Prescribed Movements:</span>
                              <div className="routine-pills-row">
                                {p.exercises.map((ex) => (
                                  <span key={ex.id} className="movement-pill">
                                    {ex.name} ({ex.sets ? `${ex.sets}x${ex.reps || 'reps'}` : `${ex.target_duration_seconds}s`})
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}

                          <button
                            type="button"
                            className="btn-start-plan-session"
                            onClick={() => handleStartWorkout(p)}
                          >
                            <Play size={14} />
                            <span>Start Routine Session</span>
                          </button>
                        </div>
                      );
                    })
                  )}
                </div>
              )}

              {/* Workout Session History */}
              {workoutSessions.length > 0 && (
                <div className="member-session-history-section">
                  <span className="history-section-title">Recent Completed Workouts</span>
                  <div className="sessions-compact-list">
                    {workoutSessions.slice(0, 4).map((s) => (
                      <div key={s.id} className="session-compact-row">
                        <div className="session-row-info">
                          <strong className="session-row-name">{s.session_name || 'Workout Session'}</strong>
                          <span className="session-row-meta">
                            {s.session_date} | {s.exercises ? s.exercises.length : 0} movements logged
                          </span>
                        </div>
                        <div className="session-row-status">
                          {s.is_coach_verified ? (
                            <span className="verified-badge-gold" title="Verified by Strength Coach">
                              <Award size={13} /> Coach Verified
                            </span>
                          ) : (
                            <span className="self-reported-badge">Self-Reported</span>
                          )}
                          <span className="session-pts-pill">+5 pts</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right Column: Attendance Heatmap & Verified PRs */}
          <div className="dashboard-col right-col">
            {/* Quick Metrics Bar */}
            <div className="metrics-summary-row">
              <div className="metric-box">
                <span className="metric-label">Monthly Sessions</span>
                <strong className="metric-value">{user?.attendanceThisMonth || 0}</strong>
                <span className="metric-hint">Target: 24/month</span>
              </div>
              <div className="metric-box">
                <span className="metric-label">Active Streak</span>
                <strong className="metric-value gold-text">{user?.streakDays || 0} Days</strong>
                <span className="metric-hint">Consecutive discipline</span>
              </div>
              <div className="metric-box">
                <span className="metric-label">Membership Tier</span>
                <strong className="metric-value">{user?.membershipPlan || 'Quarterly'}</strong>
                <span className="metric-hint">Valid through {user?.validUntil}</span>
              </div>
            </div>

            {/* Gamification & Privacy Profile Card */}
            <div className="gamification-profile-card">
              <div className="gamification-header">
                <div className="gamification-title-group">
                  <Trophy size={20} className="gold-text" />
                  <div>
                    <h3 className="widget-title">Leaderboard Standing & Gaming Handle</h3>
                    <p className="widget-sub">Privacy-first gamification with auditable server points.</p>
                  </div>
                </div>
                <div className="points-pill-gold">
                  <strong>{standing.points} pts</strong>
                  <span>This Month</span>
                </div>
              </div>

              {/* Personal Rank & Progress Stats */}
              <div className="gamification-stats-row">
                <div className="stat-pill-item">
                  <span className="stat-label">Campus Rank</span>
                  <strong className="stat-value gold-text">
                    {standing.rank ? `#${standing.rank} of ${standing.totalMembers}` : 'Unranked'}
                  </strong>
                </div>
                <div className="stat-pill-item">
                  <span className="stat-label">Discipline Tier</span>
                  <strong className="stat-value">{standing.tier}</strong>
                </div>
                <div className="stat-pill-item">
                  <span className="stat-label">Active Days</span>
                  <strong className="stat-value">{standing.distinctDays} Days</strong>
                </div>
              </div>

              {/* Gaming Alias Management */}
              <div className="alias-section">
                <div className="alias-label-row">
                  <span className="setting-label">Public Gaming Alias</span>
                  <span className="alias-privacy-note">
                    Displayed instead of your real name on public boards.
                  </span>
                </div>

                {isEditingAlias ? (
                  <form onSubmit={handleSaveAlias} className="alias-edit-form">
                    <input
                      type="text"
                      className="input-alias"
                      placeholder="e.g. Kingslayer, IronTitan"
                      value={aliasInput}
                      onChange={(e) => setAliasInput(e.target.value)}
                      maxLength={30}
                      minLength={3}
                      autoFocus
                    />
                    <button
                      type="submit"
                      disabled={savingPrefs}
                      className="btn-save-alias"
                    >
                      <Check size={16} />
                      <span>{savingPrefs ? 'Saving...' : 'Save'}</span>
                    </button>
                    <button
                      type="button"
                      className="btn-cancel-alias"
                      onClick={() => {
                        setIsEditingAlias(false);
                        setAliasInput(standing.alias);
                      }}
                    >
                      Cancel
                    </button>
                  </form>
                ) : (
                  <div className="alias-display-row">
                    <div className="current-alias-chip">
                      <span className="avatar-chip mini">
                        {(standing.alias || 'A').charAt(0).toUpperCase()}
                      </span>
                      <strong>{standing.alias || 'Athlete_Unset'}</strong>
                    </div>
                    <button
                      type="button"
                      className="btn-edit-alias"
                      onClick={() => setIsEditingAlias(true)}
                    >
                      <Edit2 size={14} />
                      <span>Edit Handle</span>
                    </button>
                  </div>
                )}
              </div>

              {/* Privacy Opt-In / Opt-Out Switch */}
              <div className="privacy-toggle-section">
                <div className="toggle-info">
                  <div className="toggle-title-line">
                    {standing.isLeaderboardVisible ? (
                      <Eye size={16} className="gold-text" />
                    ) : (
                      <EyeOff size={16} className="text-muted" />
                    )}
                    <strong>Public Leaderboard Visibility</strong>
                  </div>
                  <p className="toggle-explainer">
                    {standing.isLeaderboardVisible
                      ? 'Enabled: Your gaming handle and points appear on campus and community leaderboards.'
                      : 'Disabled (Private): You are hidden from public rankings. You still earn points and track progress here.'}
                  </p>
                </div>
                <button
                  type="button"
                  className={`btn-privacy-switch ${standing.isLeaderboardVisible ? 'active' : 'private'}`}
                  onClick={handleToggleVisibility}
                  disabled={savingPrefs}
                >
                  {standing.isLeaderboardVisible ? 'Public (Visible)' : 'Hidden (Private)'}
                </button>
              </div>

              {/* Recent Points Ledger Preview */}
              {recentLedger.length > 0 && (
                <div className="recent-points-section">
                  <span className="setting-label mb-2">Recent Points Ledger</span>
                  <div className="points-history-list">
                    {recentLedger.map((item) => (
                      <div key={item.id} className="points-history-item">
                        <div className="points-item-meta">
                          <span className="points-source-badge">{item.sourceType.replace('_', ' ')}</span>
                          <span className="points-date">{item.eventDate}</span>
                        </div>
                        <span className={`points-amount ${item.points >= 0 ? 'positive' : 'negative'}`}>
                          {item.points >= 0 ? `+${item.points}` : item.points} pts
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Monthly Attendance Chart / Grid */}
            <div className="attendance-chart-card">
              <div className="chart-header">
                <div className="chart-title-wrap">
                  <Calendar size={18} className="gold-text" />
                  <h3 className="widget-title">October 2026 Attendance Heatmap</h3>
                </div>
                <div className="attendance-legend">
                  <span className="legend-item"><span className="legend-swatch attended" /> Attended</span>
                  <span className="legend-item"><span className="legend-swatch missed" /> Rest Day</span>
                </div>
              </div>

              <div className="calendar-heatmap-grid" aria-label="Monthly workout attendance calendar">
                {currentMonthDays.map((d) => (
                  <div
                    key={d.day}
                    className={`calendar-day-cell ${d.isAttended ? 'attended' : ''} ${d.isToday ? 'today' : ''}`}
                    title={`Oct ${d.day}: ${d.isAttended ? 'Attended Gym' : 'Rest Day'}`}
                  >
                    <span className="cell-day-num">{d.day}</span>
                    {d.isAttended && <span className="cell-check-dot" aria-hidden="true" />}
                  </div>
                ))}
              </div>
              <p className="chart-caption">
                Attendance is verified via desk RFID scan or portal check-in during gym hours.
              </p>
            </div>

            {/* Personal Records (PRs) */}
            <div className="pr-tracker-card">
              <div className="pr-header">
                <h3 className="widget-title">Verified Personal Records (PRs)</h3>
                <span className="pr-certified-tag">Coach Verified</span>
              </div>

              <div className="pr-grid">
                <div className="pr-item">
                  <span className="pr-lift-name">Bench Press</span>
                  <strong className="pr-weight">{user?.prs?.benchPress || '115 kg'}</strong>
                  <span className="pr-rep-tag">1 Rep Max</span>
                </div>
                <div className="pr-item">
                  <span className="pr-lift-name">Back Squat</span>
                  <strong className="pr-weight">{user?.prs?.squat || '160 kg'}</strong>
                  <span className="pr-rep-tag">1 Rep Max</span>
                </div>
                <div className="pr-item">
                  <span className="pr-lift-name">Deadlift</span>
                  <strong className="pr-weight">{user?.prs?.deadlift || '205 kg'}</strong>
                  <span className="pr-rep-tag">1 Rep Max</span>
                </div>
                <div className="pr-item">
                  <span className="pr-lift-name">Strict Pull-Ups</span>
                  <strong className="pr-weight">{user?.prs?.pullUps || '22 reps'}</strong>
                  <span className="pr-rep-tag">Max Unbroken</span>
                </div>
              </div>
            </div>

            {/* Private Fitness Progress Journal */}
            <div className="progress-journal-card">
              <div className="progress-journal-header">
                <div className="journal-title-wrap">
                  <Lock size={16} className="gold-text" />
                  <h3 className="widget-title">Private Fitness Progress Journal</h3>
                </div>
                <button
                  type="button"
                  className="btn-log-progress"
                  onClick={() => setShowProgressModal(true)}
                >
                  <Plus size={14} />
                  <span>Log Metric</span>
                </button>
              </div>

              <p className="privacy-guarantee-text">
                Your body measurements, weight, and private notes are visible only to you. They are never published on leaderboards.
              </p>

              {progressRecords.length === 0 ? (
                <div className="empty-journal-box">
                  <p>No confidential metrics logged yet. Track your body weight, measurements, or lift milestones privately.</p>
                </div>
              ) : (
                <div className="progress-history-chips">
                  {progressRecords.slice(0, 6).map((rec) => (
                    <div key={rec.id} className="progress-history-item">
                      <div className="progress-item-left">
                        <span className="metric-tag">{rec.record_type.replace('_', ' ')}</span>
                        <strong className="metric-val">
                          {rec.value != null ? `${rec.value} ${rec.unit || ''}` : rec.text_value}
                        </strong>
                      </div>
                      <div className="progress-item-right">
                        <span className="metric-date">{rec.recorded_date}</span>
                        {rec.is_private ? (
                          <span className="lock-pill" title="Private to Member"><Lock size={10} /> Private</span>
                        ) : (
                          <span className="unlock-pill" title="Shared with Coach"><Unlock size={10} /> Shared</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
        )}

        {dashboardSection === 'profile' && (
          <MemberProfileView
            currentUser={user}
            onUserUpdate={onUserUpdate}
          />
        )}

        {dashboardSection === 'performance' && (
          <FitnessPerformanceTracker
            currentUser={user}
          />
        )}
      </div>

      {showQRModal && (
        <MemberQRModal
          member={user}
          onClose={() => setShowQRModal(false)}
        />
      )}

      {/* Modal: Log Fitness Metric */}
      {showProgressModal && (
        <div className="modal-backdrop">
          <div className="modal-dialog-compact">
            <div className="modal-header">
              <h3>Log Confidential Fitness Metric</h3>
              <button
                type="button"
                className="btn-close-modal"
                onClick={() => setShowProgressModal(false)}
              >
                &times;
              </button>
            </div>
            <form onSubmit={handleSaveProgress} className="plan-form">
              <div className="form-group">
                <label>Metric Type *</label>
                <select
                  value={progressForm.record_type}
                  onChange={(e) => setProgressForm({ ...progressForm, record_type: e.target.value })}
                >
                  <option value="body_weight">Body Weight</option>
                  <option value="body_fat">Body Fat %</option>
                  <option value="personal_record">Personal Record (PR)</option>
                  <option value="chest">Chest Circumference</option>
                  <option value="waist">Waist Circumference</option>
                  <option value="hips">Hips Circumference</option>
                  <option value="biceps">Biceps Circumference</option>
                  <option value="notes">Progress Note</option>
                </select>
              </div>

              <div className="form-row">
                <div className="form-group flex-2">
                  <label>Value</label>
                  <input
                    type="number"
                    step="0.1"
                    placeholder="e.g. 74.5"
                    value={progressForm.value}
                    onChange={(e) => setProgressForm({ ...progressForm, value: e.target.value })}
                  />
                </div>
                <div className="form-group flex-1">
                  <label>Unit</label>
                  <input
                    type="text"
                    placeholder="kg, cm, %"
                    value={progressForm.unit}
                    onChange={(e) => setProgressForm({ ...progressForm, unit: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Notes / Context</label>
                <textarea
                  rows="2"
                  placeholder="e.g. Weighed first thing in the morning fasted."
                  value={progressForm.notes}
                  onChange={(e) => setProgressForm({ ...progressForm, notes: e.target.value })}
                />
              </div>

              <div className="checkbox-privacy-row">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={progressForm.is_private}
                    onChange={(e) => setProgressForm({ ...progressForm, is_private: e.target.checked })}
                  />
                  <span>Keep this record strictly private (hidden from coach)</span>
                </label>
              </div>

              <div className="modal-actions-bar">
                <button
                  type="button"
                  className="btn-cancel"
                  onClick={() => setShowProgressModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-confirm-save">
                  Save Metric
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
