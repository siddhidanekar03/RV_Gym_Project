import { useState } from 'react';
import { X, Lock, Mail, User, Phone, AlertCircle } from 'lucide-react';
import { loginUser, registerUser } from '../api';
import { validatePhoneNumber } from '../utils/phoneValidation';

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
  const [fieldErrors, setFieldErrors] = useState({});

  const handleLogin = async (e) => {
    e.preventDefault();
    setError(null);
    setFieldErrors({});
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
    setFieldErrors({});

    const clientErrors = {};
    if (!regName.trim() || regName.trim().length < 2) {
      clientErrors.name = 'Full name must be at least 2 characters.';
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!regEmail || !emailRegex.test(regEmail.trim())) {
      clientErrors.email = 'Please enter a valid email address (e.g., name@domain.com).';
    }
    if (!regPassword || regPassword.length < 8) {
      clientErrors.password = 'Password must be at least 8 characters long.';
    }
    if (regPhone && regPhone.trim().length > 0) {
      const phoneErr = validatePhoneNumber(regPhone, false);
      if (phoneErr) {
        clientErrors.phone = phoneErr;
      }
    }
    if (!regAcceptedTerms) {
      clientErrors.acceptedTerms = 'You must accept the Terms & Conditions and Privacy Policy.';
    }

    if (Object.keys(clientErrors).length > 0) {
      setFieldErrors(clientErrors);
      setError(Object.values(clientErrors)[0]);
      return;
    }

    setSubmitting(true);
    try {
      const data = await registerUser({
        name: regName.trim(),
        email: regEmail.trim().toLowerCase(),
        phone: regPhone.trim() || null,
        password: regPassword,
        acceptedTerms: regAcceptedTerms
      });
      onLoginSuccess(data.token, data.user);
      onClose();
    } catch (err) {
      if (err.fieldErrors && Object.keys(err.fieldErrors).length > 0) {
        setFieldErrors(err.fieldErrors);
      }
      setError(err.message || 'Registration failed. Please check the entered fields.');
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
                  className={`form-input has-icon ${fieldErrors.name ? 'input-error' : ''}`}
                  value={regName}
                  onChange={(e) => {
                    setRegName(e.target.value);
                    if (fieldErrors.name) setFieldErrors({ ...fieldErrors, name: null });
                  }}
                />
              </div>
              {fieldErrors.name && <span className="field-error-text">{fieldErrors.name}</span>}
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
                  className={`form-input has-icon ${fieldErrors.email ? 'input-error' : ''}`}
                  value={regEmail}
                  onChange={(e) => {
                    setRegEmail(e.target.value);
                    if (fieldErrors.email) setFieldErrors({ ...fieldErrors, email: null });
                  }}
                />
              </div>
              {fieldErrors.email && <span className="field-error-text">{fieldErrors.email}</span>}
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
                  className={`form-input has-icon ${fieldErrors.phone ? 'input-error' : ''}`}
                  value={regPhone}
                  onChange={(e) => {
                    setRegPhone(e.target.value);
                    if (fieldErrors.phone) setFieldErrors({ ...fieldErrors, phone: null });
                  }}
                />
              </div>
              {fieldErrors.phone && <span className="field-error-text">{fieldErrors.phone}</span>}
            </div>

            <div className="form-group">
              <label htmlFor="reg-pass" className="form-label">
                Create Secure Password (Min 8 chars) <span className="required-star">*</span>
              </label>
              <div className="input-with-icon">
                <Lock size={16} className="input-icon" />
                <input
                  id="reg-pass"
                  type="password"
                  required
                  placeholder="••••••••"
                  className={`form-input has-icon ${fieldErrors.password ? 'input-error' : ''}`}
                  value={regPassword}
                  onChange={(e) => {
                    setRegPassword(e.target.value);
                    if (fieldErrors.password) setFieldErrors({ ...fieldErrors, password: null });
                  }}
                />
              </div>
              {fieldErrors.password && <span className="field-error-text">{fieldErrors.password}</span>}
            </div>

            <div className="terms-checkbox-wrap">
              <label className="checkbox-container">
                <input
                  type="checkbox"
                  checked={regAcceptedTerms}
                  onChange={(e) => {
                    setRegAcceptedTerms(e.target.checked);
                    if (fieldErrors.acceptedTerms) setFieldErrors({ ...fieldErrors, acceptedTerms: null });
                  }}
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
              {fieldErrors.acceptedTerms && (
                <div className="field-error-text mt-1">{fieldErrors.acceptedTerms}</div>
              )}
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
