import { useState, useEffect } from 'react';
import {
  X,
  User,
  Shield,
  Activity,
  Heart,
  Scale,
  Calendar,
  Phone,
  Mail,
  MapPin,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  Plus,
  Lock,
  ChevronRight,
  Target
} from 'lucide-react';
import {
  fetchMemberProfile,
  updateMemberProfile,
  fetchMemberMeasurements,
  logMemberMeasurement
} from '../api';

export default function MemberProfileModal({
  memberId,
  currentUser,
  onClose,
  onProfileUpdated
}) {
  const [profile, setProfile] = useState(null);
  const [measurements, setMeasurements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [feedback, setFeedback] = useState(null);

  // Tab: 'overview' | 'health' | 'measurements'
  const [activeTab, setActiveTab] = useState('overview');

  // New measurement form state
  const [showAddMeasurement, setShowAddMeasurement] = useState(false);
  const [measForm, setMeasForm] = useState({
    recorded_date: new Date().toISOString().split('T')[0],
    weight_kg: '',
    height_cm: '',
    body_fat_pct: '',
    chest_cm: '',
    waist_cm: '',
    hips_cm: '',
    arms_cm: '',
    thighs_cm: '',
    calves_cm: '',
    notes: '',
  });
  const [savingMeasurement, setSavingMeasurement] = useState(false);

  const loadData = async () => {
    if (!memberId) return;
    setLoading(true);
    setError(null);
    try {
      const [profData, measData] = await Promise.all([
        fetchMemberProfile(memberId),
        fetchMemberMeasurements(memberId, 20, 0).catch(() => []),
      ]);
      setProfile(profData);
      setMeasurements(measData || []);
    } catch (err) {
      setError(err.message || 'Unable to load member profile details.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [memberId]);

  const handleAddMeasurementSubmit = async (e) => {
    e.preventDefault();
    setSavingMeasurement(true);
    setError(null);
    try {
      const payload = {
        recorded_date: measForm.recorded_date,
        weight_kg: measForm.weight_kg ? parseFloat(measForm.weight_kg) : undefined,
        height_cm: measForm.height_cm ? parseFloat(measForm.height_cm) : undefined,
        body_fat_pct: measForm.body_fat_pct ? parseFloat(measForm.body_fat_pct) : undefined,
        chest_cm: measForm.chest_cm ? parseFloat(measForm.chest_cm) : undefined,
        waist_cm: measForm.waist_cm ? parseFloat(measForm.waist_cm) : undefined,
        hips_cm: measForm.hips_cm ? parseFloat(measForm.hips_cm) : undefined,
        arms_cm: measForm.arms_cm ? parseFloat(measForm.arms_cm) : undefined,
        thighs_cm: measForm.thighs_cm ? parseFloat(measForm.thighs_cm) : undefined,
        calves_cm: measForm.calves_cm ? parseFloat(measForm.calves_cm) : undefined,
        notes: measForm.notes.trim() || undefined,
      };
      await logMemberMeasurement(memberId, payload);
      setFeedback('Measurement recorded successfully.');
      setShowAddMeasurement(false);
      setMeasForm({
        recorded_date: new Date().toISOString().split('T')[0],
        weight_kg: '',
        height_cm: '',
        body_fat_pct: '',
        chest_cm: '',
        waist_cm: '',
        hips_cm: '',
        arms_cm: '',
        thighs_cm: '',
        calves_cm: '',
        notes: '',
      });
      await loadData();
      if (onProfileUpdated) onProfileUpdated();
    } catch (err) {
      setError(err.message || 'Failed to record measurement.');
    } finally {
      setSavingMeasurement(false);
    }
  };

  const isFrontDesk = currentUser?.role === 'front_desk' || currentUser?.role === 'staff';
  const isCoach = currentUser?.role === 'trainer';

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="member-profile-modal-title">
      <div className="member-profile-modal-card">
        {/* Header */}
        <div className="modal-header">
          <div className="profile-modal-title-lockup">
            <div className="profile-modal-avatar">
              {profile?.profilePhotoUrl ? (
                <img src={profile.profilePhotoUrl} alt={profile.name} />
              ) : (
                <User size={24} className="gold-text" />
              )}
            </div>
            <div>
              <h3 id="member-profile-modal-title">{profile ? profile.name : 'Member Profile'}</h3>
              <p className="profile-modal-sub">
                ID: <strong>{profile?.membershipId || profile?.id?.slice(0, 8)}</strong>
                {profile?.branchName && ` | Branch: ${profile.branchName}`}
                {profile?.calculatedAge !== null && profile?.calculatedAge !== undefined && ` | Age: ${profile.calculatedAge}`}
              </p>
            </div>
          </div>
          <button type="button" className="close-btn" onClick={onClose} aria-label="Close profile">
            <X size={18} />
          </button>
        </div>

        {/* Status Alerts */}
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

        {/* Tab Navigation */}
        <div className="profile-nav-tabs">
          <button
            type="button"
            className={`profile-tab-btn ${activeTab === 'overview' ? 'active' : ''}`}
            onClick={() => setActiveTab('overview')}
          >
            <User size={15} /> Overview & Contact
          </button>
          <button
            type="button"
            className={`profile-tab-btn ${activeTab === 'health' ? 'active' : ''}`}
            onClick={() => setActiveTab('health')}
          >
            <Heart size={15} /> Health & Restrictions
          </button>
          <button
            type="button"
            className={`profile-tab-btn ${activeTab === 'measurements' ? 'active' : ''}`}
            onClick={() => setActiveTab('measurements')}
          >
            <Scale size={15} /> Measurements ({measurements.length})
          </button>
        </div>

        {/* Body Content */}
        <div className="profile-modal-body">
          {loading ? (
            <div className="profile-loading-state">
              <RefreshCw size={28} className="spinner-icon gold-text" />
              <p>Loading member profile details...</p>
            </div>
          ) : !profile ? (
            <div className="profile-empty-state">
              <p>Profile information could not be retrieved.</p>
            </div>
          ) : (
            <>
              {/* TAB 1: OVERVIEW & CONTACT */}
              {activeTab === 'overview' && (
                <div className="profile-tab-pane">
                  {/* Membership & Status Grid */}
                  <div className="profile-info-grid">
                    <div className="info-item">
                      <span className="label">Membership Status</span>
                      <span className={`status-pill ${profile.membershipStatus === 'active' ? 'active' : 'inactive'}`}>
                        {profile.membershipStatus.toUpperCase()}
                      </span>
                    </div>
                    <div className="info-item">
                      <span className="label">Current Plan</span>
                      <span className="value">{profile.membershipPlan || 'None'}</span>
                    </div>
                    <div className="info-item">
                      <span className="label">Valid Until</span>
                      <span className="value">{profile.validUntil || 'N/A'}</span>
                    </div>
                    <div className="info-item">
                      <span className="label">Attendance Streak</span>
                      <span className="value gold-text">{profile.streakDays} Days</span>
                    </div>
                  </div>

                  {/* Personal Contact Details */}
                  <div className="profile-section-card">
                    <h4 className="section-title"><User size={16} /> Personal Information</h4>
                    <div className="detail-rows-list">
                      <div className="detail-row">
                        <span className="detail-label"><Mail size={14} /> Email</span>
                        <span className="detail-value">{profile.email}</span>
                      </div>
                      <div className="detail-row">
                        <span className="detail-label"><Phone size={14} /> Phone</span>
                        <span className="detail-value">{profile.phone || 'Not provided'}</span>
                      </div>
                      <div className="detail-row">
                        <span className="detail-label"><Calendar size={14} /> Date of Birth</span>
                        <span className="detail-value">
                          {profile.dateOfBirth ? `${profile.dateOfBirth} (Age ${profile.calculatedAge})` : 'Not provided'}
                        </span>
                      </div>
                      <div className="detail-row">
                        <span className="detail-label">Gender</span>
                        <span className="detail-value">{profile.gender || 'Not specified'}</span>
                      </div>
                      <div className="detail-row">
                        <span className="detail-label"><MapPin size={14} /> Address</span>
                        <span className="detail-value">{profile.address || 'Not provided'}</span>
                      </div>
                      <div className="detail-row">
                        <span className="detail-label"><Shield size={14} /> Assigned Coach</span>
                        <span className="detail-value">{profile.assignedTrainerName || 'No coach assigned'}</span>
                      </div>
                    </div>
                  </div>

                  {/* Emergency Contact */}
                  <div className="profile-section-card emergency-card">
                    <h4 className="section-title"><Phone size={16} /> Emergency Contact</h4>
                    <div className="detail-rows-list">
                      <div className="detail-row">
                        <span className="detail-label">Contact Name</span>
                        <span className="detail-value">{profile.emergencyContactName || 'Not recorded'}</span>
                      </div>
                      <div className="detail-row">
                        <span className="detail-label">Contact Phone</span>
                        <span className="detail-value">{profile.emergencyContactPhone || 'Not recorded'}</span>
                      </div>
                    </div>
                  </div>

                  {/* Physical Targets */}
                  <div className="profile-section-card">
                    <h4 className="section-title"><Target size={16} /> Training Targets</h4>
                    <div className="detail-rows-list">
                      <div className="detail-row">
                        <span className="detail-label">Primary Goal</span>
                        <span className="detail-value">{profile.primaryGoal?.replace('_', ' ')?.toUpperCase()}</span>
                      </div>
                      <div className="detail-row">
                        <span className="detail-label">Recorded Height</span>
                        <span className="detail-value">{profile.heightCm ? `${profile.heightCm} cm` : 'Not recorded'}</span>
                      </div>
                      <div className="detail-row">
                        <span className="detail-label">Target Goal Weight</span>
                        <span className="detail-value">{profile.targetWeightKg ? `${profile.targetWeightKg} kg` : 'Not set'}</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 2: HEALTH & RESTRICTIONS */}
              {activeTab === 'health' && (
                <div className="profile-tab-pane">
                  {/* Privacy Notice */}
                  <div className="privacy-callout-box">
                    <Lock size={16} className="gold-text" />
                    <div>
                      <strong>Health Data Confidentiality Notice</strong>
                      <p>{profile.privacyNotice}</p>
                    </div>
                  </div>

                  {isFrontDesk ? (
                    <div className="redacted-notice-box">
                      <Lock size={20} />
                      <h4>Health Details Redacted for Reception Role</h4>
                      <p>
                        Front-desk staff do not have authorization to view sensitive medical or injury notes.
                        In an emergency, consult emergency contact details on the Overview tab.
                      </p>
                    </div>
                  ) : (
                    <div className="health-details-container">
                      <div className="health-field-card">
                        <span className="health-field-title">Exercise Restrictions / Movements to Avoid</span>
                        <p className="health-field-text">
                          {profile.exerciseRestrictions || 'None reported by member.'}
                        </p>
                      </div>

                      <div className="health-field-card">
                        <span className="health-field-title">Current Injuries or Physical Limitations</span>
                        <p className="health-field-text">
                          {profile.currentInjuries || 'None reported.'}
                        </p>
                      </div>

                      <div className="health-field-card">
                        <span className="health-field-title">Past Injury History</span>
                        <p className="health-field-text">
                          {profile.pastInjuries || 'None reported.'}
                        </p>
                      </div>

                      {/* Only Org Admin or Member themselves can see detailed conditions/medications */}
                      {profile.accessScope === 'full' && (
                        <>
                          <div className="health-field-card">
                            <span className="health-field-title">Known Health Conditions</span>
                            <p className="health-field-text">
                              {profile.healthConditions || 'None disclosed.'}
                            </p>
                          </div>

                          <div className="health-field-card">
                            <span className="health-field-title">Allergies</span>
                            <p className="health-field-text">
                              {profile.allergies || 'None recorded.'}
                            </p>
                          </div>

                          <div className="health-field-card">
                            <span className="health-field-title">Surgery History</span>
                            <p className="health-field-text">
                              {profile.surgeryHistory || 'None recorded.'}
                            </p>
                          </div>

                          <div className="health-field-card">
                            <span className="health-field-title">Current Medications (Consented)</span>
                            <p className="health-field-text">
                              {profile.hasMedicationConsent
                                ? (profile.currentMedications || 'None recorded.')
                                : 'Member did not provide explicit consent to record medications.'}
                            </p>
                          </div>

                          <div className="health-field-card">
                            <span className="health-field-title">Confidential Health Notes</span>
                            <p className="health-field-text">
                              {profile.healthNotes || 'No notes.'}
                            </p>
                          </div>
                        </>
                      )}

                      <div className="health-field-card">
                        <span className="health-field-title">Fitness Goals</span>
                        <p className="health-field-text">
                          {profile.fitnessGoals || 'None stated.'}
                        </p>
                      </div>

                      <div className="health-update-timestamp">
                        <span>Last profile disclosure update: {profile.lastHealthUpdate ? new Date(profile.lastHealthUpdate).toLocaleDateString() : 'Never'}</span>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 3: BODY MEASUREMENTS */}
              {activeTab === 'measurements' && (
                <div className="profile-tab-pane">
                  <div className="measurements-header-row">
                    <div>
                      <h4 className="section-title"><Scale size={16} /> Body Measurement Records</h4>
                      <p className="text-muted">Dated time-series weight and circumference metrics.</p>
                    </div>
                    <button
                      type="button"
                      className="btn-gold-small"
                      onClick={() => setShowAddMeasurement(!showAddMeasurement)}
                    >
                      <Plus size={14} />
                      <span>{showAddMeasurement ? 'Cancel' : 'Log New Measurement'}</span>
                    </button>
                  </div>

                  {/* Add Measurement Form */}
                  {showAddMeasurement && (
                    <form onSubmit={handleAddMeasurementSubmit} className="add-measurement-subform">
                      <h5>Record Member Measurement</h5>
                      <div className="subform-grid">
                        <div className="form-group">
                          <label htmlFor="meas-date">Recorded Date *</label>
                          <input
                            id="meas-date"
                            type="date"
                            className="profile-input"
                            value={measForm.recorded_date}
                            onChange={(e) => setMeasForm({ ...measForm, recorded_date: e.target.value })}
                            max={new Date().toISOString().split('T')[0]}
                            required
                          />
                        </div>
                        <div className="form-group">
                          <label htmlFor="meas-weight">Weight (kg) *</label>
                          <input
                            id="meas-weight"
                            type="number"
                            step="0.1"
                            min="20"
                            max="350"
                            className="profile-input"
                            placeholder="e.g. 74.5"
                            value={measForm.weight_kg}
                            onChange={(e) => setMeasForm({ ...measForm, weight_kg: e.target.value })}
                            required
                          />
                        </div>
                        <div className="form-group">
                          <label htmlFor="meas-height">Height (cm)</label>
                          <input
                            id="meas-height"
                            type="number"
                            step="0.1"
                            min="80"
                            max="260"
                            className="profile-input"
                            placeholder="e.g. 176"
                            value={measForm.height_cm}
                            onChange={(e) => setMeasForm({ ...measForm, height_cm: e.target.value })}
                          />
                        </div>
                        <div className="form-group">
                          <label htmlFor="meas-fat">Body Fat %</label>
                          <input
                            id="meas-fat"
                            type="number"
                            step="0.1"
                            min="3"
                            max="65"
                            className="profile-input"
                            placeholder="e.g. 16.5"
                            value={measForm.body_fat_pct}
                            onChange={(e) => setMeasForm({ ...measForm, body_fat_pct: e.target.value })}
                          />
                        </div>
                        <div className="form-group">
                          <label htmlFor="meas-chest">Chest (cm)</label>
                          <input
                            id="meas-chest"
                            type="number"
                            step="0.1"
                            min="10"
                            max="200"
                            className="profile-input"
                            placeholder="e.g. 98.0"
                            value={measForm.chest_cm}
                            onChange={(e) => setMeasForm({ ...measForm, chest_cm: e.target.value })}
                          />
                        </div>
                        <div className="form-group">
                          <label htmlFor="meas-waist">Waist (cm)</label>
                          <input
                            id="meas-waist"
                            type="number"
                            step="0.1"
                            min="10"
                            max="200"
                            className="profile-input"
                            placeholder="e.g. 82.5"
                            value={measForm.waist_cm}
                            onChange={(e) => setMeasForm({ ...measForm, waist_cm: e.target.value })}
                          />
                        </div>
                        <div className="form-group">
                          <label htmlFor="meas-hips">Hips (cm)</label>
                          <input
                            id="meas-hips"
                            type="number"
                            step="0.1"
                            min="10"
                            max="200"
                            className="profile-input"
                            placeholder="e.g. 96.0"
                            value={measForm.hips_cm}
                            onChange={(e) => setMeasForm({ ...measForm, hips_cm: e.target.value })}
                          />
                        </div>
                        <div className="form-group">
                          <label htmlFor="meas-arms">Arms (cm)</label>
                          <input
                            id="meas-arms"
                            type="number"
                            step="0.1"
                            min="10"
                            max="100"
                            className="profile-input"
                            placeholder="e.g. 36.5"
                            value={measForm.arms_cm}
                            onChange={(e) => setMeasForm({ ...measForm, arms_cm: e.target.value })}
                          />
                        </div>
                      </div>
                      <div className="form-group">
                        <label htmlFor="meas-notes">Notes (Optional)</label>
                        <input
                          id="meas-notes"
                          type="text"
                          className="profile-input"
                          placeholder="e.g. Measured post workout; morning fasted weigh-in"
                          value={measForm.notes}
                          onChange={(e) => setMeasForm({ ...measForm, notes: e.target.value })}
                        />
                      </div>
                      <div className="subform-actions">
                        <button
                          type="button"
                          className="btn-cancel"
                          onClick={() => setShowAddMeasurement(false)}
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          className="btn-gold-small"
                          disabled={savingMeasurement}
                        >
                          {savingMeasurement ? 'Saving...' : 'Save Measurement'}
                        </button>
                      </div>
                    </form>
                  )}

                  {/* Measurements Table */}
                  {measurements.length === 0 ? (
                    <div className="profile-empty-state">
                      <Scale size={32} className="gold-text" />
                      <p>No body measurement records logged yet for this member.</p>
                    </div>
                  ) : (
                    <div className="measurements-table-wrap">
                      <table className="measurements-table">
                        <thead>
                          <tr>
                            <th>Date</th>
                            <th>Weight</th>
                            <th>Height</th>
                            <th>Body Fat</th>
                            <th>Chest</th>
                            <th>Waist</th>
                            <th>Arms</th>
                            <th>Recorded By</th>
                          </tr>
                        </thead>
                        <tbody>
                          {measurements.map((m) => (
                            <tr key={m.id}>
                              <td><strong>{m.recordedDate}</strong></td>
                              <td>{m.weightKg ? `${m.weightKg} kg` : '-'}</td>
                              <td>{m.heightCm ? `${m.heightCm} cm` : '-'}</td>
                              <td>{m.bodyFatPct ? `${m.bodyFatPct}%` : '-'}</td>
                              <td>{m.chestCm ? `${m.chestCm} cm` : '-'}</td>
                              <td>{m.waistCm ? `${m.waistCm} cm` : '-'}</td>
                              <td>{m.armsCm ? `${m.armsCm} cm` : '-'}</td>
                              <td>
                                <span className={`role-tag ${m.recordedByRole}`}>
                                  {m.recordedByRole}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
