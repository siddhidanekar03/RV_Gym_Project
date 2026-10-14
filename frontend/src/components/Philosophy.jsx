import { Target, Compass, Flame } from 'lucide-react';

export default function Philosophy() {
  return (
    <section className="section-container dark-surface" aria-label="Brand Philosophy">
      <div className="section-header">
        <span className="section-eyebrow">THE RVFITNESS CODE</span>
        <h2 className="section-title">Disciplined Training Philosophy</h2>
        <p className="section-lead">
          We operate on simple truths: consistency produces results, correct form protects longevity, and a focused gym environment elevates everyone.
        </p>
      </div>

      <div className="philosophy-grid">
        <div className="philosophy-card">
          <div className="philosophy-icon-wrap" aria-hidden="true">
            <Target size={24} className="gold-text" />
          </div>
          <h3 className="philosophy-title">Purpose Over Gimmicks</h3>
          <p className="philosophy-body">
            We prioritize heavy compound movements, calibrated loads, and methodical volume progression rather than fleeting fitness trends.
          </p>
        </div>

        <div className="philosophy-card">
          <div className="philosophy-icon-wrap" aria-hidden="true">
            <Compass size={24} className="gold-text" />
          </div>
          <h3 className="philosophy-title">Coaching Integrity</h3>
          <p className="philosophy-body">
            Our trainers are educators first. We teach movement mechanics, breath control, and lifting discipline so members train safely with confidence.
          </p>
        </div>

        <div className="philosophy-card">
          <div className="philosophy-icon-wrap" aria-hidden="true">
            <Flame size={24} className="gold-text" />
          </div>
          <h3 className="philosophy-title">A Respected Atmosphere</h3>
          <p className="philosophy-body">
            Weights are re-racked, chalk is respected, and mutual encouragement is standard. The gym is a sanctuary for personal physical improvement.
          </p>
        </div>
      </div>
    </section>
  );
}
