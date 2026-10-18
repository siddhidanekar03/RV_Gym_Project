import { useState, useRef } from 'react';
import { ShieldCheck, Wifi, QrCode } from 'lucide-react';

export default function MembershipCard3D({ member, onOpenQR }) {
  const [rotate, setRotate] = useState({ x: 0, y: 0 });
  const [glare, setGlare] = useState({ x: 50, y: 50, opacity: 0 });
  const [is3DActive, setIs3DActive] = useState(true);
  const cardRef = useRef(null);

  const handleMouseMove = (e) => {
    if (!is3DActive || !cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;

    const rotateX = ((y - centerY) / centerY) * -12;
    const rotateY = ((x - centerX) / centerX) * 14;

    const glareX = (x / rect.width) * 100;
    const glareY = (y / rect.height) * 100;

    setRotate({ x: rotateX, y: rotateY });
    setGlare({ x: glareX, y: glareY, opacity: 0.35 });
  };

  const handleMouseLeave = () => {
    setRotate({ x: 0, y: 0 });
    setGlare({ x: 50, y: 50, opacity: 0 });
  };

  return (
    <div className="card-3d-wrapper">
      <div className="card-3d-header">
        <div className="card-3d-title">
          <ShieldCheck size={18} className="gold-text" />
          <span>Official Member Keycard</span>
        </div>
        <button
          type="button"
          className="btn-text-subtle"
          onClick={() => setIs3DActive(!is3DActive)}
          aria-label={is3DActive ? 'Disable 3D tilt interaction' : 'Enable 3D tilt interaction'}
        >
          {is3DActive ? '3D Active' : 'Static Mode'}
        </button>
      </div>

      <div
        className="card-3d-stage"
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
      >
        <div
          ref={cardRef}
          className={`membership-card-mesh ${!is3DActive ? 'static-card' : ''}`}
          style={{
            transform: is3DActive
              ? `perspective(1000px) rotateX(${rotate.x}deg) rotateY(${rotate.y}deg)`
              : 'none'
          }}
          aria-label={`Membership card for ${member?.name || 'Member'}, ID: ${member?.membershipId || 'RVF-2026-088'}`}
        >
          {/* Holographic Specular Glare Layer */}
          <div
            className="card-glare"
            style={{
              background: `radial-gradient(circle at ${glare.x}% ${glare.y}%, rgba(255, 230, 150, ${glare.opacity}) 0%, transparent 60%)`
            }}
          />

          {/* Top Bar */}
          <div className="card-top">
            <div className="card-brand-lockup">
              <span className="card-logo-badge">RV</span>
              <div>
                <strong className="card-brand-name">RVFITNESS</strong>
                <span className="card-brand-loc">NARSOBAWADI</span>
              </div>
            </div>
            <div className="card-rfid-chip" title="RFID Access Active">
              <Wifi size={18} className="gold-text" />
              <span className="chip-label">RFID ACCESS</span>
            </div>
          </div>

          {/* Mid Section: Chip and Tier */}
          <div className="card-mid">
            <div className="smart-chip" aria-hidden="true">
              <div className="chip-lines" />
            </div>
            <div className="membership-tier-tag">
              {member?.membershipPlan || 'VIP Plan'}
            </div>
          </div>

          {/* Bottom Section: Member Details & Barcode */}
          <div className="card-bottom">
            <div className="member-info">
              <span className="info-label">MEMBER NAME</span>
              <span className="info-value">{member?.name || 'Prathamesh Patil'}</span>
            </div>
            <div className="member-meta-grid">
              <div>
                <span className="info-label">MEMBERSHIP ID</span>
                <span className="info-code">{member?.membershipId || 'RVF-2026-088'}</span>
              </div>
              <div>
                <span className="info-label">VALID UNTIL</span>
                <span className="info-code">{member?.validUntil || 'Dec 31, 2026'}</span>
              </div>
            </div>
            <div className="card-barcode-row">
              <div className="digital-barcode" aria-hidden="true">
                {[4, 2, 6, 2, 4, 8, 3, 5, 2, 7, 3, 5, 4, 2, 6, 3, 7, 2, 4, 3, 5, 2, 6, 4].map((w, i) => (
                  <span key={i} style={{ width: `${w}px` }} />
                ))}
              </div>
              <div
                className={`qr-badge ${onOpenQR ? 'clickable' : ''}`}
                title={onOpenQR ? "Click to open Entry QR Pass" : "Scan at Front Gate"}
                onClick={onOpenQR}
                role={onOpenQR ? "button" : undefined}
                tabIndex={onOpenQR ? 0 : undefined}
                onKeyDown={(e) => {
                  if (onOpenQR && (e.key === 'Enter' || e.key === ' ')) {
                    e.preventDefault();
                    onOpenQR();
                  }
                }}
              >
                <QrCode size={24} />
              </div>
            </div>
          </div>
        </div>
      </div>
      <p className="card-3d-hint">Hover or drag to inspect 3D security seal and finish.</p>
    </div>
  );
}
