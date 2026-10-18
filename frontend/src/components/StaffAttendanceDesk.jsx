import { useState, useEffect, useRef } from 'react';
import {
  Search,
  QrCode,
  UserCheck,
  ShieldAlert,
  FileSpreadsheet,
  FileText,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  Camera,
  Keyboard,
  Clock,
  Download,
  AlertTriangle,
  UserPlus,
  User
} from 'lucide-react';
import jsQR from 'jsqr';
import {
  lookupMembersForDesk,
  manualCheckIn,
  qrCheckIn,
  managerOverride,
  paperBackfill,
  fetchBranchMonthlyReport,
  getBranchReportExportUrl,
  downloadBranchReportExport
} from '../api';
import AssignMembershipModal from './AssignMembershipModal';
import MemberProfileModal from './MemberProfileModal';

const MANUAL_REASONS = [
  { value: 'no_account', label: 'No Online Account (Walk-in / Offline Member)' },
  { value: 'no_internet', label: 'Internet / Desk Network Connectivity Outage' },
  { value: 'qr_invalid', label: 'QR Token Expired / Unreadable / Screen Issue' },
  { value: 'other', label: 'Other Administrative Exception (Notes Required)' },
];

const TODAY_ISO = new Date().toISOString().split('T')[0];

export default function StaffAttendanceDesk({ currentUser, branchId = 'narsobawadi' }) {
  const effectiveBranchId = (!branchId || branchId === 'all') ? (currentUser?.branch_id || 'narsobawadi') : branchId;
  const [activeTab, setActiveTab] = useState('lookup'); // 'lookup' | 'qr_scan' | 'override' | 'backfill' | 'reports'

  // Direct Membership Assignment State
  const [showAssignModal, setShowAssignModal] = useState(false);
  const [assignTargetMember, setAssignTargetMember] = useState(null);

  // Member Profile Modal State
  const [profileModalMemberId, setProfileModalMemberId] = useState(null);

  // Member Search & Disambiguation State
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [selectedMember, setSelectedMember] = useState(null);
  const [lookupError, setLookupError] = useState(null);

  // Manual Check-In State
  const [manualReason, setManualReason] = useState('no_internet');
  const [manualNotes, setManualNotes] = useState('');
  const [isSubmittingCheckIn, setIsSubmittingCheckIn] = useState(false);
  const [checkInFeedback, setCheckInFeedback] = useState(null);
  const [checkInError, setCheckInError] = useState(null);

  // Unlinked Walk-in Member Form
  const [isWalkinWithoutAccount, setIsWalkinWithoutAccount] = useState(false);
  const [walkinName, setWalkinName] = useState('');
  const [walkinPhone, setWalkinPhone] = useState('');
  const [walkinMembershipId, setWalkinMembershipId] = useState('');

  // QR Scanner State (Camera & 2D Imager Wedge)
  const [scannerMode, setScannerMode] = useState('wedge'); // 'wedge' | 'camera'
  const [imagerToken, setImagerToken] = useState('');
  const [cameraError, setCameraError] = useState(null);
  const [scanSuccessFlash, setScanSuccessFlash] = useState(false);
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const hiddenCanvasRef = useRef(null);
  const animationFrameRef = useRef(null);
  const lastScannedTokenRef = useRef('');
  const lastScanTimeRef = useRef(0);

  // Manager Override State
  const [overrideAttemptId, setOverrideAttemptId] = useState('');
  const [overrideReasonText, setOverrideReasonText] = useState('');
  const [isSubmittingOverride, setIsSubmittingOverride] = useState(false);
  const [overrideFeedback, setOverrideFeedback] = useState(null);
  const [overrideError, setOverrideError] = useState(null);

  // Paper Backfill State
  const [backfillDate, setBackfillDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    return d.toISOString().split('T')[0];
  });
  const [backfillEntryOperator, setBackfillEntryOperator] = useState('');
  const [backfillReasonText, setBackfillReasonText] = useState('Desk power outage - recorded from paper ledger');
  const [isSubmittingBackfill, setIsSubmittingBackfill] = useState(false);
  const [backfillFeedback, setBackfillFeedback] = useState(null);
  const [backfillError, setBackfillError] = useState(null);

  // Monthly Report State
  const [reportYear, setReportYear] = useState(2026);
  const [reportMonth, setReportMonth] = useState(10);
  const [reportData, setReportData] = useState(null);
  const [loadingReport, setLoadingReport] = useState(false);
  const [reportError, setReportError] = useState(null);

  const isManagerOrAdmin = ['org_admin', 'admin', 'branch_manager', 'manager'].includes(currentUser?.role);

  const loadMonthlyReport = async () => {
    setLoadingReport(true);
    setReportError(null);
    try {
      const data = await fetchBranchMonthlyReport(effectiveBranchId, reportYear, reportMonth);
      setReportData(data);
    } catch (err) {
      setReportError(err.message || 'Unable to load branch monthly attendance report.');
    } finally {
      setLoadingReport(false);
    }
  };

  const [exportingFormat, setExportingFormat] = useState(null);

  const handleExport = async (format) => {
    setExportingFormat(format);
    try {
      await downloadBranchReportExport(effectiveBranchId, reportYear, reportMonth, format);
    } catch (err) {
      setReportError(err.message || `Failed to export ${format.toUpperCase()} report.`);
    } finally {
      setExportingFormat(null);
    }
  };

  const startCamera = async () => {
    setCameraError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' }
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
    } catch {
      setCameraError('Camera access unavailable. Use 2D Imager Wedge or manual code entry below.');
    }
  };

  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
  };

  // Debounced Member Lookup
  useEffect(() => {
    if (!searchQuery.trim()) {
      return;
    }

    const timer = setTimeout(async () => {
      setSearching(true);
      setLookupError(null);
      try {
        const res = await lookupMembersForDesk(searchQuery, effectiveBranchId);
        setSearchResults(res.members || []);
        if (res.members && res.members.length === 1) {
          setSelectedMember(res.members[0]);
        }
      } catch (err) {
        setLookupError(err.message || 'Error searching membership roster.');
      } finally {
        setSearching(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [searchQuery, effectiveBranchId]);

  // Load Monthly Report on tab switch or period change
  useEffect(() => {
    if (activeTab === 'reports') {
      loadMonthlyReport();
    }
  }, [activeTab, reportYear, reportMonth, effectiveBranchId]);

  // Direct QR verification helper
  const handleDirectQRScan = async (rawToken) => {
    if (!rawToken || !rawToken.trim()) return;
    const token = rawToken.trim().replace(/^["']|["']$/g, '');
    setCheckInError(null);
    setCheckInFeedback(null);
    setIsSubmittingCheckIn(true);

    try {
      const res = await qrCheckIn(token, effectiveBranchId);
      setCheckInFeedback(res.message || 'QR Check-In recorded successfully.');
      setImagerToken('');
    } catch (err) {
      setCheckInError(err.message || 'QR Verification failed.');
    } finally {
      setIsSubmittingCheckIn(false);
    }
  };

  // Camera QR Scanner Lifecycle and Active Frame Decode Loop
  useEffect(() => {
    if (activeTab === 'qr_scan' && scannerMode === 'camera') {
      startCamera();
    } else {
      stopCamera();
      return;
    }

    let isScanning = true;
    let barcodeDetector = null;
    if (typeof window !== 'undefined' && 'BarcodeDetector' in window) {
      try {
        barcodeDetector = new window.BarcodeDetector({ formats: ['qr_code'] });
      } catch (err) {
        barcodeDetector = null;
      }
    }

    const scanLoop = async () => {
      if (!isScanning) return;

      const video = videoRef.current;
      if (video && video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0) {
        const now = Date.now();
        if (now - lastScanTimeRef.current >= 120 && !isSubmittingCheckIn) {
          let detectedToken = null;

          // 1. Try native BarcodeDetector if supported
          if (barcodeDetector) {
            try {
              const barcodes = await barcodeDetector.detect(video);
              if (barcodes && barcodes.length > 0 && barcodes[0].rawValue) {
                detectedToken = barcodes[0].rawValue.trim();
              }
            } catch (e) {
              // fallback to jsQR
            }
          }

          // 2. jsQR Canvas fallback
          if (!detectedToken && hiddenCanvasRef.current) {
            try {
              const canvas = hiddenCanvasRef.current;
              canvas.width = video.videoWidth;
              canvas.height = video.videoHeight;
              const ctx = canvas.getContext('2d', { willReadFrequently: true });
              if (ctx) {
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
                const code = jsQR(imageData.data, imageData.width, imageData.height, {
                  inversionAttempts: 'dontInvert',
                });
                if (code && code.data && code.data.trim()) {
                  detectedToken = code.data.trim();
                }
              }
            } catch (e) {
              // Ignore canvas buffer glitch
            }
          }

          if (detectedToken) {
            if (detectedToken !== lastScannedTokenRef.current || now - lastScanTimeRef.current > 3000) {
              lastScannedTokenRef.current = detectedToken;
              lastScanTimeRef.current = now;
              setScanSuccessFlash(true);
              setTimeout(() => setScanSuccessFlash(false), 900);
              await handleDirectQRScan(detectedToken);
            }
          }
        }
      }

      if (isScanning) {
        animationFrameRef.current = requestAnimationFrame(scanLoop);
      }
    };

    animationFrameRef.current = requestAnimationFrame(scanLoop);

    return () => {
      isScanning = false;
      stopCamera();
    };
  }, [activeTab, scannerMode, isSubmittingCheckIn, effectiveBranchId]);

  // Handle Manual Check-In Submit
  const handleManualCheckInSubmit = async (e) => {
    e.preventDefault();
    setCheckInError(null);
    setCheckInFeedback(null);
    setIsSubmittingCheckIn(true);

    try {
      let payload = {
        branchId: effectiveBranchId,
        reasonCode: manualReason,
        notes: manualNotes,
      };

      if (isWalkinWithoutAccount) {
        if (!walkinName.trim() || !walkinPhone.trim()) {
          throw new Error('Name and contact phone are required for offline walk-in check-in.');
        }
        payload.name = walkinName.trim();
        payload.phone = walkinPhone.trim();
        payload.memberId = walkinMembershipId.trim() || undefined;
      } else {
        if (!selectedMember) {
          throw new Error('Please select a verified member from search results.');
        }
        payload.memberId = selectedMember.id;
      }

      const res = await manualCheckIn(payload);
      setCheckInFeedback(res.message);
      // Reset selections
      setSelectedMember(null);
      setSearchQuery('');
      setSearchResults([]);
      setWalkinName('');
      setWalkinPhone('');
      setWalkinMembershipId('');
      setManualNotes('');
    } catch (err) {
      setCheckInError(err.message || 'Check-in failed');
    } finally {
      setIsSubmittingCheckIn(false);
    }
  };

  // Handle QR Check-In Submit (from Imager Wedge or Camera frame)
  const handleQRCheckInSubmit = async (e) => {
    if (e) e.preventDefault();
    if (!imagerToken.trim()) return;
    await handleDirectQRScan(imagerToken);
  };

  // Handle Manager Override Submit
  const handleOverrideSubmit = async (e) => {
    e.preventDefault();
    if (!overrideAttemptId.trim()) return;
    setOverrideError(null);
    setOverrideFeedback(null);
    setIsSubmittingOverride(true);

    try {
      const res = await managerOverride({
        attemptId: overrideAttemptId.trim(),
        reason: overrideReasonText.trim(),
      });
      setOverrideFeedback(res.message);
      setOverrideAttemptId('');
      setOverrideReasonText('');
    } catch (err) {
      setOverrideError(err.message || 'Override authorization failed');
    } finally {
      setIsSubmittingOverride(false);
    }
  };

  // Handle Paper Backfill Submit
  const handleBackfillSubmit = async (e) => {
    e.preventDefault();
    setBackfillError(null);
    setBackfillFeedback(null);
    setIsSubmittingBackfill(true);

    try {
      let payload = {
        branchId,
        visitDate: backfillDate,
        entryOperator: backfillEntryOperator.trim(),
        reason: backfillReasonText.trim(),
      };

      if (isWalkinWithoutAccount) {
        if (!walkinName.trim() || !walkinPhone.trim()) {
          throw new Error('Member name and phone are required for backfill.');
        }
        payload.name = walkinName.trim();
        payload.phone = walkinPhone.trim();
        payload.memberId = walkinMembershipId.trim() || undefined;
      } else {
        if (!selectedMember) {
          throw new Error('Please select a member for this backfill entry.');
        }
        payload.memberId = selectedMember.id;
      }

      const res = await paperBackfill(payload);
      setBackfillFeedback(res.message);
      // Reset form
      setSelectedMember(null);
      setSearchQuery('');
      setSearchResults([]);
      setBackfillEntryOperator('');
    } catch (err) {
      setBackfillError(err.message || 'Paper backfill failed');
    } finally {
      setIsSubmittingBackfill(false);
    }
  };

  return (
    <div className="attendance-desk-container">
      {/* Top Navigation Tabs */}
      <div className="desk-tabs-bar" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'lookup'}
          className={`desk-tab-btn ${activeTab === 'lookup' ? 'active' : ''}`}
          onClick={() => setActiveTab('lookup')}
        >
          <Search size={16} />
          <span>Member Lookup & Desk Check-In</span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'qr_scan'}
          className={`desk-tab-btn ${activeTab === 'qr_scan' ? 'active' : ''}`}
          onClick={() => setActiveTab('qr_scan')}
        >
          <QrCode size={16} />
          <span>QR Scanner & 2D Imager</span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'override'}
          className={`desk-tab-btn ${activeTab === 'override' ? 'active' : ''}`}
          onClick={() => setActiveTab('override')}
        >
          <ShieldAlert size={16} />
          <span>Manager Override</span>
          {!isManagerOrAdmin && <span className="tab-pill-lock">Manager Only</span>}
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'backfill'}
          className={`desk-tab-btn ${activeTab === 'backfill' ? 'active' : ''}`}
          onClick={() => setActiveTab('backfill')}
        >
          <Clock size={16} />
          <span>Paper-Log Backfill</span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'reports'}
          className={`desk-tab-btn ${activeTab === 'reports' ? 'active' : ''}`}
          onClick={() => setActiveTab('reports')}
        >
          <FileSpreadsheet size={16} />
          <span>Monthly Attendance Reports</span>
        </button>
      </div>

      {/* Global Desk Feedback Banners */}
      {checkInFeedback && (
        <div className="desk-alert success" role="status">
          <CheckCircle2 size={20} className="gold-text" />
          <span>{checkInFeedback}</span>
        </div>
      )}
      {checkInError && (
        <div className="desk-alert danger" role="alert">
          <AlertCircle size={20} />
          <span>{checkInError}</span>
        </div>
      )}

      {/* TAB 1: MEMBER LOOKUP & MANUAL CHECK-IN */}
      {activeTab === 'lookup' && (
        <div className="desk-tab-content">
          <div className="desk-split-layout">
            {/* Left: Member Lookup & Disambiguation */}
            <div className="desk-card">
              <div className="card-header-row">
                <h3 className="desk-card-title">Member Search & Eligibility</h3>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <button
                    type="button"
                    className="btn-desk-assign-action"
                    onClick={() => {
                      setAssignTargetMember(null);
                      setShowAssignModal(true);
                    }}
                    title="Assign membership plan to existing member"
                  >
                    <UserPlus size={14} />
                    <span>Assign Membership</span>
                  </button>
                  <span className="desk-badge">Branch: {branchId}</span>
                </div>
              </div>

              {/* Toggle offline walk-in */}
              <div className="walkin-toggle-box">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={isWalkinWithoutAccount}
                    onChange={(e) => {
                      setIsWalkinWithoutAccount(e.target.checked);
                      if (e.target.checked) setSelectedMember(null);
                    }}
                  />
                  <span>Walk-in Member without Web Portal Account</span>
                </label>
              </div>

              {!isWalkinWithoutAccount ? (
                <>
                  <div className="search-input-wrap">
                    <Search size={18} className="search-icon" />
                    <input
                      type="text"
                      className="desk-search-input"
                      placeholder="Search by Member ID, phone (+91), or full name..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                    />
                    {searching && <RefreshCw size={16} className="spinner-icon search-spinner" />}
                  </div>

                  {lookupError && (
                    <div className="search-error-note">
                      <AlertCircle size={14} />
                      <span>{lookupError}</span>
                    </div>
                  )}

                  {/* Disambiguation Results List */}
                  <div className="disambiguation-list" aria-label="Member search results">
                    {searchResults.length === 0 && searchQuery.trim() && !searching && (
                      <div className="empty-search-state">
                        <p>No matching members found for &quot;{searchQuery}&quot;.</p>
                        <button
                          type="button"
                          className="btn-link-gold"
                          onClick={() => {
                            setIsWalkinWithoutAccount(true);
                            setWalkinName(searchQuery);
                          }}
                        >
                          <UserPlus size={14} /> Check in as unregistered walk-in member
                        </button>
                      </div>
                    )}

                    {searchResults.map((m) => (
                      <div
                        key={m.id}
                        className={`member-result-item ${selectedMember?.id === m.id ? 'selected' : ''}`}
                        onClick={() => setSelectedMember(m)}
                        role="button"
                        tabIndex={0}
                      >
                        <div className="member-item-main">
                          <strong className="member-name">{m.name}</strong>
                          <span className="member-id-tag">{m.membershipId}</span>
                        </div>
                        <div className="member-item-meta">
                          <span>Phone: <code>{m.maskedPhone}</code></span>
                          <span className="bullet">•</span>
                          <span>Plan: {m.planName}</span>
                          <span className="bullet">•</span>
                          <span className={`status-pill ${m.status}`}>{m.status}</span>
                        </div>

                        {/* Real-time eligibility badge & profile button */}
                        <div className="member-item-eligibility">
                          {m.isEligible ? (
                            <span className="eligibility-tag eligible">
                              <CheckCircle2 size={12} /> Eligible for Check-In
                            </span>
                          ) : (
                            <span className="eligibility-tag ineligible" title={m.ineligibilityReason}>
                              <AlertTriangle size={12} /> {m.ineligibilityReason || 'Ineligible'}
                            </span>
                          )}
                          <button
                            type="button"
                            className="btn-desk-profile-tag"
                            title="View member health profile, emergency contacts, and measurements"
                            onClick={(e) => {
                              e.stopPropagation();
                              setProfileModalMemberId(m.id);
                            }}
                          >
                            <User size={12} />
                            <span>Profile</span>
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                /* Unlinked Walk-in Member Details Form */
                <div className="offline-walkin-form">
                  <div className="form-group">
                    <label className="form-label" htmlFor="desk-walkin-name">Member Full Name *</label>
                    <input
                      id="desk-walkin-name"
                      type="text"
                      className="desk-input"
                      placeholder="e.g. Ramesh Patil"
                      value={walkinName}
                      onChange={(e) => setWalkinName(e.target.value)}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="desk-walkin-phone">Contact Phone Number *</label>
                    <input
                      id="desk-walkin-phone"
                      type="tel"
                      className="desk-input"
                      placeholder="e.g. +91 98220 12345"
                      value={walkinPhone}
                      onChange={(e) => setWalkinPhone(e.target.value)}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="desk-walkin-id">Physical Card / Membership ID (Optional)</label>
                    <input
                      id="desk-walkin-id"
                      type="text"
                      className="desk-input"
                      placeholder="e.g. RVF-PHYS-108"
                      value={walkinMembershipId}
                      onChange={(e) => setWalkinMembershipId(e.target.value)}
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Right: Selected Member Overview & Check-In Action */}
            <div className="desk-card">
              <h3 className="desk-card-title">Desk Check-In Action</h3>

              {selectedMember && !isWalkinWithoutAccount ? (
                <div className="selected-member-card">
                  <div className="card-top-info">
                    <div>
                      <h4 className="active-member-name">{selectedMember.name}</h4>
                      <p className="active-member-sub">
                        ID: <strong>{selectedMember.membershipId}</strong> | Phone: <code>{selectedMember.maskedPhone}</code>
                      </p>
                    </div>
                    <div className="selected-card-badges">
                      <button
                        type="button"
                        className="btn-desk-view-profile"
                        title="View detailed health, injury history, and body measurements"
                        onClick={() => setProfileModalMemberId(selectedMember.id)}
                      >
                        <User size={13} />
                        <span>Full Profile</span>
                      </button>
                      <div className="streak-badge">
                        <span className="gold-text">{selectedMember.streakDays}</span> Day Streak
                      </div>
                    </div>
                  </div>

                  <div className="eligibility-status-box">
                    {selectedMember.isEligible ? (
                      <div className="status-banner eligible">
                        <CheckCircle2 size={18} />
                        <div>
                          <strong>Verified & Eligible for Floor Entry</strong>
                          <p>Plan: {selectedMember.planName} (Valid until {selectedMember.validUntil})</p>
                        </div>
                      </div>
                    ) : (
                      <div className="status-banner ineligible">
                        <AlertCircle size={18} />
                        <div>
                          <strong>Check-In Denied by Policy</strong>
                          <p>{selectedMember.ineligibilityReason}</p>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '8px', flexWrap: 'wrap' }}>
                            <button
                              type="button"
                              className="btn-desk-assign-action"
                              onClick={() => {
                                setAssignTargetMember({
                                  id: selectedMember.id,
                                  name: selectedMember.name,
                                  phone: selectedMember.phone || selectedMember.maskedPhone,
                                  email: selectedMember.email || '',
                                  branch_id: selectedMember.branchId || branchId,
                                  membership_id: selectedMember.membershipId,
                                });
                                setShowAssignModal(true);
                              }}
                            >
                              <UserPlus size={13} />
                              <span>Assign Membership Plan</span>
                            </button>
                            {isManagerOrAdmin && (
                              <button
                                type="button"
                                className="btn-override-link"
                                onClick={() => {
                                  setActiveTab('override');
                                }}
                              >
                                Request Manager Override
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ) : isWalkinWithoutAccount ? (
                <div className="selected-member-card offline-info">
                  <h4 className="active-member-name">Offline Desk Walk-in</h4>
                  <p className="active-member-sub">
                    Direct entry for registered front-desk members without active web logins.
                  </p>
                </div>
              ) : (
                <div className="empty-select-state">
                  <UserCheck size={36} className="text-muted" />
                  <p>Search and select a member from the left panel to execute desk check-in.</p>
                </div>
              )}

              {/* Check-In Submission Form */}
              {(selectedMember || isWalkinWithoutAccount) && (
                <form onSubmit={handleManualCheckInSubmit} className="manual-checkin-form">
                  <div className="form-group">
                    <label className="form-label" htmlFor="desk-manual-reason">Mandatory Check-In Reason Code *</label>
                    <select
                      id="desk-manual-reason"
                      className="desk-select"
                      value={manualReason}
                      onChange={(e) => setManualReason(e.target.value)}
                      required
                    >
                      {MANUAL_REASONS.map((r) => (
                        <option key={r.value} value={r.value}>
                          {r.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label" htmlFor="desk-manual-notes">
                      Desk Notes {manualReason === 'other' ? '(Mandatory for Other)' : '(Optional)'}
                    </label>
                    <input
                      id="desk-manual-notes"
                      type="text"
                      className="desk-input"
                      placeholder="e.g. Scanned physical pass; unreadable phone screen"
                      value={manualNotes}
                      onChange={(e) => setManualNotes(e.target.value)}
                      required={manualReason === 'other'}
                    />
                  </div>

                  <button
                    type="submit"
                    className="btn-desk-gold"
                    disabled={isSubmittingCheckIn || (selectedMember && !selectedMember.isEligible && !isWalkinWithoutAccount)}
                  >
                    <UserCheck size={18} />
                    <span>{isSubmittingCheckIn ? 'Recording...' : 'Record Desk Check-In'}</span>
                  </button>
                </form>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: QR CAMERA & 2D IMAGER SCANNER */}
      {activeTab === 'qr_scan' && (
        <div className="desk-tab-content">
          <div className="desk-card scanner-container">
            <div className="scanner-header-row">
              <div>
                <h3 className="desk-card-title">Front Desk QR Ingestion Station</h3>
                <p className="text-muted">
                  Accepts optical 2D barcode imagers, USB wedge scanners, and browser camera streams.
                </p>
              </div>

              {/* Mode switch */}
              <div className="scanner-mode-toggles">
                <button
                  type="button"
                  className={`mode-btn ${scannerMode === 'wedge' ? 'active' : ''}`}
                  onClick={() => setScannerMode('wedge')}
                >
                  <Keyboard size={16} /> 2D Optical Imager Wedge
                </button>
                <button
                  type="button"
                  className={`mode-btn ${scannerMode === 'camera' ? 'active' : ''}`}
                  onClick={() => setScannerMode('camera')}
                >
                  <Camera size={16} /> Browser Camera Feed
                </button>
              </div>
            </div>

            {scannerMode === 'camera' ? (
              <div className="camera-scan-box">
                {cameraError ? (
                  <div className="camera-error-banner">
                    <AlertTriangle size={24} />
                    <p>{cameraError}</p>
                  </div>
                ) : (
                  <div className="camera-viewport-wrap">
                    <video ref={videoRef} autoPlay playsInline muted className="scanner-video-feed" />
                    <canvas ref={hiddenCanvasRef} style={{ display: 'none' }} />
                    <div className={`scanner-reticle ${scanSuccessFlash ? 'scanner-reticle-flash' : ''}`} aria-hidden="true" />
                    <div className="scanner-guidance">
                      {scanSuccessFlash ? 'QR Code Scanned! Verifying admission...' : 'Align member entry QR within the gold frame'}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              /* 2D Optical Imager Hardware Wedge */
              <div className="wedge-scan-box">
                <form onSubmit={handleQRCheckInSubmit} className="wedge-form">
                  <div className="imager-icon-banner" aria-hidden="true">
                    <QrCode size={48} className="gold-text" />
                  </div>
                  <label className="wedge-label" htmlFor="imager-token-input">
                    Optical Scanner Input (Listening for 2D Barcode Reader Wedge)
                  </label>
                  <div className="wedge-input-group">
                    <input
                      id="imager-token-input"
                      type="text"
                      className="wedge-text-input"
                      placeholder="Point 2D imager at member phone or paste QR entry token..."
                      value={imagerToken}
                      onChange={(e) => setImagerToken(e.target.value)}
                      autoFocus
                    />
                    <button
                      type="submit"
                      className="btn-desk-gold"
                      disabled={isSubmittingCheckIn || !imagerToken.trim()}
                    >
                      Verify Entry
                    </button>
                  </div>
                  <p className="wedge-hint">
                    Physical USB / Bluetooth barcode scanners automatically transmit the encoded token and press Enter.
                  </p>
                </form>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 3: MANAGER OVERRIDE */}
      {activeTab === 'override' && (
        <div className="desk-tab-content">
          <div className="desk-card">
            <div className="card-header-row">
              <h3 className="desk-card-title">Manager Supervisory Override</h3>
              <span className="badge-warning">Supervisory Authority Required</span>
            </div>

            {overrideFeedback && (
              <div className="desk-alert success" role="status">
                <CheckCircle2 size={18} />
                <span>{overrideFeedback}</span>
              </div>
            )}
            {overrideError && (
              <div className="desk-alert danger" role="alert">
                <AlertCircle size={18} />
                <span>{overrideError}</span>
              </div>
            )}

            {!isManagerOrAdmin ? (
              <div className="unauthorized-card">
                <ShieldAlert size={48} className="danger-text" />
                <h4>Manager Authorization Required</h4>
                <p>
                  Front desk operators cannot override policy rejections without supervisory credentials.
                  Please request a Branch Manager or Organization Administrator to authorize this transaction.
                </p>
              </div>
            ) : (
              <form onSubmit={handleOverrideSubmit} className="override-form">
                <p className="override-intro-text">
                  Manager overrides permit an exceptional floor entry following a rejected check-in attempt.
                  The original rejection attempt is strictly preserved in the audit log.
                </p>

                <div className="form-group">
                  <label className="form-label" htmlFor="override-attempt-id">Rejected Attendance Attempt ID *</label>
                  <input
                    id="override-attempt-id"
                    type="text"
                    className="desk-input font-mono"
                    placeholder="Enter or paste Attendance Attempt UUID..."
                    value={overrideAttemptId}
                    onChange={(e) => setOverrideAttemptId(e.target.value)}
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="override-reason-text">
                    Mandatory Manager Override Justification (Min 5 chars) *
                  </label>
                  <textarea
                    id="override-reason-text"
                    className="desk-textarea"
                    rows={3}
                    placeholder="e.g. Member unfreeze form signed in person at counter; billing payment in cash verified..."
                    value={overrideReasonText}
                    onChange={(e) => setOverrideReasonText(e.target.value)}
                    required
                    minLength={5}
                  />
                </div>

                <button
                  type="submit"
                  className="btn-desk-gold"
                  disabled={isSubmittingOverride || !overrideAttemptId.trim() || overrideReasonText.trim().length < 5}
                >
                  <ShieldAlert size={18} />
                  <span>{isSubmittingOverride ? 'Authorizing Override...' : 'Authorize Manager Override'}</span>
                </button>
              </form>
            )}
          </div>
        </div>
      )}

      {/* TAB 4: PAPER-LOG BACKFILL */}
      {activeTab === 'backfill' && (
        <div className="desk-tab-content">
          <div className="desk-card">
            <div className="card-header-row">
              <h3 className="desk-card-title">Controlled Paper-Log Outage Backfill</h3>
              <span className="desk-badge">Desk Downtime &amp; ISP Outages</span>
            </div>

            {backfillFeedback && (
              <div className="desk-alert success" role="status">
                <CheckCircle2 size={18} />
                <span>{backfillFeedback}</span>
              </div>
            )}
            {backfillError && (
              <div className="desk-alert danger" role="alert">
                <AlertCircle size={18} />
                <span>{backfillError}</span>
              </div>
            )}

            <form onSubmit={handleBackfillSubmit} className="backfill-form">
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label" htmlFor="backfill-visit-date">Original Visit Date (Past or Today) *</label>
                  <input
                    id="backfill-visit-date"
                    type="date"
                    className="desk-input"
                    value={backfillDate}
                    max={TODAY_ISO}
                    onChange={(e) => setBackfillDate(e.target.value)}
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label" htmlFor="backfill-entry-operator">Original Entry Operator on Paper Log *</label>
                  <input
                    id="backfill-entry-operator"
                    type="text"
                    className="desk-input"
                    placeholder="e.g. Operator Sandeep (Desk Register #1)"
                    value={backfillEntryOperator}
                    onChange={(e) => setBackfillEntryOperator(e.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="backfill-reason-text">Reason for Backfill Entry *</label>
                <input
                  id="backfill-reason-text"
                  type="text"
                  className="desk-input"
                  placeholder="e.g. Power grid downtime & ISP outage on October 12"
                  value={backfillReasonText}
                  onChange={(e) => setBackfillReasonText(e.target.value)}
                  required
                />
              </div>

              {/* Member identification */}
              <div className="form-group">
                <label className="form-label" htmlFor="backfill-member-id">Member UUID, Membership ID, or Search Query *</label>
                <input
                  id="backfill-member-id"
                  type="text"
                  className="desk-input"
                  placeholder="Member ID, phone number, or name..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  required
                />
              </div>

              {searchResults.length > 0 && (
                <div className="disambiguation-list small">
                  {searchResults.map((m) => (
                    <div
                      key={m.id}
                      className={`member-result-item ${selectedMember?.id === m.id ? 'selected' : ''}`}
                      onClick={() => setSelectedMember(m)}
                    >
                      <strong className="member-name">{m.name}</strong> ({m.membershipId})
                      <span className="text-muted ml-2">Phone: {m.maskedPhone}</span>
                    </div>
                  ))}
                </div>
              )}

              <button
                type="submit"
                className="btn-desk-gold"
                disabled={isSubmittingBackfill || !backfillEntryOperator.trim() || !backfillReasonText.trim()}
              >
                <Clock size={18} />
                <span>{isSubmittingBackfill ? 'Recording Backfill...' : 'Commit Historical Backfill'}</span>
              </button>
            </form>
          </div>
        </div>
      )}

      {/* TAB 5: MONTHLY ATTENDANCE REPORTS */}
      {activeTab === 'reports' && (
        <div className="desk-tab-content">
          <div className="desk-card">
            {/* Header with Month/Year selection and Export Buttons */}
            <div className="reports-top-bar">
              <div className="period-selector-group">
                <div className="selector-item">
                  <label htmlFor="report-month-select">Month</label>
                  <select
                    id="report-month-select"
                    className="desk-select"
                    value={reportMonth}
                    onChange={(e) => setReportMonth(parseInt(e.target.value, 10))}
                  >
                    {[
                      { val: 1, name: 'January' },
                      { val: 2, name: 'February' },
                      { val: 3, name: 'March' },
                      { val: 4, name: 'April' },
                      { val: 5, name: 'May' },
                      { val: 6, name: 'June' },
                      { val: 7, name: 'July' },
                      { val: 8, name: 'August' },
                      { val: 9, name: 'September' },
                      { val: 10, name: 'October' },
                      { val: 11, name: 'November' },
                      { val: 12, name: 'December' },
                    ].map((m) => (
                      <option key={m.val} value={m.val}>{m.name}</option>
                    ))}
                  </select>
                </div>

                <div className="selector-item">
                  <label htmlFor="report-year-select">Year</label>
                  <select
                    id="report-year-select"
                    className="desk-select"
                    value={reportYear}
                    onChange={(e) => setReportYear(parseInt(e.target.value, 10))}
                  >
                    {[2024, 2025, 2026, 2027].map((y) => (
                      <option key={y} value={y}>{y}</option>
                    ))}
                  </select>
                </div>

                <button
                  type="button"
                  className="btn-refresh-report"
                  onClick={loadMonthlyReport}
                  title="Recalculate report summaries"
                >
                  <RefreshCw size={16} className={loadingReport ? 'spinner-icon' : ''} />
                  <span>Recalculate</span>
                </button>
              </div>

              {/* Export Buttons */}
              <div className="export-actions-group">
                <button
                  type="button"
                  onClick={() => handleExport('csv')}
                  disabled={exportingFormat === 'csv'}
                  className="btn-export csv"
                  title="Export Attendance Report as CSV"
                >
                  <Download size={15} />
                  <span>{exportingFormat === 'csv' ? 'Exporting...' : 'Export CSV'}</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleExport('pdf')}
                  disabled={exportingFormat === 'pdf'}
                  className="btn-export pdf"
                  title="Export Attendance Report as PDF"
                >
                  <FileText size={15} />
                  <span>{exportingFormat === 'pdf' ? 'Exporting...' : 'Export PDF'}</span>
                </button>
              </div>
            </div>

            {loadingReport && (
              <div className="desk-loading-state">
                <RefreshCw size={28} className="spinner-icon gold-text" />
                <p>Generating reproducible branch attendance summary for {reportMonth}/{reportYear}...</p>
              </div>
            )}

            {reportError && (
              <div className="desk-alert danger" role="alert">
                <AlertCircle size={20} />
                <span>{reportError}</span>
              </div>
            )}

            {!loadingReport && !reportError && reportData && (
              <div className="report-summary-view">
                {/* Metric Summary Grid */}
                <div className="report-metrics-grid">
                  <div className="report-metric-card">
                    <span className="rep-label">Distinct Attendance Days</span>
                    <strong className="rep-value gold-text">{reportData.distinctAttendanceDays}</strong>
                    <span className="rep-sub">Floor activity dates</span>
                  </div>

                  <div className="report-metric-card">
                    <span className="rep-label">Dynamic QR Check-Ins</span>
                    <strong className="rep-value">{reportData.qrCheckins}</strong>
                    <span className="rep-sub">Single-use token entry</span>
                  </div>

                  <div className="report-metric-card">
                    <span className="rep-label">Desk Manual Check-Ins</span>
                    <strong className="rep-value">{reportData.manualCheckins}</strong>
                    <span className="rep-sub">Staff assisted verify</span>
                  </div>

                  <div className="report-metric-card">
                    <span className="rep-label">Paper Backfills</span>
                    <strong className="rep-value">{reportData.backfilledCheckins}</strong>
                    <span className="rep-sub">Outage recovery entries</span>
                  </div>

                  <div className="report-metric-card">
                    <span className="rep-label">Manager Overrides</span>
                    <strong className="rep-value">{reportData.managerOverrides}</strong>
                    <span className="rep-sub">Supervisory approvals</span>
                  </div>

                  <div className="report-metric-card">
                    <span className="rep-label">Rejected Attempts</span>
                    <strong className="rep-value danger-text">{reportData.rejectedAttemptsCount}</strong>
                    <span className="rep-sub">Failed QR or policy stops</span>
                  </div>
                </div>

                {/* Staff Operator Manual Check-In Ratio Analysis */}
                <div className="report-table-section">
                  <h4 className="section-title">Staff Operator Manual Check-In Analysis</h4>
                  <div className="table-responsive">
                    <table className="admin-table">
                      <thead>
                        <tr>
                          <th scope="col">Staff Operator Name</th>
                          <th scope="col">Operator ID</th>
                          <th scope="col">Manual Check-Ins Facilitated</th>
                          <th scope="col">Total Check-Ins Handled</th>
                          <th scope="col">Manual Ratio %</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(!reportData.operatorMetrics || reportData.operatorMetrics.length === 0) ? (
                          <tr>
                            <td colSpan={5} className="text-center text-muted">
                              No manual desk check-ins recorded by staff operators in this period.
                            </td>
                          </tr>
                        ) : (
                          reportData.operatorMetrics.map((op) => (
                            <tr key={op.operatorId}>
                              <td><strong>{op.operatorName}</strong></td>
                              <td><code className="text-muted">{op.operatorId.slice(0, 12)}...</code></td>
                              <td>{op.manualCount}</td>
                              <td>{op.totalCount}</td>
                              <td>
                                <span className={`ratio-pill ${op.manualRatioPercent > 30 ? 'high' : 'normal'}`}>
                                  {op.manualRatioPercent}%
                                </span>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Daily Attendance Breakdown */}
                <div className="report-table-section mt-6">
                  <h4 className="section-title">Daily Calendar Attendance Breakdown</h4>
                  <div className="table-responsive">
                    <table className="admin-table">
                      <thead>
                        <tr>
                          <th scope="col">Calendar Date</th>
                          <th scope="col">Total Floor Check-Ins</th>
                          <th scope="col">QR Codes</th>
                          <th scope="col">Desk Manual</th>
                          <th scope="col">Manager Override</th>
                          <th scope="col">Outage Backfill</th>
                        </tr>
                      </thead>
                      <tbody>
                        {reportData.dailyBreakdown?.map((d) => (
                          <tr key={d.date} className={d.totalCount > 0 ? 'active-row' : ''}>
                            <td><strong>{d.date}</strong></td>
                            <td className="gold-text font-bold">{d.totalCount}</td>
                            <td>{d.qrCount}</td>
                            <td>{d.manualCount}</td>
                            <td>{d.overrideCount}</td>
                            <td>{d.backfillCount}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Direct Membership Assignment Modal */}
      <AssignMembershipModal
        isOpen={showAssignModal}
        onClose={() => setShowAssignModal(false)}
        preselectedMember={assignTargetMember}
        initialBranchId={effectiveBranchId}
        onSuccess={() => {
          setCheckInFeedback('Membership successfully assigned to member.');
          // Refresh member search
          if (searchQuery.trim()) {
            setSearchQuery(searchQuery.trim());
          }
        }}
      />

      {/* Staff / Coach Member Profile Modal */}
      {profileModalMemberId && (
        <MemberProfileModal
          memberId={profileModalMemberId}
          currentUser={currentUser}
          onClose={() => setProfileModalMemberId(null)}
          onProfileUpdated={() => {
            if (searchQuery.trim()) {
              lookupMembersForDesk(searchQuery, effectiveBranchId)
                .then((res) => setSearchResults(res.members || []))
                .catch(() => {});
            }
          }}
        />
      )}
    </div>
  );
}
