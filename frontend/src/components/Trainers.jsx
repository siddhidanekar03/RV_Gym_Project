import { useState, useEffect } from 'react';
import { UserCheck, RefreshCw, AlertCircle, Calendar } from 'lucide-react';
import { fetchTrainers } from '../api';

export default function Trainers({ onBookConsultation }) {
  const [trainers, setTrainers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await fetchTrainers();
        setTrainers(data.trainers || []);
      } catch (err) {
        setError(err.message || 'Unable to retrieve verified coaching roster.');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <section id="trainers" className="section-container" aria-label="Certified Coaching Staff">
      <div className="section-header">
        <span className="section-eyebrow">COACHING ROSTER</span>
        <h2 className="section-title">Certified Coaches & Trainers</h2>
        <p className="section-lead">
          Verified coaching credentials and specialized guidance for strength athletes, beginners, and physique goals.
        </p>
      </div>

      {loading && (
        <div className="status-container" role="status">
          <RefreshCw className="spinner-icon gold-text" size={32} />
          <p>Loading certified coaching roster...</p>
        </div>
      )}

      {error && (
        <div className="error-banner" role="alert">
          <AlertCircle size={24} className="danger-text" />
          <p>{error}</p>
        </div>
      )}

      {!loading && !error && (
        <div className="trainers-grid">
          {trainers.map((coach) => (
            <article key={coach.id} className="trainer-card">
              {/* Clearly Marked Approved Portrait Placeholder */}
              <div className="trainer-media-box">
                <div className="trainer-placeholder-avatar">
                  <span className="coach-monogram">{coach.name.charAt(0)}</span>
                  <span className="portrait-badge">
                    [Pending Approved Coach Portrait: {coach.name}]
                  </span>
                </div>
                <div className="coach-exp-tag">{coach.experience}</div>
              </div>

              <div className="trainer-body">
                <h3 className="trainer-name">{coach.name}</h3>
                <p className="trainer-role">{coach.role}</p>

                <div className="cert-box">
                  <UserCheck size={14} className="gold-text" />
                  <span>{coach.certifications}</span>
                </div>

                <p className="trainer-bio">{coach.bio}</p>

                <button
                  type="button"
                  className="btn-outline full-width mt-auto"
                  onClick={() => onBookConsultation(coach)}
                >
                  <Calendar size={14} />
                  <span>Consult Coach {coach.name.split(' ')[0]}</span>
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
