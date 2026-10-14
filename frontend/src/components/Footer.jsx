import { ShieldCheck, MapPin, Phone, Mail, Clock } from 'lucide-react';

const CURRENT_YEAR = 2026;

export default function Footer({ onNavigate, onOpenPrivacy, onOpenTerms }) {

  return (
    <footer className="site-footer" aria-label="Site Footer">
      <div className="footer-top-container">
        {/* Brand Column */}
        <div className="footer-col brand-col">
          <div className="footer-brand">
            <span className="brand-badge" aria-hidden="true">RV</span>
            <div>
              <span className="footer-brand-title">RVFITNESS</span>
              <span className="footer-brand-sub">NARSOBAWADI</span>
            </div>
          </div>
          <p className="footer-tagline">
            Disciplined strength, verified coaching, and athletic conditioning in Narsobawadi.
          </p>
          <div className="footer-verified-badge">
            <ShieldCheck size={16} className="gold-text" />
            <span>Official Gym Management Portal</span>
          </div>
        </div>

        {/* Navigation Links Column */}
        <div className="footer-col">
          <h4 className="footer-heading">Navigation</h4>
          <ul className="footer-links-list">
            <li><button type="button" onClick={() => onNavigate('home')}>Home</button></li>
            <li><button type="button" onClick={() => onNavigate('about')}>About RVFitness</button></li>
            <li><button type="button" onClick={() => onNavigate('equipment')}>Equipment</button></li>
            <li><button type="button" onClick={() => onNavigate('trainers')}>Coaches & Staff</button></li>
            <li><button type="button" onClick={() => onNavigate('events')}>Events & Meets</button></li>
            <li><button type="button" onClick={() => onNavigate('leaderboard')}>Public Leaderboard</button></li>
            <li><button type="button" onClick={() => onNavigate('gallery')}>Facility Zones</button></li>
          </ul>
        </div>

        {/* Membership Options Column */}
        <div className="footer-col">
          <h4 className="footer-heading">Memberships</h4>
          <ul className="footer-links-list">
            <li><button type="button" onClick={() => onNavigate('memberships')}>Monthly Access</button></li>
            <li><button type="button" onClick={() => onNavigate('memberships')}>Quarterly Plan (Featured)</button></li>
            <li><button type="button" onClick={() => onNavigate('memberships')}>Annual Unlimited</button></li>
            <li><button type="button" onClick={() => onNavigate('contact')}>Front Desk Inquiries</button></li>
          </ul>
        </div>

        {/* Contact Info Column */}
        <div className="footer-col contact-col">
          <h4 className="footer-heading">Facility Contact</h4>
          <ul className="footer-contact-list">
            <li>
              <MapPin size={16} className="gold-text flex-shrink-0" />
              <span>Near Datta Mandir Road, Narsobawadi 416104</span>
            </li>
            <li>
              <Phone size={16} className="gold-text flex-shrink-0" />
              <span>+91 98220 12345</span>
            </li>
            <li>
              <Mail size={16} className="gold-text flex-shrink-0" />
              <span>contact@rvfitness.in</span>
            </li>
            <li>
              <Clock size={16} className="gold-text flex-shrink-0" />
              <span>Mon-Sat: 6 AM - 10 PM | Sun: 7 AM - 12 PM</span>
            </li>
          </ul>
        </div>
      </div>

      <div className="footer-bottom-container">
        <p className="footer-copyright">
          © {CURRENT_YEAR} RVFitness Narsobawadi. All rights reserved.
        </p>

        <div className="footer-legal-links">
          <button type="button" className="legal-btn" onClick={onOpenPrivacy}>
            Privacy Policy
          </button>
          <span className="legal-divider" aria-hidden="true">•</span>
          <button type="button" className="legal-btn" onClick={onOpenTerms}>
            Terms & Conditions
          </button>
        </div>
      </div>
    </footer>
  );
}
