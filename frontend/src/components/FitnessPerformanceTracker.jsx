import { useState, useEffect } from 'react';
import {
  Activity,
  Flame,
  Scale,
  Target,
  Trophy,
  Dumbbell,
  Calendar,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Plus,
  TrendingUp,
  TrendingDown,
  Award,
  ChevronRight,
  ShieldCheck,
  Clock,
  User,
  Users
} from 'lucide-react';
import {
  fetchMyPerformanceSummary,
  fetchMyWeightHistory,
  fetchMyCompletedWorkouts,
  recordCompletedWorkout,
  fetchCoachAssignedMembers,
  fetchMemberPerformanceSummary,
  fetchMemberWeightHistory,
  fetchMemberCompletedWorkouts
} from '../api';

export default function FitnessPerformanceTracker({
  currentUser,
  targetMemberId = null,
  isCoachView = false
}) {
  const [summary, setSummary] = useState(null);
  const [weightHistory, setWeightHistory] = useState([]);
  const [workoutSessions, setWorkoutSessions] = useState([]);
  const [coachMembers, setCoachMembers] = useState([]);
  const [selectedCoachMember, setSelectedCoachMember] = useState(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [feedback, setFeedback] = useState(null);

  // Active tracker tab: 'overview' | 'weight_chart' | 'workouts' | 'coach_roster'
  const [activeTab, setActiveTab] = useState(isCoachView ? 'coach_roster' : 'overview');

  // Workout Session Logging Modal
  const [showLogWorkoutModal, setShowLogWorkoutModal] = useState(false);
  const [submittingWorkout, setSubmittingWorkout] = useState(false);
  const [workoutForm, setWorkoutForm] = useState({
    sessionName: 'Strength & Hypertrophy Session',
    sessionDate: new Date().toISOString().split('T')[0],
    durationMinutes: 45,
    rpe: 8,
    notes: '',
    exercises: [
      { exerciseName: 'Barbell Back Squat', sets: 4, reps: 8, weightKg: 80 },
      { exerciseName: 'Barbell Bench Press', sets: 4, reps: 8, weightKg: 65 },
    ],
  });

  const isCoach = ['trainer', 'org_admin', 'admin'].includes(currentUser?.role);
  const effectiveUserId = selectedCoachMember?.memberId || targetMemberId || currentUser?.id;

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      if (isCoach && !targetMemberId && !selectedCoachMember) {
        // Load coach assigned members overview
        const membersData = await fetchCoachAssignedMembers().catch(() => []);
        setCoachMembers(membersData || []);
      }

      if (effectiveUserId) {
        const [sumData, wtData, wSessions] = await Promise.all([
          selectedCoachMember
            ? fetchMemberPerformanceSummary(selectedCoachMember.memberId)
            : fetchMyPerformanceSummary(),
          selectedCoachMember
            ? fetchMemberWeightHistory(selectedCoachMember.memberId)
            : fetchMyWeightHistory(),
          selectedCoachMember
            ? fetchMemberCompletedWorkouts(selectedCoachMember.memberId, 25, 0)
            : fetchMyCompletedWorkouts(25, 0),
        ]);
        setSummary(sumData);
        setWeightHistory(wtData || []);
        setWorkoutSessions(wSessions || []);
      }
    } catch (err) {
      setError(err.message || 'Unable to load performance metrics.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [effectiveUserId, selectedCoachMember]);

  const handleAddExerciseRow = () => {
    setWorkoutForm((prev) => ({
      ...prev,
      exercises: [
        ...prev.exercises,
        { exerciseName: '', sets: 3, reps: 10, weightKg: 0 },
      ],
    }));
  };

  const handleRemoveExerciseRow = (index) => {
    setWorkoutForm((prev) => ({
      ...prev,
      exercises: prev.exercises.filter((_, i) => i !== index),
    }));
  };

  const handleExerciseChange = (index, field, value) => {
    setWorkoutForm((prev) => {
      const updated = [...prev.exercises];
      updated[index] = { ...updated[index], [field]: value };
      return { ...prev, exercises: updated };
    });
  };

  const handleLogWorkoutSubmit = async (e) => {
    e.preventDefault();
    setSubmittingWorkout(true);
    setError(null);
    try {
      const payload = {
        sessionName: workoutForm.sessionName.trim(),
        sessionDate: workoutForm.sessionDate,
        durationMinutes: parseInt(workoutForm.durationMinutes, 10) || 45,
        rpe: parseInt(workoutForm.rpe, 10) || 7,
        notes: workoutForm.notes.trim() || undefined,
        exercises: workoutForm.exercises
          .filter((ex) => ex.exerciseName && ex.exerciseName.trim())
          .map((ex) => ({
            exerciseName: ex.exerciseName.trim(),
            sets: ex.sets ? parseInt(ex.sets, 10) : undefined,
            reps: ex.reps ? parseInt(ex.reps, 10) : undefined,
            weightKg: ex.weightKg ? parseFloat(ex.weightKg) : undefined,
          })),
      };

      await recordCompletedWorkout(payload, selectedCoachMember?.memberId || null);
      setFeedback('Workout session recorded successfully! Points and personal records awarded.');
      setShowLogWorkoutModal(false);
      setWorkoutForm({
        sessionName: 'Strength & Hypertrophy Session',
        sessionDate: new Date().toISOString().split('T')[0],
        durationMinutes: 45,
        rpe: 8,
        notes: '',
        exercises: [
          { exerciseName: 'Barbell Back Squat', sets: 4, reps: 8, weightKg: 80 },
          { exerciseName: 'Barbell Bench Press', sets: 4, reps: 8, weightKg: 65 },
        ],
      });
      await loadData();
    } catch (err) {
      setError(err.message || 'Failed to record workout session.');
    } finally {
      setSubmittingWorkout(false);
    }
  };

  // Helper to calculate SVG chart points for weight progress
  const renderWeightSVGChart = () => {
    if (!weightHistory || weightHistory.length < 2) {
      return (
        <div className="chart-empty-state">
          <Scale size={32} className="gold-text" />
          <p>At least two dated weigh-in measurements are required to plot progress trends.</p>
        </div>
      );
    }

    const weights = weightHistory.map((w) => w.weightKg);
    const minW = Math.floor(Math.min(...weights) - 2);
    const maxW = Math.ceil(Math.max(...weights) + 2);
    const rangeW = maxW - minW || 1;

    const width = 680;
    const height = 240;
    const padding = 45;

    const points = weightHistory.map((item, idx) => {
      const x = padding + (idx / (weightHistory.length - 1)) * (width - padding * 2);
      const y = height - padding - ((item.weightKg - minW) / rangeW) * (height - padding * 2);
      return { x, y, weight: item.weightKg, date: item.date };
    });

    const pointsString = points.map((p) => `${p.x},${p.y}`).join(' ');

    return (
      <div className="svg-chart-container">
        <svg viewBox={`0 0 ${width} ${height}`} className="progress-svg-chart">
          {/* Y Axis Guide Lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((pct, i) => {
            const y = height - padding - pct * (height - padding * 2);
            const val = (minW + pct * rangeW).toFixed(1);
            return (
              <g key={i}>
                <line x1={padding} y1={y} x2={width - padding} y2={y} stroke="#2a2e39" strokeDasharray="3 3" />
                <text x={padding - 8} y={y + 4} textAnchor="end" fill="#8892b0" fontSize="11">
                  {val} kg
                </text>
              </g>
            );
          })}

          {/* Area fill */}
          <polygon
            points={`${points[0].x},${height - padding} ${pointsString} ${points[points.length - 1].x},${height - padding}`}
            fill="url(#weightGradient)"
            opacity="0.25"
          />

          {/* Connecting Trend Line */}
          <polyline
            points={pointsString}
            fill="none"
            stroke="#d4af37"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Data Points */}
          {points.map((p, idx) => (
            <g key={idx} className="chart-point-group">
              <circle cx={p.x} cy={p.y} r="5" fill="#14171f" stroke="#d4af37" strokeWidth="2.5" />
              <text x={p.x} y={p.y - 10} textAnchor="middle" fill="#f0f3f8" fontSize="10" fontWeight="bold">
                {p.weight}
              </text>
              <text x={p.x} y={height - padding + 16} textAnchor="middle" fill="#8892b0" fontSize="9">
                {p.date.slice(5)}
              </text>
            </g>
          ))}

          <defs>
            <linearGradient id="weightGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#d4af37" stopOpacity="0.8" />
              <stop offset="100%" stopColor="#d4af37" stopOpacity="0.0" />
            </linearGradient>
          </defs>
        </svg>
      </div>
    );
  };

  return (
    <div className="fitness-tracker-container">
      {/* Tracker Header */}
      <div className="tracker-header-row">
        <div>
          <h2>Fitness Performance & Progress Tracker</h2>
          <p className="tracker-sub">
            {selectedCoachMember
              ? `Reviewing training progress for: ${selectedCoachMember.memberName}`
              : 'Verifiable personal records, goal adherence, and physical progress metrics.'}
          </p>
        </div>

        <div className="tracker-actions-right">
          {selectedCoachMember && (
            <button
              type="button"
              className="btn-outline-gold"
              onClick={() => {
                setSelectedCoachMember(null);
                setActiveTab('coach_roster');
              }}
            >
              Back to Coach Roster
            </button>
          )}

          <button
            type="button"
            className="btn-gold-action"
            onClick={() => setShowLogWorkoutModal(true)}
          >
            <Plus size={16} />
            <span>Log Completed Workout</span>
          </button>
        </div>
      </div>

      {/* Feedback Alerts */}
      {feedback && (
        <div className="feedback-banner success">
          <CheckCircle2 size={16} />
          <span>{feedback}</span>
        </div>
      )}
      {error && (
        <div className="feedback-banner error">
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="tracker-nav-tabs">
        {isCoach && !targetMemberId && (
          <button
            type="button"
            className={`tracker-tab-btn ${activeTab === 'coach_roster' ? 'active' : ''}`}
            onClick={() => setActiveTab('coach_roster')}
          >
            <Users size={16} /> Assigned Athletes ({coachMembers.length})
          </button>
        )}
        <button
          type="button"
          className={`tracker-tab-btn ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          <Activity size={16} /> Performance Summary
        </button>
        <button
          type="button"
          className={`tracker-tab-btn ${activeTab === 'weight_chart' ? 'active' : ''}`}
          onClick={() => setActiveTab('weight_chart')}
        >
          <TrendingUp size={16} /> Weight Trend ({weightHistory.length} Weigh-ins)
        </button>
        <button
          type="button"
          className={`tracker-tab-btn ${activeTab === 'workouts' ? 'active' : ''}`}
          onClick={() => setActiveTab('workouts')}
        >
          <Dumbbell size={16} /> Completed Workouts ({workoutSessions.length})
        </button>
      </div>

      {/* TAB: COACH ROSTER */}
      {activeTab === 'coach_roster' && isCoach && (
        <div className="coach-roster-pane">
          <div className="roster-header">
            <h3>Assigned Member Training Oversight</h3>
            <p className="card-subtitle">
              Monitor goal progress, monthly workout volume, weight trends, and consented movement restrictions.
            </p>
          </div>

          {coachMembers.length === 0 ? (
            <div className="empty-roster-state">
              <Users size={36} className="gold-text" />
              <h4>No Members Currently Assigned</h4>
              <p>When members are assigned to your coaching roster, their progress metrics will appear here.</p>
            </div>
          ) : (
            <div className="coach-members-grid">
              {coachMembers.map((m) => (
                <div key={m.memberId} className="coach-member-card">
                  <div className="member-card-top">
                    <div>
                      <h4 className="card-member-name">{m.memberName}</h4>
                      <p className="card-member-meta">
                        {m.memberEmail} | Plan: {m.membershipPlan}
                      </p>
                    </div>
                    <span className="goal-badge">{m.primaryGoal?.replace('_', ' ')?.toUpperCase()}</span>
                  </div>

                  <div className="member-card-metrics">
                    <div className="c-metric">
                      <span className="lbl">Current Weight</span>
                      <span className="val">{m.currentWeightKg ? `${m.currentWeightKg} kg` : 'N/A'}</span>
                    </div>
                    <div className="c-metric">
                      <span className="lbl">Net Weight Change</span>
                      <span className="val gold-text">
                        {m.netWeightChangeKg !== null && m.netWeightChangeKg !== undefined
                          ? `${m.netWeightChangeKg > 0 ? '+' : ''}${m.netWeightChangeKg} kg`
                          : 'Baseline Pending'}
                      </span>
                    </div>
                    <div className="c-metric">
                      <span className="lbl">Workouts This Month</span>
                      <span className="val">{m.workoutsCompletedThisMonth}</span>
                    </div>
                    <div className="c-metric">
                      <span className="lbl">Streak</span>
                      <span className="val">{m.streakDays} Days</span>
                    </div>
                  </div>

                  {m.hasHealthRestrictions && (
                    <div className="coach-restriction-callout">
                      <AlertTriangle size={14} className="gold-text" />
                      <span><strong>Restriction:</strong> {m.movementRestrictions || 'Exercise limitations reported.'}</span>
                    </div>
                  )}

                  <div className="member-card-actions">
                    <button
                      type="button"
                      className="btn-gold-small full-width"
                      onClick={() => {
                        setSelectedCoachMember(m);
                        setActiveTab('overview');
                      }}
                    >
                      <span>Inspect Training Analytics</span>
                      <ChevronRight size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB: OVERVIEW */}
      {activeTab === 'overview' && (
        <div className="tracker-overview-pane">
          {/* Summary Metric Cards */}
          <div className="tracker-stats-grid">
            <div className="tracker-stat-card">
              <div className="card-icon-wrap gold">
                <Scale size={22} />
              </div>
              <div className="card-content">
                <span className="stat-label">Current Weight</span>
                <div className="stat-value">
                  {summary?.currentWeightKg ? `${summary.currentWeightKg} kg` : 'Not recorded'}
                </div>
                <small className="stat-sub">
                  Baseline: {summary?.baselineWeightKg ? `${summary.baselineWeightKg} kg` : 'No baseline yet'}
                </small>
              </div>
            </div>

            <div className="tracker-stat-card">
              <div className="card-icon-wrap green">
                <Target size={22} />
              </div>
              <div className="card-content">
                <span className="stat-label">Net Weight Change</span>
                <div className="stat-value gold-text">
                  {summary?.netWeightChangeKg !== null && summary?.netWeightChangeKg !== undefined
                    ? `${summary.netWeightChangeKg > 0 ? '+' : ''}${summary.netWeightChangeKg} kg`
                    : 'Pending Data'}
                </div>
                <small className="stat-sub">
                  Calculation: Latest ({summary?.currentWeightKg || 0}) - Baseline ({summary?.baselineWeightKg || 0})
                </small>
              </div>
            </div>

            <div className="tracker-stat-card">
              <div className="card-icon-wrap purple">
                <Dumbbell size={22} />
              </div>
              <div className="card-content">
                <span className="stat-label">Monthly Workouts</span>
                <div className="stat-value">{summary?.workoutsCompletedThisMonth || 0}</div>
                <small className="stat-sub">
                  Week: {summary?.workoutsCompletedThisWeek || 0} | Total: {summary?.totalCompletedWorkouts || 0}
                </small>
              </div>
            </div>

            <div className="tracker-stat-card">
              <div className="card-icon-wrap orange">
                <Flame size={22} />
              </div>
              <div className="card-content">
                <span className="stat-label">Consistency Streak</span>
                <div className="stat-value">{summary?.streakDays || 0} Days</div>
                <small className="stat-sub">
                  Attendance check-ins this month: {summary?.attendanceThisMonth || 0}
                </small>
              </div>
            </div>
          </div>

          {/* Goal Progress Banner */}
          <div className="goal-progress-banner">
            <div className="banner-top">
              <div>
                <h4>Training Objective: {summary?.primaryGoal?.replace('_', ' ')?.toUpperCase()}</h4>
                <p className="text-muted">{summary?.goalStatusMessage}</p>
              </div>
              {summary?.goalProgressPct !== null && summary?.goalProgressPct !== undefined && (
                <div className="progress-pct-badge">
                  {summary.goalProgressPct}% Target Reached
                </div>
              )}
            </div>

            {summary?.goalProgressPct !== null && summary?.goalProgressPct !== undefined && (
              <div className="progress-bar-track">
                <div
                  className="progress-bar-fill"
                  style={{ width: `${Math.min(100, Math.max(0, summary.goalProgressPct))}%` }}
                />
              </div>
            )}
          </div>

          {/* Two-Column Section: Personal Records & Latest Circumferences */}
          <div className="overview-split-row">
            {/* Recent Personal Records */}
            <div className="overview-card">
              <div className="card-header">
                <Trophy size={18} className="gold-text" />
                <h3>Personal Best Records (PRs)</h3>
              </div>
              {summary?.recentPRs && summary.recentPRs.length > 0 ? (
                <div className="prs-list">
                  {summary.recentPRs.map((pr, idx) => (
                    <div key={idx} className="pr-item">
                      <div className="pr-item-main">
                        <strong className="exercise-name">{pr.exerciseName}</strong>
                        <span className="pr-date">{pr.recordedAt}</span>
                      </div>
                      <div className="pr-item-value">
                        <span className="pr-val">{pr.value} {pr.unit}</span>
                        {pr.reps > 1 && <span className="reps-tag">x{pr.reps} reps</span>}
                        {pr.isCoachVerified && (
                          <span className="verified-badge" title="Coach Verified Performance">
                            <ShieldCheck size={12} /> Verified
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="card-empty-note">
                  <p>No Personal Records logged yet. Complete heavy lifts in workout logs to establish PRs.</p>
                </div>
              )}
            </div>

            {/* Latest Anatomical Circumferences */}
            <div className="overview-card">
              <div className="card-header">
                <Scale size={18} className="gold-text" />
                <h3>Latest Body Measurements</h3>
              </div>
              {summary?.latestMeasurements ? (
                <div className="circumference-grid">
                  <div className="c-item">
                    <span className="c-lbl">Chest</span>
                    <span className="c-val">{summary.latestMeasurements.chestCm ? `${summary.latestMeasurements.chestCm} cm` : '-'}</span>
                  </div>
                  <div className="c-item">
                    <span className="c-lbl">Waist</span>
                    <span className="c-val">{summary.latestMeasurements.waistCm ? `${summary.latestMeasurements.waistCm} cm` : '-'}</span>
                  </div>
                  <div className="c-item">
                    <span className="c-lbl">Hips</span>
                    <span className="c-val">{summary.latestMeasurements.hipsCm ? `${summary.latestMeasurements.hipsCm} cm` : '-'}</span>
                  </div>
                  <div className="c-item">
                    <span className="c-lbl">Arms</span>
                    <span className="c-val">{summary.latestMeasurements.armsCm ? `${summary.latestMeasurements.armsCm} cm` : '-'}</span>
                  </div>
                  <div className="c-item">
                    <span className="c-lbl">Body Fat %</span>
                    <span className="c-val">{summary.latestMeasurements.bodyFatPct ? `${summary.latestMeasurements.bodyFatPct}%` : '-'}</span>
                  </div>
                  <div className="c-item">
                    <span className="c-lbl">Height</span>
                    <span className="c-val">{summary.latestMeasurements.heightCm ? `${summary.latestMeasurements.heightCm} cm` : '-'}</span>
                  </div>
                </div>
              ) : (
                <div className="card-empty-note">
                  <p>No circumferences recorded yet. Record body measurements on the profile tab.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB: WEIGHT PROGRESS CHART */}
      {activeTab === 'weight_chart' && (
        <div className="tracker-chart-pane">
          <div className="chart-header-card">
            <div className="header-info">
              <h3>Chronological Body Weight Progression</h3>
              <p className="card-subtitle">
                Time-series weigh-in trajectory plotted from authentic dated measurement records.
              </p>
            </div>
            {summary?.baselineWeightKg && summary?.currentWeightKg && (
              <div className="chart-meta-badge">
                Baseline: <strong>{summary.baselineWeightKg} kg</strong> → Latest: <strong>{summary.currentWeightKg} kg</strong>
                <span className="delta-tag">({summary.netWeightChangeKg > 0 ? '+' : ''}{summary.netWeightChangeKg} kg)</span>
              </div>
            )}
          </div>

          <div className="chart-canvas-box">
            {renderWeightSVGChart()}
          </div>

          {/* Historical Weigh-in Data Table */}
          <div className="weight-history-table-card">
            <h4>Recorded Weigh-in Log</h4>
            <div className="table-responsive">
              <table className="weighin-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Weight</th>
                    <th>Recorded By</th>
                    <th>Role</th>
                    <th>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {weightHistory.map((w, idx) => (
                    <tr key={idx}>
                      <td><strong>{w.date}</strong></td>
                      <td className="gold-text">{w.weightKg} kg</td>
                      <td>{w.recordedBy}</td>
                      <td><span className={`role-tag ${w.recordedByRole}`}>{w.recordedByRole}</span></td>
                      <td>{w.notes || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB: COMPLETED WORKOUTS */}
      {activeTab === 'workouts' && (
        <div className="tracker-workouts-pane">
          <div className="workouts-top-bar">
            <div>
              <h3>Completed Workout Sessions</h3>
              <p className="card-subtitle">
                Authentic logged workouts distinguishing completed sessions from scheduled plans.
              </p>
            </div>
            <button
              type="button"
              className="btn-gold-action"
              onClick={() => setShowLogWorkoutModal(true)}
            >
              <Plus size={16} />
              <span>Record Completed Session</span>
            </button>
          </div>

          {workoutSessions.length === 0 ? (
            <div className="empty-workouts-card">
              <Dumbbell size={36} className="gold-text" />
              <h4>No Completed Workouts Recorded</h4>
              <p>Record your workout sets and weights lifted to track exercise performance over time.</p>
            </div>
          ) : (
            <div className="completed-sessions-list">
              {workoutSessions.map((s) => (
                <div key={s.id} className="completed-session-card">
                  <div className="session-card-header">
                    <div>
                      <h4 className="session-title">{s.session_name || 'Workout Session'}</h4>
                      <div className="session-meta-row">
                        <span><Calendar size={13} /> {s.session_date}</span>
                        {s.duration_minutes && <span><Clock size={13} /> {s.duration_minutes} Mins</span>}
                        {s.rpe && <span className="rpe-badge">RPE {s.rpe}/10</span>}
                        {s.is_coach_verified && (
                          <span className="coach-verified-badge">
                            <ShieldCheck size={12} /> Coach Verified
                          </span>
                        )}
                      </div>
                    </div>
                    <span className="status-completed-pill">COMPLETED</span>
                  </div>

                  {s.exercises && s.exercises.length > 0 && (
                    <div className="session-exercises-list">
                      {s.exercises.map((ex, exIdx) => (
                        <div key={ex.id || exIdx} className="session-exercise-row">
                          <span className="ex-name">{ex.exercise_name}</span>
                          <span className="ex-details">
                            {ex.sets_completed && `${ex.sets_completed} sets`}
                            {ex.reps_completed && ` x ${ex.reps_completed} reps`}
                            {ex.weight_kg && ` @ ${ex.weight_kg} kg`}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {s.notes && (
                    <div className="session-notes-box">
                      <p><em>Notes: {s.notes}</em></p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* MODAL: LOG COMPLETED WORKOUT */}
      {showLogWorkoutModal && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="workout-modal-title">
          <div className="workout-modal-card">
            <div className="modal-header">
              <div className="modal-title-lockup">
                <Dumbbell size={20} className="gold-text" />
                <h3 id="workout-modal-title">Record Completed Workout Session</h3>
              </div>
              <button
                type="button"
                className="close-btn"
                onClick={() => setShowLogWorkoutModal(false)}
              >
                &times;
              </button>
            </div>

            <form onSubmit={handleLogWorkoutSubmit} className="workout-modal-form">
              <div className="form-grid-2">
                <div className="form-group">
                  <label htmlFor="w-name">Session Name *</label>
                  <input
                    id="w-name"
                    type="text"
                    className="profile-input"
                    value={workoutForm.sessionName}
                    onChange={(e) => setWorkoutForm({ ...workoutForm, sessionName: e.target.value })}
                    required
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="w-date">Workout Date *</label>
                  <input
                    id="w-date"
                    type="date"
                    className="profile-input"
                    value={workoutForm.sessionDate}
                    onChange={(e) => setWorkoutForm({ ...workoutForm, sessionDate: e.target.value })}
                    max={new Date().toISOString().split('T')[0]}
                    required
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="w-dur">Duration (Minutes)</label>
                  <input
                    id="w-dur"
                    type="number"
                    min="1"
                    max="600"
                    className="profile-input"
                    value={workoutForm.durationMinutes}
                    onChange={(e) => setWorkoutForm({ ...workoutForm, durationMinutes: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="w-rpe">Perceived Exertion (RPE 1-10)</label>
                  <select
                    id="w-rpe"
                    className="profile-input"
                    value={workoutForm.rpe}
                    onChange={(e) => setWorkoutForm({ ...workoutForm, rpe: e.target.value })}
                  >
                    <option value="6">6 - Moderate Effort</option>
                    <option value="7">7 - Vigorous (3 reps in reserve)</option>
                    <option value="8">8 - Heavy (2 reps in reserve)</option>
                    <option value="9">9 - Very Heavy (1 rep in reserve)</option>
                    <option value="10">10 - Maximum Effort / PR Attempt</option>
                  </select>
                </div>
              </div>

              {/* Exercises Performed Section */}
              <div className="exercises-form-section">
                <div className="exercises-section-header">
                  <h4>Exercises Performed</h4>
                  <button
                    type="button"
                    className="btn-outline-gold-sm"
                    onClick={handleAddExerciseRow}
                  >
                    <Plus size={14} /> Add Exercise
                  </button>
                </div>

                {workoutForm.exercises.map((ex, idx) => (
                  <div key={idx} className="exercise-input-row">
                    <div className="ex-field-name">
                      <input
                        type="text"
                        className="profile-input"
                        placeholder="Exercise name (e.g. Barbell Squat)"
                        value={ex.exerciseName}
                        onChange={(e) => handleExerciseChange(idx, 'exerciseName', e.target.value)}
                        required
                      />
                    </div>
                    <div className="ex-field-sm">
                      <input
                        type="number"
                        min="1"
                        max="50"
                        className="profile-input"
                        placeholder="Sets"
                        value={ex.sets}
                        onChange={(e) => handleExerciseChange(idx, 'sets', e.target.value)}
                      />
                    </div>
                    <div className="ex-field-sm">
                      <input
                        type="number"
                        min="1"
                        max="500"
                        className="profile-input"
                        placeholder="Reps"
                        value={ex.reps}
                        onChange={(e) => handleExerciseChange(idx, 'reps', e.target.value)}
                      />
                    </div>
                    <div className="ex-field-sm">
                      <input
                        type="number"
                        step="0.5"
                        min="0"
                        max="1000"
                        className="profile-input"
                        placeholder="Kg"
                        value={ex.weightKg}
                        onChange={(e) => handleExerciseChange(idx, 'weightKg', e.target.value)}
                      />
                    </div>
                    {workoutForm.exercises.length > 1 && (
                      <button
                        type="button"
                        className="btn-remove-row"
                        onClick={() => handleRemoveExerciseRow(idx)}
                        title="Remove Exercise"
                      >
                        &times;
                      </button>
                    )}
                  </div>
                ))}
              </div>

              <div className="form-group full-width">
                <label htmlFor="w-notes">Session Notes (Optional)</label>
                <textarea
                  id="w-notes"
                  rows={2}
                  className="profile-input"
                  placeholder="e.g. Good intensity, increased bench press load by 2.5kg."
                  value={workoutForm.notes}
                  onChange={(e) => setWorkoutForm({ ...workoutForm, notes: e.target.value })}
                />
              </div>

              <div className="modal-actions-row">
                <button
                  type="button"
                  className="btn-cancel"
                  onClick={() => setShowLogWorkoutModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-gold-save"
                  disabled={submittingWorkout}
                >
                  {submittingWorkout ? 'Recording Session...' : 'Save Completed Workout'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
