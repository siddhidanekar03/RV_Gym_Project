import { useState, useEffect } from 'react';
import { Check, AlertCircle, RefreshCw, Star, ShieldCheck } from 'lucide-react';
import { fetchPlans } from '../api';

export default function Memberships({ onSelectPlan }) {
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadPlans = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPlans();
      setPlans(data.plans || []);
    } catch (err) {
      setError(err.message || 'Unable to retrieve live membership plans from the gym server.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPlans();
  }, []);

  return (
    <section id="memberships" className="section-container dark-surface" aria-label="Membership Plans">
      <div className="section-header">
        <span className="section-eyebrow">ENROLLMENT OPTIONS</span>
        <h2 className="section-title">Verified Membership Plans</h2>
        <p className="section-lead">
          Straightforward pricing with full facility access. All rates and benefits are served directly from the RVFitness management system.
        </p>
      </div>

      {loading && (
        <div className="status-container" role="status" aria-live="polite">
          <RefreshCw className="spinner-icon gold-text" size={32} />
          <p>Connecting to RVFitness database for current rates...</p>
        </div>
      )}

      {error && (
        <div className="error-banner" role="alert">
          <AlertCircle size={24} className="danger-text" />
          <div className="error-content">
            <strong>Unable to Load Verified Plans</strong>
            <p>{error}</p>
            <button type="button" className="btn-retry" onClick={loadPlans}>
              <RefreshCw size={14} />
              <span>Retry Server Connection</span>
            </button>
          </div>
        </div>
      )}

      {!loading && !error && plans.length === 0 && (
        <div className="empty-state-card" role="status">
          <p>No membership plans are currently active in the management database.</p>
        </div>
      )}

      {!loading && !error && plans.length > 0 && (
        <div className="plans-grid">
          {plans.map((plan) => (
            <div
              key={plan.id}
              className={`plan-card ${plan.featured ? 'featured-card' : ''}`}
            >
              {plan.featured && (
                <div className="featured-ribbon">
                  <Star size={12} fill="currentColor" />
                  <span>RECOMMENDED PLAN</span>
                </div>
              )}

              <div className="plan-header">
                <h3 className="plan-name">{plan.name}</h3>
                <div className="plan-price-block">
                  <span className="currency">{plan.currency}</span>
                  <span className="amount">{plan.price.toLocaleString('en-IN')}</span>
                  <span className="billing-cycle">/{plan.billingCycle.replace('per ', '')}</span>
                </div>
                <div className="plan-status-row">
                  <span className="plan-status-badge">
                    <ShieldCheck size={14} className="gold-text" />
                    <span>Active Status ({plan.durationDays} Days)</span>
                  </span>
                </div>
              </div>

              <div className="plan-divider" />

              <ul className="plan-perks-list" aria-label={`Perks for ${plan.name} plan`}>
                {plan.perks.map((perk, idx) => (
                  <li key={idx} className="perk-item">
                    <Check size={16} className="perk-check" aria-hidden="true" />
                    <span>{perk}</span>
                  </li>
                ))}
              </ul>

              <div className="plan-footer">
                <button
                  type="button"
                  className={plan.featured ? 'btn-gold-solid full-width' : 'btn-outline full-width'}
                  onClick={() => onSelectPlan(plan)}
                >
                  Choose {plan.name}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
