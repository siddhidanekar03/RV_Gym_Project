import { useState, useEffect } from 'react';
import {
  User,
  Heart,
  Scale,
  Target,
  Shield,
  Save,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  Lock,
  Plus,
  Calendar,
  Phone,
  Mail,
  MapPin,
  Clock
} from 'lucide-react';
import {
  fetchMyProfile,
  updateMyProfile,
  fetchMyMeasurements,
  logMyMeasurement
} from '../api';

export default function MemberProfileView({ currentUser, onUserUpdate }) {
  const [profile, setProfile] = useState(null);
  const [measurements, setMeasurements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [feedback, setFeedback] = useState(null);

  // Active sub-tab: 'personal' | 'health' | 'measurements' | 'targets'
  const [subTab, setSubTab] = useState('personal');

  // Form states
  const [personalForm, setPersonalForm] = useState({
    name: '',
    phone: '',
    date_of_birth: '',
    gender: '',
    profile_photo_url: '',
    address: '',
    emergency_contact_name: '',
    emergency_contact_phone: '',
  });

  const [healthForm, setHealthForm] = useState({
    past_injuries: '',
    current_injuries: '',
    health_conditions: '',
    exercise_restrictions: '',
    allergies: '',
    surgery_history: '',
    current_medications: '',
    has_medication_consent: false,
    fitness_goals: '',
    health_notes: '',
  });

  const [targetsForm, setTargetsForm] = useState({
    height_cm: '',
    target_weight_kg: '',
    primary_goal: 'general_fitness',
  });

  // Measurement logging subform state
  const [showAddMeas, setShowAddMeas] = useState(false);
  const [savingMeas, setSavingMeas] = useState(false);
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

  const loadProfileData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [profData, measData] = await Promise.all([
        fetchMyProfile(),
        fetchMyMeasurements(50, 0).catch(() => []),
      ]);
      setProfile(profData);
      setMeasurements(measData || []);

      // Populate personal form
      setPersonalForm({
        name: profData.name || '',
        phone: profData.phone || '',
        date_of_birth: profData.dateOfBirth || '',
        gender: profData.gender || '',
        profile_photo_url: profData.profilePhotoUrl || '',
        address: profData.address || '',
        emergency_contact_name: profData.emergencyContactName || '',
        emergency_contact_phone: profData.emergencyContactPhone || '',
      });

      // Populate health form
      setHealthForm({
        past_injuries: profData.pastInjuries || '',
        current_injuries: profData.currentInjuries || '',
        health_conditions: profData.healthConditions || '',
        exercise_restrictions: profData.exerciseRestrictions || '',
        allergies: profData.allergies || '',
        surgery_history: profData.surgeryHistory || '',
        current_medications: profData.currentMedications || '',
        has_medication_consent: profData.hasMedicationConsent || false,
        fitness_goals: profData.fitnessGoals || '',
        health_notes: profData.healthNotes || '',
      });

      // Populate targets form
      setTargetsForm({
        height_cm: profData.heightCm ? String(profData.heightCm) : '',
        target_weight_kg: profData.targetWeightKg ? String(profData.targetWeightKg) : '',
        primary_goal: profData.primaryGoal || 'general_fitness',
      });
    } catch (err) {
      setError(err.message || 'Unable to load member profile.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProfileData();
  }, []);

  const handleSavePersonal = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setFeedback(null);
    try {
      const payload = {
        personal: {
          name: personalForm.name.trim() || undefined,
          phone: personalForm.phone.trim() || undefined,
          date_of_birth: personalForm.date_of_birth || undefined,
          gender: personalForm.gender.trim() || undefined,
          profile_photo_url: personalForm.profile_photo_url.trim() || undefined,
          address: personalForm.address.trim() || undefined,
          emergency_contact_name: personalForm.emergency_contact_name.trim() || undefined,
          emergency_contact_phone: personalForm.emergency_contact_phone.trim() || undefined,
        },
      };
      const updated = await updateMyProfile(payload);
      setProfile(updated);
      setFeedback('Personal information saved successfully.');
      if (onUserUpdate && updated) {
        onUserUpdate({ ...currentUser, name: updated.name, phone: updated.phone });
      }
    } catch (err) {
      setError(err.message || 'Failed to update personal details.');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveHealth = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setFeedback(null);
    try {
      const payload = {
        health: {
          past_injuries: healthForm.past_injuries.trim() || undefined,
          current_injuries: healthForm.current_injuries.trim() || undefined,
          health_conditions: healthForm.health_conditions.trim() || undefined,
          exercise_restrictions: healthForm.exercise_restrictions.trim() || undefined,
          allergies: healthForm.allergies.trim() || undefined,
          surgery_history: healthForm.surgery_history.trim() || undefined,
          current_medications: healthForm.has_medication_consent
            ? (healthForm.current_medications.trim() || undefined)
            : undefined,
          has_medication_consent: healthForm.has_medication_consent,
          fitness_goals: healthForm.fitness_goals.trim() || undefined,
          health_notes: healthForm.health_notes.trim() || undefined,
        },
      };
      const updated = await updateMyProfile(payload);
      setProfile(updated);
      setFeedback('Health and injury disclosures updated safely.');
    } catch (err) {
      setError(err.message || 'Failed to update health information.');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveTargets = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setFeedback(null);
    try {
      const payload = {
        targets: {
          height_cm: targetsForm.height_cm ? parseFloat(targetsForm.height_cm) : undefined,
          target_weight_kg: targetsForm.target_weight_kg ? parseFloat(targetsForm.target_weight_kg) : undefined,
          primary_goal: targetsForm.primary_goal || 'general_fitness',
        },
      };
      const updated = await updateMyProfile(payload);
      setProfile(updated);
      setFeedback('Training goals and physical targets saved.');
    } catch (err) {
      setError(err.message || 'Failed to update targets.');
    } finally {
      setSaving(false);
    }
  };

  const handleAddMeasurementSubmit = async (e) => {
    e.preventDefault();
    setSavingMeas(true);
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
      await logMyMeasurement(payload);
      setFeedback('New body measurement record saved.');
      setShowAddMeas(false);
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
      await loadProfileData();
    } catch (err) {
      setError(err.message || 'Failed to record measurement.');
    } finally {
      setSavingMeas(false);
    }
  };

  if (loading) {
    return (
      <div className="profile-view-loading">
        <RefreshCw size={32} className="spinner-icon gold-text" />
        <p>Loading member profile details...</p>
      </div>
    );
  }

  return (
    <div className="member-profile-view-container">
      {/* Profile Header */}
      <div className="profile-view-hero">
        <div className="hero-left">
          <div className="hero-avatar">
            {profile?.profilePhotoUrl ? (
              <img src={profile.profilePhotoUrl} alt={profile.name} />
            ) : (
              <User size={36} className="gold-text" />
            )}
          </div>
          <div className="hero-meta">
            <h2>{profile?.name}</h2>
            <p className="hero-sub">
              Membership ID: <strong>{profile?.membershipId || 'RVF-MEMBER'}</strong>
              {profile?.branchName && ` | Branch: ${profile.branchName}`}
              {profile?.calculatedAge !== null && profile?.calculatedAge !== undefined && ` | Age: ${profile.calculatedAge}`}
            </p>
            <div className="hero-badges-row">
              <span className={`hero-pill ${profile?.membershipStatus === 'active' ? 'active' : 'inactive'}`}>
                {profile?.membershipStatus?.toUpperCase()} MEMBER
              </span>
              <span className="hero-pill plan-pill">
                {profile?.membershipPlan || 'VIP Membership'}
              </span>
              <span className="hero-pill streak-pill">
                {profile?.streakDays || 0} Day Attendance Streak
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Notifications */}
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

      {/* Sub-navigation tabs */}
      <div className="profile-section-nav">
        <button
          type="button"
          className={`nav-tab-btn ${subTab === 'personal' ? 'active' : ''}`}
          onClick={() => setSubTab('personal')}
        >
          <User size={16} /> Personal Details
        </button>
        <button
          type="button"
          className={`nav-tab-btn ${subTab === 'health' ? 'active' : ''}`}
          onClick={() => setSubTab('health')}
        >
          <Heart size={16} /> Health & Injury History
        </button>
        <button
          type="button"
          className={`nav-tab-btn ${subTab === 'measurements' ? 'active' : ''}`}
          onClick={() => setSubTab('measurements')}
        >
          <Scale size={16} /> Body Measurements ({measurements.length})
        </button>
        <button
          type="button"
          className={`nav-tab-btn ${subTab === 'targets' ? 'active' : ''}`}
          onClick={() => setSubTab('targets')}
        >
          <Target size={16} /> Goals & Physical Targets
        </button>
      </div>

      {/* SUBTAB 1: PERSONAL DETAILS */}
      {subTab === 'personal' && (
        <form onSubmit={handleSavePersonal} className="profile-form-pane">
          <div className="form-card">
            <h3 className="card-title"><User size={18} /> Personal Information</h3>
            <p className="card-subtitle">
              Keep your contact details up to date for emergency safety and account verification.
            </p>

            <div className="form-grid-2">
              <div className="form-group">
                <label htmlFor="pf-name">Full Name *</label>
                <input
                  id="pf-name"
                  type="text"
                  className="profile-input"
                  value={personalForm.name}
                  onChange={(e) => setPersonalForm({ ...personalForm, name: e.target.value })}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="pf-email">Email Address (Account Identifier)</label>
                <input
                  id="pf-email"
                  type="email"
                  className="profile-input disabled"
                  value={profile?.email || ''}
                  disabled
                />
                <small className="field-hint">Email updates require verified login credential revision.</small>
              </div>

              <div className="form-group">
                <label htmlFor="pf-phone">Phone Number</label>
                <input
                  id="pf-phone"
                  type="tel"
                  className="profile-input"
                  placeholder="+91 98220 12345"
                  value={personalForm.phone}
                  onChange={(e) => setPersonalForm({ ...personalForm, phone: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label htmlFor="pf-dob">Date of Birth</label>
                <input
                  id="pf-dob"
                  type="date"
                  className="profile-input"
                  value={personalForm.date_of_birth}
                  onChange={(e) => setPersonalForm({ ...personalForm, date_of_birth: e.target.value })}
                  max={new Date().toISOString().split('T')[0]}
                />
                {profile?.calculatedAge !== null && profile?.calculatedAge !== undefined && (
                  <small className="field-hint gold-text">
                    Calculated age: <strong>{profile.calculatedAge} years</strong> (computed dynamically from DOB)
                  </small>
                )}
              </div>

              <div className="form-group">
                <label htmlFor="pf-gender">Gender (Optional)</label>
                <select
                  id="pf-gender"
                  className="profile-input"
                  value={personalForm.gender}
                  onChange={(e) => setPersonalForm({ ...personalForm, gender: e.target.value })}
                >
                  <option value="">Prefer not to say</option>
                  <option value="male">Male</option>
                  <option value="female">Female</option>
                  <option value="other">Other / Non-binary</option>
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="pf-photo">Profile Photo URL (Optional)</label>
                <input
                  id="pf-photo"
                  type="url"
                  className="profile-input"
                  placeholder="https://example.com/avatar.jpg"
                  value={personalForm.profile_photo_url}
                  onChange={(e) => setPersonalForm({ ...personalForm, profile_photo_url: e.target.value })}
                />
              </div>
            </div>

            <div className="form-group full-width">
              <label htmlFor="pf-address">Residential Address (Optional)</label>
              <textarea
                id="pf-address"
                rows={2}
                className="profile-input"
                placeholder="Street address, city, pin code"
                value={personalForm.address}
                onChange={(e) => setPersonalForm({ ...personalForm, address: e.target.value })}
              />
            </div>
          </div>

          {/* Emergency Contact */}
          <div className="form-card">
            <h3 className="card-title"><Phone size={18} /> Emergency Contact Information</h3>
            <p className="card-subtitle">
              Designated contact in the event of an acute injury, physical limitation, or gym floor incident.
            </p>

            <div className="form-grid-2">
              <div className="form-group">
                <label htmlFor="pf-ec-name">Emergency Contact Full Name</label>
                <input
                  id="pf-ec-name"
                  type="text"
                  className="profile-input"
                  placeholder="e.g. Suresh Patil"
                  value={personalForm.emergency_contact_name}
                  onChange={(e) => setPersonalForm({ ...personalForm, emergency_contact_name: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label htmlFor="pf-ec-phone">Emergency Contact Phone Number</label>
                <input
                  id="pf-ec-phone"
                  type="tel"
                  className="profile-input"
                  placeholder="e.g. +91 98220 99999"
                  value={personalForm.emergency_contact_phone}
                  onChange={(e) => setPersonalForm({ ...personalForm, emergency_contact_phone: e.target.value })}
                />
              </div>
            </div>
          </div>

          <div className="form-actions-row">
            <button type="submit" className="btn-gold-save" disabled={saving}>
              <Save size={16} />
              <span>{saving ? 'Saving Changes...' : 'Save Personal Details'}</span>
            </button>
          </div>
        </form>
      )}

      {/* SUBTAB 2: HEALTH & INJURY HISTORY */}
      {subTab === 'health' && (
        <form onSubmit={handleSaveHealth} className="profile-form-pane">
          {/* Privacy Callout */}
          <div className="privacy-notice-box">
            <div className="privacy-icon-wrap">
              <Lock size={20} className="gold-text" />
            </div>
            <div>
              <h4>Health Data Privacy and Least-Privilege Protection</h4>
              <p>
                Your health information is sensitive personal data collected solely to ensure safe exercise programming.
                Only essential movement restrictions are shared with your assigned strength coach.
                Front-desk staff do not have access to these medical notes. Health data is never exposed in public APIs, QR codes, or logs.
              </p>
            </div>
          </div>

          <div className="form-card">
            <h3 className="card-title"><Heart size={18} /> Training Restrictions and Injury History</h3>
            <p className="card-subtitle">
              Help your coach tailor your exercise protocol to prevent re-injury and optimize recovery.
            </p>

            <div className="form-group full-width">
              <label htmlFor="hf-restr">Exercise Restrictions / Movements to Avoid</label>
              <textarea
                id="hf-restr"
                rows={2}
                className="profile-input"
                placeholder="e.g. Avoid overhead pressing due to rotator cuff impingement; no deep squats below 90 degrees."
                value={healthForm.exercise_restrictions}
                onChange={(e) => setHealthForm({ ...healthForm, exercise_restrictions: e.target.value })}
              />
              <small className="field-hint">This field is shared with your assigned strength coach for safety.</small>
            </div>

            <div className="form-grid-2">
              <div className="form-group">
                <label htmlFor="hf-curr-inj">Current Injuries / Limitations</label>
                <textarea
                  id="hf-curr-inj"
                  rows={2}
                  className="profile-input"
                  placeholder="e.g. Mild lower back strain, right wrist sprain"
                  value={healthForm.current_injuries}
                  onChange={(e) => setHealthForm({ ...healthForm, current_injuries: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label htmlFor="hf-past-inj">Past Injuries</label>
                <textarea
                  id="hf-past-inj"
                  rows={2}
                  className="profile-input"
                  placeholder="e.g. Left knee ACL tear in 2023 (fully rehabilitated)"
                  value={healthForm.past_injuries}
                  onChange={(e) => setHealthForm({ ...healthForm, past_injuries: e.target.value })}
                />
              </div>
            </div>

            <div className="form-grid-2">
              <div className="form-group">
                <label htmlFor="hf-cond">Health Conditions Disclosed</label>
                <textarea
                  id="hf-cond"
                  rows={2}
                  className="profile-input"
                  placeholder="e.g. Asthma, hypertension, diabetes (kept strictly confidential)"
                  value={healthForm.health_conditions}
                  onChange={(e) => setHealthForm({ ...healthForm, health_conditions: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label htmlFor="hf-allergies">Allergies Relevant to Gym Safety</label>
                <textarea
                  id="hf-allergies"
                  rows={2}
                  className="profile-input"
                  placeholder="e.g. Latex allergy, chalk sensitivity"
                  value={healthForm.allergies}
                  onChange={(e) => setHealthForm({ ...healthForm, allergies: e.target.value })}
                />
              </div>
            </div>

            <div className="form-group full-width">
              <label htmlFor="hf-surgery">Past Surgeries (Relevant to Training)</label>
              <textarea
                id="hf-surgery"
                rows={2}
                className="profile-input"
                placeholder="e.g. Arthroscopic meniscus repair (2022)"
                value={healthForm.surgery_history}
                onChange={(e) => setHealthForm({ ...healthForm, surgery_history: e.target.value })}
              />
            </div>
          </div>

          {/* Consented Medications Section */}
          <div className="form-card">
            <h3 className="card-title"><Shield size={18} /> Medications and Confidential Notes</h3>
            <p className="card-subtitle">
              Current medications are optional and only recorded when needed for safe training with explicit consent.
            </p>

            <div className="checkbox-consent-row">
              <input
                id="hf-consent"
                type="checkbox"
                checked={healthForm.has_medication_consent}
                onChange={(e) => setHealthForm({ ...healthForm, has_medication_consent: e.target.checked })}
              />
              <label htmlFor="hf-consent">
                I give explicit consent to record my current medications strictly for training safety and emergency awareness.
              </label>
            </div>

            {healthForm.has_medication_consent && (
              <div className="form-group full-width" style={{ marginTop: '16px' }}>
                <label htmlFor="hf-meds">Current Medications</label>
                <textarea
                  id="hf-meds"
                  rows={2}
                  className="profile-input"
                  placeholder="e.g. Albuterol inhaler as needed for exercise-induced bronchospasm"
                  value={healthForm.current_medications}
                  onChange={(e) => setHealthForm({ ...healthForm, current_medications: e.target.value })}
                />
              </div>
            )}

            <div className="form-group full-width" style={{ marginTop: '16px' }}>
              <label htmlFor="hf-notes">Additional Health Notes (Optional)</label>
              <textarea
                id="hf-notes"
                rows={2}
                className="profile-input"
                placeholder="Any additional physical considerations or safety notes you wish to document"
                value={healthForm.health_notes}
                onChange={(e) => setHealthForm({ ...healthForm, health_notes: e.target.value })}
              />
            </div>

            <div className="update-timestamp-box">
              <Clock size={14} />
              <span>
                Last Health Disclosure Revision: {profile?.lastHealthUpdate ? new Date(profile.lastHealthUpdate).toLocaleDateString() : 'Never revised'}
              </span>
            </div>
          </div>

          <div className="form-actions-row">
            <button type="submit" className="btn-gold-save" disabled={saving}>
              <Save size={16} />
              <span>{saving ? 'Saving...' : 'Save Health Disclosures'}</span>
            </button>
          </div>
        </form>
      )}

      {/* SUBTAB 3: BODY MEASUREMENTS */}
      {subTab === 'measurements' && (
        <div className="profile-tab-pane">
          <div className="measurements-top-bar">
            <div>
              <h3>Time-Series Body Measurements</h3>
              <p className="card-subtitle">
                Track historical weight, height, body fat, and muscle circumferences over time.
              </p>
            </div>
            <button
              type="button"
              className="btn-gold-action"
              onClick={() => setShowAddMeas(!showAddMeas)}
            >
              <Plus size={16} />
              <span>{showAddMeas ? 'Cancel' : 'Log New Measurement'}</span>
            </button>
          </div>

          {/* Add Measurement Subform */}
          {showAddMeas && (
            <form onSubmit={handleAddMeasurementSubmit} className="measurement-add-card">
              <h4>Log Body Measurement Record</h4>
              <div className="form-grid-3">
                <div className="form-group">
                  <label htmlFor="m-date">Measurement Date *</label>
                  <input
                    id="m-date"
                    type="date"
                    className="profile-input"
                    value={measForm.recorded_date}
                    onChange={(e) => setMeasForm({ ...measForm, recorded_date: e.target.value })}
                    max={new Date().toISOString().split('T')[0]}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="m-weight">Weight (kg) *</label>
                  <input
                    id="m-weight"
                    type="number"
                    step="0.1"
                    min="20"
                    max="350"
                    className="profile-input"
                    placeholder="e.g. 75.0"
                    value={measForm.weight_kg}
                    onChange={(e) => setMeasForm({ ...measForm, weight_kg: e.target.value })}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="m-height">Height (cm)</label>
                  <input
                    id="m-height"
                    type="number"
                    step="0.1"
                    min="80"
                    max="260"
                    className="profile-input"
                    placeholder="e.g. 175.5"
                    value={measForm.height_cm}
                    onChange={(e) => setMeasForm({ ...measForm, height_cm: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="m-fat">Body Fat %</label>
                  <input
                    id="m-fat"
                    type="number"
                    step="0.1"
                    min="3"
                    max="65"
                    className="profile-input"
                    placeholder="e.g. 15.5"
                    value={measForm.body_fat_pct}
                    onChange={(e) => setMeasForm({ ...measForm, body_fat_pct: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="m-chest">Chest (cm)</label>
                  <input
                    id="m-chest"
                    type="number"
                    step="0.1"
                    min="10"
                    max="200"
                    className="profile-input"
                    placeholder="e.g. 100"
                    value={measForm.chest_cm}
                    onChange={(e) => setMeasForm({ ...measForm, chest_cm: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="m-waist">Waist (cm)</label>
                  <input
                    id="m-waist"
                    type="number"
                    step="0.1"
                    min="10"
                    max="200"
                    className="profile-input"
                    placeholder="e.g. 84"
                    value={measForm.waist_cm}
                    onChange={(e) => setMeasForm({ ...measForm, waist_cm: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="m-hips">Hips (cm)</label>
                  <input
                    id="m-hips"
                    type="number"
                    step="0.1"
                    min="10"
                    max="200"
                    className="profile-input"
                    placeholder="e.g. 98"
                    value={measForm.hips_cm}
                    onChange={(e) => setMeasForm({ ...measForm, hips_cm: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="m-arms">Arms (cm)</label>
                  <input
                    id="m-arms"
                    type="number"
                    step="0.1"
                    min="10"
                    max="100"
                    className="profile-input"
                    placeholder="e.g. 37"
                    value={measForm.arms_cm}
                    onChange={(e) => setMeasForm({ ...measForm, arms_cm: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="m-thighs">Thighs (cm)</label>
                  <input
                    id="m-thighs"
                    type="number"
                    step="0.1"
                    min="10"
                    max="150"
                    className="profile-input"
                    placeholder="e.g. 58"
                    value={measForm.thighs_cm}
                    onChange={(e) => setMeasForm({ ...measForm, thighs_cm: e.target.value })}
                  />
                </div>
              </div>
              <div className="form-group full-width">
                <label htmlFor="m-notes">Measurement Notes</label>
                <input
                  id="m-notes"
                  type="text"
                  className="profile-input"
                  placeholder="e.g. Fasted morning weigh-in; body composition scan"
                  value={measForm.notes}
                  onChange={(e) => setMeasForm({ ...measForm, notes: e.target.value })}
                />
              </div>
              <div className="form-actions-row">
                <button
                  type="button"
                  className="btn-cancel"
                  onClick={() => setShowAddMeas(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-gold-save"
                  disabled={savingMeas}
                >
                  <Save size={16} />
                  <span>{savingMeas ? 'Saving...' : 'Save Measurement'}</span>
                </button>
              </div>
            </form>
          )}

          {/* Measurements List */}
          {measurements.length === 0 ? (
            <div className="empty-measurements-card">
              <Scale size={36} className="gold-text" />
              <h4>No Body Measurements Recorded</h4>
              <p>Start tracking your physical progress by recording your weight, height, and circumferences above.</p>
            </div>
          ) : (
            <div className="measurements-history-table-wrap">
              <table className="measurements-data-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Weight</th>
                    <th>Height</th>
                    <th>Body Fat</th>
                    <th>Chest</th>
                    <th>Waist</th>
                    <th>Hips</th>
                    <th>Arms</th>
                    <th>Source</th>
                    <th>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {measurements.map((m) => (
                    <tr key={m.id}>
                      <td><strong>{m.recordedDate}</strong></td>
                      <td className="gold-text">{m.weightKg ? `${m.weightKg} kg` : '-'}</td>
                      <td>{m.heightCm ? `${m.heightCm} cm` : '-'}</td>
                      <td>{m.bodyFatPct ? `${m.bodyFatPct}%` : '-'}</td>
                      <td>{m.chestCm ? `${m.chestCm} cm` : '-'}</td>
                      <td>{m.waistCm ? `${m.waistCm} cm` : '-'}</td>
                      <td>{m.hipsCm ? `${m.hipsCm} cm` : '-'}</td>
                      <td>{m.armsCm ? `${m.armsCm} cm` : '-'}</td>
                      <td>
                        <span className={`source-pill ${m.recordedByRole}`}>
                          {m.recordedByRole}
                        </span>
                      </td>
                      <td className="notes-cell">{m.notes || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* SUBTAB 4: GOALS & TARGETS */}
      {subTab === 'targets' && (
        <form onSubmit={handleSaveTargets} className="profile-form-pane">
          <div className="form-card">
            <h3 className="card-title"><Target size={18} /> Training Goals and Target Benchmarks</h3>
            <p className="card-subtitle">
              Set your target body weight and training objective to calculate accurate progress indicators.
            </p>

            <div className="form-grid-3">
              <div className="form-group">
                <label htmlFor="tf-goal">Primary Fitness Objective</label>
                <select
                  id="tf-goal"
                  className="profile-input"
                  value={targetsForm.primary_goal}
                  onChange={(e) => setTargetsForm({ ...targetsForm, primary_goal: e.target.value })}
                >
                  <option value="general_fitness">General Health & Fitness</option>
                  <option value="strength">Strength & Hypertrophy</option>
                  <option value="fat_loss">Fat Loss & Leanness</option>
                  <option value="athletic_performance">Athletic Performance</option>
                  <option value="rehabilitation">Mobility & Rehabilitation</option>
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="tf-height">Standing Height (cm)</label>
                <input
                  id="tf-height"
                  type="number"
                  step="0.1"
                  min="80"
                  max="260"
                  className="profile-input"
                  placeholder="e.g. 178.0"
                  value={targetsForm.height_cm}
                  onChange={(e) => setTargetsForm({ ...targetsForm, height_cm: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label htmlFor="tf-target-weight">Target Body Weight (kg)</label>
                <input
                  id="tf-target-weight"
                  type="number"
                  step="0.1"
                  min="20"
                  max="350"
                  className="profile-input"
                  placeholder="e.g. 72.0"
                  value={targetsForm.target_weight_kg}
                  onChange={(e) => setTargetsForm({ ...targetsForm, target_weight_kg: e.target.value })}
                />
              </div>
            </div>
          </div>

          <div className="form-actions-row">
            <button type="submit" className="btn-gold-save" disabled={saving}>
              <Save size={16} />
              <span>{saving ? 'Saving...' : 'Save Targets'}</span>
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
