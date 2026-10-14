import { useState, useEffect } from 'react';
import { Medal, Flame, CalendarCheck, RefreshCw, AlertCircle } from 'lucide-react';
import { fetchLeaderboard } from '../api';

export default function Leaderboard() {
  const [entries, setEntries] = useState([]);
  const [category, setCategory] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadData = async (cat) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchLeaderboard(cat);
      setEntries(data.leaderboard || []);
    } catch (err) {
      setError(err.message || 'Unable to retrieve gym leaderboard.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData(category);
  }, [category]);

  const getRankBadge = (rank) => {
    if (rank === 1) return <span className="rank-badge rank-1" title="First Place"><Medal size={16} /> #1</span>;
    if (rank === 2) return <span className="rank-badge rank-2" title="Second Place"><Medal size={16} /> #2</span>;
    if (rank === 3) return <span className="rank-badge rank-3" title="Third Place"><Medal size={16} /> #3</span>;
    return <span className="rank-badge rank-default">#{rank}</span>;
  };

  return (
    <section id="leaderboard" className="section-container" aria-label="Public Gym Leaderboard">
      <div className="section-header">
        <span className="section-eyebrow">COMMUNITY STANDINGS</span>
        <h2 className="section-title">Public Gym Leaderboard</h2>
        <p className="section-lead">
          Verified strength totals and active training consistency recorded on the RVFitness gym floor.
        </p>
      </div>

      <div className="leaderboard-card-container">
        {/* Category Controls */}
        <div className="leaderboard-toolbar">
          <div className="filter-pill-row mb-0">
            <button
              type="button"
              className={`filter-pill ${category === 'all' ? 'active' : ''}`}
              onClick={() => setCategory('all')}
            >
              All Categories
            </button>
            <button
              type="button"
              className={`filter-pill ${category === 'Power Total' ? 'active' : ''}`}
              onClick={() => setCategory('Power Total')}
            >
              Power Total (S/B/D)
            </button>
          </div>
          <span className="privacy-note">
            Non-sensitive competition handles displayed with member consent.
          </span>
        </div>

        {loading && (
          <div className="status-container" role="status">
            <RefreshCw className="spinner-icon gold-text" size={32} />
            <p>Loading leaderboard standings...</p>
          </div>
        )}

        {error && (
          <div className="error-banner" role="alert">
            <AlertCircle size={24} className="danger-text" />
            <p>{error}</p>
          </div>
        )}

        {!loading && !error && (
          <div className="table-responsive">
            <table className="leaderboard-table">
              <thead>
                <tr>
                  <th scope="col" className="col-rank">Rank</th>
                  <th scope="col" className="col-member">Member</th>
                  <th scope="col" className="col-metric">Category</th>
                  <th scope="col" className="col-score">Verified Score</th>
                  <th scope="col" className="col-streak">Streak</th>
                  <th scope="col" className="col-visits">Monthly Visits</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((item) => (
                  <tr key={`${item.rank}-${item.name}`}>
                    <td className="col-rank">{getRankBadge(item.rank)}</td>
                    <td className="col-member">
                      <div className="member-name-cell">
                        <span className="avatar-chip">{item.name.charAt(0)}</span>
                        <strong>{item.name}</strong>
                      </div>
                    </td>
                    <td className="col-metric">
                      <span className="category-tag-subtle">{item.category}</span>
                    </td>
                    <td className="col-score">
                      <span className="score-value">{item.score}</span>
                    </td>
                    <td className="col-streak">
                      <span className="streak-badge">
                        <Flame size={14} className="gold-text" />
                        <span>{item.streak} Days</span>
                      </span>
                    </td>
                    <td className="col-visits">
                      <span className="visits-text">
                        <CalendarCheck size={14} className="text-muted" />
                        <span>{item.visitsThisMonth} sessions</span>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
