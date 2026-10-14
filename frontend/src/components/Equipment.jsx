import { useState, useEffect } from 'react';
import { Dumbbell, RefreshCw, AlertCircle, CheckCircle2 } from 'lucide-react';
import { fetchEquipment } from '../api';

export default function Equipment() {
  const [equipmentList, setEquipmentList] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await fetchEquipment();
        setEquipmentList(data.equipment || []);
      } catch (err) {
        setError(err.message || 'Unable to retrieve verified equipment inventory.');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const categories = ['All', ...new Set(equipmentList.map(e => e.category))];

  const filtered = selectedCategory === 'All'
    ? equipmentList
    : equipmentList.filter(e => e.category === selectedCategory);

  return (
    <section id="equipment" className="section-container" aria-label="Gym Equipment Inventory">
      <div className="section-header">
        <span className="section-eyebrow">VERIFIED HARDWARE</span>
        <h2 className="section-title">Training Equipment</h2>
        <p className="section-lead">
          Industrial-grade strength and conditioning apparatus verified on the RVFitness gym floor in Narsobawadi.
        </p>
      </div>

      {/* Category Filter Pills */}
      {categories.length > 1 && (
        <div className="filter-pill-row" role="tablist" aria-label="Filter equipment by category">
          {categories.map((cat) => (
            <button
              key={cat}
              type="button"
              role="tab"
              aria-selected={selectedCategory === cat}
              className={`filter-pill ${selectedCategory === cat ? 'active' : ''}`}
              onClick={() => setSelectedCategory(cat)}
            >
              {cat}
            </button>
          ))}
        </div>
      )}

      {loading && (
        <div className="status-container" role="status">
          <RefreshCw className="spinner-icon gold-text" size={32} />
          <p>Loading verified equipment list...</p>
        </div>
      )}

      {error && (
        <div className="error-banner" role="alert">
          <AlertCircle size={24} className="danger-text" />
          <p>{error}</p>
        </div>
      )}

      {!loading && !error && (
        <div className="equipment-grid">
          {filtered.map((item) => (
            <article key={item.id} className="equipment-card">
              {/* Clearly Identified Placeholder Visual */}
              <div className="equipment-media-box">
                <div className="media-placeholder-graphic">
                  <Dumbbell size={36} className="placeholder-icon-gold" aria-hidden="true" />
                  <span className="placeholder-badge">
                    [Pending Authorized Equipment Photo]
                  </span>
                </div>
                <span className="category-tag">{item.category}</span>
              </div>

              <div className="equipment-info">
                <h3 className="equipment-name">{item.name}</h3>
                <p className="equipment-spec">{item.spec}</p>
                <div className="equipment-status">
                  <CheckCircle2 size={14} className="gold-text" />
                  <span>Verified On Gym Floor</span>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
