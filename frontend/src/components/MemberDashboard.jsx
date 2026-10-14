import { useState } from 'react';
import {
  Calendar,
  Flame,
  Dumbbell,
  CheckCircle2,
  AlertCircle,
  Sparkles,
  User,
  ArrowLeft
} from 'lucide-react';
import confetti from 'canvas-confetti';
import MembershipCard3D from './MembershipCard3D';
import { memberCheckIn } from '../api';

export default function MemberDashboard({
  user,
  token,
  onUserUpdate,
  onClose
}) {
  const [checkingIn, setCheckingIn] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [error, setError] = useState(null);

  const handleCheckIn = async () => {
    if (user.todayCheckedIn) return;
    setCheckingIn(true);
    setError(null);
    setFeedback(null);

    try {
      const data = await memberCheckIn(token);
      setFeedback(data.message);
      // Trigger subtle celebration
      confetti({
        particleCount: 50,
        spread: 60,
        origin: { y: 0.8 },
        colors: ['#d4af37', '#f8fafc', '#b89325']
      });

      // Update parent user state
      onUserUpdate({
        ...user,
        todayCheckedIn: true,
        streakDays: data.streakDays,
        attendanceThisMonth: data.attendanceThisMonth
      });
    } catch (err) {
      setError(err.message || 'Check-in failed');
    } finally {
      setCheckingIn(false);
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
        {error && (
          <div className="feedback-alert danger" role="alert">
            <AlertCircle size={18} />
            <span>{error}</span>
          </div>
        )}

        <div className="dashboard-grid">
          {/* Left Column: 3D Digital Card & Fast Check-In */}
          <div className="dashboard-col left-col">
            <MembershipCard3D member={user} />

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
                  <button
                    type="button"
                    disabled={checkingIn}
                    className="btn-checkin-gold"
                    onClick={handleCheckIn}
                  >
                    <Sparkles size={18} />
                    <span>{checkingIn ? 'Verifying Check-In...' : 'Check In To Gym Today'}</span>
                  </button>
                )}
              </div>
            </div>

            {/* Assigned Routine from Coach */}
            <div className="workout-routine-card">
              <div className="routine-header">
                <Dumbbell size={18} className="gold-text" />
                <h3 className="widget-title">Assigned Training Routine</h3>
              </div>
              <p className="coach-assignment">
                Assigned by <strong>{user?.assignedPlan?.trainer || 'Head Coach Rohit V.'}</strong>
              </p>
              <div className="routine-split-tag">
                {user?.assignedPlan?.split || 'Strength Progression'}
              </div>
              <div className="today-focus-box">
                <span className="focus-label">Today&apos;s Workout Focus:</span>
                <p className="focus-text">
                  {user?.assignedPlan?.todayFocus || 'Compound lifts focus: Progressive overload on Bench and Accessories.'}
                </p>
              </div>
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
          </div>
        </div>
      </div>
    </div>
  );
}
