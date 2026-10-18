import { useState, useEffect } from 'react';
import { Menu, X, User, LogOut, LayoutDashboard } from 'lucide-react';

export default function Header({
  activeSection,
  onNavigate,
  currentUser,
  onOpenAuth,
  onOpenPortal,
  onLogout
}) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [isScrolled, setIsScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 20);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const navItems = [
    { id: 'home', label: 'Home' },
    { id: 'about', label: 'About' },
    { id: 'memberships', label: 'Memberships' },
    { id: 'equipment', label: 'Equipment' },
    { id: 'trainers', label: 'Trainers' },
    { id: 'events', label: 'Events' },
    { id: 'leaderboard', label: 'Leaderboard' },
    { id: 'gallery', label: 'Gallery' },
    { id: 'contact', label: 'Contact' },
  ];

  const handleLinkClick = (id) => {
    setMobileOpen(false);
    onNavigate(id);
  };

  return (
    <header className={`site-header ${isScrolled ? 'scrolled' : ''}`}>
      <div className="header-container">
        {/* Brand */}
        <a
          href="#home"
          className="header-brand"
          onClick={(e) => {
            e.preventDefault();
            handleLinkClick('home');
          }}
          aria-label="RVFitness Home"
        >
          <span className="brand-badge" aria-hidden="true">RV</span>
          <div className="brand-text">
            <span className="brand-title">RVFITNESS</span>
            <span className="brand-sub">NARSOBAWADI</span>
          </div>
        </a>

        {/* Desktop Navigation */}
        <nav className="desktop-nav" aria-label="Main Navigation">
          <ul className="nav-list">
            {navItems.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={`nav-link ${activeSection === item.id ? 'active' : ''}`}
                  onClick={() => handleLinkClick(item.id)}
                >
                  {item.label}
                </button>
              </li>
            ))}
          </ul>
        </nav>

        {/* Action Controls */}
        <div className="header-actions">
          {currentUser ? (
            <div className="user-nav-group">
              <button
                type="button"
                className="btn-portal"
                onClick={onOpenPortal}
                title="Open Management Portal"
              >
                <LayoutDashboard size={16} />
                <span>{['admin', 'org_admin', 'branch_manager', 'front_desk', 'staff'].includes(currentUser.role) ? 'Staff Desk' : 'Member Portal'}</span>
              </button>
              <button
                type="button"
                className="btn-icon"
                onClick={onLogout}
                title="Log out of account"
                aria-label="Log out"
              >
                <LogOut size={16} />
              </button>
            </div>
          ) : (
            <button
              type="button"
              className="btn-login"
              onClick={onOpenAuth}
            >
              <User size={16} />
              <span>Login</span>
            </button>
          )}

          <button
            type="button"
            className="btn-gold-solid"
            onClick={() => handleLinkClick('memberships')}
          >
            Join Now
          </button>

          {/* Mobile Menu Trigger */}
          <button
            type="button"
            className="mobile-menu-trigger"
            aria-expanded={mobileOpen}
            aria-label="Toggle navigation menu"
            onClick={() => setMobileOpen(!mobileOpen)}
          >
            {mobileOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>
      </div>

      {/* Mobile Navigation Drawer */}
      {mobileOpen && (
        <div className="mobile-drawer" role="dialog" aria-modal="true">
          <nav className="mobile-nav-list" aria-label="Mobile Navigation">
            {navItems.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`mobile-nav-link ${activeSection === item.id ? 'active' : ''}`}
                onClick={() => handleLinkClick(item.id)}
              >
                {item.label}
              </button>
            ))}
            <div className="mobile-drawer-footer">
              {currentUser ? (
                <button
                  type="button"
                  className="mobile-portal-btn"
                  onClick={() => {
                    setMobileOpen(false);
                    onOpenPortal();
                  }}
                >
                  <LayoutDashboard size={18} />
                  <span>{['admin', 'org_admin', 'branch_manager', 'front_desk', 'staff'].includes(currentUser.role) ? 'Staff Desk' : 'Member Portal'}</span>
                </button>
              ) : (
                <button
                  type="button"
                  className="mobile-login-btn"
                  onClick={() => {
                    setMobileOpen(false);
                    onOpenAuth();
                  }}
                >
                  <User size={18} />
                  <span>Member Login</span>
                </button>
              )}
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}
