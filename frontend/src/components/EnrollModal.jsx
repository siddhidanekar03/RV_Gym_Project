import { useState } from 'react';
import { X, AlertCircle, CheckCircle2 } from 'lucide-react';
import { submitEnrollment } from '../api';

export default function EnrollModal({
  plan,
  onClose,
  onOpenPrivacy,
  onOpenTerms
}) {
  const [formData, setFormData] = useState({
    name: '',
    phone: '',
    email: '',
    acceptedTerms: false
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [successResult, setSuccessResult] = useState(null);

  if (!plan) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (!formData.name.trim() || formData.name.trim().length < 2) {
      setError('Please provide your full legal name.');
      return;
    }
    if (!formData.phone.trim() || formData.phone.trim().length < 8) {
      setError('Please provide a valid contact phone number.');
      return;
    }
    if (!formData.acceptedTerms) {
      setError('You must accept the Terms & Conditions and Privacy Policy to enroll.');
      return;
    }

    setSubmitting(true);
    try {
      const res = await submitEnrollment({
        planId: plan.id,
        name: formData.name,
        phone: formData.phone,
        email: formData.email,
        acceptedTerms: formData.acceptedTerms
      });
      setSuccessResult(res);
    } catch (err) {
      setError(err.message || 'Enrollment submission failed. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="enroll-modal-title">
      <div className="modal-container">
        <div className="modal-header">
          <div>
            <span className="modal-eyebrow">MEMBERSHIP APPLICATION</span>
            <h3 id="enroll-modal-title" className="modal-title">
              Enroll in {plan.name} Plan
            </h3>
          </div>
          <button
            type="button"
            className="btn-modal-close"
            onClick={onClose}
            aria-label="Close enrollment dialog"
          >
            <X size={20} />
          </button>
        </div>

        {successResult ? (
          <div className="modal-body success-state-body">
            <CheckCircle2 size={48} className="gold-text mb-4" />
            <h4 className="success-heading">Enrollment Request Registered</h4>
            <p className="success-copy">
              {successResult.message}
            </p>
            <div className="receipt-box">
              <div className="receipt-row">
                <span>Selected Plan:</span>
                <strong>{plan.name} ({plan.durationDays} Days)</strong>
              </div>
              <div className="receipt-row">
                <span>Total Due at Desk:</span>
                <strong className="gold-text">{plan.currency}{plan.price.toLocaleString('en-IN')}</strong>
              </div>
              <div className="receipt-row">
                <span>Member Name:</span>
                <span>{formData.name}</span>
              </div>
              <div className="receipt-row">
                <span>Reference ID:</span>
                <span className="font-mono">{successResult.enrollment.id}</span>
              </div>
            </div>
            <p className="activation-note">
              Please present this confirmation at the RVFitness reception counter to finalize payment and receive your personalized RFID keycard.
            </p>
            <button
              type="button"
              className="btn-gold-solid full-width mt-4"
              onClick={onClose}
            >
              Done & Return to Homepage
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="modal-body" noValidate>
            {error && (
              <div className="form-error-alert" role="alert">
                <AlertCircle size={18} />
                <span>{error}</span>
              </div>
            )}

            {/* Plan Summary Strip */}
            <div className="plan-summary-banner">
              <div>
                <span className="summary-label">Selected Tier</span>
                <strong className="summary-name">{plan.name} Membership</strong>
              </div>
              <div className="summary-price-col">
                <span className="summary-label">Verified Rate</span>
                <strong className="summary-price">{plan.currency}{plan.price.toLocaleString('en-IN')}</strong>
                <small className="summary-cycle">/{plan.billingCycle.replace('per ', '')}</small>
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="enroll-name" className="form-label">
                Full Name <span className="required-star">*</span>
              </label>
              <input
                id="enroll-name"
                type="text"
                required
                placeholder="Enter full legal name"
                className="form-input"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label htmlFor="enroll-phone" className="form-label">
                Contact Phone <span className="required-star">*</span>
              </label>
              <input
                id="enroll-phone"
                type="tel"
                required
                placeholder="+91 98000 00000"
                className="form-input"
                value={formData.phone}
                onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label htmlFor="enroll-email" className="form-label">
                Email Address (Optional)
              </label>
              <input
                id="enroll-email"
                type="email"
                placeholder="member@example.com"
                className="form-input"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              />
            </div>

            {/* Terms and Privacy Checkbox */}
            <div className="terms-checkbox-wrap">
              <label className="checkbox-container">
                <input
                  type="checkbox"
                  checked={formData.acceptedTerms}
                  onChange={(e) => setFormData({ ...formData, acceptedTerms: e.target.checked })}
                />
                <span className="checkbox-label-text">
                  I have read and agree to the{' '}
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

            <div className="modal-actions-footer">
              <button
                type="button"
                className="btn-outline"
                onClick={onClose}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="btn-gold-solid"
              >
                {submitting ? 'Registering Application...' : 'Confirm Enrollment'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
