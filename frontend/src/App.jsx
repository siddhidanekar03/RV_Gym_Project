import { useState, useEffect } from 'react';
import Header from './components/Header';
import Hero from './components/Hero';
import Features from './components/Features';
import Memberships from './components/Memberships';
import Equipment from './components/Equipment';
import Philosophy from './components/Philosophy';
import Trainers from './components/Trainers';
import Events from './components/Events';
import Leaderboard from './components/Leaderboard';
import Gallery from './components/Gallery';
import Contact from './components/Contact';
import Footer from './components/Footer';
import EnrollModal from './components/EnrollModal';
import AuthModal from './components/AuthModal';
import MemberDashboard from './components/MemberDashboard';
import AdminDashboard from './components/AdminDashboard';
import LegalModal from './components/LegalModal';
import { fetchCurrentUser, logoutUser } from './api';
import './App.css';

export default function App() {
  const [activeSection, setActiveSection] = useState('home');
  const [currentUser, setCurrentUser] = useState(() => {
    try {
      const saved = localStorage.getItem('rvf_user');
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });

  const [authResolved, setAuthResolved] = useState(false);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [legalModalType, setLegalModalType] = useState(null); // 'privacy' | 'terms' | null
  const [showPortal, setShowPortal] = useState(false);
  const [consultationCoach, setConsultationCoach] = useState(null);

  const handleLogout = async () => {
    try {
      await logoutUser();
    } catch {
      // Best effort cleanup
    }
    setCurrentUser(null);
    localStorage.removeItem('rvf_user');
    localStorage.removeItem('rvf_token');
    setShowPortal(false);
  };

  // Verify stored session on mount via secure HttpOnly cookie
  useEffect(() => {
    fetchCurrentUser()
      .then((data) => {
        if (data && data.user) {
          setCurrentUser(data.user);
          localStorage.setItem('rvf_user', JSON.stringify(data.user));
        } else {
          setCurrentUser(null);
          localStorage.removeItem('rvf_user');
        }
      })
      .catch(() => {
        setCurrentUser(null);
        localStorage.removeItem('rvf_user');
      })
      .finally(() => {
        setAuthResolved(true);
      });
  }, []);

  // Handle session expiration cleanly across entire application
  useEffect(() => {
    const handleExpired = () => {
      setCurrentUser(null);
      localStorage.removeItem('rvf_user');
      setShowPortal(false);
      setShowAuthModal(true);
    };
    window.addEventListener('rvf:auth_expired', handleExpired);
    return () => window.removeEventListener('rvf:auth_expired', handleExpired);
  }, []);

  // Handle URL hash changes
  useEffect(() => {
    const handleHash = () => {
      const hash = window.location.hash.replace('#', '');
      if (hash) {
        if (hash === 'privacy') {
          setLegalModalType('privacy');
        } else if (hash === 'terms') {
          setLegalModalType('terms');
        } else if (hash === 'portal' && currentUser) {
          setShowPortal(true);
        } else {
          setActiveSection(hash);
          const el = document.getElementById(hash);
          if (el) el.scrollIntoView({ behavior: 'smooth' });
        }
      }
    };

    handleHash();
    window.addEventListener('hashchange', handleHash);
    return () => window.removeEventListener('hashchange', handleHash);
  }, [currentUser]);

  const handleNavigate = (sectionId) => {
    setActiveSection(sectionId);
    setShowPortal(false);
    window.history.pushState(null, '', `#${sectionId}`);
    const el = document.getElementById(sectionId);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' });
    }
  };

  const handleLoginSuccess = (_token, user) => {
    setCurrentUser(user);
    localStorage.setItem('rvf_user', JSON.stringify(user));
    setShowPortal(true);
  };


  const handleBookConsultation = (coach) => {
    setConsultationCoach(coach);
    handleNavigate('contact');
  };

  const handleRegisterEvent = (evt) => {
    setConsultationCoach({ name: evt.title, role: 'Event Registration' });
    handleNavigate('contact');
  };

  return (
    <div className="rvfitness-app">
      {/* Site Header */}
      <Header
        activeSection={activeSection}
        onNavigate={handleNavigate}
        currentUser={currentUser}
        onOpenAuth={() => setShowAuthModal(true)}
        onOpenPortal={() => setShowPortal(true)}
        onLogout={handleLogout}
      />

      {/* Authenticated Dashboard / Management Portal View */}
      {showPortal ? (
        !authResolved ? (
          <div className="status-container" style={{ minHeight: '60vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
            <div className="spinner-icon gold-text" style={{ width: 40, height: 40, border: '3px solid #d4af37', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
            <p style={{ marginTop: 16, color: '#e0e0e0' }}>Verifying authenticated session...</p>
          </div>
        ) : currentUser ? (
          ['admin', 'org_admin', 'branch_manager', 'front_desk', 'staff'].includes(currentUser.role) ? (
            <AdminDashboard
              user={currentUser}
              onClose={() => setShowPortal(false)}
            />
          ) : (
            <MemberDashboard
              user={currentUser}
              onUserUpdate={(updatedUser) => {
                setCurrentUser(updatedUser);
                localStorage.setItem('rvf_user', JSON.stringify(updatedUser));
              }}
              onClose={() => setShowPortal(false)}
            />
          )
        ) : (
          <div className="status-container" style={{ minHeight: '60vh', textAlign: 'center', padding: '60px 20px' }}>
            <h3 style={{ color: '#d4af37', marginBottom: 12 }}>Authentication Required</h3>
            <p style={{ color: '#aaa', marginBottom: 20 }}>Please sign in to access your portal desk.</p>
            <button
              type="button"
              className="btn-gold-large"
              onClick={() => setShowAuthModal(true)}
            >
              Sign In to RVFitness
            </button>
          </div>
        )
      ) : (
        <>
          {/* Main Public Content */}
          <main id="main-content">
            <Hero
              onEnrollClick={() => handleNavigate('memberships')}
              onExploreClick={() => handleNavigate('about')}
            />

            <Features />

            <Memberships
              onSelectPlan={(plan) => setSelectedPlan(plan)}
            />

            <Equipment />

            <Philosophy />

            <Trainers
              onBookConsultation={handleBookConsultation}
            />

            <Events
              onRegisterEvent={handleRegisterEvent}
            />

            <Leaderboard />

            <Gallery />

            <Contact
              consultationCoach={consultationCoach}
              onClearConsultation={() => setConsultationCoach(null)}
            />
          </main>

          {/* Footer */}
          <Footer
            onNavigate={handleNavigate}
            onOpenPrivacy={() => setLegalModalType('privacy')}
            onOpenTerms={() => setLegalModalType('terms')}
          />
        </>
      )}
      {/* Enrollment Modal */}
      {selectedPlan && (
        <EnrollModal
          plan={selectedPlan}
          currentUser={currentUser}
          onSuccess={async () => {
            try {
              const data = await fetchCurrentUser();
              if (data && data.user) {
                setCurrentUser(data.user);
                localStorage.setItem('rvf_user', JSON.stringify(data.user));
              }
            } catch {
              // Ignore failure to refresh session
            }
          }}
          onClose={() => setSelectedPlan(null)}
          onOpenPrivacy={() => setLegalModalType('privacy')}
          onOpenTerms={() => setLegalModalType('terms')}
        />
      )}

      {/* Authentication Modal */}
      {showAuthModal && (
        <AuthModal
          onClose={() => setShowAuthModal(false)}
          onLoginSuccess={handleLoginSuccess}
          onOpenPrivacy={() => setLegalModalType('privacy')}
          onOpenTerms={() => setLegalModalType('terms')}
        />
      )}

      {/* Legal Modals (Privacy & Terms) */}
      {legalModalType && (
        <LegalModal
          type={legalModalType}
          onClose={() => setLegalModalType(null)}
        />
      )}
    </div>
  );
}