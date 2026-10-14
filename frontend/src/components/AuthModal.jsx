import { useState } from 'react';
import { X, Lock, Mail, User, Phone, AlertCircle } from 'lucide-react';
import { loginUser, registerUser } from '../api';

export default function AuthModal({
  onClose,
  onLoginSuccess,
  onOpenPrivacy,
  onOpenTerms
}) {
  const [tab, setTab] = useState('login'); // 'login' | 'register'
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');

  const [regName, setRegName] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regPhone, setRegPhone] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regAcceptedTerms, setRegAcceptedTerms] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError(null);
    if (!loginEmail || !loginPassword) {
      setError('Please provide both email and password.');
      return;
    }

    setSubmitting(true);
    try {
      const data = await loginUser(loginEmail, loginPassword);
      onLoginSuccess(data.token, data.user);
      onClose();
    } catch (err) {
      setError(err.message || 'Login failed. Please verify your credentials.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setError(null);

    if (!regAcceptedTerms) {
      setError('You must accept the Terms & Conditions and Privacy Policy to register.');
      return;
    }
    if (!regName.trim() || regName.trim().length < 2) {
      setError('Please enter your full name.');
      return;
    }
    if (!regEmail || !regEmail.includes('@')) {
      setError('Please enter a valid email address.');
      return;
    }
    if (!regPassword || regPassword.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }

    setSubmitting(true);
    try {
      const data = await registerUser({
        name: regName,
        email: regEmail,
        phone: regPhone,
        password: regPassword,
        acceptedTerms: regAcceptedTerms
      });
      onLoginSuccess(data.token, data.user);
      onClose();
    } catch (err) {
      setError(err.message || 'Registration failed. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const fillDemo = (role) => {
    setError(null);
    if (role === 'member') {
      setTab('login');
      setLoginEmail('member@rvfitness.in');
      setLoginPassword('password123');
    } else {
      setTab('login');
      setLoginEmail('admin@rvfitness.in');
      setLoginPassword('adminpassword123');
    }
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="auth-modal-title">
      <div className="modal-container auth-modal-container">
        <div className="modal-header">
          <div>
            <span className="modal-eyebrow">PORTAL AUTHENTICATION</span>
            <h3 id="auth-modal-title" className="modal-title">
              {tab === 'login' ? 'Sign In to RVFitness' : 'Create Member Account'}
            </h3>
          </div>
          <button
            type="button"
            className="btn-modal-close"
            onClick={onClose}
            aria-label="Close authentication dialog"
          >
            <X size={20} />
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="auth-tab-bar" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'login'}
            className={`auth-tab-btn ${tab === 'login' ? 'active' : ''}`}
            onClick={() => { setTab('login'); setError(null); }}
          >
            Sign In
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'register'}
            className={`auth-tab-btn ${tab === 'register' ? 'active' : ''}`}
            onClick={() => { setTab('register'); setError(null); }}
          >
            Register Account
          </button>
        </div>

        {/* Quick Test Credentials for Local Development Only */}
        {import.meta.env.DEV && (
          <div className="demo-credentials-banner">
            <span className="demo-label">Local Dev Testing:</span>
            <div className="demo-buttons-group">
              <button
                type="button"
                className="btn-demo-pill"
                onClick={() => fillDemo('member')}
              >
                Dev Member
              </button>
              <button
                type="button"
                className="btn-demo-pill"
                onClick={() => fillDemo('admin')}
              >
                Dev Staff
              </button>
            </div>
          </div>
        )}

        {error && (
          <div className="form-error-alert" role="alert">
            <AlertCircle size={18} />
            <span>{error}</span>
          </div>
        )}

        {tab === 'login' ? (
          <form onSubmit={handleLogin} className="modal-body auth-body" noValidate>
            <div className="form-group">
              <label htmlFor="login-email" className="form-label">
                Email Address
              </label>
              <div className="input-with-icon">
                <Mail size={16} className="input-icon" />
                <input
                  id="login-email"
                  type="email"
                  required
                  placeholder="member@rvfitness.in"
                  className="form-input has-icon"
                  value={loginEmail}
                  onChange={(e) => setLoginEmail(e.target.value)}
                />
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="login-password" className="form-label">
                Password
              </label>
              <div className="input-with-icon">
                <Lock size={16} className="input-icon" />
                <input
                  id="login-password"
                  type="password"
                  required
                  placeholder="••••••••"
                  className="form-input has-icon"
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="btn-gold-solid full-width mt-4"
            >
              {submitting ? 'Authenticating...' : 'Sign In to Account'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleRegister} className="modal-body auth-body" noValidate>
            <div className="form-group">
              <label htmlFor="reg-name" className="form-label">
                Full Legal Name <span className="required-star">*</span>
              </label>
              <div className="input-with-icon">
                <User size={16} className="input-icon" />
                <input
                  id="reg-name"
                  type="text"
                  required
                  placeholder="Enter full name"
                  className="form-input has-icon"
                  value={regName}
                  onChange={(e) => setRegName(e.target.value)}
                />
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="reg-email" className="form-label">
                Email Address <span className="required-star">*</span>
              </label>
              <div className="input-with-icon">
                <Mail size={16} className="input-icon" />
                <input
                  id="reg-email"
                  type="email"
                  required
                  placeholder="yourname@domain.com"
                  className="form-input has-icon"
                  value={regEmail}
                  onChange={(e) => setRegEmail(e.target.value)}
                />
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="reg-phone" className="form-label">
                Phone Number
              </label>
              <div className="input-with-icon">
                <Phone size={16} className="input-icon" />
                <input
                  id="reg-phone"
                  type="tel"
                  placeholder="+91 98000 00000"
                  className="form-input has-icon"
                  value={regPhone}
                  onChange={(e) => setRegPhone(e.target.value)}
                />
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="reg-pass" className="form-label">
                Create Password (Min 6 chars) <span className="required-star">*</span>
              </label>
              <div className="input-with-icon">
                <Lock size={16} className="input-icon" />
                <input
                  id="reg-pass"
                  type="password"
                  required
                  placeholder="••••••••"
                  className="form-input has-icon"
                  value={regPassword}
                  onChange={(e) => setRegPassword(e.target.value)}
                />
              </div>
            </div>

            <div className="terms-checkbox-wrap">
              <label className="checkbox-container">
                <input
                  type="checkbox"
                  checked={regAcceptedTerms}
                  onChange={(e) => setRegAcceptedTerms(e.target.checked)}
                />
                <span className="checkbox-label-text">
                  I accept the{' '}
                  <button
                    type="button"
                    className="inline-link"
                    onClick={(e) => {
                      e.preventDefault();
                      onOpenTerms();
                    }}
                  >
                    Terms & Conditions
                  </button>{' '}
                  and{' '}
                  <button
                    type="button"
                    className="inline-link"
                    onClick={(e) => {
                      e.preventDefault();
                      onOpenPrivacy();
                    }}
                  >
                    Privacy Policy
                  </button>.
                </span>
              </label>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="btn-gold-solid full-width mt-4"
            >
              {submitting ? 'Creating Account...' : 'Complete Registration'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
