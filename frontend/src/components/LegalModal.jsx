import { X, ShieldCheck, FileText } from 'lucide-react';

export default function LegalModal({ type, onClose }) {
  if (!type) return null;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="legal-modal-title">
      <div className="modal-container legal-modal-container">
        <div className="modal-header">
          <div className="modal-title-lockup">
            {type === 'privacy' ? (
              <ShieldCheck size={24} className="gold-text" />
            ) : (
              <FileText size={24} className="gold-text" />
            )}
            <div>
              <span className="modal-eyebrow">LEGAL DOCUMENTATION</span>
              <h3 id="legal-modal-title" className="modal-title">
                {type === 'privacy' ? 'RVFitness Privacy Policy' : 'RVFitness Terms & Conditions'}
              </h3>
            </div>
          </div>
          <button
            type="button"
            className="btn-modal-close"
            onClick={onClose}
            aria-label="Close legal policy dialog"
          >
            <X size={20} />
          </button>
        </div>

        <div className="modal-body legal-modal-body">
          {type === 'privacy' ? (
            <div className="legal-text-flow">
              <p className="effective-date">Last Updated: October 2026 · RVFitness Narsobawadi</p>

              <h4>1. Commitment to Member Privacy</h4>
              <p>
                RVFitness (located in Narsobawadi, Maharashtra) respects your personal privacy. This Privacy Policy details how we collect, store, and safeguard your personal details, attendance records, and emergency contact information.
              </p>

              <h4>2. Information We Collect</h4>
              <p>
                When registering as an RVFitness member or submitting inquiries, we collect:
              </p>
              <ul>
                <li>Identity Details: Full legal name, date of birth, and identity proof for facility security.</li>
                <li>Contact Data: Phone number and email address for membership renewal and emergency notices.</li>
                <li>Operational Data: RFID check-in timestamps, attendance streaks, and verified personal record milestones.</li>
              </ul>

              <h4>3. Use of Information</h4>
              <p>
                Collected data is used strictly for:
              </p>
              <ul>
                <li>Facility access verification and locker assignments.</li>
                <li>Accredited coaching guidance and personal progress tracking.</li>
                <li>Facility security and emergency response on the gym floor.</li>
              </ul>

              <h4>4. Data Protection & Non-Disclosure</h4>
              <p>
                We do not sell, rent, or trade your personal information to third-party advertisers. All member information is held on secured management servers with role-restricted access.
              </p>

              <h4>5. Contact Our Privacy Administrator</h4>
              <p>
                For data review or deletion requests, contact our facility desk at Datta Mandir Road, Narsobawadi or email <strong>contact@rvfitness.in</strong>.
              </p>
            </div>
          ) : (
            <div className="legal-text-flow">
              <p className="effective-date">Last Updated: October 2026 · RVFitness Narsobawadi</p>

              <h4>1. Acceptance of Terms</h4>
              <p>
                By enrolling in an RVFitness membership or entering the gym premises, you agree to comply with the rules, safety standards, and code of conduct outlined herein.
              </p>

              <h4>2. Health and Physical Readiness</h4>
              <p>
                Members affirm that they are in suitable physical health to engage in vigorous resistance training, weightlifting, and cardiovascular exercise. Members are advised to consult a qualified physician prior to starting heavy lifting programs.
              </p>

              <h4>3. Facility Etiquette and Safety</h4>
              <ul>
                <li>Re-racking: All dumbbells, weight plates, and barbells must be returned to their designated storage trees immediately after use.</li>
                <li>Footwear: Clean, closed-toe athletic training shoes are mandatory on the gym floor at all times.</li>
                <li>Collars & Clips: Weight collars must be secured on all barbell lifts.</li>
                <li>Hygiene: Members must utilize personal sweat towels and wipe equipment pads after use.</li>
              </ul>

              <h4>4. Membership Dues and Validity</h4>
              <p>
                Membership plans (Monthly, Quarterly, Yearly) are non-transferable and non-refundable once activated. Access privileges expire promptly at the conclusion of the paid term unless renewed prior to the expiration date.
              </p>

              <h4>5. Code of Conduct</h4>
              <p>
                RVFitness maintains a zero-tolerance policy for harassment, unsafe lifting behavior, or property damage. Management reserves the right to suspend or terminate membership access for violations of gym policy.
              </p>
            </div>
          )}
        </div>

        <div className="modal-actions-footer">
          <button
            type="button"
            className="btn-gold-solid full-width"
            onClick={onClose}
          >
            I Understand & Acknowledge
          </button>
        </div>
      </div>
    </div>
  );
}
