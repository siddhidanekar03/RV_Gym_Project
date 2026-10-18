import { useState, useEffect } from 'react';
import { ArrowRight, Clock, MapPin, Dumbbell, Camera } from 'lucide-react';
import { fetchGymInfo } from '../api';

export default function Hero({ onEnrollClick, onExploreClick }) {
  const [heroData, setHeroData] = useState(null);
  const [imageLoadError, setImageLoadError] = useState(false);

  useEffect(() => {
    fetchGymInfo()
      .then((data) => {
        if (data && data.hero) {
          setHeroData(data);
          setImageLoadError(false);
        }
      })
      .catch(() => {});
  }, []);

  const hero = heroData?.hero || {};
  const badgeText = hero.badgeText || 'RVFITNESS · NARSOBAWADI';
  const badgeTiming = hero.badgeTiming || '6:00 AM - 10:00 PM';
  const headline = hero.headline || 'BUILD STRENGTH.\nDEMAND DISCIPLINE.\nDEFINE YOURSELF.';
  const subtitle = hero.subtitle || 'A serious strength and athletic conditioning facility in Narsobawadi. Certified coaching, modern free-weight equipment, and a focused environment designed for consistent progress.';
  const ctaPrimary = hero.ctaPrimary || 'Enroll In Membership';
  const ctaSecondary = hero.ctaSecondary || 'Explore Facilities';
  const coverImageUrl = hero.coverImageUrl || null;

  return (
    <section id="home" className="hero-section" aria-label="Welcome to RVFitness">
      <div className="hero-grid-overlay" aria-hidden="true" />

      <div className="hero-content-wrapper">
        <div className="hero-text-block">
          {/* Facility Status Badge */}
          <div className="hero-badge">
            <span className="live-dot" aria-hidden="true" />
            <span className="badge-text">{badgeText}</span>
            <span className="badge-timing">{badgeTiming}</span>
          </div>

          <h1 className="hero-headline" style={{ whiteSpace: 'pre-line' }}>
            {headline}
          </h1>

          <p className="hero-description">
            {subtitle}
          </p>

          <div className="hero-actions-row">
            <button
              type="button"
              className="btn-gold-large"
              onClick={onEnrollClick}
            >
              <span>{ctaPrimary}</span>
              <ArrowRight size={18} aria-hidden="true" />
            </button>
            <button
              type="button"
              className="btn-outline-large"
              onClick={onExploreClick}
            >
              <span>{ctaSecondary}</span>
            </button>
          </div>

          {/* Verified Facility Details Strip */}
          <div className="facility-strip" aria-label="Verified Facility Overview">
            <div className="strip-item">
              <Clock size={18} className="gold-text" aria-hidden="true" />
              <div>
                <strong>Operating Hours</strong>
                <span>6 AM - 10 PM Daily (Sun: 7 AM - 12 PM)</span>
              </div>
            </div>
            <div className="strip-divider" aria-hidden="true" />
            <div className="strip-item">
              <MapPin size={18} className="gold-text" aria-hidden="true" />
              <div>
                <strong>Facility Location</strong>
                <span>Datta Mandir Road, Narsobawadi</span>
              </div>
            </div>
            <div className="strip-divider" aria-hidden="true" />
            <div className="strip-item">
              <Dumbbell size={18} className="gold-text" aria-hidden="true" />
              <div>
                <strong>Floor Equipment</strong>
                <span>Olympic Racks & Heavy Free Weights</span>
              </div>
            </div>
          </div>
        </div>

        {/* Hero Visual Block with Dynamic Cover Image Support */}
        <div className="hero-visual-card">
          <div className="hero-visual-inner">
            <div className="visual-graphic-container">
              {coverImageUrl && !imageLoadError ? (
                <div className="hero-cover-image-wrap" style={{ position: 'relative', width: '100%', height: '100%' }}>
                  <img
                    src={coverImageUrl}
                    alt="RVFitness facility floor"
                    className="hero-cover-img"
                    style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
                    onError={() => setImageLoadError(true)}
                  />
                  <div
                    style={{
                      position: 'absolute',
                      inset: 0,
                      background: 'linear-gradient(180deg, rgba(12, 14, 18, 0.1) 0%, rgba(12, 14, 18, 0.75) 100%)',
                      pointerEvents: 'none',
                    }}
                  />
                  <div
                    style={{
                      position: 'absolute',
                      bottom: '16px',
                      left: '16px',
                      right: '16px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '8px 12px',
                      background: 'rgba(12, 14, 18, 0.85)',
                      backdropFilter: 'blur(8px)',
                      border: '1px solid rgba(212, 175, 55, 0.3)',
                      borderRadius: '4px',
                      zIndex: 2,
                    }}
                  >
                    <span style={{ fontSize: '11px', fontWeight: '700', letterSpacing: '1px', color: 'var(--accent-gold)' }}>
                      RVFITNESS TRAINING FACILITY
                    </span>
                    <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Narsobawadi</span>
                  </div>
                </div>
              ) : (
                <>
                  <div className="monogram-watermark" aria-hidden="true">RV</div>
                  <div className="gym-floor-diagram" aria-hidden="true">
                    <div className="diagram-zone zone-free-weights">
                      <span>FREE WEIGHTS ZONE</span>
                    </div>
                    <div className="diagram-zone zone-racks">
                      <span>POWER RACKS</span>
                    </div>
                    <div className="diagram-zone zone-cardio">
                      <span>CARDIO ROW</span>
                    </div>
                    <div className="diagram-zone zone-turf">
                      <span>TURF TRACK</span>
                    </div>
                  </div>
                </>
              )}
            </div>

            {(!coverImageUrl || imageLoadError) && (
              <div className="placeholder-tag-banner">
                <Camera size={18} className="gold-text" aria-hidden="true" />
                <div>
                  <strong>Pending Authorized Gym Photography</strong>
                  <small>Floor photography is scheduled for publication upon facility review.</small>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
