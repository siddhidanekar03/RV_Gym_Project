import { useState, useEffect } from 'react';
import {
  X,
  Search,
  UserCheck,
  CreditCard,
  Shield,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  Building2,
  DollarSign,
  Calendar,
  AlertTriangle,
  UserPlus
} from 'lucide-react';
import {
  searchOwnerMembers,
  assignMembershipToMember,
  fetchOwnerPlans,
  fetchBranches
} from '../api';

export default function AssignMembershipModal({
  isOpen,
  onClose,
  preselectedMember = null,
  initialBranchId = 'narsobawadi',
  onSuccess = null
}) {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [selectedMember, setSelectedMember] = useState(preselectedMember);

  const [plans, setPlans] = useState([]);
  const [loadingPlans, setLoadingPlans] = useState(false);
  const [selectedPlanId, setSelectedPlanId] = useState('');

  const [branches, setBranches] = useState([]);
  const [selectedBranchId, setSelectedBranchId] = useState(initialBranchId);

  const [recordPayment, setRecordPayment] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState('cash');
  const [paymentReference, setPaymentReference] = useState('');
  const [notes, setNotes] = useState('');

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);
  const [successFeedback, setSuccessFeedback] = useState(null);

  // Sync preselected member when modal opens
  useEffect(() => {
    if (preselectedMember) {
      setSelectedMember(preselectedMember);
      if (preselectedMember.branch_id) {
        setSelectedBranchId(preselectedMember.branch_id);
      }
    } else {
      setSelectedMember(null);
      setSearchQuery('');
      setSearchResults([]);
    }
  }, [preselectedMember, isOpen]);

  // Load plans and branches
  useEffect(() => {
    if (!isOpen) return;

    let isMounted = true;
    async function loadMetadata() {
      setLoadingPlans(true);
      try {
        const [planRes, branchRes] = await Promise.all([
          fetchOwnerPlans().catch(() => ({ plans: [] })),
          fetchBranches().catch(() => ({ branches: [] }))
        ]);

        if (isMounted) {
          const activePlans = (planRes.plans || []).filter((p) => p.isActive !== false);
          setPlans(activePlans);
          if (activePlans.length > 0 && !selectedPlanId) {
            setSelectedPlanId(activePlans[0].id);
          }

          const branchList = branchRes.branches || [];
          setBranches(branchList);
          if (branchList.length > 0 && !selectedBranchId) {
            setSelectedBranchId(branchList[0].id);
          }
        }
      } catch (err) {
        if (isMounted) {
          setErrorMessage(err.message || 'Failed to load membership plans.');
        }
      } finally {
        if (isMounted) setLoadingPlans(false);
      }
    }

    loadMetadata();

    return () => {
      isMounted = false;
    };
  }, [isOpen]);

  // Search members debounced
  useEffect(() => {
    if (!isOpen || selectedMember) return;
    if (!searchQuery.trim() || searchQuery.trim().length < 2) {
      setSearchResults([]);
      return;
    }

    const timer = setTimeout(async () => {
      setSearching(true);
      setErrorMessage(null);
      try {
        const res = await searchOwnerMembers(searchQuery.trim(), selectedBranchId);
        setSearchResults(res.members || []);
      } catch (err) {
        setErrorMessage(err.message || 'Error searching members.');
      } finally {
        setSearching(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [searchQuery, selectedBranchId, selectedMember, isOpen]);

  if (!isOpen) return null;

  const currentPlan = plans.find((p) => p.id === selectedPlanId);

  // Check if member already has active membership or pending enrollment
  const hasActivePlan = Boolean(selectedMember?.active_membership);
  const hasPendingEnrollment = Boolean(selectedMember?.pending_enrollment);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selectedMember) {
      setErrorMessage('Please select a member first.');
      return;
    }
    if (!selectedPlanId) {
      setErrorMessage('Please select a membership plan.');
      return;
    }

    if (hasActivePlan) {
      setErrorMessage('This member already has an active membership. Direct assignment is blocked to prevent conflict.');
      return;
    }

    if (hasPendingEnrollment) {
      setErrorMessage('This member already has a pending enrollment request in review.');
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setSuccessFeedback(null);

    try {
      const payload = {
        user_id: selectedMember.id,
        plan_id: selectedPlanId,
        branch_id: selectedBranchId,
        record_payment: recordPayment,
        payment_method: recordPayment ? paymentMethod : null,
        payment_reference: recordPayment && paymentReference.trim() ? paymentReference.trim() : null,
        notes: notes.trim() || null
      };

      const res = await assignMembershipToMember(payload);
      setSuccessFeedback(res.message || 'Membership assigned successfully.');

      if (onSuccess) {
        onSuccess(res);
      }

      // Close modal after brief pause
      setTimeout(() => {
        onClose();
      }, 1400);
    } catch (err) {
      setErrorMessage(err.message || 'Failed to assign membership.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="owner-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="assign-modal-title">
      <div className="owner-modal-card assign-membership-card">
        <div className="modal-header">
          <div className="header-title-wrap">
            <CreditCard size={20} className="gold-text" />
            <h3 id="assign-modal-title">Assign Membership Plan</h3>
          </div>
          <button type="button" className="close-btn" onClick={onClose} aria-label="Close dialog">
            <X size={18} />
          </button>
        </div>

        {errorMessage && (
          <div className="modal-alert-banner error" role="alert">
            <AlertCircle size={16} />
            <span>{errorMessage}</span>
          </div>
        )}

        {successFeedback && (
          <div className="modal-alert-banner success" role="status">
            <CheckCircle2 size={16} />
            <span>{successFeedback}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="modal-form">
          {/* Step 1: Member Selection */}
          <div className="form-section">
            <label className="form-section-title">1. Member Verification & Selection</label>

            {!selectedMember ? (
              <div className="member-search-box">
                <div className="search-input-wrap">
                  <Search size={16} className="search-icon" />
                  <input
                    type="text"
                    className="owner-input"
                    placeholder="Search by full name, phone number (+91), email, or member ID..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    autoFocus
                  />
                  {searching && <RefreshCw size={14} className="spinner-icon search-spinner" />}
                </div>

                {searchQuery.trim().length >= 2 && searchResults.length === 0 && !searching && (
                  <div className="empty-search-state">
                    <p>No registered members found matching &quot;{searchQuery}&quot;.</p>
                  </div>
                )}

                {searchResults.length > 0 && (
                  <div className="assign-search-results">
                    {searchResults.map((m) => (
                      <div
                        key={m.id}
                        className="assign-search-item"
                        onClick={() => {
                          setSelectedMember(m);
                          if (m.branch_id) setSelectedBranchId(m.branch_id);
                        }}
                        role="button"
                        tabIndex={0}
                      >
                        <div className="item-main">
                          <strong>{m.name}</strong>
                          <span className="member-code">{m.membership_id}</span>
                        </div>
                        <div className="item-meta">
                          <span>{m.email}</span>
                          <span className="bullet">•</span>
                          <span>{m.phone || 'No phone'}</span>
                          <span className="bullet">•</span>
                          <span className="branch-tag">{m.branch_id}</span>
                        </div>
                        {m.active_membership && (
                          <div className="status-note warning">
                            <AlertTriangle size={12} /> Active Plan: {m.active_membership.plan_name} (Expires {m.active_membership.end_date})
                          </div>
                        )}
                        {m.pending_enrollment && (
                          <div className="status-note info">
                            <AlertCircle size={12} /> Pending Enrollment in Queue ({m.pending_enrollment.status})
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="selected-member-preview">
                <div className="preview-header">
                  <div>
                    <h4 className="preview-name">{selectedMember.name}</h4>
                    <p className="preview-sub">
                      ID: <strong>{selectedMember.membership_id || 'Will auto-generate on assignment'}</strong>
                    </p>
                  </div>
                  {!preselectedMember && (
                    <button
                      type="button"
                      className="btn-change-member"
                      onClick={() => {
                        setSelectedMember(null);
                        setSearchQuery('');
                      }}
                    >
                      Change Member
                    </button>
                  )}
                </div>

                <div className="preview-grid">
                  <div>
                    <span className="detail-label">Email:</span>
                    <span className="detail-value">{selectedMember.email}</span>
                  </div>
                  <div>
                    <span className="detail-label">Phone:</span>
                    <span className="detail-value">{selectedMember.phone || 'Not recorded'}</span>
                  </div>
                  <div>
                    <span className="detail-label">Branch:</span>
                    <span className="detail-value">{selectedMember.branch_id || selectedBranchId}</span>
                  </div>
                  <div>
                    <span className="detail-label">Current Status:</span>
                    <span className={`detail-value ${hasActivePlan ? 'gold-text' : ''}`}>
                      {hasActivePlan
                        ? `Active (${selectedMember.active_membership?.plan_name})`
                        : hasPendingEnrollment
                        ? 'Pending Enrollment'
                        : 'No Active Membership'}
                    </span>
                  </div>
                </div>

                {hasActivePlan && (
                  <div className="member-conflict-banner warning">
                    <AlertTriangle size={16} />
                    <span>
                      Member currently has an active plan ending {selectedMember.active_membership?.end_date}. To prevent billing conflicts, please use the renewal workflow instead.
                    </span>
                  </div>
                )}

                {hasPendingEnrollment && (
                  <div className="member-conflict-banner info">
                    <AlertCircle size={16} />
                    <span>
                      Member already has a pending application awaiting desk approval. Review it in the Requests queue.
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Step 2: Plan & Branch Configuration */}
          <div className="form-section">
            <label className="form-section-title">2. Plan & Branch Configuration</label>

            <div className="form-row-2">
              <div className="form-group">
                <label htmlFor="assign-plan">Select Membership Plan *</label>
                {loadingPlans ? (
                  <div className="input-loading-placeholder">Loading plans...</div>
                ) : (
                  <select
                    id="assign-plan"
                    className="owner-input"
                    value={selectedPlanId}
                    onChange={(e) => setSelectedPlanId(e.target.value)}
                    required
                  >
                    {plans.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name} - {p.currency || '₹'}{p.price} ({p.durationDays || p.duration_days} Days)
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <div className="form-group">
                <label htmlFor="assign-branch">Home Facility Branch *</label>
                <select
                  id="assign-branch"
                  className="owner-input"
                  value={selectedBranchId}
                  onChange={(e) => setSelectedBranchId(e.target.value)}
                  required
                >
                  {branches.length > 0 ? (
                    branches.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name} ({b.city || 'Kolhapur'})
                      </option>
                    ))
                  ) : (
                    <option value="narsobawadi">RVFitness Narsobawadi Flagship</option>
                  )}
                </select>
              </div>
            </div>

            {/* Plan Confirmation Card */}
            {currentPlan && (
              <div className="plan-confirmation-box">
                <div className="box-header">
                  <span className="box-title">{currentPlan.name}</span>
                  <span className="box-price">
                    {currentPlan.currency || '₹'}{currentPlan.price}
                    <small> / {currentPlan.billingCycle || currentPlan.billing_cycle || 'protocol'}</small>
                  </span>
                </div>
                <div className="box-details-grid">
                  <div>
                    <span className="meta-lbl">Duration:</span>
                    <strong>{currentPlan.durationDays || currentPlan.duration_days} Calendar Days</strong>
                  </div>
                  <div>
                    <span className="meta-lbl">Access Scope:</span>
                    <strong>{currentPlan.accessScope === 'all_branches' ? 'All Organization Branches' : 'Single Branch'}</strong>
                  </div>
                  <div>
                    <span className="meta-lbl">Total Due:</span>
                    <strong className="gold-text">{currentPlan.currency || '₹'}{currentPlan.price} INR</strong>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Step 3: Payment Collection at Desk (Optional) */}
          <div className="form-section">
            <label className="form-section-title">3. Desk Payment Collection</label>

            <div className="checkbox-toggle-wrap">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={recordPayment}
                  onChange={(e) => setRecordPayment(e.target.checked)}
                />
                <span>Record payment collected immediately at front desk</span>
              </label>
            </div>

            {recordPayment && (
              <div className="payment-fields-box">
                <div className="form-row-2">
                  <div className="form-group">
                    <label htmlFor="assign-payment-method">Payment Method *</label>
                    <select
                      id="assign-payment-method"
                      className="owner-input"
                      value={paymentMethod}
                      onChange={(e) => setPaymentMethod(e.target.value)}
                      required={recordPayment}
                    >
                      <option value="cash">Cash (Counter Receipt)</option>
                      <option value="upi">UPI (GPay / PhonePe / QR)</option>
                      <option value="card">Card (POS Terminal)</option>
                      <option value="bank_transfer">Direct Bank NEFT / IMPS</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label htmlFor="assign-payment-ref">
                      Transaction / Receipt Reference {paymentMethod !== 'cash' ? '*' : '(Optional)'}
                    </label>
                    <input
                      id="assign-payment-ref"
                      type="text"
                      className="owner-input"
                      placeholder={paymentMethod === 'cash' ? 'Optional counter receipt number' : 'e.g. UPI Ref / Txn ID'}
                      value={paymentReference}
                      onChange={(e) => setPaymentReference(e.target.value)}
                      required={recordPayment && paymentMethod !== 'cash'}
                    />
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Step 4: Notes */}
          <div className="form-group">
            <label htmlFor="assign-notes">Administrative Notes (Optional)</label>
            <input
              id="assign-notes"
              type="text"
              className="owner-input"
              placeholder="e.g. In-person desk registration; verified ID document"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>

          {/* Submit Actions */}
          <div className="modal-actions-row">
            <button type="button" className="btn-cancel" onClick={onClose} disabled={isSubmitting}>
              Cancel
            </button>
            <button
              type="submit"
              className="btn-gold-large"
              disabled={isSubmitting || !selectedMember || hasActivePlan || hasPendingEnrollment}
            >
              {isSubmitting ? (
                <>
                  <RefreshCw size={16} className="spinner-icon" />
                  <span>Assigning Plan & Pass...</span>
                </>
              ) : (
                <>
                  <UserPlus size={16} />
                  <span>Assign Membership & Activate Pass</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
