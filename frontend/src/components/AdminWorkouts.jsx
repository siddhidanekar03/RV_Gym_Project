import { useState, useEffect } from 'react';
import {
  Dumbbell,
  Plus,
  Trash2,
  UserCheck,
  CheckCircle2,
  Clock,
  Shield,
  Search,
  Filter,
  AlertCircle,
  Award
} from 'lucide-react';
import {
  fetchWorkoutPlans,
  createWorkoutPlan,
  archiveWorkoutPlan,
  assignPlanToMember,
  fetchWorkoutSessions,
  verifyWorkoutSession,
  fetchFitnessProgress,
} from '../api';

export default function AdminWorkouts({ currentUser }) {
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [feedback, setFeedback] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [activeTab, setActiveTab] = useState('plans'); // 'plans' | 'verification' | 'progress'

  // Modal states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showAssignModal, setShowAssignModal] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState(null);

  // New plan form state
  const [newPlan, setNewPlan] = useState({
    name: '',
    description: '',
    goal: 'strength',
    difficulty: 'intermediate',
    duration_weeks: 4,
    status: 'active',
    exercises: [
      {
        day_number: 1,
        day_name: 'Day 1: Compound Foundations',
        exercise_order: 1,
        name: 'Barbell Back Squat',
        instructions: 'Maintain upright posture, brace core, hit parallel depth.',
        sets: 4,
        reps: 8,
        target_weight_kg: 80,
        rest_seconds: 90,
      },
    ],
  });

  // Assign form state
  const [assignMemberId, setAssignMemberId] = useState('');
  const [assignNotes, setAssignNotes] = useState('');

  // Verification & progress state
  const [memberIdQuery, setMemberIdQuery] = useState('');
  const [recentSessions, setRecentSessions] = useState([]);
  const [progressRecords, setProgressRecords] = useState([]);
  const [searchingMember, setSearchingMember] = useState(false);

  const loadPlans = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWorkoutPlans({
        branchId: currentUser?.role === 'trainer' ? currentUser.branch_id : undefined,
        status: statusFilter || undefined,
      });
      setPlans(res || []);
    } catch (err) {
      setError(err.message || 'Failed to load workout plans.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPlans();
  }, [statusFilter]);

  const handleAddExerciseRow = () => {
    const nextOrder = newPlan.exercises.length + 1;
    setNewPlan({
      ...newPlan,
      exercises: [
        ...newPlan.exercises,
        {
          day_number: 1,
          day_name: 'Day 1',
          exercise_order: nextOrder,
          name: '',
          instructions: '',
          sets: 3,
          reps: 10,
          target_weight_kg: 20,
          rest_seconds: 60,
        },
      ],
    });
  };

  const handleRemoveExerciseRow = (idx) => {
    const updated = newPlan.exercises.filter((_, i) => i !== idx);
    setNewPlan({ ...newPlan, exercises: updated });
  };

  const handleExerciseChange = (idx, field, val) => {
    const updated = [...newPlan.exercises];
    updated[idx][field] = val;
    setNewPlan({ ...newPlan, exercises: updated });
  };

  const handleCreatePlan = async (e) => {
    e.preventDefault();
    setError(null);
    setFeedback(null);

    if (!newPlan.name.trim()) {
      setError('Please provide a descriptive workout plan name.');
      return;
    }

    try {
      await createWorkoutPlan(newPlan);
      setFeedback(`Workout plan "${newPlan.name}" created successfully.`);
      setShowCreateModal(false);
      setNewPlan({
        name: '',
        description: '',
        goal: 'strength',
        difficulty: 'intermediate',
        duration_weeks: 4,
        status: 'active',
        exercises: [
          {
            day_number: 1,
            day_name: 'Day 1',
            exercise_order: 1,
            name: '',
            instructions: '',
            sets: 3,
            reps: 10,
            target_weight_kg: 0,
            rest_seconds: 60,
          },
        ],
      });
      await loadPlans();
    } catch (err) {
      setError(err.message || 'Failed to create plan.');
    }
  };

  const handleArchivePlan = async (planId) => {
    if (!window.confirm('Archive this workout plan? Historical session data will be preserved.')) return;
    try {
      await archiveWorkoutPlan(planId);
      setFeedback('Workout plan archived.');
      await loadPlans();
    } catch (err) {
      setError(err.message || 'Failed to archive plan.');
    }
  };

  const handleAssignPlan = async (e) => {
    e.preventDefault();
    if (!selectedPlan || !assignMemberId.trim()) return;
    setError(null);
    setFeedback(null);

    try {
      await assignPlanToMember(selectedPlan.id, {
        member_id: assignMemberId.trim(),
        notes: assignNotes.trim() || undefined,
      });
      setFeedback(`Plan successfully assigned to member ${assignMemberId}.`);
      setShowAssignModal(false);
      setAssignMemberId('');
      setAssignNotes('');
      await loadPlans();
    } catch (err) {
      setError(err.message || 'Failed to assign plan.');
    }
  };

  const handleSearchMember = async (e) => {
    e.preventDefault();
    if (!memberIdQuery.trim()) return;
    setSearchingMember(true);
    setError(null);
    try {
      const [sessions, progress] = await Promise.all([
        fetchWorkoutSessions(memberIdQuery.trim()).catch(() => []),
        fetchFitnessProgress(memberIdQuery.trim()).catch(() => []),
      ]);
      setRecentSessions(sessions || []);
      setProgressRecords(progress || []);
    } catch (err) {
      setError(err.message || 'Unable to retrieve member records.');
    } finally {
      setSearchingMember(false);
    }
  };

  const handleCoachVerifySession = async (sessionId) => {
    try {
      await verifyWorkoutSession(sessionId, {
        is_coach_verified: true,
        notes: `Coach verified by ${currentUser?.name || 'Staff'}.`,
      });
      setFeedback('Workout session successfully verified by coach.');
      // Refresh list
      if (memberIdQuery) {
        const s = await fetchWorkoutSessions(memberIdQuery.trim());
        setRecentSessions(s || []);
      }
    } catch (err) {
      setError(err.message || 'Verification failed.');
    }
  };

  return (
    <div className="admin-workouts-container">
      {/* Top Controls Bar */}
      <div className="admin-workouts-header">
        <div className="header-tabs">
          <button
            type="button"
            className={`subnav-btn ${activeTab === 'plans' ? 'active' : ''}`}
            onClick={() => setActiveTab('plans')}
          >
            <Dumbbell size={16} />
            <span>Prescribed Plans</span>
          </button>
          <button
            type="button"
            className={`subnav-btn ${activeTab === 'verification' ? 'active' : ''}`}
            onClick={() => setActiveTab('verification')}
          >
            <Award size={16} />
            <span>Session Verification</span>
          </button>
        </div>

        {activeTab === 'plans' && (
          <div className="header-actions">
            <div className="filter-group">
              <Filter size={14} className="gold-text" />
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="select-status-filter"
              >
                <option value="">All Statuses</option>
                <option value="active">Active Plans</option>
                <option value="draft">Drafts</option>
                <option value="archived">Archived</option>
              </select>
            </div>

            <button
              type="button"
              className="btn-create-plan"
              onClick={() => setShowCreateModal(true)}
            >
              <Plus size={16} />
              <span>Create Workout Plan</span>
            </button>
          </div>
        )}
      </div>

      {feedback && (
        <div className="alert-feedback-gold">
          <CheckCircle2 size={16} />
          <span>{feedback}</span>
        </div>
      )}

      {error && (
        <div className="alert-error-red">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* Main Tab 1: Workout Plans List */}
      {activeTab === 'plans' && (
        <div className="plans-display-area">
          {loading ? (
            <div className="loading-state">
              <span className="spinner" />
              <p>Loading prescribed workout plans...</p>
            </div>
          ) : plans.length === 0 ? (
            <div className="empty-state-box">
              <Dumbbell size={36} className="gold-text opacity-50" />
              <h4>No Workout Plans Found</h4>
              <p>Create a structured routine prescription to guide member strength and hypertrophy progression.</p>
            </div>
          ) : (
            <div className="plans-grid">
              {plans.map((p) => (
                <div key={p.id} className="plan-management-card">
                  <div className="plan-card-header">
                    <div className="plan-badge-row">
                      <span className={`status-pill ${p.status}`}>{p.status}</span>
                      <span className="difficulty-pill">{p.difficulty}</span>
                      <span className="goal-pill">{p.goal.replace('_', ' ')}</span>
                    </div>
                    <strong className="plan-card-title">{p.name}</strong>
                    <p className="plan-card-desc">{p.description || 'Structured multi-week progression protocol.'}</p>
                  </div>

                  <div className="plan-details-row">
                    <div className="detail-item">
                      <Clock size={14} className="gold-text" />
                      <span>{p.duration_weeks ? `${p.duration_weeks} Weeks` : 'Continuous'}</span>
                    </div>
                    <div className="detail-item">
                      <UserCheck size={14} className="gold-text" />
                      <span>{p.assigned_member_count || 0} Members</span>
                    </div>
                    <div className="detail-item">
                      <Shield size={14} className="gold-text" />
                      <span>Coach: {p.trainer_name || 'Staff'}</span>
                    </div>
                  </div>

                  {/* Exercises Preview */}
                  {p.exercises && p.exercises.length > 0 && (
                    <div className="plan-exercises-preview">
                      <span className="exercises-label">Prescribed Movements ({p.exercises.length}):</span>
                      <div className="exercises-chip-list">
                        {p.exercises.slice(0, 4).map((ex) => (
                          <div key={ex.id} className="exercise-chip">
                            <strong>{ex.name}</strong>
                            <span>{ex.sets ? `${ex.sets}x${ex.reps || 'reps'}` : `${ex.target_duration_seconds}s`}</span>
                          </div>
                        ))}
                        {p.exercises.length > 4 && (
                          <span className="more-chip">+{p.exercises.length - 4} more</span>
                        )}
                      </div>
                    </div>
                  )}

                  <div className="plan-actions-footer">
                    <button
                      type="button"
                      className="btn-assign-member"
                      onClick={() => {
                        setSelectedPlan(p);
                        setShowAssignModal(true);
                      }}
                      disabled={p.status === 'archived'}
                    >
                      <UserCheck size={14} />
                      <span>Assign to Member</span>
                    </button>
                    {p.status !== 'archived' && (
                      <button
                        type="button"
                        className="btn-archive-plan"
                        onClick={() => handleArchivePlan(p.id)}
                        title="Archive Plan"
                      >
                        <Trash2 size={14} />
                        <span>Archive</span>
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Main Tab 2: Session Verification & Progress Review */}
      {activeTab === 'verification' && (
        <div className="verification-search-area">
          <form onSubmit={handleSearchMember} className="member-lookup-bar">
            <Search size={18} className="gold-text" />
            <input
              type="text"
              placeholder="Enter Member ID (e.g. pg-mem-1, user UUID) to inspect sessions & progress..."
              value={memberIdQuery}
              onChange={(e) => setMemberIdQuery(e.target.value)}
              className="member-lookup-input"
            />
            <button type="submit" className="btn-search-lookup" disabled={searchingMember}>
              {searchingMember ? 'Searching...' : 'Inspect Athlete Records'}
            </button>
          </form>

          {recentSessions.length > 0 && (
            <div className="sessions-table-wrapper">
              <h4 className="section-subtitle">Recorded Workout Sessions</h4>
              <table className="sessions-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Session / Plan</th>
                    <th>Status</th>
                    <th>Exercises Logged</th>
                    <th>Coach Verification</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {recentSessions.map((s) => (
                    <tr key={s.id}>
                      <td>{s.session_date}</td>
                      <td>
                        <strong>{s.session_name || 'Workout Session'}</strong>
                        {s.plan_name && <span className="table-subtext">{s.plan_name}</span>}
                      </td>
                      <td>
                        <span className={`status-badge ${s.status}`}>{s.status}</span>
                      </td>
                      <td>{s.exercises ? s.exercises.length : 0} movements</td>
                      <td>
                        {s.is_coach_verified ? (
                          <span className="verified-badge-gold">
                            <CheckCircle2 size={14} /> Verified Coach
                          </span>
                        ) : (
                          <span className="text-muted">Self-Reported</span>
                        )}
                      </td>
                      <td>
                        {!s.is_coach_verified && s.status === 'completed' && (
                          <button
                            type="button"
                            className="btn-verify-action"
                            onClick={() => handleCoachVerifySession(s.id)}
                          >
                            <Award size={14} />
                            <span>Verify Session</span>
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {progressRecords.length > 0 && (
            <div className="progress-records-table-wrapper mt-4">
              <h4 className="section-subtitle">Shared Progress Metrics (Assigned Athlete Only)</h4>
              <div className="progress-chips-grid">
                {progressRecords.map((r) => (
                  <div key={r.id} className="progress-chip-card">
                    <span className="chip-metric-type">{r.record_type.replace('_', ' ')}</span>
                    <strong className="chip-metric-val">
                      {r.value ? `${r.value} ${r.unit || ''}` : r.text_value}
                    </strong>
                    <span className="chip-metric-date">{r.recorded_date}</span>
                    {r.notes && <p className="chip-metric-notes">{r.notes}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Modal: Create Workout Plan */}
      {showCreateModal && (
        <div className="modal-backdrop">
          <div className="modal-dialog-plan">
            <div className="modal-header">
              <h3>Create Prescribed Workout Plan</h3>
              <button
                type="button"
                className="btn-close-modal"
                onClick={() => setShowCreateModal(false)}
              >
                &times;
              </button>
            </div>
            <form onSubmit={handleCreatePlan} className="plan-form">
              <div className="form-row">
                <div className="form-group flex-2">
                  <label>Plan Name *</label>
                  <input
                    type="text"
                    required
                    value={newPlan.name}
                    onChange={(e) => setNewPlan({ ...newPlan, name: e.target.value })}
                    placeholder="e.g. Hypertrophy Foundations 1"
                  />
                </div>
                <div className="form-group flex-1">
                  <label>Focus / Goal</label>
                  <select
                    value={newPlan.goal}
                    onChange={(e) => setNewPlan({ ...newPlan, goal: e.target.value })}
                  >
                    <option value="strength">Strength</option>
                    <option value="hypertrophy">Hypertrophy</option>
                    <option value="endurance">Endurance</option>
                    <option value="mobility">Mobility</option>
                    <option value="general_fitness">General Fitness</option>
                  </select>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Difficulty</label>
                  <select
                    value={newPlan.difficulty}
                    onChange={(e) => setNewPlan({ ...newPlan, difficulty: e.target.value })}
                  >
                    <option value="beginner">Beginner</option>
                    <option value="intermediate">Intermediate</option>
                    <option value="advanced">Advanced</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Duration (Weeks)</label>
                  <input
                    type="number"
                    min="1"
                    max="52"
                    value={newPlan.duration_weeks}
                    onChange={(e) => setNewPlan({ ...newPlan, duration_weeks: parseInt(e.target.value) || 4 })}
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Description & Coaching Protocol</label>
                <textarea
                  rows="2"
                  value={newPlan.description}
                  onChange={(e) => setNewPlan({ ...newPlan, description: e.target.value })}
                  placeholder="Outline routine structure, progressive overload targets, and recovery guidance."
                />
              </div>

              {/* Prescribed Movements Section */}
              <div className="prescribed-movements-section">
                <div className="section-head-bar">
                  <span className="section-title">Prescribed Movements</span>
                  <button
                    type="button"
                    className="btn-add-exercise-row"
                    onClick={handleAddExerciseRow}
                  >
                    <Plus size={14} /> Add Movement
                  </button>
                </div>

                <div className="exercise-rows-container">
                  {newPlan.exercises.map((ex, idx) => (
                    <div key={idx} className="exercise-row-card">
                      <div className="row-inputs-grid">
                        <input
                          type="text"
                          required
                          placeholder="Movement Name (e.g. Romanian Deadlift)"
                          value={ex.name}
                          onChange={(e) => handleExerciseChange(idx, 'name', e.target.value)}
                          className="input-movement-name"
                        />
                        <input
                          type="number"
                          placeholder="Sets"
                          min="1"
                          max="20"
                          value={ex.sets}
                          onChange={(e) => handleExerciseChange(idx, 'sets', parseInt(e.target.value) || 3)}
                          className="input-narrow"
                        />
                        <input
                          type="number"
                          placeholder="Reps"
                          min="1"
                          max="100"
                          value={ex.reps}
                          onChange={(e) => handleExerciseChange(idx, 'reps', parseInt(e.target.value) || 10)}
                          className="input-narrow"
                        />
                        <input
                          type="number"
                          placeholder="Target kg"
                          step="0.5"
                          value={ex.target_weight_kg || ''}
                          onChange={(e) => handleExerciseChange(idx, 'target_weight_kg', parseFloat(e.target.value) || 0)}
                          className="input-narrow"
                        />
                        <input
                          type="number"
                          placeholder="Rest (s)"
                          value={ex.rest_seconds}
                          onChange={(e) => handleExerciseChange(idx, 'rest_seconds', parseInt(e.target.value) || 60)}
                          className="input-narrow"
                        />
                        {newPlan.exercises.length > 1 && (
                          <button
                            type="button"
                            className="btn-remove-row"
                            onClick={() => handleRemoveExerciseRow(idx)}
                          >
                            <Trash2 size={14} />
                          </button>
                        )}
                      </div>
                      <input
                        type="text"
                        placeholder="Coaching instructions / form cues"
                        value={ex.instructions}
                        onChange={(e) => handleExerciseChange(idx, 'instructions', e.target.value)}
                        className="input-instructions"
                      />
                    </div>
                  ))}
                </div>
              </div>

              <div className="modal-actions-bar">
                <button
                  type="button"
                  className="btn-cancel"
                  onClick={() => setShowCreateModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-confirm-save">
                  Save Plan Prescription
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Assign Plan to Member */}
      {showAssignModal && selectedPlan && (
        <div className="modal-backdrop">
          <div className="modal-dialog-compact">
            <div className="modal-header">
              <h3>Assign Plan: {selectedPlan.name}</h3>
              <button
                type="button"
                className="btn-close-modal"
                onClick={() => setShowAssignModal(false)}
              >
                &times;
              </button>
            </div>
            <form onSubmit={handleAssignPlan} className="plan-form">
              <div className="form-group">
                <label>Member ID (e.g. pg-mem-1 or User UUID) *</label>
                <input
                  type="text"
                  required
                  placeholder="Enter Member ID"
                  value={assignMemberId}
                  onChange={(e) => setAssignMemberId(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>Assignment Notes / Directives</label>
                <textarea
                  rows="2"
                  placeholder="e.g. Execute on Mon, Wed, Fri with active rest on weekends."
                  value={assignNotes}
                  onChange={(e) => setAssignNotes(e.target.value)}
                />
              </div>
              <div className="modal-actions-bar">
                <button
                  type="button"
                  className="btn-cancel"
                  onClick={() => setShowAssignModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-confirm-save">
                  Assign Plan
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
