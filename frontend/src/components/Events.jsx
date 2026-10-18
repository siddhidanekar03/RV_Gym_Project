import { useState, useEffect } from 'react';
import { CalendarDays, Trophy, RefreshCw, AlertCircle, ArrowUpRight } from 'lucide-react';
import { fetchPublicAnnouncements, fetchEvents } from '../api';

export default function Events({ onRegisterEvent }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function load() {
      try {
        // First try live announcements feed
        const annData = await fetchPublicAnnouncements().catch(() => null);
        if (annData && annData.announcements && annData.announcements.length > 0) {
          const mapped = annData.announcements.map((a) => ({
            id: a.id,
            title: a.title,
            description: a.body,
            date: a.publishedAt ? new Date(a.publishedAt).toLocaleDateString() : 'Scheduled',
            status: a.category.toUpperCase(),
            imageUrl: a.imageUrl,
            isAnnouncement: true,
            branchName: a.branchName,
            isOrgWide: a.isOrgWide,
          }));
          setEvents(mapped);
        } else {
          // Fallback to static competitions feed
          const data = await fetchEvents();
          setEvents(data.events || []);
        }
      } catch (err) {
        setError(err.message || 'Unable to load scheduled events.');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <section id="events" className="section-container dark-surface" aria-label="Announcements & Events">
      <div className="section-header">
        <span className="section-eyebrow">FACILITY ANNOUNCEMENTS</span>
        <h2 className="section-title">Events & Competitions</h2>
        <p className="section-lead">
          Official gym competitions, seasonal lifting meets, and member discipline challenges organized at RVFitness.
        </p>
      </div>

      {loading && (
        <div className="status-container" role="status">
          <RefreshCw className="spinner-icon gold-text" size={32} />
          <p>Loading published events feed...</p>
        </div>
      )}

      {error && (
        <div className="error-banner" role="alert">
          <AlertCircle size={24} className="danger-text" />
          <p>{error}</p>
        </div>
      )}

      {!loading && !error && events.length === 0 && (
        <div className="empty-state-card">
          <p>No member events are currently open for registration.</p>
        </div>
      )}

      {!loading && !error && events.length > 0 && (
        <div className="events-grid">
          {events.map((evt) => (
            <article key={evt.id} className="event-card">
              <div className="event-badge-row">
                <span className="event-date-badge">
                  <CalendarDays size={14} />
                  <span>{evt.date}</span>
                </span>
                <span className="event-status-pill">{evt.status}</span>
              </div>

              {evt.imageUrl && (
                <div className="event-banner-wrap">
                  <img src={evt.imageUrl} alt="" className="event-banner-img" />
                </div>
              )}

              <div className="event-body">
                <h3 className="event-title">
                  <Trophy size={20} className="gold-text inline-icon" aria-hidden="true" />
                  <span>{evt.title}</span>
                </h3>
                <p className="event-desc">{evt.description}</p>
              </div>

              <div className="event-footer">
                <button
                  type="button"
                  className="btn-gold-solid full-width"
                  onClick={() => onRegisterEvent(evt)}
                >
                  <span>Register at Front Desk</span>
                  <ArrowUpRight size={16} />
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
