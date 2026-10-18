import { useState, useEffect } from 'react';
import {
  Medal,
  Flame,
  CalendarCheck,
  RefreshCw,
  AlertCircle,
  Shield,
  HelpCircle,
  Building,
  Calendar,
  ChevronLeft,
  ChevronRight,
  X
} from 'lucide-react';
import { fetchLeaderboard, fetchBranches, fetchScoringRules } from '../api';

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

export default function Leaderboard() {
  const [entries, setEntries] = useState([]);
  const [category, setCategory] = useState('Points');
  const [branchId, setBranchId] = useState('all');
  const [branches, setBranches] = useState([]);
  const [month, setMonth] = useState(10);
  const [year, setYear] = useState(2026);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [limit] = useState(25);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showRules, setShowRules] = useState(false);
  const [rulesData, setRulesData] = useState(null);

  // Load available branches
  useEffect(() => {
    let ignore = false;
    fetchBranches()
      .then((data) => {
        if (!ignore && Array.isArray(data)) {
          setBranches(data);
        }
      })
      .catch(() => {});
    return () => {
      ignore = true;
    };
  }, []);

  // Load scoring rules when opened
  useEffect(() => {
    let ignore = false;
    if (showRules && !rulesData) {
      fetchScoringRules()
        .then((data) => {
          if (!ignore) setRulesData(data);
        })
        .catch(() => {});
    }
    return () => {
      ignore = true;
    };
  }, [showRules, rulesData]);

  // Load leaderboard data on filter changes
  useEffect(() => {
    let ignore = false;
    async function loadData() {
      setLoading(true);
      setError(null);
      try {
        const params = {
          category: category === 'all' ? undefined : category,
          month,
          year,
          branchId: branchId === 'all' ? undefined : branchId,
          page,
          limit,
        };
        const res = await fetchLeaderboard(params);
        if (!ignore) {
          setEntries(res.leaderboard || []);
          setTotal(res.total || (res.leaderboard ? res.leaderboard.length : 0));
        }
      } catch (err) {
        if (!ignore) {
          setError(err.message || 'Unable to retrieve gym leaderboard.');
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    }
    loadData();
    return () => {
      ignore = true;
    };
  }, [category, branchId, month, year, page, limit]);

  const getRankBadge = (rank) => {
    if (rank === 1) return <span className="rank-badge rank-1" title="First Place"><Medal size={16} /> #1</span>;
    if (rank === 2) return <span className="rank-badge rank-2" title="Second Place"><Medal size={16} /> #2</span>;
    if (rank === 3) return <span className="rank-badge rank-3" title="Third Place"><Medal size={16} /> #3</span>;
    return <span className="rank-badge rank-default">#{rank}</span>;
  };

  const totalPages = Math.ceil(total / limit) || 1;

  return (
    <section id="leaderboard" className="section-container" aria-label="Public Gym Leaderboard">
      <div className="section-header">
        <span className="section-eyebrow">COMMUNITY STANDINGS</span>
        <h2 className="section-title">Privacy-First Gym Leaderboard</h2>
        <p className="section-lead">
          Verified floor attendance discipline and strength totals. Competition standings display gaming aliases only.
        </p>
      </div>

      <div className="leaderboard-card-container">
        {/* Controls Toolbar */}
        <div className="leaderboard-toolbar-grid">
          {/* Category Pills */}
          <div className="filter-pill-row">
            <button
              type="button"
              className={`filter-pill ${category === 'Points' ? 'active' : ''}`}
              onClick={() => {
                setCategory('Points');
                setPage(1);
              }}
            >
              Monthly Discipline Points
            </button>
            <button
              type="button"
              className={`filter-pill ${category === 'Power Total' ? 'active' : ''}`}
              onClick={() => {
                setCategory('Power Total');
                setPage(1);
              }}
            >
              Power Total (S/B/D)
            </button>
          </div>

          {/* Branch & Date Filters */}
          <div className="filters-right-group">
            <div className="select-wrap">
              <Building size={16} className="input-icon-left" />
              <select
                aria-label="Filter by Gym Campus"
                className="select-custom"
                value={branchId}
                onChange={(e) => {
                  setBranchId(e.target.value);
                  setPage(1);
                }}
              >
                <option value="all">All Campuses (Org-Wide)</option>
                {branches.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="select-wrap">
              <Calendar size={16} className="input-icon-left" />
              <select
                aria-label="Filter by Month"
                className="select-custom"
                value={month}
                onChange={(e) => {
                  setMonth(Number(e.target.value));
                  setPage(1);
                }}
              >
                {MONTH_NAMES.map((name, idx) => (
                  <option key={name} value={idx + 1}>
                    {name}
                  </option>
                ))}
              </select>
            </div>

            <div className="select-wrap">
              <select
                aria-label="Filter by Year"
                className="select-custom"
                value={year}
                onChange={(e) => {
                  setYear(Number(e.target.value));
                  setPage(1);
                }}
              >
                <option value={2025}>2025</option>
                <option value={2026}>2026</option>
                <option value={2027}>2027</option>
              </select>
            </div>

            <button
              type="button"
              className="btn-rules-toggle"
              onClick={() => setShowRules(true)}
              title="View transparent scoring rules"
            >
              <HelpCircle size={16} />
              <span>Scoring Rules</span>
            </button>
          </div>
        </div>

        {/* Privacy Note */}
        <div className="leaderboard-privacy-banner" role="note">
          <Shield size={16} className="gold-text flex-shrink-0" />
          <span>
            Privacy-safe standings: Only non-identifying gaming handles are published. Legal names, phone numbers,
            emails, and member IDs are never exposed in public responses. Members who opt out are strictly excluded.
          </span>
        </div>

        {/* Loading State */}
        {loading && (
          <div className="status-container" role="status">
            <RefreshCw className="spinner-icon gold-text" size={32} />
            <p>Retrieving verified standings for {MONTH_NAMES[month - 1]} {year}...</p>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="error-banner" role="alert">
            <AlertCircle size={24} className="danger-text" />
            <p>{error}</p>
          </div>
        )}

        {/* Empty State */}
        {!loading && !error && entries.length === 0 && (
          <div className="leaderboard-empty-state" role="status">
            <Medal size={48} className="gold-text opacity-40 mb-3" />
            <h3>No Standings Recorded Yet</h3>
            <p>
              No verified attendance points or coach-verified lifts found for {MONTH_NAMES[month - 1]} {year}{' '}
              {branchId !== 'all' ? `at this campus` : 'across campuses'}. Floor check-ins will populate this board automatically.
            </p>
          </div>
        )}

        {/* Data Table */}
        {!loading && !error && entries.length > 0 && (
          <>
            <div className="table-responsive">
              <table className="leaderboard-table">
                <thead>
                  <tr>
                    <th scope="col" className="col-rank">Rank</th>
                    <th scope="col" className="col-member">Gaming Handle</th>
                    <th scope="col" className="col-metric">Category</th>
                    <th scope="col" className="col-score">Verified Score</th>
                    <th scope="col" className="col-streak">Active Streak</th>
                    <th scope="col" className="col-visits">Attendance Days</th>
                    <th scope="col" className="col-branch">Campus</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((item) => (
                    <tr key={`${item.rank}-${item.name}`}>
                      <td className="col-rank">{getRankBadge(item.rank)}</td>
                      <td className="col-member">
                        <div className="member-name-cell">
                          <span className="avatar-chip">
                            {(item.alias || item.name).charAt(0).toUpperCase()}
                          </span>
                          <div className="handle-group">
                            <strong className="gaming-handle">{item.alias || item.name}</strong>
                            {item.tier && (
                              <span className={`tier-badge tier-${item.tier.toLowerCase()}`}>
                                {item.tier}
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="col-metric">
                        <span className="category-tag-subtle">{item.category}</span>
                      </td>
                      <td className="col-score">
                        <span className="score-value gold-text">{item.score}</span>
                      </td>
                      <td className="col-streak">
                        <span className="streak-badge">
                          <Flame size={14} className="gold-text" />
                          <span>{item.streak || 0} Days</span>
                        </span>
                      </td>
                      <td className="col-visits">
                        <span className="visits-text">
                          <CalendarCheck size={14} className="text-muted" />
                          <span>{item.distinctDays || item.visitsThisMonth || 0} Days</span>
                        </span>
                      </td>
                      <td className="col-branch">
                        <span className="branch-tag">{item.branchName || 'RVFitness'}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <div className="leaderboard-pagination">
                <button
                  type="button"
                  className="btn-page-nav"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  aria-label="Previous page"
                >
                  <ChevronLeft size={16} />
                  <span>Previous</span>
                </button>
                <span className="page-indicator">
                  Page {page} of {totalPages} ({total} participants)
                </span>
                <button
                  type="button"
                  className="btn-page-nav"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  aria-label="Next page"
                >
                  <span>Next</span>
                  <ChevronRight size={16} />
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Transparent Scoring Rules Modal */}
      {showRules && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="rules-modal-title">
          <div className="modal-card scoring-rules-modal">
            <div className="modal-header">
              <div className="modal-title-wrap">
                <Shield size={20} className="gold-text" />
                <h3 id="rules-modal-title" className="modal-title">Transparent Scoring Policy</h3>
              </div>
              <button
                type="button"
                className="btn-modal-close"
                onClick={() => setShowRules(false)}
                aria-label="Close scoring rules modal"
              >
                <X size={18} />
              </button>
            </div>

            <div className="modal-body">
              <p className="rules-lead">
                Points are calculated durably on the server using an append-only points ledger. Scoring enforces strict
                anti-abuse controls to incentivize consistent discipline rather than excessive or fabricated visits.
              </p>

              <div className="rules-grid">
                {(rulesData?.rules || [
                  {
                    activity: 'Verified Floor Check-In',
                    points: 10,
                    description: 'Awarded for verified gym entrance via desk RFID scan, entry QR token, or staff desk check-in.',
                    frequencyLimit: 'Maximum 1 award per calendar date.'
                  },
                  {
                    activity: 'Coach-Verified Personal Record (PR)',
                    points: 25,
                    description: 'Awarded when certified RVFitness strength coach verifies a benchmark lift or fitness achievement.',
                    frequencyLimit: 'Per verified milestone submission.'
                  },
                  {
                    activity: '7-Day Discipline Streak Milestone',
                    points: 20,
                    description: 'Bonus awarded upon reaching every 7 consecutive days of consistent training discipline.',
                    frequencyLimit: 'Awarded at each 7-day milestone (7, 14, 21, 28... days).'
                  },
                ]).map((r) => (
                  <div key={r.activity} className="rule-card-item">
                    <div className="rule-top-line">
                      <strong className="rule-activity">{r.activity}</strong>
                      <span className="rule-points-pill">+{r.points} pts</span>
                    </div>
                    <p className="rule-desc">{r.description}</p>
                    <span className="rule-limit-tag">{r.frequencyLimit}</span>
                  </div>
                ))}
              </div>

              <div className="anti-abuse-box">
                <AlertCircle size={16} className="gold-text flex-shrink-0" />
                <p>
                  {rulesData?.antiAbusePolicy ||
                    'Anti-abuse policy: Points are only awarded for successful, verified attendance records. Failed check-in attempts, QR scans without entrance, rejected attempts, and duplicate scans earn zero points. A strict daily cap prevents artificial point inflation.'}
                </p>
              </div>
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn-primary-gold"
                onClick={() => setShowRules(false)}
              >
                Understood
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
