import { useState } from 'react';
import { MapPin, Phone, Mail, Clock, Send, CheckCircle2, AlertCircle, X } from 'lucide-react';
import { submitContact } from '../api';

export default function Contact({ consultationCoach = null, onClearConsultation = () => {} }) {
  const [formData, setFormData] = useState({
    name: '',
    phone: '',
    email: '',
    message: consultationCoach ? `Requesting consultation with ${consultationCoach.name} (${consultationCoach.role})` : ''
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    // Client-side validation
    if (!formData.name.trim() || formData.name.trim().length < 2) {
      setError('Please provide your full name (at least 2 characters).');
      return;
    }
    if (!formData.phone.trim() || formData.phone.trim().length < 8) {
      setError('Please provide a valid contact phone number.');
      return;
    }

    setSubmitting(true);
    try {
      await submitContact(formData);
      setSubmitted(true);
      setFormData({ name: '', phone: '', email: '', message: '' });
      onClearConsultation();
    } catch (err) {
      setError(err.message || 'Unable to submit enquiry. Please check your connection and try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section id="contact" className="section-container" aria-label="Contact and Facility Location">
      <div className="section-header">
        <span className="section-eyebrow">FACILITY INQUIRIES</span>
        <h2 className="section-title">Visit or Contact RVFitness</h2>
        <p className="section-lead">
          Reach out for membership queries, coaching consultations, or visit the facility during floor hours.
        </p>
      </div>

      <div className="contact-layout-grid">
        {/* Verified Facility Details */}
        <div className="contact-details-card">
          <h3 className="details-title">Gym Information</h3>
          <p className="details-intro">
            Official operational address and verified communication channels for RVFitness.
          </p>

          <div className="details-list">
            <div className="detail-item">
              <div className="detail-icon-wrap" aria-hidden="true">
                <MapPin size={20} className="gold-text" />
              </div>
              <div>
                <strong>Facility Address</strong>
                <address className="detail-address">
                  RVFitness Center<br />
                  Near Datta Mandir Road, Narsobawadi<br />
                  Kolhapur District, Maharashtra 416104
                </address>
              </div>
            </div>

            <div className="detail-item">
              <div className="detail-icon-wrap" aria-hidden="true">
                <Phone size={20} className="gold-text" />
              </div>
              <div>
                <strong>Phone & WhatsApp</strong>
                <p>+91 98220 12345</p>
                <small className="detail-hint">Desk hours: 6:00 AM - 10:00 PM</small>
              </div>
            </div>

            <div className="detail-item">
              <div className="detail-icon-wrap" aria-hidden="true">
                <Mail size={20} className="gold-text" />
              </div>
              <div>
                <strong>Email Inquiries</strong>
                <p>contact@rvfitness.in</p>
              </div>
            </div>

            <div className="detail-item">
              <div className="detail-icon-wrap" aria-hidden="true">
                <Clock size={20} className="gold-text" />
              </div>
              <div>
                <strong>Operating Schedule</strong>
                <p>Mon - Sat: 6:00 AM – 10:00 PM</p>
                <p>Sun: 7:00 AM – 12:00 PM</p>
              </div>
            </div>
          </div>
        </div>

        {/* Validated Contact Form */}
        <div className="contact-form-card">
          <h3 className="form-title">Send a Direct Enquiry</h3>
          <p className="form-subtext">
            Submit your contact details and our front desk will follow up promptly.
          </p>

          {submitted ? (
            <div className="success-banner" role="status">
              <CheckCircle2 size={32} className="gold-text" />
              <div>
                <h4>Enquiry Recorded Successfully</h4>
                <p>
                  Thank you! Your information has been logged in the RVFitness database. Our staff will contact you shortly.
                </p>
                <button
                  type="button"
                  className="btn-outline small mt-3"
                  onClick={() => setSubmitted(false)}
                >
                  Send Another Message
                </button>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="contact-form" noValidate>
              {error && (
                <div className="form-error-alert" role="alert">
                  <AlertCircle size={18} />
                  <span>{error}</span>
                </div>
              )}

              {consultationCoach && (
                <div className="coach-tag-notice">
                  <span>Booking inquiry for Coach: <strong>{consultationCoach.name}</strong></span>
                  <button type="button" onClick={onClearConsultation} className="close-coach-tag" aria-label="Clear coach selection">
                    <X size={12} aria-hidden="true" />
                  </button>
                </div>
              )}

              <div className="form-group">
                <label htmlFor="contact-name" className="form-label">
                  Full Name <span className="required-star">*</span>
                </label>
                <input
                  id="contact-name"
                  type="text"
                  required
                  placeholder="e.g. Ramesh Patil"
                  className="form-input"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label htmlFor="contact-phone" className="form-label">
                  Phone Number <span className="required-star">*</span>
                </label>
                <input
                  id="contact-phone"
                  type="tel"
                  required
                  placeholder="+91 98000 00000"
                  className="form-input"
                  value={formData.phone}
                  onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label htmlFor="contact-email" className="form-label">
                  Email Address (Optional)
                </label>
                <input
                  id="contact-email"
                  type="email"
                  placeholder="name@example.com"
                  className="form-input"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label htmlFor="contact-message" className="form-label">
                  Message or Fitness Goal
                </label>
                <textarea
                  id="contact-message"
                  rows={4}
                  placeholder="Describe your current fitness level, target goals, or preferred training time..."
                  className="form-textarea"
                  value={formData.message}
                  onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                />
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="btn-gold-solid full-width"
              >
                {submitting ? (
                  <span>Recording Enquiry...</span>
                ) : (
                  <>
                    <Send size={16} />
                    <span>Send Inquiries to Front Desk</span>
                  </>
                )}
              </button>
            </form>
          )}
        </div>
      </div>
    </section>
  );
}
