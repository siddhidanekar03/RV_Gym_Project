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
      });
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
      {showPortal && currentUser ? (
        ['admin', 'org_admin', 'branch_manager', 'front_desk', 'staff'].includes(currentUser.role) ? (
          <AdminDashboard
            user={currentUser}
            onClose={() => setShowPortal(false)}
          />
        ) : (
          <MemberDashboard
            user={currentUser}
            token={token}
            onUserUpdate={(updatedUser) => {
              setCurrentUser(updatedUser);
              localStorage.setItem('rvf_user', JSON.stringify(updatedUser));
            }}
            onClose={() => setShowPortal(false)}
          />
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