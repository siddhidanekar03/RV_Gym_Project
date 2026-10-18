import { useState, useEffect } from 'react';
import {
  LayoutDashboard,
  Globe,
  Dumbbell,
  Users,
  CreditCard,
  Building,
  QrCode,
  Megaphone,
  Settings,
  Plus,
  Edit2,
  Trash2,
  Upload,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Eye,
  Shield,
  Clock,
  MapPin,
  X,
  Save,
  Camera,
  Layers,
  Archive,
  Phone,
  Mail,
  Award,
  ClipboardCheck,
  FileText,
  Check,
  Search,
  Filter,
  UserPlus,
  Image as ImageIcon
} from 'lucide-react';
import {
  fetchWebsiteContent,
  updateWebsiteContent,
  fetchOwnerEquipment,
  createOwnerEquipment,
  updateOwnerEquipment,
  deleteOwnerEquipment,
  uploadOwnerEquipmentPhoto,
  fetchOwnerGallery,
  createOwnerGallery,
  updateOwnerGallery,
  deleteOwnerGallery,
  uploadOwnerGalleryPhoto,
  fetchOwnerCoaches,
  createOwnerCoach,
  updateOwnerCoach,
  uploadOwnerCoachPhoto,
  deleteOwnerCoachPhoto,
  fetchOwnerPlans,
  createOwnerPlan,
  updateOwnerPlan,
  archiveOwnerPlan,
  uploadOwnerMedia,
  fetchBranches,
  fetchOwnerEnrollments,
  fetchOwnerEnrollmentById,
  approveOwnerEnrollment,
  rejectOwnerEnrollment,
} from '../api';
import StaffAttendanceDesk from './StaffAttendanceDesk';
import AdminAnnouncements from './AdminAnnouncements';
import AssignMembershipModal from './AssignMembershipModal';
import { validatePhoneNumber } from '../utils/phoneValidation';

export default function GymOwnerPanel({ user, onClose }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [branches, setBranches] = useState([]);
  const [selectedBranchId, setSelectedBranchId] = useState(user?.branch_id || 'narsobawadi');

  // Feedback notifications
  const [feedback, setFeedback] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  // Overview stats
  const [stats, setStats] = useState({
    equipmentCount: 0,
    coachesCount: 0,
    plansCount: 0,
    branchesCount: 1,
  });

  // Website Content state
  const [heroForm, setHeroForm] = useState({
    headline: 'BUILD STRENGTH.\nDEMAND DISCIPLINE.\nDEFINE YOURSELF.',
    subtitle: 'A serious strength and athletic conditioning facility in Narsobawadi. Certified coaching, modern free-weight equipment, and a focused environment designed for consistent progress.',
    badgeText: 'RVFITNESS · NARSOBAWADI',
    badgeTiming: '6:00 AM - 10:00 PM',
    ctaPrimary: 'Enroll In Membership',
    ctaSecondary: 'Explore Facilities',
    coverImageUrl: '',
  });
  const [contactForm, setContactForm] = useState({
    phone: '+91 98220 12345',
    email: 'contact@rvfitness.in',
    location: 'Near Datta Mandir Road, Narsobawadi, Kolhapur District, Maharashtra 416104',
  });
  const [savingContent, setSavingContent] = useState(false);
  const [previewWebsite, setPreviewWebsite] = useState(false);

  // Equipment state
  const [equipmentList, setEquipmentList] = useState([]);
  const [loadingEquipment, setLoadingEquipment] = useState(false);
  const [showAddEquipmentModal, setShowAddEquipmentModal] = useState(false);
  const [editingEquipment, setEditingEquipment] = useState(null);
  const [equipmentForm, setEquipmentForm] = useState({
    name: '',
    category: 'Free Weights',
    spec: '',
    brand_model: '',
    branch_id: selectedBranchId,
    primary_image_url: '',
    is_published: true,
  });
  const [uploadingEquipmentId, setUploadingEquipmentId] = useState(null);
  const [deletingEquipmentItem, setDeletingEquipmentItem] = useState(null);

  // Gallery state
  const [galleryList, setGalleryList] = useState([]);
  const [loadingGallery, setLoadingGallery] = useState(false);
  const [showAddGalleryModal, setShowAddGalleryModal] = useState(false);
  const [galleryForm, setGalleryForm] = useState({
    zone: '',
    description: '',
    image_url: '',
    status: 'In Active Use',
    branch_id: selectedBranchId,
    is_published: true,
  });
  const [deletingGalleryItem, setDeletingGalleryItem] = useState(null);

  // Coaches state
  const [coachesList, setCoachesList] = useState([]);
  const [loadingCoaches, setLoadingCoaches] = useState(false);
  const [showAddCoachModal, setShowAddCoachModal] = useState(false);
  const [editingCoach, setEditingCoach] = useState(null);
  const [coachPhotoUploading, setCoachPhotoUploading] = useState(false);
  const [coachForm, setCoachForm] = useState({
    name: '',
    email: '',
    password: '',
    phone: '',
    branch_id: selectedBranchId,
    specialization: 'Strength & Conditioning Coach',
    bio: '',
    certificationsText: 'Certified Personal Trainer, CPR/AED',
    experience_years: 3,
    max_clients: 20,
    is_accepting_clients: true,
    photo_url: '',
  });
  const [editCoachForm, setEditCoachForm] = useState({
    specialization: '',
    bio: '',
    certificationsText: '',
    experience_years: 3,
    max_clients: 20,
    is_accepting_clients: true,
    photo_url: '',
    is_active: true,
  });

  // Direct Membership Assignment Modal state
  const [showAssignMembershipModal, setShowAssignMembershipModal] = useState(false);

  // Plans state
  const [plansList, setPlansList] = useState([]);
  const [loadingPlans, setLoadingPlans] = useState(false);
  const [showAddPlanModal, setShowAddPlanModal] = useState(false);
  const [editingPlan, setEditingPlan] = useState(null);
  const [planForm, setPlanForm] = useState({
    id: '',
    name: '',
    category: 'strength',
    access_scope: 'single_branch',
    price: '2500.00',
    currency: '₹',
    billing_cycle: 'per month',
    duration_days: 30,
    is_featured: false,
    is_active: true,
    description: '',
    perksText: 'Full gym floor access\nStandard locker room access\nInitial fitness assessment',
  });
  const [deletingPlanItem, setDeletingPlanItem] = useState(null);

  // Enrollment Approvals Queue state
  const [enrollmentsList, setEnrollmentsList] = useState([]);
  const [loadingEnrollments, setLoadingEnrollments] = useState(false);
  const [enrollmentStatusFilter, setEnrollmentStatusFilter] = useState('all');
  const [enrollmentSearchQuery, setEnrollmentSearchQuery] = useState('');
  const [selectedEnrollmentForDetail, setSelectedEnrollmentForDetail] = useState(null);
  const [showApprovalModal, setShowApprovalModal] = useState(false);
  const [showRejectionModal, setShowRejectionModal] = useState(false);
  const [targetEnrollment, setTargetEnrollment] = useState(null);

  // Approval Form state (supports optional desk payment recording)
  const [approvalForm, setApprovalForm] = useState({
    record_payment: false,
    payment_method: 'cash',
    reference_number: '',
    notes: '',
  });
  const [submittingApproval, setSubmittingApproval] = useState(false);

  // Rejection Form state
  const [rejectionForm, setRejectionForm] = useState({
    reason: '',
  });
  const [submittingRejection, setSubmittingRejection] = useState(false);

  // Auto-clear notifications
  useEffect(() => {
    if (feedback || errorMessage) {
      const timer = setTimeout(() => {
        setFeedback(null);
        setErrorMessage(null);
      }, 6000);
      return () => clearTimeout(timer);
    }
  }, [feedback, errorMessage]);

  // Initial Load
  useEffect(() => {
    loadInitialData();
  }, [selectedBranchId]);

  const loadEnrollments = async (status = enrollmentStatusFilter, search = enrollmentSearchQuery) => {
    setLoadingEnrollments(true);
    try {
      const res = await fetchOwnerEnrollments({
        status,
        branchId: selectedBranchId === 'all' ? '' : selectedBranchId,
        search,
      });
      const list = res.enrollments || [];
      setEnrollmentsList(list);
      const pendingCount = list.filter(e => e.status === 'pending_verification' || e.status === 'Pending Verification at Gym Desk').length;
      setStats((prev) => ({
        ...prev,
        pendingEnrollmentCount: res.totalPending !== undefined ? res.totalPending : pendingCount,
      }));
    } catch (err) {
      setErrorMessage(err.message || 'Failed to fetch membership applications.');
    } finally {
      setLoadingEnrollments(false);
    }
  };

  const handleOpenApproveModal = (enrollment) => {
    setTargetEnrollment(enrollment);
    setApprovalForm({
      record_payment: false,
      payment_method: 'cash',
      reference_number: '',
      notes: '',
    });
    setShowApprovalModal(true);
  };

  const handleConfirmApproval = async (e) => {
    e.preventDefault();
    if (!targetEnrollment) return;
    setSubmittingApproval(true);
    setErrorMessage(null);
    try {
      const payload = {
        record_payment: approvalForm.record_payment,
        payment_method: approvalForm.payment_method,
        reference_number: approvalForm.reference_number || undefined,
        notes: approvalForm.notes || undefined,
      };
      const res = await approveOwnerEnrollment(targetEnrollment.id, payload);
      setFeedback(res.message || 'Enrollment request approved successfully.');
      setShowApprovalModal(false);
      setTargetEnrollment(null);
      await loadEnrollments();
      await loadInitialData();
    } catch (err) {
      setErrorMessage(err.message || 'Failed to approve enrollment.');
    } finally {
      setSubmittingApproval(false);
    }
  };

  const handleOpenRejectModal = (enrollment) => {
    setTargetEnrollment(enrollment);
    setRejectionForm({
      reason: '',
    });
    setShowRejectionModal(true);
  };

  const handleConfirmRejection = async (e) => {
    e.preventDefault();
    if (!targetEnrollment) return;
    if (!rejectionForm.reason.trim()) {
      setErrorMessage('Please provide a reason for rejecting this application.');
      return;
    }
    setSubmittingRejection(true);
    setErrorMessage(null);
    try {
      const payload = {
        reason: rejectionForm.reason.trim(),
      };
      const res = await rejectOwnerEnrollment(targetEnrollment.id, payload);
      setFeedback(res.message || 'Enrollment application rejected.');
      setShowRejectionModal(false);
      setTargetEnrollment(null);
      await loadEnrollments();
      await loadInitialData();
    } catch (err) {
      setErrorMessage(err.message || 'Failed to reject enrollment.');
    } finally {
      setSubmittingRejection(false);
    }
  };

  const handleViewEnrollmentDetail = async (enrollment) => {
    try {
      const res = await fetchOwnerEnrollmentById(enrollment.id);
      setSelectedEnrollmentForDetail(res.enrollment || enrollment);
    } catch (err) {
      setSelectedEnrollmentForDetail(enrollment);
    }
  };

  const loadInitialData = async () => {
    try {
      // Load website content
      const contentRes = await fetchWebsiteContent().catch(() => ({ sections: {} }));
      if (contentRes.sections) {
        if (contentRes.sections.homepage_hero?.data) {
          setHeroForm((prev) => ({ ...prev, ...contentRes.sections.homepage_hero.data }));
        }
        if (contentRes.sections.contact?.data) {
          setContactForm((prev) => ({ ...prev, ...contentRes.sections.contact.data }));
        }
      }

      // Load equipment
      setLoadingEquipment(true);
      const equipRes = await fetchOwnerEquipment(selectedBranchId).catch(() => ({ equipment: [] }));
      setEquipmentList(equipRes.equipment || []);
      setLoadingEquipment(false);

      // Load gallery
      setLoadingGallery(true);
      const galRes = await fetchOwnerGallery(selectedBranchId).catch(() => ({ gallery: [] }));
      setGalleryList(galRes.gallery || []);
      setLoadingGallery(false);

      // Load coaches
      setLoadingCoaches(true);
      const coachRes = await fetchOwnerCoaches(selectedBranchId).catch(() => ({ coaches: [] }));
      setCoachesList(coachRes.coaches || []);
      setLoadingCoaches(false);

      // Load plans
      setLoadingPlans(true);
      const planRes = await fetchOwnerPlans().catch(() => ({ plans: [] }));
      setPlansList(planRes.plans || []);
      setLoadingPlans(false);

      // Load enrollments queue
      const enrRes = await fetchOwnerEnrollments({ status: 'all', branchId: selectedBranchId === 'all' ? '' : selectedBranchId }).catch(() => ({ enrollments: [], totalPending: 0 }));
      const enrList = enrRes.enrollments || [];
      setEnrollmentsList(enrList);
      const pendingCount = enrList.filter(e => e.status === 'pending_verification' || e.status === 'Pending Verification at Gym Desk').length;

      // Update overview statistics
      setStats({
        equipmentCount: equipRes.equipment?.length || 0,
        coachesCount: coachRes.coaches?.length || 0,
        plansCount: planRes.plans?.length || 0,
        branchesCount: 1,
        pendingEnrollmentCount: enrRes.totalPending !== undefined ? enrRes.totalPending : pendingCount,
      });
    } catch (err) {
      setErrorMessage(err.message || 'Failed to load owner management records.');
    }
  };

  // 1. Website Content Save Handlers
  const handleSaveHeroContent = async (e) => {
    e.preventDefault();
    setSavingContent(true);
    setErrorMessage(null);
    try {
      await updateWebsiteContent('homepage_hero', heroForm);
      setFeedback('Homepage Hero section updated successfully. Changes are now visible on the public website.');
    } catch (err) {
      setErrorMessage(err.message || 'Failed to save Hero section.');
    } finally {
      setSavingContent(false);
    }
  };

  const handleSaveContactContent = async (e) => {
    e.preventDefault();
    setSavingContent(true);
    setErrorMessage(null);
    try {
      await updateWebsiteContent('contact', contactForm);
      setFeedback('Facility contact details updated successfully.');
    } catch (err) {
      setErrorMessage(err.message || 'Failed to update contact details.');
    } finally {
      setSavingContent(false);
    }
  };

  const handleHeroCoverUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      setErrorMessage('Please select a valid image file (JPEG, PNG, or WebP).');
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setErrorMessage('Hero cover photograph must not exceed 5.0 MB.');
      return;
    }
    try {
      const res = await uploadOwnerMedia(file);
      setHeroForm((prev) => ({ ...prev, coverImageUrl: res.imageUrl }));
      setFeedback('Hero background cover photo uploaded. Save changes to publish.');
    } catch (err) {
      setErrorMessage(err.message || 'Cover photo upload failed.');
    }
  };

  const handleRemoveHeroCover = () => {
    setHeroForm((prev) => ({ ...prev, coverImageUrl: '' }));
    setFeedback('Hero image cleared. Save changes to restore default diagram.');
  };

  // 2. Equipment Handlers
  const handleCreateEquipment = async (e) => {
    e.preventDefault();
    setErrorMessage(null);
    try {
      await createOwnerEquipment({
        ...equipmentForm,
        branch_id: selectedBranchId,
      });
      setFeedback(`Equipment '${equipmentForm.name}' added successfully.`);
      setShowAddEquipmentModal(false);
      setEquipmentForm({
        name: '',
        category: 'Free Weights',
        spec: '',
        brand_model: '',
        branch_id: selectedBranchId,
        primary_image_url: '',
        is_published: true,
      });
      loadInitialData();
    } catch (err) {
      setErrorMessage(err.message || 'Failed to add equipment.');
    }
  };

  const handleUpdateEquipment = async (e) => {
    e.preventDefault();
    if (!editingEquipment) return;
    setErrorMessage(null);
    try {
      await updateOwnerEquipment(editingEquipment.id, equipmentForm);
      setFeedback(`Equipment '${equipmentForm.name}' updated successfully.`);
      setEditingEquipment(null);
      loadInitialData();
    } catch (err) {
      setErrorMessage(err.message || 'Failed to update equipment item.');
    }
  };

  const handleDeleteEquipment = async () => {
    if (!deletingEquipmentItem) return;
    try {
      await deleteOwnerEquipment(deletingEquipmentItem.id);
      setFeedback(`Equipment '${deletingEquipmentItem.name}' removed successfully.`);
      setDeletingEquipmentItem(null);
      loadInitialData();
    } catch (err) {
      setErrorMessage(err.message || 'Failed to delete equipment item.');
    }
  };

  const handleEquipmentPhotoUpload = async (equipmentId, file, setPrimary = true) => {
    if (!file) return;
    try {
      await uploadOwnerEquipmentPhoto(equipmentId, file);
      setFeedback('Equipment photo uploaded successfully.');
      loadInitialData();
    } catch (err) {
      setErrorMessage(err.message || 'Photo upload failed.');
    }
  };

  // 3. Gallery Handlers
  const handleCreateGalleryItem = async (e) => {
    e.preventDefault();
    setErrorMessage(null);
    try {
      await createOwnerGallery({
        ...galleryForm,
        branch_id: selectedBranchId,
      });
      setFeedback(`Gallery zone '${galleryForm.zone}' added successfully.`);
      setShowAddGalleryModal(false);
      setGalleryForm({
        zone: '',
        description: '',
        image_url: '',
        status: 'In Active Use',
        branch_id: selectedBranchId,
        is_published: true,
      });
      loadInitialData();
    } catch (err) {
      setErrorMessage(err.message || 'Failed to create gallery zone.');
    }
  };

  const handleGalleryPhotoUpload = async (file) => {
    if (!file) return;
    try {
      const res = await uploadOwnerGalleryPhoto(file);
      setGalleryForm((prev) => ({ ...prev, image_url: res.imageUrl }));
      setFeedback('Gallery photograph uploaded.');
    } catch (err) {
      setErrorMessage(err.message || 'Photo upload failed.');
    }
  };

  const handleDeleteGallery = async () => {
    if (!deletingGalleryItem) return;
    try {
      await deleteOwnerGallery(deletingGalleryItem.id);
      setFeedback(`Gallery zone '${deletingGalleryItem.zone}' deleted successfully.`);
      setDeletingGalleryItem(null);
      loadInitialData();
    } catch (err) {
      setErrorMessage(err.message || 'Failed to delete gallery zone.');
    }
  };

  // 4. Coaches Handlers
  const handleCreateCoach = async (e) => {
    e.preventDefault();
    setErrorMessage(null);
    try {
      const certs = coachForm.certificationsText
        .split('\n')
        .map((c) => c.trim())
        .filter(Boolean);

      if (coachForm.phone) {
        const phoneCheck = validatePhoneNumber(coachForm.phone);
        if (!phoneCheck.isValid) {
          throw new Error(phoneCheck.error || 'Invalid coach phone number format.');
        }
      }

      await createOwnerCoach({
        name: coachForm.name,
        email: coachForm.email,
        password: coachForm.password,
        phone: coachForm.phone,
        branch_id: selectedBranchId,
        specialization: coachForm.specialization,
        bio: coachForm.bio,
        certifications: certs,
        experience_years: parseInt(coachForm.experience_years, 10) || 1,
        max_clients: parseInt(coachForm.max_clients, 10) || 20,
        is_accepting_clients: coachForm.is_accepting_clients,
        photo_url: coachForm.photo_url || null,
      });
      setFeedback(`Coach '${coachForm.name}' created successfully.`);
      setShowAddCoachModal(false);
      setCoachForm({
        name: '',
        email: '',
        password: '',
        phone: '',
        branch_id: selectedBranchId,
        specialization: 'Strength & Conditioning Coach',
        bio: '',
        certificationsText: 'Certified Personal Trainer, CPR/AED',
        experience_years: 3,
        max_clients: 20,
        is_accepting_clients: true,
        photo_url: '',
      });
      loadInitialData();
    } catch (err) {
      setErrorMessage(err.message || 'Failed to create coach account.');
    }
  };

  const handleOpenEditCoach = (coach) => {
    setEditingCoach(coach);
    setEditCoachForm({
      specialization: coach.specialization || '',
      bio: coach.bio || '',
      certificationsText: (coach.certifications || []).join('\n'),
      experience_years: coach.experienceYears !== undefined ? coach.experienceYears : (coach.experience_years || 1),
      max_clients: coach.maxClients !== undefined ? coach.maxClients : (coach.max_clients || 20),
      is_accepting_clients: coach.isAcceptingClients !== undefined ? coach.isAcceptingClients : true,
      photo_url: coach.photo_url || coach.photoUrl || '',
      is_active: coach.isActive !== undefined ? coach.isActive : true,
    });
  };

  const handleUpdateCoach = async (e) => {
    e.preventDefault();
    if (!editingCoach) return;
    setErrorMessage(null);
    try {
      const certs = editCoachForm.certificationsText
        .split('\n')
        .map((c) => c.trim())
        .filter(Boolean);

      await updateOwnerCoach(editingCoach.id, {
        specialization: editCoachForm.specialization,
        bio: editCoachForm.bio,
        certifications: certs,
        experience_years: parseInt(editCoachForm.experience_years, 10) || 1,
        max_clients: parseInt(editCoachForm.max_clients, 10) || 20,
        is_accepting_clients: editCoachForm.is_accepting_clients,
        photo_url: editCoachForm.photo_url || null,
        is_active: editCoachForm.is_active,
      });
      setFeedback(`Coach '${editingCoach.name}' details updated successfully.`);
      setEditingCoach(null);
      loadInitialData();
    } catch (err) {
      setErrorMessage(err.message || 'Failed to update coach details.');
    }
  };

  const handleCoachPhotoUpload = async (e, isEdit = false) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      setErrorMessage('Please select a valid image file (JPEG, PNG, or WebP).');
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setErrorMessage('Coach portrait must not exceed 5.0 MB.');
      return;
    }
    setCoachPhotoUploading(true);
    setErrorMessage(null);
    try {
      const res = await uploadOwnerCoachPhoto(file);
      if (isEdit) {
        setEditCoachForm((prev) => ({ ...prev, photo_url: res.imageUrl }));
      } else {
        setCoachForm((prev) => ({ ...prev, photo_url: res.imageUrl }));
      }
      setFeedback('Coach photograph uploaded.');
    } catch (err) {
      setErrorMessage(err.message || 'Coach photo upload failed.');
    } finally {
      setCoachPhotoUploading(false);
    }
  };

  const handleRemoveCoachPhoto = async (isEdit = false) => {
    if (isEdit && editingCoach) {
      try {
        await deleteOwnerCoachPhoto(editingCoach.id);
        setEditCoachForm((prev) => ({ ...prev, photo_url: '' }));
        setFeedback('Coach photograph removed.');
        loadInitialData();
      } catch (err) {
        setEditCoachForm((prev) => ({ ...prev, photo_url: '' }));
      }
    } else {
      setCoachForm((prev) => ({ ...prev, photo_url: '' }));
    }
  };

  const handleToggleCoachStatus = async (coach) => {
    try {
      await updateOwnerCoach(coach.id, { is_active: !coach.isActive });
      setFeedback(`Coach '${coach.name}' status set to ${!coach.isActive ? 'Active' : 'Inactive'}.`);
      loadInitialData();
    } catch (err) {
      setErrorMessage(err.message || 'Failed to update coach status.');
    }
  };

  // 5. Plans Handlers
  const handleCreatePlan = async (e) => {
    e.preventDefault();
    setErrorMessage(null);
    try {
      const perks = planForm.perksText
        .split('\n')
        .map((p) => p.trim())
        .filter(Boolean);

      await createOwnerPlan({
        id: planForm.id,
        name: planForm.name,
        category: planForm.category,
        access_scope: planForm.access_scope,
        price: parseFloat(planForm.price),
        currency: planForm.currency,
        billing_cycle: planForm.billing_cycle,
        duration_days: parseInt(planForm.duration_days, 10),
        is_featured: planForm.is_featured,
        is_active: planForm.is_active,
        description: planForm.description,
        perks,
      });
      setFeedback(`Membership plan '${planForm.name}' created successfully.`);
      setShowAddPlanModal(false);
      loadInitialData();
    } catch (err) {
      setErrorMessage(err.message || 'Failed to create membership plan.');
    }
  };

  const handleTogglePlanActive = async (plan) => {
    try {
      await updateOwnerPlan(plan.id, { is_active: !plan.isActive });
      setFeedback(`Plan '${plan.name}' is now ${!plan.isActive ? 'Published (Active)' : 'Archived (Inactive)'}.`);
      loadInitialData();
    } catch (err) {
      setErrorMessage(err.message || 'Failed to toggle plan status.');
    }
  };

  const handleDeleteOrArchivePlan = async () => {
    if (!deletingPlanItem) return;
    try {
      await archiveOwnerPlan(deletingPlanItem.id);
      setFeedback(`Plan '${deletingPlanItem.name}' removed or archived.`);
      setDeletingPlanItem(null);
      loadInitialData();
    } catch (err) {
      setErrorMessage(err.message || 'Cannot delete plan.');
    }
  };

  return (
    <div className="dashboard-overlay owner-panel-container" role="dialog" aria-modal="true" aria-label="Gym Owner Management Portal">
      {/* Top Header Bar */}
      <header className="dashboard-header-bar">
        <div className="dashboard-title-group">
          <button type="button" className="btn-back-home" onClick={onClose} title="Return to public site">
            <span>&larr; Return to Site</span>
          </button>
          <div className="vertical-bar" aria-hidden="true" />
          <h2 className="dashboard-title">
            RVFitness <span className="gold-text">Owner Management Desk</span>
          </h2>
        </div>

        <div className="dashboard-user-badge">
          <Shield size={16} className="gold-text" />
          <span>{user?.name}</span>
          <span className="badge-pill-status">Organization Admin</span>
        </div>
      </header>

      {/* Global Notifications */}
      {feedback && (
        <div className="owner-alert-banner success" role="status">
          <CheckCircle2 size={18} />
          <span>{feedback}</span>
          <button type="button" className="close-banner-btn" onClick={() => setFeedback(null)}>
            <X size={14} />
          </button>
        </div>
      )}
      {errorMessage && (
        <div className="owner-alert-banner error" role="alert">
          <AlertCircle size={18} />
          <span>{errorMessage}</span>
          <button type="button" className="close-banner-btn" onClick={() => setErrorMessage(null)}>
            <X size={14} />
          </button>
        </div>
      )}

      {/* Subnavigation Bar */}
      <nav className="admin-subnav-bar owner-nav-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'overview'}
          className={`admin-nav-tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          <LayoutDashboard size={16} />
          <span>Overview</span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'website'}
          className={`admin-nav-tab ${activeTab === 'website' ? 'active' : ''}`}
          onClick={() => setActiveTab('website')}
        >
          <Globe size={16} />
          <span>Website Editor</span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'equipment'}
          className={`admin-nav-tab ${activeTab === 'equipment' ? 'active' : ''}`}
          onClick={() => setActiveTab('equipment')}
        >
          <Dumbbell size={16} />
          <span>Equipment & Gallery</span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'coaches'}
          className={`admin-nav-tab ${activeTab === 'coaches' ? 'active' : ''}`}
          onClick={() => setActiveTab('coaches')}
        >
          <Users size={16} />
          <span>Coaches & Staff</span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'plans'}
          className={`admin-nav-tab ${activeTab === 'plans' ? 'active' : ''}`}
          onClick={() => setActiveTab('plans')}
        >
          <CreditCard size={16} />
          <span>Membership Plans</span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'enrollments'}
          className={`admin-nav-tab ${activeTab === 'enrollments' ? 'active' : ''}`}
          onClick={() => {
            setActiveTab('enrollments');
            loadEnrollments();
          }}
        >
          <ClipboardCheck size={16} />
          <span>Membership Requests</span>
          {stats.pendingEnrollmentCount > 0 && (
            <span className="subnav-pill-gold">{stats.pendingEnrollmentCount}</span>
          )}
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'attendance'}
          className={`admin-nav-tab ${activeTab === 'attendance' ? 'active' : ''}`}
          onClick={() => setActiveTab('attendance')}
        >
          <QrCode size={16} />
          <span>Members & Attendance</span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'announcements'}
          className={`admin-nav-tab ${activeTab === 'announcements' ? 'active' : ''}`}
          onClick={() => setActiveTab('announcements')}
        >
          <Megaphone size={16} />
          <span>Announcements</span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'settings'}
          className={`admin-nav-tab ${activeTab === 'settings' ? 'active' : ''}`}
          onClick={() => setActiveTab('settings')}
        >
          <Settings size={16} />
          <span>Settings</span>
        </button>
      </nav>

      {/* Main Content Area */}
      <main className="owner-main-content">
        {/* ==================================================================== */}
        {/* TAB 1: OVERVIEW */}
        {/* ==================================================================== */}
        {activeTab === 'overview' && (
          <div className="owner-tab-pane">
            <div className="owner-overview-hero">
              <div className="overview-welcome">
                <h2>Welcome, {user?.name}</h2>
                <p>
                  Gym Owner Administrative Desk. Manage website content, verify equipment inventory photographs,
                  supervise coaching staff, and configure membership plan offerings.
                </p>
              </div>

              <div className="overview-facility-badge">
                <MapPin size={16} className="gold-text" />
                <span>Primary Facility: <strong>Narsobawadi Main Campus</strong></span>
              </div>
            </div>

            {/* Quick Metrics Grid */}
            <div className="owner-metrics-grid">
              <div className="metric-card" onClick={() => { setActiveTab('enrollments'); loadEnrollments(); }}>
                <div className="metric-icon-box gold">
                  <ClipboardCheck size={24} />
                </div>
                <div className="metric-data">
                  <span className="metric-value">{stats.pendingEnrollmentCount || 0}</span>
                  <span className="metric-label">Pending Enrollments</span>
                </div>
              </div>

              <div className="metric-card" onClick={() => setActiveTab('equipment')}>
                <div className="metric-icon-box gold">
                  <Dumbbell size={24} />
                </div>
                <div className="metric-data">
                  <span className="metric-value">{stats.equipmentCount}</span>
                  <span className="metric-label">Equipment Items</span>
                </div>
              </div>

              <div className="metric-card" onClick={() => setActiveTab('coaches')}>
                <div className="metric-icon-box">
                  <Users size={24} />
                </div>
                <div className="metric-data">
                  <span className="metric-value">{stats.coachesCount}</span>
                  <span className="metric-label">Certified Coaches</span>
                </div>
              </div>

              <div className="metric-card" onClick={() => setActiveTab('plans')}>
                <div className="metric-icon-box gold">
                  <CreditCard size={24} />
                </div>
                <div className="metric-data">
                  <span className="metric-value">{stats.plansCount}</span>
                  <span className="metric-label">Membership Plans</span>
                </div>
              </div>

              <div className="metric-card" onClick={() => setActiveTab('website')}>
                <div className="metric-icon-box">
                  <Globe size={24} />
                </div>
                <div className="metric-data">
                  <span className="metric-value">Active</span>
                  <span className="metric-label">Website Status</span>
                </div>
              </div>
            </div>

            {/* Quick Operational Shortcuts */}
            <div className="owner-quick-actions">
              <h3 className="section-subtitle">Operational Shortcuts</h3>
              <div className="shortcuts-row">
                <button type="button" className="btn-shortcut" onClick={() => { setActiveTab('enrollments'); loadEnrollments(); }}>
                  <ClipboardCheck size={18} />
                  <span>Review Membership Requests</span>
                </button>
                <button type="button" className="btn-shortcut" onClick={() => setActiveTab('website')}>
                  <Globe size={18} />
                  <span>Edit Homepage Hero</span>
                </button>
                <button type="button" className="btn-shortcut" onClick={() => { setActiveTab('equipment'); setShowAddEquipmentModal(true); }}>
                  <Plus size={18} />
                  <span>Add New Equipment</span>
                </button>
                <button type="button" className="btn-shortcut" onClick={() => { setActiveTab('coaches'); setShowAddCoachModal(true); }}>
                  <Users size={18} />
                  <span>Add New Coach</span>
                </button>
                <button type="button" className="btn-shortcut" onClick={() => setActiveTab('attendance')}>
                  <QrCode size={18} />
                  <span>Open Attendance Desk</span>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ==================================================================== */}
        {/* TAB 2: WEBSITE EDITOR */}
        {/* ==================================================================== */}
        {activeTab === 'website' && (
          <div className="owner-tab-pane">
            <div className="tab-pane-header">
              <div>
                <h2>Website Content Management</h2>
                <p>Customize the public homepage headline, facility description, operating hours, and imagery without writing code.</p>
              </div>
              <button
                type="button"
                className="btn-outline-gold"
                onClick={() => setPreviewWebsite(!previewWebsite)}
              >
                <Eye size={16} />
                <span>{previewWebsite ? 'Hide Live Preview' : 'Show Live Preview'}</span>
              </button>
            </div>

            {previewWebsite && (
              <div
                className="website-preview-box"
                style={
                  heroForm.coverImageUrl
                    ? {
                        backgroundImage: `linear-gradient(rgba(8, 9, 11, 0.82), rgba(8, 9, 11, 0.88)), url(${heroForm.coverImageUrl})`,
                        backgroundSize: 'cover',
                        backgroundPosition: 'center',
                      }
                    : undefined
                }
              >
                <div className="preview-bar">Live Hero Preview (Public Website Appearance)</div>
                <div className="preview-hero-content">
                  <div className="preview-badge">{heroForm.badgeText} · {heroForm.badgeTiming}</div>
                  <h1 className="preview-title" style={{ whiteSpace: 'pre-line' }}>{heroForm.headline}</h1>
                  <p className="preview-subtitle">{heroForm.subtitle}</p>
                  <div className="preview-buttons">
                    <button type="button" className="btn-gold-small">{heroForm.ctaPrimary}</button>
                    <button type="button" className="btn-outline-small">{heroForm.ctaSecondary}</button>
                  </div>
                </div>
              </div>
            )}

            <div className="editor-grid">
              {/* Hero Section Form */}
              <form onSubmit={handleSaveHeroContent} className="owner-card-form">
                <div className="card-form-header">
                  <Globe size={20} className="gold-text" />
                  <h3>Homepage Hero Section</h3>
                </div>

                <div className="form-group">
                  <label htmlFor="hero-headline">Hero Headline (Lines separated by Enter)</label>
                  <textarea
                    id="hero-headline"
                    rows={3}
                    className="owner-input"
                    value={heroForm.headline}
                    onChange={(e) => setHeroForm({ ...heroForm, headline: e.target.value })}
                    required
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="hero-subtitle">Facility Subtitle and Description</label>
                  <textarea
                    id="hero-subtitle"
                    rows={4}
                    className="owner-input"
                    value={heroForm.subtitle}
                    onChange={(e) => setHeroForm({ ...heroForm, subtitle: e.target.value })}
                    required
                  />
                </div>

                <div className="form-row-2">
                  <div className="form-group">
                    <label htmlFor="hero-badge-text">Top Status Badge Text</label>
                    <input
                      id="hero-badge-text"
                      type="text"
                      className="owner-input"
                      value={heroForm.badgeText}
                      onChange={(e) => setHeroForm({ ...heroForm, badgeText: e.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="hero-badge-timing">Operating Hours on Badge</label>
                    <input
                      id="hero-badge-timing"
                      type="text"
                      className="owner-input"
                      value={heroForm.badgeTiming}
                      onChange={(e) => setHeroForm({ ...heroForm, badgeTiming: e.target.value })}
                    />
                  </div>
                </div>

                <div className="form-row-2">
                  <div className="form-group">
                    <label htmlFor="hero-cta-primary">Primary Button Label</label>
                    <input
                      id="hero-cta-primary"
                      type="text"
                      className="owner-input"
                      value={heroForm.ctaPrimary}
                      onChange={(e) => setHeroForm({ ...heroForm, ctaPrimary: e.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="hero-cta-secondary">Secondary Button Label</label>
                    <input
                      id="hero-cta-secondary"
                      type="text"
                      className="owner-input"
                      value={heroForm.ctaSecondary}
                      onChange={(e) => setHeroForm({ ...heroForm, ctaSecondary: e.target.value })}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label>Cover Background Photograph (Optional)</label>
                  <div className="hero-photo-management-block">
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      onChange={handleHeroCoverUpload}
                      className="file-input-hidden"
                      id="hero-cover-upload"
                    />

                    {heroForm.coverImageUrl ? (
                      <div className="hero-cover-preview-card">
                        <img
                          src={heroForm.coverImageUrl}
                          alt="Hero Cover Preview"
                          className="hero-cover-thumbnail"
                        />
                        <div className="hero-cover-meta">
                          <div className="hero-cover-status">
                            <CheckCircle2 size={14} className="gold-text" />
                            <span>Custom Cover Photo Configured</span>
                          </div>
                          <code className="hero-cover-path">{heroForm.coverImageUrl}</code>
                          <div className="hero-cover-actions">
                            <label htmlFor="hero-cover-upload" className="btn-outline-gold-sm">
                              <Upload size={14} />
                              <span>Replace Photo</span>
                            </label>
                            <button
                              type="button"
                              className="btn-danger-sm"
                              onClick={handleRemoveHeroCover}
                            >
                              <Trash2 size={14} />
                              <span>Remove Image & Restore Default Diagram</span>
                            </button>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="file-upload-row">
                        <label htmlFor="hero-cover-upload" className="btn-file-upload">
                          <Upload size={16} />
                          <span>Upload Hero Photo (Max 5MB)</span>
                        </label>
                        <span className="file-hint-note">
                          When no custom photo is uploaded, the site displays the default architectural 3D gym floor blueprint diagram.
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="form-actions-bar">
                  <button type="submit" className="btn-gold-large" disabled={savingContent}>
                    <Save size={16} />
                    <span>{savingContent ? 'Publishing...' : 'Save & Publish Hero Changes'}</span>
                  </button>
                </div>
              </form>

              {/* Facility & Contact Details Form */}
              <form onSubmit={handleSaveContactContent} className="owner-card-form">
                <div className="card-form-header">
                  <MapPin size={20} className="gold-text" />
                  <h3>Facility Contact & Details</h3>
                </div>

                <div className="form-group">
                  <label htmlFor="contact-phone">Public Contact Phone</label>
                  <input
                    id="contact-phone"
                    type="text"
                    className="owner-input"
                    value={contactForm.phone}
                    onChange={(e) => setContactForm({ ...contactForm, phone: e.target.value })}
                    required
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="contact-email">Public Inquiries Email</label>
                  <input
                    id="contact-email"
                    type="email"
                    className="owner-input"
                    value={contactForm.email}
                    onChange={(e) => setContactForm({ ...contactForm, email: e.target.value })}
                    required
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="contact-location">Physical Gym Address</label>
                  <textarea
                    id="contact-location"
                    rows={3}
                    className="owner-input"
                    value={contactForm.location}
                    onChange={(e) => setContactForm({ ...contactForm, location: e.target.value })}
                    required
                  />
                </div>

                <div className="form-actions-bar">
                  <button type="submit" className="btn-gold-large" disabled={savingContent}>
                    <Save size={16} />
                    <span>{savingContent ? 'Updating...' : 'Update Contact Information'}</span>
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* ==================================================================== */}
        {/* TAB 3: EQUIPMENT & GALLERY */}
        {/* ==================================================================== */}
        {activeTab === 'equipment' && (
          <div className="owner-tab-pane">
            <div className="tab-pane-header">
              <div>
                <h2>Equipment & Facility Photography</h2>
                <p>Manage verified equipment items, upload photographs, set cover images, and configure gym floor gallery showcases.</p>
              </div>
              <div className="header-actions-group">
                <button
                  type="button"
                  className="btn-gold-large"
                  onClick={() => setShowAddEquipmentModal(true)}
                >
                  <Plus size={16} />
                  <span>Add Equipment Item</span>
                </button>
                <button
                  type="button"
                  className="btn-outline-gold"
                  onClick={() => setShowAddGalleryModal(true)}
                >
                  <Camera size={16} />
                  <span>Add Gallery Zone</span>
                </button>
              </div>
            </div>

            {/* Equipment Items Section */}
            <section className="owner-sub-section">
              <h3 className="section-subtitle">Gym Floor Equipment Inventory ({equipmentList.length})</h3>

              {loadingEquipment ? (
                <div className="status-container">
                  <RefreshCw size={28} className="spinner-icon gold-text" />
                  <p>Loading equipment records...</p>
                </div>
              ) : equipmentList.length === 0 ? (
                <div className="empty-state-box">
                  <Dumbbell size={36} className="gold-text" />
                  <p>No custom equipment items found. The public site currently displays default verified inventory.</p>
                  <button
                    type="button"
                    className="btn-gold-small"
                    onClick={() => setShowAddEquipmentModal(true)}
                  >
                    Add First Equipment Item
                  </button>
                </div>
              ) : (
                <div className="owner-equipment-grid">
                  {equipmentList.map((item) => (
                    <div key={item.id} className="owner-equipment-card">
                      <div className="equipment-thumb-box">
                        {item.primaryImageUrl ? (
                          <img src={item.primaryImageUrl} alt={item.name} className="thumb-img" />
                        ) : (
                          <div className="no-photo-badge">
                            <Camera size={24} />
                            <span>No Photo Uploaded</span>
                          </div>
                        )}
                        <span className="category-pill">{item.category}</span>
                      </div>

                      <div className="equipment-card-details">
                        <h4>{item.name}</h4>
                        {item.brandModel && <div className="brand-text">{item.brandModel}</div>}
                        <p className="spec-text">{item.spec}</p>

                        <div className="card-actions-row">
                          <label className="btn-file-upload-small" title="Upload equipment photo">
                            <Upload size={14} />
                            <span>Upload Photo</span>
                            <input
                              type="file"
                              accept="image/jpeg,image/png,image/webp"
                              className="file-input-hidden"
                              onChange={(e) => {
                                const f = e.target.files?.[0];
                                if (f) handleEquipmentPhotoUpload(item.id, f, true);
                              }}
                            />
                          </label>

                          <button
                            type="button"
                            className="btn-action-icon delete"
                            onClick={() => setDeletingEquipmentItem(item)}
                            title="Delete equipment item"
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Gallery Zones Section */}
            <section className="owner-sub-section" style={{ marginTop: 40 }}>
              <h3 className="section-subtitle">Facility Floor Gallery Showcases ({galleryList.length})</h3>

              {loadingGallery ? (
                <div className="status-container">
                  <RefreshCw size={28} className="spinner-icon gold-text" />
                  <p>Loading gallery items...</p>
                </div>
              ) : galleryList.length === 0 ? (
                <div className="empty-state-box">
                  <Camera size={36} className="gold-text" />
                  <p>No custom gallery items configured. The public site displays default facility training zones.</p>
                  <button
                    type="button"
                    className="btn-gold-small"
                    onClick={() => setShowAddGalleryModal(true)}
                  >
                    Add First Gallery Zone
                  </button>
                </div>
              ) : (
                <div className="owner-gallery-grid">
                  {galleryList.map((gal) => (
                    <div key={gal.id} className="owner-gallery-card">
                      <div className="gallery-thumb-box">
                        {gal.imageUrl ? (
                          <img src={gal.imageUrl} alt={gal.zone} className="thumb-img" />
                        ) : (
                          <div className="no-photo-badge">Pending Photo</div>
                        )}
                      </div>
                      <div className="gallery-card-details">
                        <h4>{gal.zone}</h4>
                        <p>{gal.description}</p>
                        <span className="status-tag">{gal.status}</span>
                        <div className="card-actions-row">
                          <button
                            type="button"
                            className="btn-action-icon delete"
                            onClick={() => setDeletingGalleryItem(gal)}
                            title="Delete gallery zone"
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        )}

        {/* ==================================================================== */}
        {/* TAB 4: COACHES & STAFF */}
        {/* ==================================================================== */}
        {activeTab === 'coaches' && (
          <div className="owner-tab-pane">
            <div className="tab-pane-header">
              <div>
                <h2>Coaches & Training Staff</h2>
                <p>Add new coach credentials, edit trainer biographies, manage client capacity, and assign staff to branches.</p>
              </div>
              <button
                type="button"
                className="btn-gold-large"
                onClick={() => setShowAddCoachModal(true)}
              >
                <Plus size={16} />
                <span>Add Certified Coach</span>
              </button>
            </div>

            {loadingCoaches ? (
              <div className="status-container">
                <RefreshCw size={28} className="spinner-icon gold-text" />
                <p>Loading coaches roster...</p>
              </div>
            ) : coachesList.length === 0 ? (
              <div className="empty-state-box">
                <Users size={36} className="gold-text" />
                <p>No coaches currently created in database. The site is displaying default coaching fixtures.</p>
                <button
                  type="button"
                  className="btn-gold-small"
                  onClick={() => setShowAddCoachModal(true)}
                >
                  Create First Coach Account
                </button>
              </div>
            ) : (
              <div className="owner-coaches-table-wrapper">
                <table className="owner-data-table">
                  <thead>
                    <tr>
                      <th>Coach Name</th>
                      <th>Specialization</th>
                      <th>Branch</th>
                      <th>Contact Email</th>
                      <th>Experience</th>
                      <th>Assigned Members</th>
                      <th>Status</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {coachesList.map((c) => (
                      <tr key={c.id}>
                        <td>
                          <div className="coach-cell-profile">
                            {c.photo_url || c.photoUrl ? (
                              <img
                                src={c.photo_url || c.photoUrl}
                                alt={c.name}
                                className="coach-table-avatar"
                                onError={(e) => {
                                  e.currentTarget.style.display = 'none';
                                  if (e.currentTarget.nextSibling) {
                                    e.currentTarget.nextSibling.style.display = 'flex';
                                  }
                                }}
                              />
                            ) : null}
                            <div
                              className="coach-monogram-small"
                              style={{ display: c.photo_url || c.photoUrl ? 'none' : 'flex' }}
                            >
                              {c.name
                                ? c.name
                                    .split(' ')
                                    .map((n) => n[0])
                                    .join('')
                                    .slice(0, 2)
                                    .toUpperCase()
                                : 'CO'}
                            </div>
                            <div className="coach-name-wrap">
                              <strong>{c.name}</strong>
                              <small className="coach-branch-small">{c.branchName || c.branch_id}</small>
                            </div>
                          </div>
                        </td>
                        <td>{c.specialization}</td>
                        <td>{c.branchName}</td>
                        <td>{c.email}</td>
                        <td>{c.experienceYears} Years</td>
                        <td>
                          <span className="member-count-pill">{c.assignedMembersCount} / {c.maxClients}</span>
                        </td>
                        <td>
                          <span className={`status-badge ${c.isActive ? 'active' : 'inactive'}`}>
                            {c.isActive ? 'Active Duty' : 'Inactive'}
                          </span>
                        </td>
                        <td>
                          <div className="table-actions-inline">
                            <button
                              type="button"
                              className="btn-table-action edit"
                              onClick={() => handleOpenEditCoach(c)}
                              title="Edit coach profile, certifications, and portrait"
                            >
                              <Edit2 size={13} />
                              <span>Edit</span>
                            </button>
                            <button
                              type="button"
                              className={`btn-table-action ${c.isActive ? 'deactivate' : 'activate'}`}
                              onClick={() => handleToggleCoachStatus(c)}
                            >
                              {c.isActive ? 'Deactivate' : 'Activate'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* ==================================================================== */}
        {/* TAB 5: MEMBERSHIP PLANS */}
        {/* ==================================================================== */}
        {activeTab === 'plans' && (
          <div className="owner-tab-pane">
            <div className="tab-pane-header">
              <div>
                <h2>Membership Plan Offerings</h2>
                <p>Configure plan tiers, duration, pricing, perks, and branch scope. Safe guard rules prevent deleting plans with active member subscriptions.</p>
              </div>
              <button
                type="button"
                className="btn-gold-large"
                onClick={() => setShowAddPlanModal(true)}
              >
                <Plus size={16} />
                <span>Create New Plan</span>
              </button>
            </div>

            {loadingPlans ? (
              <div className="status-container">
                <RefreshCw size={28} className="spinner-icon gold-text" />
                <p>Loading membership plans...</p>
              </div>
            ) : (
              <div className="owner-plans-grid">
                {plansList.map((plan) => (
                  <div key={plan.id} className={`owner-plan-card ${plan.isFeatured ? 'featured' : ''}`}>
                    {plan.isFeatured && <div className="featured-ribbon">Featured Plan</div>}

                    <div className="plan-card-header">
                      <h3>{plan.name}</h3>
                      <span className="plan-price-tag">
                        {plan.currency}{plan.price} <small>/ {plan.billingCycle}</small>
                      </span>
                    </div>

                    <p className="plan-scope">Access: {plan.accessScope === 'all_branches' ? 'All Organization Branches' : 'Single Branch'}</p>
                    <p className="plan-duration">Duration: {plan.durationDays} Days</p>

                    <div className="plan-perks-box">
                      <strong>Included Benefits:</strong>
                      <ul>
                        {plan.perks.map((p, idx) => (
                          <li key={idx}>✓ {p}</li>
                        ))}
                      </ul>
                    </div>

                    <div className="plan-stats-strip">
                      <span>Active Subscribers: <strong>{plan.activeSubscribersCount}</strong></span>
                      <span>Status: <strong className={plan.isActive ? 'active-text' : 'inactive-text'}>{plan.isActive ? 'Published' : 'Archived'}</strong></span>
                    </div>

                    <div className="plan-card-actions">
                      <button
                        type="button"
                        className="btn-plan-toggle"
                        onClick={() => handleTogglePlanActive(plan)}
                      >
                        {plan.isActive ? 'Archive Plan' : 'Publish Plan'}
                      </button>

                      <button
                        type="button"
                        className="btn-plan-delete"
                        onClick={() => setDeletingPlanItem(plan)}
                        title="Delete or Archive Plan"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ==================================================================== */}
        {/* TAB: MEMBERSHIP ENROLLMENT APPROVALS & QUEUE */}
        {/* ==================================================================== */}
        {activeTab === 'enrollments' && (
          <div className="owner-tab-pane">
            <div className="tab-pane-header">
              <div>
                <h2>Membership Enrollment Requests</h2>
                <p>Review new member registrations, approve or reject applications, record offline payments, and activate RFID keycards.</p>
              </div>
              <div className="header-actions-group">
                <button
                  type="button"
                  className="btn-gold-large"
                  onClick={() => setShowAssignMembershipModal(true)}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}
                >
                  <UserPlus size={16} />
                  <span>Assign Membership</span>
                </button>
                <button
                  type="button"
                  className="btn-outline-gold"
                  onClick={() => loadEnrollments()}
                  disabled={loadingEnrollments}
                  title="Refresh enrollment list"
                >
                  <RefreshCw size={16} className={loadingEnrollments ? 'spinner-icon' : ''} />
                  <span>Refresh Queue</span>
                </button>
              </div>
            </div>

            {/* Controls Filter Bar */}
            <div className="enrollment-filter-bar">
              <div className="filter-pills-row" role="tablist" aria-label="Enrollment status filters">
                <button
                  type="button"
                  className={`filter-pill ${enrollmentStatusFilter === 'all' ? 'active' : ''}`}
                  onClick={() => {
                    setEnrollmentStatusFilter('all');
                    loadEnrollments('all');
                  }}
                >
                  All Requests
                </button>
                <button
                  type="button"
                  className={`filter-pill ${enrollmentStatusFilter === 'pending' ? 'active' : ''}`}
                  onClick={() => {
                    setEnrollmentStatusFilter('pending');
                    loadEnrollments('pending');
                  }}
                >
                  Pending Approval
                  {stats.pendingEnrollmentCount > 0 && (
                    <span className="pill-badge-gold">{stats.pendingEnrollmentCount}</span>
                  )}
                </button>
                <button
                  type="button"
                  className={`filter-pill ${enrollmentStatusFilter === 'payment_pending' ? 'active' : ''}`}
                  onClick={() => {
                    setEnrollmentStatusFilter('payment_pending');
                    loadEnrollments('payment_pending');
                  }}
                >
                  Payment Pending
                </button>
                <button
                  type="button"
                  className={`filter-pill ${enrollmentStatusFilter === 'active' ? 'active' : ''}`}
                  onClick={() => {
                    setEnrollmentStatusFilter('active');
                    loadEnrollments('active');
                  }}
                >
                  Active Memberships
                </button>
                <button
                  type="button"
                  className={`filter-pill ${enrollmentStatusFilter === 'rejected' ? 'active' : ''}`}
                  onClick={() => {
                    setEnrollmentStatusFilter('rejected');
                    loadEnrollments('rejected');
                  }}
                >
                  Rejected
                </button>
              </div>

              <div className="search-and-branch-row">
                <div className="search-input-wrap">
                  <Search size={16} className="search-icon" />
                  <input
                    type="text"
                    placeholder="Search by name, email, phone, or reference ID..."
                    value={enrollmentSearchQuery}
                    onChange={(e) => {
                      setEnrollmentSearchQuery(e.target.value);
                      loadEnrollments(enrollmentStatusFilter, e.target.value);
                    }}
                    className="owner-search-input"
                  />
                </div>

                {branches.length > 1 && (
                  <div className="branch-select-wrap">
                    <select
                      className="owner-select"
                      value={selectedBranchId}
                      onChange={(e) => setSelectedBranchId(e.target.value)}
                    >
                      <option value="all">All Branches</option>
                      {branches.map((b) => (
                        <option key={b.id} value={b.id}>{b.name}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
            </div>

            {/* Queue Table */}
            {loadingEnrollments ? (
              <div className="status-container" role="status">
                <RefreshCw className="spinner-icon gold-text" size={28} />
                <p>Loading membership enrollment queue...</p>
              </div>
            ) : enrollmentsList.length === 0 ? (
              <div className="empty-state-box">
                <ClipboardCheck size={48} className="gold-text" />
                <h3>No Enrollment Records Found</h3>
                <p>There are no enrollment requests matching your active filter criteria.</p>
              </div>
            ) : (
              <div className="table-responsive">
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th scope="col">Reference ID</th>
                      <th scope="col">Applicant</th>
                      <th scope="col">Selected Plan</th>
                      <th scope="col">Branch</th>
                      <th scope="col">Fee / Balance</th>
                      <th scope="col">Status</th>
                      <th scope="col">Submitted</th>
                      <th scope="col" className="text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {enrollmentsList.map((enr) => {
                      const isPending = enr.status === 'pending_verification' || enr.status === 'Pending Verification at Gym Desk';
                      const isPaymentPending = enr.status === 'payment_pending';
                      const isActive = enr.status === 'active';
                      const isRejected = enr.status === 'rejected';

                      return (
                        <tr key={enr.id}>
                          <td className="font-mono text-muted" title={enr.id}>
                            {enr.id.slice(0, 8)}...
                          </td>
                          <td>
                            <strong>{enr.name}</strong>
                            <div className="sub-text text-muted">{enr.phone}</div>
                            {enr.email && <div className="sub-text text-muted">{enr.email}</div>}
                          </td>
                          <td>
                            <span className="category-tag-subtle">{enr.planName}</span>
                            <div className="sub-text text-muted">{enr.durationDays || 30} Days</div>
                          </td>
                          <td>
                            <span className="badge-branch">{enr.branchId || 'Narsobawadi'}</span>
                          </td>
                          <td>
                            <strong className="gold-text">₹{enr.price?.toLocaleString('en-IN')}</strong>
                            {enr.balanceDue !== undefined && enr.balanceDue > 0 && (
                              <div className="sub-text text-danger font-bold">
                                Due: ₹{enr.balanceDue?.toLocaleString('en-IN')}
                              </div>
                            )}
                            {enr.balanceDue === 0 && (
                              <div className="sub-text text-success">Fully Paid</div>
                            )}
                          </td>
                          <td>
                            {isPending && <span className="badge-warning">Pending Review</span>}
                            {isPaymentPending && <span className="badge-gold">Payment Pending</span>}
                            {isActive && <span className="badge-success">Active</span>}
                            {isRejected && <span className="badge-danger">Rejected</span>}
                          </td>
                          <td className="sub-text text-muted">
                            {enr.createdAt ? new Date(enr.createdAt).toLocaleDateString() : 'Recent'}
                          </td>
                          <td className="text-right">
                            <div className="action-buttons-group">
                              {isPending && (
                                <>
                                  <button
                                    type="button"
                                    className="btn-approve-sm"
                                    onClick={() => handleOpenApproveModal(enr)}
                                    title="Approve membership request"
                                  >
                                    <Check size={14} />
                                    <span>Approve</span>
                                  </button>
                                  <button
                                    type="button"
                                    className="btn-reject-sm"
                                    onClick={() => handleOpenRejectModal(enr)}
                                    title="Reject membership request"
                                  >
                                    <X size={14} />
                                    <span>Reject</span>
                                  </button>
                                </>
                              )}
                              {isPaymentPending && (
                                <button
                                  type="button"
                                  className="btn-approve-sm"
                                  onClick={() => handleOpenApproveModal(enr)}
                                  title="Record front-desk payment and activate"
                                >
                                  <Check size={14} />
                                  <span>Record Payment</span>
                                </button>
                              )}
                              <button
                                type="button"
                                className="btn-detail-sm"
                                onClick={() => handleViewEnrollmentDetail(enr)}
                                title="View full application details"
                              >
                                <Eye size={14} />
                                <span>Details</span>
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* ==================================================================== */}
        {/* TAB 6: MEMBERS & ATTENDANCE DESK */}
        {/* ==================================================================== */}
        {activeTab === 'attendance' && (
          <div className="owner-tab-pane">
            <StaffAttendanceDesk
              currentUser={user}
              branchId={selectedBranchId === 'all' ? (user?.branch_id || 'narsobawadi') : selectedBranchId}
            />
          </div>
        )}

        {/* ==================================================================== */}
        {/* TAB 7: ANNOUNCEMENTS */}
        {/* ==================================================================== */}
        {activeTab === 'announcements' && (
          <div className="owner-tab-pane">
            <AdminAnnouncements
              user={user}
              branchId={selectedBranchId}
            />
          </div>
        )}

        {/* ==================================================================== */}
        {/* TAB 8: SETTINGS & AUDIT */}
        {/* ==================================================================== */}
        {activeTab === 'settings' && (
          <div className="owner-tab-pane">
            <h2>Organization & Security Settings</h2>
            <p>Enterprise authorization settings, session lifetime parameters, and data protection policies.</p>

            <div className="settings-cards-grid">
              <div className="settings-card">
                <h3>Session & Authentication Policies</h3>
                <ul>
                  <li><strong>Mechanism:</strong> Server-Side HttpOnly Session Cookie (`rvf_session`)</li>
                  <li><strong>CSRF Defense:</strong> Synchronizer Token Header (`X-CSRF-Token`) on all mutating requests</li>
                  <li><strong>Role:</strong> Organization Administrator (`org_admin` with Gym Owner designation)</li>
                  <li><strong>Scope:</strong> Multi-branch administrative authority across RVFitness network</li>
                </ul>
              </div>

              <div className="settings-card">
                <h3>Media Storage & Persistent Volume</h3>
                <ul>
                  <li><strong>Volume:</strong> `rvfitness_media_data` mounted at `/app/uploads`</li>
                  <li><strong>Allowed Image Formats:</strong> JPEG, PNG, WebP</li>
                  <li><strong>Max File Size:</strong> 5.0 MB per upload</li>
                  <li><strong>Path Security:</strong> Sanitized UUID filenames with traversal protection</li>
                </ul>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* ==================================================================== */}
      {/* MODAL: ADD EQUIPMENT */}
      {/* ==================================================================== */}
      {showAddEquipmentModal && (
        <div className="owner-modal-backdrop" role="dialog" aria-modal="true">
          <div className="owner-modal-card">
            <div className="modal-header">
              <h3>Add Verified Equipment Item</h3>
              <button type="button" className="close-btn" onClick={() => setShowAddEquipmentModal(false)}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleCreateEquipment} className="modal-form">
              <div className="form-group">
                <label htmlFor="eq-name">Equipment Name</label>
                <input
                  id="eq-name"
                  type="text"
                  className="owner-input"
                  placeholder="e.g. Olympic Barbells & Calibrated Plates"
                  value={equipmentForm.name}
                  onChange={(e) => setEquipmentForm({ ...equipmentForm, name: e.target.value })}
                  required
                />
              </div>

              <div className="form-row-2">
                <div className="form-group">
                  <label htmlFor="eq-category">Category</label>
                  <select
                    id="eq-category"
                    className="owner-input"
                    value={equipmentForm.category}
                    onChange={(e) => setEquipmentForm({ ...equipmentForm, category: e.target.value })}
                  >
                    <option value="Free Weights">Free Weights</option>
                    <option value="Powerlifting">Powerlifting</option>
                    <option value="Cables & Pulleys">Cables & Pulleys</option>
                    <option value="Cardio">Cardio</option>
                    <option value="Functional & HIIT">Functional & HIIT</option>
                    <option value="Hypertrophy Machines">Hypertrophy Machines</option>
                  </select>
                </div>
                <div className="form-group">
                  <label htmlFor="eq-brand">Brand / Model (Optional)</label>
                  <input
                    id="eq-brand"
                    type="text"
                    className="owner-input"
                    placeholder="e.g. Eleiko / Rogue"
                    value={equipmentForm.brand_model}
                    onChange={(e) => setEquipmentForm({ ...equipmentForm, brand_model: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-group">
                <label htmlFor="eq-spec">Technical Specifications & Details</label>
                <textarea
                  id="eq-spec"
                  rows={3}
                  className="owner-input"
                  placeholder="e.g. Calibrated 20kg competition steel bars and bumper plates from 2.5kg to 25kg."
                  value={equipmentForm.spec}
                  onChange={(e) => setEquipmentForm({ ...equipmentForm, spec: e.target.value })}
                  required
                />
              </div>

              <div className="modal-actions-row">
                <button type="button" className="btn-cancel" onClick={() => setShowAddEquipmentModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-gold-large">
                  Save Equipment Item
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* MODAL: ADD GALLERY ZONE */}
      {/* ==================================================================== */}
      {showAddGalleryModal && (
        <div className="owner-modal-backdrop" role="dialog" aria-modal="true">
          <div className="owner-modal-card">
            <div className="modal-header">
              <h3>Add Facility Gallery Zone</h3>
              <button type="button" className="close-btn" onClick={() => setShowAddGalleryModal(false)}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleCreateGalleryItem} className="modal-form">
              <div className="form-group">
                <label htmlFor="gal-zone">Zone Name</label>
                <input
                  id="gal-zone"
                  type="text"
                  className="owner-input"
                  placeholder="e.g. Powerlifting Cage Arena"
                  value={galleryForm.zone}
                  onChange={(e) => setGalleryForm({ ...galleryForm, zone: e.target.value })}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="gal-desc">Description</label>
                <textarea
                  id="gal-desc"
                  rows={3}
                  className="owner-input"
                  placeholder="e.g. Dual commercial 3x3 steel power cages with calibrated steel plates and deadlift jacks."
                  value={galleryForm.description}
                  onChange={(e) => setGalleryForm({ ...galleryForm, description: e.target.value })}
                  required
                />
              </div>

              <div className="form-group">
                <label>Zone Photography (Max 5MB)</label>
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) handleGalleryPhotoUpload(f);
                  }}
                  className="file-input-hidden"
                  id="gal-file-input"
                />
                <label htmlFor="gal-file-input" className="btn-file-upload">
                  <Upload size={16} />
                  <span>Choose Photo File</span>
                </label>
                {galleryForm.image_url && (
                  <span className="file-name-preview">Loaded: {galleryForm.image_url}</span>
                )}
              </div>

              <div className="modal-actions-row">
                <button type="button" className="btn-cancel" onClick={() => setShowAddGalleryModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-gold-large" disabled={!galleryForm.image_url}>
                  Save Gallery Zone
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* MODAL: ADD COACH */}
      {/* ==================================================================== */}
      {showAddCoachModal && (
        <div className="owner-modal-backdrop" role="dialog" aria-modal="true">
          <div className="owner-modal-card">
            <div className="modal-header">
              <h3>Create Coach or Trainer Account</h3>
              <button type="button" className="close-btn" onClick={() => setShowAddCoachModal(false)}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleCreateCoach} className="modal-form">
              <div className="form-row-2">
                <div className="form-group">
                  <label htmlFor="coach-name">Full Name</label>
                  <input
                    id="coach-name"
                    type="text"
                    className="owner-input"
                    placeholder="e.g. Vikram S."
                    value={coachForm.name}
                    onChange={(e) => setCoachForm({ ...coachForm, name: e.target.value })}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="coach-email">Login Email</label>
                  <input
                    id="coach-email"
                    type="email"
                    className="owner-input"
                    placeholder="coach@rvfitness.in"
                    value={coachForm.email}
                    onChange={(e) => setCoachForm({ ...coachForm, email: e.target.value })}
                    required
                  />
                </div>
              </div>

              <div className="form-row-2">
                <div className="form-group">
                  <label htmlFor="coach-password">Initial Password (Min 8 characters)</label>
                  <input
                    id="coach-password"
                    type="password"
                    className="owner-input"
                    placeholder="Min 8 characters"
                    value={coachForm.password}
                    onChange={(e) => setCoachForm({ ...coachForm, password: e.target.value })}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="coach-phone">Contact Phone</label>
                  <input
                    id="coach-phone"
                    type="text"
                    className="owner-input"
                    placeholder="+91 98220 54321"
                    value={coachForm.phone}
                    onChange={(e) => setCoachForm({ ...coachForm, phone: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-row-2">
                <div className="form-group">
                  <label htmlFor="coach-spec">Coaching Specialty / Role</label>
                  <input
                    id="coach-spec"
                    type="text"
                    className="owner-input"
                    placeholder="e.g. Strength & Powerlifting Coach"
                    value={coachForm.specialization}
                    onChange={(e) => setCoachForm({ ...coachForm, specialization: e.target.value })}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="coach-exp">Experience (Years)</label>
                  <input
                    id="coach-exp"
                    type="number"
                    min={0}
                    max={40}
                    className="owner-input"
                    value={coachForm.experience_years}
                    onChange={(e) => setCoachForm({ ...coachForm, experience_years: e.target.value })}
                    required
                  />
                </div>
              </div>

              <div className="form-group">
                <label htmlFor="coach-certs">Certifications (One per line)</label>
                <textarea
                  id="coach-certs"
                  rows={2}
                  className="owner-input"
                  value={coachForm.certificationsText}
                  onChange={(e) => setCoachForm({ ...coachForm, certificationsText: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label htmlFor="coach-bio">Coach Biography</label>
                <textarea
                  id="coach-bio"
                  rows={3}
                  className="owner-input"
                  placeholder="Specializes in progressive overload powerlifting and hypertrophy protocols."
                  value={coachForm.bio}
                  onChange={(e) => setCoachForm({ ...coachForm, bio: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label>Coach Portrait Photograph (Optional)</label>
                <div className="coach-photo-upload-container">
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    onChange={(e) => handleCoachPhotoUpload(e, false)}
                    className="file-input-hidden"
                    id="add-coach-photo-upload"
                  />
                  {coachForm.photo_url ? (
                    <div className="coach-photo-preview-box">
                      <img
                        src={coachForm.photo_url}
                        alt="Coach Preview"
                        className="coach-photo-thumbnail"
                      />
                      <div className="coach-photo-preview-meta">
                        <span className="gold-text">Portrait photograph attached</span>
                        <div className="photo-actions-row">
                          <label htmlFor="add-coach-photo-upload" className="btn-outline-gold-sm">
                            <Upload size={13} />
                            <span>Replace</span>
                          </label>
                          <button
                            type="button"
                            className="btn-danger-sm"
                            onClick={() => handleRemoveCoachPhoto(false)}
                          >
                            <Trash2 size={13} />
                            <span>Remove</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="file-upload-row">
                      <label htmlFor="add-coach-photo-upload" className="btn-file-upload">
                        <Upload size={16} />
                        <span>{coachPhotoUploading ? 'Uploading...' : 'Upload Coach Photo (Max 5MB)'}</span>
                      </label>
                      <span className="file-hint-note">
                        If omitted, the coach will be represented by an RVFitness monogram initials badge.
                      </span>
                    </div>
                  )}
                </div>
              </div>

              <div className="modal-actions-row">
                <button type="button" className="btn-cancel" onClick={() => setShowAddCoachModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-gold-large">
                  Create Coach Account
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* MODAL: EDIT COACH */}
      {/* ==================================================================== */}
      {editingCoach && (
        <div className="owner-modal-backdrop" role="dialog" aria-modal="true">
          <div className="owner-modal-card">
            <div className="modal-header">
              <h3>Edit Coach: {editingCoach.name}</h3>
              <button type="button" className="close-btn" onClick={() => setEditingCoach(null)}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleUpdateCoach} className="modal-form">
              <div className="form-row-2">
                <div className="form-group">
                  <label htmlFor="edit-coach-spec">Coaching Specialty / Role *</label>
                  <input
                    id="edit-coach-spec"
                    type="text"
                    className="owner-input"
                    value={editCoachForm.specialization}
                    onChange={(e) => setEditCoachForm({ ...editCoachForm, specialization: e.target.value })}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="edit-coach-exp">Experience (Years) *</label>
                  <input
                    id="edit-coach-exp"
                    type="number"
                    min={0}
                    max={40}
                    className="owner-input"
                    value={editCoachForm.experience_years}
                    onChange={(e) => setEditCoachForm({ ...editCoachForm, experience_years: e.target.value })}
                    required
                  />
                </div>
              </div>

              <div className="form-row-2">
                <div className="form-group">
                  <label htmlFor="edit-coach-clients">Client Capacity</label>
                  <input
                    id="edit-coach-clients"
                    type="number"
                    min={1}
                    max={100}
                    className="owner-input"
                    value={editCoachForm.max_clients}
                    onChange={(e) => setEditCoachForm({ ...editCoachForm, max_clients: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Roster Availability</label>
                  <label className="checkbox-label" style={{ marginTop: 8 }}>
                    <input
                      type="checkbox"
                      checked={editCoachForm.is_accepting_clients}
                      onChange={(e) => setEditCoachForm({ ...editCoachForm, is_accepting_clients: e.target.checked })}
                    />
                    <span>Accepting New Clients</span>
                  </label>
                </div>
              </div>

              <div className="form-group">
                <label htmlFor="edit-coach-certs">Certifications (One per line)</label>
                <textarea
                  id="edit-coach-certs"
                  rows={2}
                  className="owner-input"
                  value={editCoachForm.certificationsText}
                  onChange={(e) => setEditCoachForm({ ...editCoachForm, certificationsText: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label htmlFor="edit-coach-bio">Coach Biography</label>
                <textarea
                  id="edit-coach-bio"
                  rows={3}
                  className="owner-input"
                  value={editCoachForm.bio}
                  onChange={(e) => setEditCoachForm({ ...editCoachForm, bio: e.target.value })}
                />
              </div>

              {/* Coach Portrait Photo in Edit Modal */}
              <div className="form-group">
                <label>Coach Portrait Photograph</label>
                <div className="coach-photo-management-block">
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    onChange={(e) => handleCoachPhotoUpload(e, true)}
                    className="file-input-hidden"
                    id="edit-coach-photo-upload"
                  />

                  {editCoachForm.photo_url ? (
                    <div className="coach-photo-preview-box">
                      <img
                        src={editCoachForm.photo_url}
                        alt={editingCoach.name}
                        className="coach-photo-thumbnail"
                      />
                      <div className="coach-photo-preview-meta">
                        <span className="gold-text">Current photo attached</span>
                        <div className="photo-actions-row">
                          <label htmlFor="edit-coach-photo-upload" className="btn-outline-gold-sm">
                            <Upload size={13} />
                            <span>Replace Portrait</span>
                          </label>
                          <button
                            type="button"
                            className="btn-danger-sm"
                            onClick={() => handleRemoveCoachPhoto(true)}
                          >
                            <Trash2 size={13} />
                            <span>Remove Photo & Use Monogram</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="file-upload-row">
                      <label htmlFor="edit-coach-photo-upload" className="btn-file-upload">
                        <Upload size={16} />
                        <span>{coachPhotoUploading ? 'Uploading...' : 'Upload Coach Photo (Max 5MB)'}</span>
                      </label>
                      <span className="file-hint-note">
                        No photograph currently uploaded. Coach displays monogram avatar.
                      </span>
                    </div>
                  )}
                </div>
              </div>

              <div className="modal-actions-row">
                <button type="button" className="btn-cancel" onClick={() => setEditingCoach(null)}>
                  Cancel
                </button>
                <button type="submit" className="btn-gold-large">
                  Save Coach Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* MODAL: ADD PLAN */}
      {/* ==================================================================== */}
      {showAddPlanModal && (
        <div className="owner-modal-backdrop" role="dialog" aria-modal="true">
          <div className="owner-modal-card">
            <div className="modal-header">
              <h3>Create Membership Plan Offering</h3>
              <button type="button" className="close-btn" onClick={() => setShowAddPlanModal(false)}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleCreatePlan} className="modal-form">
              <div className="form-row-2">
                <div className="form-group">
                  <label htmlFor="plan-id">Plan Unique ID (lowercase_slug)</label>
                  <input
                    id="plan-id"
                    type="text"
                    className="owner-input"
                    placeholder="e.g. plan_six_months"
                    value={planForm.id}
                    onChange={(e) => setPlanForm({ ...planForm, id: e.target.value })}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="plan-name">Display Name</label>
                  <input
                    id="plan-name"
                    type="text"
                    className="owner-input"
                    placeholder="e.g. 6-Month Strength Protocol"
                    value={planForm.name}
                    onChange={(e) => setPlanForm({ ...planForm, name: e.target.value })}
                    required
                  />
                </div>
              </div>

              <div className="form-row-2">
                <div className="form-group">
                  <label htmlFor="plan-price">Price (₹ INR)</label>
                  <input
                    id="plan-price"
                    type="number"
                    step="0.01"
                    min="0"
                    className="owner-input"
                    value={planForm.price}
                    onChange={(e) => setPlanForm({ ...planForm, price: e.target.value })}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="plan-duration">Duration (Days)</label>
                  <input
                    id="plan-duration"
                    type="number"
                    min="1"
                    className="owner-input"
                    value={planForm.duration_days}
                    onChange={(e) => setPlanForm({ ...planForm, duration_days: e.target.value })}
                    required
                  />
                </div>
              </div>

              <div className="form-row-2">
                <div className="form-group">
                  <label htmlFor="plan-cycle">Billing Cycle Text</label>
                  <input
                    id="plan-cycle"
                    type="text"
                    className="owner-input"
                    placeholder="e.g. per 6 months"
                    value={planForm.billing_cycle}
                    onChange={(e) => setPlanForm({ ...planForm, billing_cycle: e.target.value })}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="plan-scope">Access Scope</label>
                  <select
                    id="plan-scope"
                    className="owner-input"
                    value={planForm.access_scope}
                    onChange={(e) => setPlanForm({ ...planForm, access_scope: e.target.value })}
                  >
                    <option value="single_branch">Single Branch (Narsobawadi)</option>
                    <option value="all_branches">All Branches (VIP Pass)</option>
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label htmlFor="plan-perks">Plan Benefits / Perks (One per line)</label>
                <textarea
                  id="plan-perks"
                  rows={3}
                  className="owner-input"
                  value={planForm.perksText}
                  onChange={(e) => setPlanForm({ ...planForm, perksText: e.target.value })}
                />
              </div>

              <div className="modal-actions-row">
                <button type="button" className="btn-cancel" onClick={() => setShowAddPlanModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-gold-large">
                  Publish Plan
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* CONFIRMATION MODALS */}
      {/* ==================================================================== */}
      {deletingEquipmentItem && (
        <div className="owner-modal-backdrop" role="dialog" aria-modal="true">
          <div className="owner-modal-card alert-modal">
            <div className="alert-modal-icon danger">
              <AlertCircle size={32} />
            </div>
            <h3>Confirm Equipment Removal</h3>
            <p>
              Are you sure you want to remove <strong>{deletingEquipmentItem.name}</strong> from the gym inventory?
              Unreferenced photographs will be cleaned up safely from storage.
            </p>
            <div className="modal-actions-row">
              <button type="button" className="btn-cancel" onClick={() => setDeletingEquipmentItem(null)}>
                Cancel
              </button>
              <button type="button" className="btn-danger-confirm" onClick={handleDeleteEquipment}>
                Confirm Removal
              </button>
            </div>
          </div>
        </div>
      )}

      {deletingGalleryItem && (
        <div className="owner-modal-backdrop" role="dialog" aria-modal="true">
          <div className="owner-modal-card alert-modal">
            <div className="alert-modal-icon danger">
              <AlertCircle size={32} />
            </div>
            <h3>Confirm Gallery Zone Removal</h3>
            <p>
              Are you sure you want to remove <strong>{deletingGalleryItem.zone}</strong> from the facility gallery?
            </p>
            <div className="modal-actions-row">
              <button type="button" className="btn-cancel" onClick={() => setDeletingGalleryItem(null)}>
                Cancel
              </button>
              <button type="button" className="btn-danger-confirm" onClick={handleDeleteGallery}>
                Confirm Removal
              </button>
            </div>
          </div>
        </div>
      )}

      {deletingPlanItem && (
        <div className="owner-modal-backdrop" role="dialog" aria-modal="true">
          <div className="owner-modal-card alert-modal">
            <div className="alert-modal-icon danger">
              <Archive size={32} />
            </div>
            <h3>Delete or Archive Plan</h3>
            <p>
              Plan: <strong>{deletingPlanItem.name}</strong> ({deletingPlanItem.activeSubscribersCount} active subscribers).
            </p>
            {deletingPlanItem.hasDependencies ? (
              <div className="dependency-warning-box">
                Active member subscriptions depend on this plan. To preserve financial integrity, please Archive
                the plan rather than deleting it.
              </div>
            ) : null}
            <div className="modal-actions-row">
              <button type="button" className="btn-cancel" onClick={() => setDeletingPlanItem(null)}>
                Cancel
              </button>
              <button
                type="button"
                className="btn-danger-confirm"
                onClick={handleDeleteOrArchivePlan}
              >
                {deletingPlanItem.hasDependencies ? 'Archive Plan (Safe)' : 'Delete Plan'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* MODAL: APPROVE ENROLLMENT */}
      {/* ==================================================================== */}
      {showApprovalModal && targetEnrollment && (
        <div className="owner-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="modal-approve-title">
          <div className="owner-modal-card">
            <div className="modal-header">
              <h3 id="modal-approve-title">Approve Membership Enrollment</h3>
              <button
                type="button"
                className="close-btn"
                onClick={() => {
                  setShowApprovalModal(false);
                  setTargetEnrollment(null);
                }}
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleConfirmApproval} className="modal-form">
              {/* Applicant Summary */}
              <div className="applicant-summary-box">
                <div className="summary-row">
                  <span>Applicant Name:</span>
                  <strong>{targetEnrollment.name}</strong>
                </div>
                <div className="summary-row">
                  <span>Contact Phone / Email:</span>
                  <span>{targetEnrollment.phone} {targetEnrollment.email ? `(${targetEnrollment.email})` : ''}</span>
                </div>
                <div className="summary-row">
                  <span>Selected Plan:</span>
                  <strong className="gold-text">{targetEnrollment.planName} ({targetEnrollment.durationDays || 30} Days)</strong>
                </div>
                <div className="summary-row">
                  <span>Facility Branch:</span>
                  <span>{targetEnrollment.branchId || 'Narsobawadi'}</span>
                </div>
                <div className="summary-row">
                  <span>Plan Rate / Amount Due:</span>
                  <strong className="gold-text">
                    ₹{(targetEnrollment.balanceDue !== undefined ? targetEnrollment.balanceDue : targetEnrollment.price)?.toLocaleString('en-IN')}
                  </strong>
                </div>
                {targetEnrollment.invoiceNumber && (
                  <div className="summary-row">
                    <span>Invoice Reference:</span>
                    <span className="font-mono">{targetEnrollment.invoiceNumber}</span>
                  </div>
                )}
              </div>

              {/* Front-Desk Payment Option */}
              <div className="payment-toggle-card">
                <label className="checkbox-custom-label">
                  <input
                    type="checkbox"
                    checked={approvalForm.record_payment}
                    onChange={(e) => setApprovalForm({ ...approvalForm, record_payment: e.target.checked })}
                  />
                  <div>
                    <strong>Record Front-Desk Payment Now</strong>
                    <p className="sub-text">Check this box if the member is physically paying at the reception desk now.</p>
                  </div>
                </label>

                {approvalForm.record_payment && (
                  <div className="desk-payment-fields mt-3">
                    <div className="form-group">
                      <label htmlFor="appr-payment-method">Payment Mode</label>
                      <select
                        id="appr-payment-method"
                        className="owner-input"
                        value={approvalForm.payment_method}
                        onChange={(e) => setApprovalForm({ ...approvalForm, payment_method: e.target.value })}
                      >
                        <option value="cash">Cash (Desk Currency)</option>
                        <option value="upi_qr">UPI / QR Code Transfer</option>
                        <option value="card_pos">Card POS Terminal</option>
                      </select>
                    </div>

                    <div className="form-group">
                      <label htmlFor="appr-ref-num">Transaction / Receipt Reference (Optional)</label>
                      <input
                        id="appr-ref-num"
                        type="text"
                        className="owner-input"
                        placeholder="e.g. UPI-9876543210 or POS Slip #"
                        value={approvalForm.reference_number}
                        onChange={(e) => setApprovalForm({ ...approvalForm, reference_number: e.target.value })}
                      />
                    </div>

                    <div className="form-group">
                      <label htmlFor="appr-notes">Staff Notes (Optional)</label>
                      <input
                        id="appr-notes"
                        type="text"
                        className="owner-input"
                        placeholder="e.g. Paid in full at desk, RFID keycard issued"
                        value={approvalForm.notes}
                        onChange={(e) => setApprovalForm({ ...approvalForm, notes: e.target.value })}
                      />
                    </div>

                    <div className="info-callout success">
                      <CheckCircle2 size={16} />
                      <span>Recording full payment will immediately activate the membership and issue an active RFID keycard valid for {targetEnrollment.durationDays || 30} days from today.</span>
                    </div>
                  </div>
                )}

                {!approvalForm.record_payment && (
                  <div className="info-callout notice mt-3">
                    <Clock size={16} />
                    <span>Approving without payment moves this enrollment to <strong>Payment Pending</strong>. The member will be instructed to visit the desk to pay before the membership and keycard activate.</span>
                  </div>
                )}
              </div>

              <div className="modal-actions-row">
                <button
                  type="button"
                  className="btn-cancel"
                  onClick={() => {
                    setShowApprovalModal(false);
                    setTargetEnrollment(null);
                  }}
                  disabled={submittingApproval}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-gold-large"
                  disabled={submittingApproval}
                >
                  {submittingApproval ? 'Processing Approval...' : approvalForm.record_payment ? 'Record Payment & Activate' : 'Approve Application'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* MODAL: REJECT ENROLLMENT */}
      {/* ==================================================================== */}
      {showRejectionModal && targetEnrollment && (
        <div className="owner-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="modal-reject-title">
          <div className="owner-modal-card alert-modal">
            <div className="alert-modal-icon danger">
              <AlertCircle size={32} />
            </div>
            <h3 id="modal-reject-title">Reject Membership Application</h3>
            <p>
              Are you sure you want to reject the application for <strong>{targetEnrollment.name}</strong> ({targetEnrollment.planName})?
            </p>
            <div className="rejection-note-callout">
              <p>This action voids any pending unpaid invoice and records an audit log. The enrollment history is preserved.</p>
            </div>

            <form onSubmit={handleConfirmRejection} className="modal-form text-left">
              <div className="form-group">
                <label htmlFor="reject-reason">
                  Reason for Rejection <span className="required-star">*</span>
                </label>
                <textarea
                  id="reject-reason"
                  rows={3}
                  className="owner-input"
                  placeholder="e.g. Member chose not to proceed; Applicant requested plan change; Verification details incomplete."
                  value={rejectionForm.reason}
                  onChange={(e) => setRejectionForm({ reason: e.target.value })}
                  required
                />
              </div>

              <div className="modal-actions-row">
                <button
                  type="button"
                  className="btn-cancel"
                  onClick={() => {
                    setShowRejectionModal(false);
                    setTargetEnrollment(null);
                  }}
                  disabled={submittingRejection}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-danger-confirm"
                  disabled={submittingRejection || !rejectionForm.reason.trim()}
                >
                  {submittingRejection ? 'Rejecting Application...' : 'Confirm Rejection'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* MODAL: ENROLLMENT DETAIL */}
      {/* ==================================================================== */}
      {selectedEnrollmentForDetail && (
        <div className="owner-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="modal-detail-title">
          <div className="owner-modal-card">
            <div className="modal-header">
              <h3 id="modal-detail-title">Application Record Details</h3>
              <button
                type="button"
                className="close-btn"
                onClick={() => setSelectedEnrollmentForDetail(null)}
              >
                <X size={18} />
              </button>
            </div>

            <div className="modal-body detail-modal-body">
              <div className="detail-meta-header">
                <div>
                  <span className="stat-label">Reference ID</span>
                  <div className="font-mono text-muted">{selectedEnrollmentForDetail.id}</div>
                </div>
                <div>
                  <span className="stat-label">Current Status</span>
                  <div>
                    {selectedEnrollmentForDetail.status === 'pending_verification' || selectedEnrollmentForDetail.status === 'Pending Verification at Gym Desk' ? (
                      <span className="badge-warning">Pending Review</span>
                    ) : selectedEnrollmentForDetail.status === 'payment_pending' ? (
                      <span className="badge-gold">Payment Pending</span>
                    ) : selectedEnrollmentForDetail.status === 'active' ? (
                      <span className="badge-success">Active</span>
                    ) : (
                      <span className="badge-danger">Rejected</span>
                    )}
                  </div>
                </div>
              </div>

              <div className="detail-sections-grid mt-3">
                <div className="detail-section">
                  <h4>Member Information</h4>
                  <div className="detail-row">
                    <span>Full Name:</span>
                    <strong>{selectedEnrollmentForDetail.name}</strong>
                  </div>
                  <div className="detail-row">
                    <span>Phone:</span>
                    <span>{selectedEnrollmentForDetail.phone}</span>
                  </div>
                  <div className="detail-row">
                    <span>Email:</span>
                    <span>{selectedEnrollmentForDetail.email || 'N/A'}</span>
                  </div>
                  <div className="detail-row">
                    <span>User Account ID:</span>
                    <span className="font-mono text-muted">{selectedEnrollmentForDetail.userId || 'Linked on approval'}</span>
                  </div>
                </div>

                <div className="detail-section">
                  <h4>Plan & Facility Details</h4>
                  <div className="detail-row">
                    <span>Plan Name:</span>
                    <strong className="gold-text">{selectedEnrollmentForDetail.planName}</strong>
                  </div>
                  <div className="detail-row">
                    <span>Facility Branch:</span>
                    <span>{selectedEnrollmentForDetail.branchId || 'Narsobawadi'}</span>
                  </div>
                  <div className="detail-row">
                    <span>Duration:</span>
                    <span>{selectedEnrollmentForDetail.durationDays || 30} Days</span>
                  </div>
                  <div className="detail-row">
                    <span>Price:</span>
                    <strong className="gold-text">₹{selectedEnrollmentForDetail.price?.toLocaleString('en-IN')}</strong>
                  </div>
                </div>
              </div>

              <div className="detail-section full-width mt-3">
                <h4>Billing & Audit Breakdown</h4>
                <div className="detail-row">
                  <span>Invoice Number:</span>
                  <span className="font-mono">{selectedEnrollmentForDetail.invoiceNumber || 'N/A'}</span>
                </div>
                <div className="detail-row">
                  <span>Balance Due:</span>
                  <strong className={selectedEnrollmentForDetail.balanceDue > 0 ? 'text-danger' : 'text-success'}>
                    ₹{(selectedEnrollmentForDetail.balanceDue !== undefined ? selectedEnrollmentForDetail.balanceDue : selectedEnrollmentForDetail.price)?.toLocaleString('en-IN')}
                  </strong>
                </div>
                <div className="detail-row">
                  <span>Submitted At:</span>
                  <span>{selectedEnrollmentForDetail.createdAt ? new Date(selectedEnrollmentForDetail.createdAt).toLocaleString() : 'N/A'}</span>
                </div>
                {selectedEnrollmentForDetail.approvedAt && (
                  <div className="detail-row">
                    <span>Approved At:</span>
                    <span>{new Date(selectedEnrollmentForDetail.approvedAt).toLocaleString()}</span>
                  </div>
                )}
                {selectedEnrollmentForDetail.approvedBy && (
                  <div className="detail-row">
                    <span>Approved By:</span>
                    <span className="font-mono text-muted">{selectedEnrollmentForDetail.approvedBy}</span>
                  </div>
                )}
                {selectedEnrollmentForDetail.rejectionReason && (
                  <div className="detail-row rejection-box">
                    <span>Rejection Reason:</span>
                    <strong className="text-danger">{selectedEnrollmentForDetail.rejectionReason}</strong>
                  </div>
                )}
              </div>

              <div className="modal-actions-row mt-4">
                <button
                  type="button"
                  className="btn-gold-solid"
                  onClick={() => setSelectedEnrollmentForDetail(null)}
                >
                  Close Details
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* MODAL: DIRECT MEMBERSHIP ASSIGNMENT */}
      {/* ==================================================================== */}
      <AssignMembershipModal
        isOpen={showAssignMembershipModal}
        onClose={() => setShowAssignMembershipModal(false)}
        initialBranchId={selectedBranchId}
        onSuccess={() => {
          setFeedback('Membership successfully assigned to member.');
          loadEnrollments();
          loadInitialData();
        }}
      />
    </div>
  );
}
