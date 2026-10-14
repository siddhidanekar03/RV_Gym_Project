import { ArrowRight, Clock, MapPin, Dumbbell, Camera } from 'lucide-react';

export default function Hero({ onEnrollClick, onExploreClick }) {
  return (
    <section id="home" className="hero-section" aria-label="Welcome to RVFitness">
      <div className="hero-grid-overlay" aria-hidden="true" />

      <div className="hero-content-wrapper">
        <div className="hero-text-block">
          {/* Facility Status Badge */}
          <div className="hero-badge">
            <span className="live-dot" aria-hidden="true" />
            <span className="badge-text">RVFITNESS · NARSOBAWADI</span>
            <span className="badge-timing">6:00 AM - 10:00 PM</span>
          </div>

          <h1 className="hero-headline">
            BUILD STRENGTH.<br />
            <span className="gold-highlight">DEMAND DISCIPLINE.</span><br />
            DEFINE YOURSELF.
          </h1>

          <p className="hero-description">
            A serious strength and athletic conditioning facility in Narsobawadi. Certified coaching, modern free-weight equipment, and a focused environment designed for consistent progress.
          </p>

          <div className="hero-actions-row">
            <button
              type="button"
              className="btn-gold-large"
              onClick={onEnrollClick}
            >
              <span>Enroll In Membership</span>
              <ArrowRight size={18} aria-hidden="true" />
            </button>
            <button
              type="button"
              className="btn-outline-large"
              onClick={onExploreClick}
            >
              <span>Explore Facilities</span>
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

        {/* Hero Visual Block with Clear Placeholder Indicator */}
        <div className="hero-visual-card">
          <div className="hero-visual-inner">
            <div className="visual-graphic-container">
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
            </div>

            <div className="placeholder-tag-banner">
              <Camera size={18} className="gold-text" aria-hidden="true" />
              <div>
                <strong>Pending Authorized Gym Photography</strong>
                <small>Floor photography is scheduled for publication upon facility review.</small>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
