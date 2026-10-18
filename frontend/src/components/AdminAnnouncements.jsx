import { useState, useEffect, useRef } from 'react';
import {
  Megaphone,
  Plus,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  Eye,
  Edit2,
  Trash2,
  Archive,
  Upload,
  Calendar,
  Clock,
  Building,
  X,
  Send,
  FileText
} from 'lucide-react';
import {
  fetchAdminAnnouncements,
  createAnnouncement,
  updateAnnouncement,
  publishAnnouncement,
  unpublishAnnouncement,
  archiveAnnouncement,
  deleteAnnouncement,
  uploadAnnouncementImage,
  fetchBranches,
  previewAnnouncement
} from '../api';

const CATEGORIES = [
  { value: 'general', label: 'General Announcement' },
  { value: 'facility', label: 'Facility Notice' },
  { value: 'class_schedule', label: 'Class & Schedule' },
  { value: 'competition', label: 'Competition & Meet' },
  { value: 'maintenance', label: 'Equipment & Maintenance' },
  { value: 'policy', label: 'Safety & Policy' },
  { value: 'emergency', label: 'Urgent / Alert' },
];

const PRIORITIES = [
  { value: 'low', label: 'Low Priority' },
  { value: 'normal', label: 'Normal Priority' },
  { value: 'high', label: 'High Priority' },
  { value: 'urgent', label: 'Urgent Priority' },
];

const AUDIENCES = [
  { value: 'public', label: 'Public (Everyone)' },
  { value: 'members_only', label: 'Members Only' },
  { value: 'staff_only', label: 'Staff & Coaches Only' },
];

export default function AdminAnnouncements({ currentUser }) {
  const [announcements, setAnnouncements] = useState([]);
  const [branches, setBranches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [branchFilter, setBranchFilter] = useState('');

  // Modals
  const [showEditor, setShowEditor] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [previewItem, setPreviewItem] = useState(null);

  // Form State
  const [formData, setFormData] = useState({
    title: '',
    body: '',
    category: 'general',
    priority: 'normal',
    audience: 'public',
    branchId: currentUser?.branch_id || 'narsobawadi',
    isOrgWide: false,
    pinned: false,
    imageUrl: '',
    publishAt: '',
    expiresAt: '',
  });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState(null);
  const [uploadingImage, setUploadingImage] = useState(false);
  const fileInputRef = useRef(null);

  const isOrgAdmin = ['org_admin', 'admin'].includes(currentUser?.role);
  const isBranchManager = ['branch_manager', 'manager'].includes(currentUser?.role);
  const canPublish = isOrgAdmin || isBranchManager;

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [annRes, branchRes] = await Promise.all([
        fetchAdminAnnouncements(
          statusFilter || null,
          isOrgAdmin ? (branchFilter || null) : currentUser?.branch_id,
          categoryFilter || null
        ),
        fetchBranches().catch(() => ({ branches: [] })),
      ]);
      setAnnouncements(annRes.announcements || []);
      setBranches(branchRes.branches || []);
    } catch (err) {
      setError(err.message || 'Unable to load administrative announcements.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [statusFilter, categoryFilter, branchFilter]);

  const openCreateModal = () => {
    setEditingItem(null);
    setFormError(null);
    setFormData({
      title: '',
      body: '',
      category: 'general',
      priority: 'normal',
      audience: 'public',
      branchId: isOrgAdmin ? (branchFilter || 'narsobawadi') : currentUser?.branch_id,
      isOrgWide: false,
      pinned: false,
      imageUrl: '',
      publishAt: '',
      expiresAt: '',
    });
    setShowEditor(true);
  };

  const openEditModal = (item) => {
    setEditingItem(item);
    setFormError(null);
    setFormData({
      title: item.title,
      body: item.body,
      category: item.category,
      priority: item.priority,
      audience: item.audience,
      branchId: item.branchId || currentUser?.branch_id || 'narsobawadi',
      isOrgWide: Boolean(item.isOrgWide),
      pinned: Boolean(item.pinned),
      imageUrl: item.imageUrl || '',
      publishAt: item.publishedAt ? item.publishedAt.slice(0, 16) : '',
      expiresAt: item.expiresAt ? item.expiresAt.slice(0, 16) : '',
    });
    setShowEditor(true);
  };

  const handleImageUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadingImage(true);
    setFormError(null);
    try {
      const res = await uploadAnnouncementImage(file);
      setFormData((prev) => ({ ...prev, imageUrl: res.imageUrl }));
    } catch (err) {
      setFormError(err.message || 'Image upload failed.');
    } finally {
      setUploadingImage(false);
    }
  };

  const handleSave = async (publishNow = false) => {
    setSaving(true);
    setFormError(null);
    setSuccessMsg(null);

    try {
      const payload = {
        title: formData.title.trim(),
        body: formData.body.trim(),
        category: formData.category,
        priority: formData.priority,
        audience: formData.audience,
        branch_id: formData.isOrgWide ? null : formData.branchId,
        is_org_wide: Boolean(formData.isOrgWide),
        pinned: Boolean(formData.pinned),
        image_url: formData.imageUrl.trim() || null,
        publish_at: formData.publishAt ? new Date(formData.publishAt).toISOString() : null,
        expires_at: formData.expiresAt ? new Date(formData.expiresAt).toISOString() : null,
      };

      if (publishNow) {
        payload.status = 'published';
        if (!payload.publish_at) {
          payload.publish_at = new Date().toISOString();
        }
      }

      if (editingItem) {
        await updateAnnouncement(editingItem.id, payload);
        if (publishNow && editingItem.status !== 'published') {
          await publishAnnouncement(editingItem.id, {
            publish_at: payload.publish_at,
            expires_at: payload.expires_at,
          });
        }
        setSuccessMsg(`Announcement '${payload.title}' updated successfully.`);
      } else {
        await createAnnouncement(payload);
        setSuccessMsg(`Announcement '${payload.title}' created successfully.`);
      }

      setShowEditor(false);
      loadData();
    } catch (err) {
      setFormError(err.message || 'Error saving announcement.');
    } finally {
      setSaving(false);
    }
  };

  const handleTogglePublish = async (item) => {
    setError(null);
    setSuccessMsg(null);
    try {
      if (item.status === 'published') {
        await unpublishAnnouncement(item.id);
        setSuccessMsg(`Announcement '${item.title}' unpublished (saved as draft).`);
      } else {
        await publishAnnouncement(item.id);
        setSuccessMsg(`Announcement '${item.title}' published successfully.`);
      }
      loadData();
    } catch (err) {
      setError(err.message || 'Action failed.');
    }
  };

  const handleArchive = async (item) => {
    setError(null);
    setSuccessMsg(null);
    try {
      await archiveAnnouncement(item.id);
      setSuccessMsg(`Announcement '${item.title}' moved to archive.`);
      loadData();
    } catch (err) {
      setError(err.message || 'Archiving failed.');
    }
  };

  const handleDelete = async (item) => {
    if (!window.confirm(`Are you sure you want to delete announcement "${item.title}"?`)) {
      return;
    }
    setError(null);
    setSuccessMsg(null);
    try {
      await deleteAnnouncement(item.id);
      setSuccessMsg(`Announcement deleted successfully.`);
      loadData();
    } catch (err) {
      setError(err.message || 'Deletion failed.');
    }
  };

  const handleOpenPreview = async (item) => {
    try {
      const res = await previewAnnouncement(item.id);
      setPreviewItem(res.announcement);
    } catch {
      // Fallback to local item
      setPreviewItem(item);
    }
  };

  return (
    <div className="admin-announcements-container" aria-label="Announcements & Operations Console">
      {/* Action Header */}
      <div className="announcements-top-bar">
        <div>
          <h3 className="section-subtitle gold-text">Operational Announcements & Facility Broadcasts</h3>
          <p className="admin-helper-text">
            Publish event alerts, class alterations, maintenance notices, and emergency communications.
          </p>
        </div>

        {canPublish && (
          <button
            type="button"
            className="btn-gold-solid"
            onClick={openCreateModal}
          >
            <Plus size={16} />
            <span>Create Notice</span>
          </button>
        )}
      </div>

      {/* Global Alerts */}
      {successMsg && (
        <div className="feedback-alert success" role="status">
          <CheckCircle2 size={18} />
          <span>{successMsg}</span>
        </div>
      )}

      {error && (
        <div className="error-banner" role="alert">
          <AlertCircle size={20} className="danger-text" />
          <span>{error}</span>
        </div>
      )}

      {/* Filters Bar */}
      <div className="announcements-filter-bar">
        <div className="filter-group">
          <label htmlFor="filter-status" className="filter-label">Status</label>
          <select
            id="filter-status"
            className="filter-select"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All Statuses</option>
            <option value="published">Published</option>
            <option value="draft">Draft</option>
            <option value="archived">Archived</option>
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="filter-cat" className="filter-label">Category</label>
          <select
            id="filter-cat"
            className="filter-select"
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
          >
            <option value="">All Categories</option>
            {CATEGORIES.map((cat) => (
              <option key={cat.value} value={cat.value}>{cat.label}</option>
            ))}
          </select>
        </div>

        {isOrgAdmin && (
          <div className="filter-group">
            <label htmlFor="filter-branch" className="filter-label">Branch Scope</label>
            <select
              id="filter-branch"
              className="filter-select"
              value={branchFilter}
              onChange={(e) => setBranchFilter(e.target.value)}
            >
              <option value="">All Branches & Org-Wide</option>
              {branches.map((b) => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </select>
          </div>
        )}

        <button
          type="button"
          className="btn-gold-outline refresh-btn"
          onClick={loadData}
          disabled={loading}
          aria-label="Refresh announcements"
        >
          <RefreshCw size={14} className={loading ? 'spinner-icon' : ''} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Table Content */}
      {loading ? (
        <div className="status-container" role="status">
          <RefreshCw className="spinner-icon gold-text" size={32} />
          <p>Retrieving operational announcement records...</p>
        </div>
      ) : announcements.length === 0 ? (
        <div className="empty-state-card">
          <Megaphone size={36} className="gold-text muted-opacity" />
          <p>No operational notices found matching the active filters.</p>
        </div>
      ) : (
        <div className="admin-table-container">
          <table className="admin-table" aria-label="Announcements Table">
            <thead>
              <tr>
                <th>Title & Category</th>
                <th>Audience</th>
                <th>Branch Target</th>
                <th>Status</th>
                <th>Schedule Window</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {announcements.map((item) => (
                <tr key={item.id} className={item.pinned ? 'row-pinned' : ''}>
                  <td>
                    <div className="title-cell-group">
                      <span className="announcement-row-title">{item.title}</span>
                      <div className="cell-badges-row">
                        <span className="badge-cat-pill">{item.category}</span>
                        {item.priority === 'urgent' && (
                          <span className="badge-priority-urgent">Urgent</span>
                        )}
                        {item.priority === 'high' && (
                          <span className="badge-priority-high">High</span>
                        )}
                        {item.pinned && (
                          <span className="badge-pinned">Pinned</span>
                        )}
                      </div>
                    </div>
                  </td>
                  <td>
                    <span className="audience-pill">{item.audience.replace('_', ' ')}</span>
                  </td>
                  <td>
                    <div className="branch-scope-cell">
                      <Building size={14} className="gold-text" />
                      <span>{item.isOrgWide ? 'All Branches (Org)' : (item.branchName || item.branchId)}</span>
                    </div>
                  </td>
                  <td>
                    <span className={`status-pill-indicator status-${item.status}`}>
                      {item.status}
                    </span>
                  </td>
                  <td>
                    <div className="timing-cell">
                      {item.publishedAt && (
                        <span className="timing-item" title="Published At">
                          <Calendar size={12} />
                          {new Date(item.publishedAt).toLocaleDateString()}
                        </span>
                      )}
                      {item.expiresAt && (
                        <span className="timing-item expiry-warn" title="Expires At">
                          <Clock size={12} />
                          Until {new Date(item.expiresAt).toLocaleDateString()}
                        </span>
                      )}
                      {!item.publishedAt && !item.expiresAt && (
                        <span className="timing-none">Unscheduled</span>
                      )}
                    </div>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <div className="table-actions-group">
                      <button
                        type="button"
                        className="btn-action-icon"
                        onClick={() => handleOpenPreview(item)}
                        title="Preview Notice"
                      >
                        <Eye size={16} />
                      </button>

                      {canPublish && (
                        <>
                          <button
                            type="button"
                            className="btn-action-icon"
                            onClick={() => openEditModal(item)}
                            title="Edit Notice"
                          >
                            <Edit2 size={16} />
                          </button>

                          <button
                            type="button"
                            className="btn-action-icon"
                            onClick={() => handleTogglePublish(item)}
                            title={item.status === 'published' ? 'Unpublish to Draft' : 'Publish Immediately'}
                          >
                            <Send size={16} className={item.status === 'published' ? 'gold-text' : ''} />
                          </button>

                          {item.status !== 'archived' && (
                            <button
                              type="button"
                              className="btn-action-icon"
                              onClick={() => handleArchive(item)}
                              title="Archive Notice"
                            >
                              <Archive size={16} />
                            </button>
                          )}

                          <button
                            type="button"
                            className="btn-action-icon danger-icon"
                            onClick={() => handleDelete(item)}
                            title="Delete Notice"
                          >
                            <Trash2 size={16} />
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Editor Modal */}
      {showEditor && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Announcement Editor">
          <div className="modal-dialog-content">
            <div className="modal-header-bar">
              <div className="modal-title-row">
                <Megaphone size={20} className="gold-text" />
                <h4>{editingItem ? 'Edit Operational Notice' : 'Draft New Announcement'}</h4>
              </div>
              <button
                type="button"
                className="btn-close-modal"
                onClick={() => setShowEditor(false)}
                aria-label="Close editor"
              >
                <X size={18} />
              </button>
            </div>

            {formError && (
              <div className="error-banner" role="alert">
                <AlertCircle size={18} className="danger-text" />
                <span>{formError}</span>
              </div>
            )}

            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSave(false);
              }}
              className="announcement-form"
            >
              {/* Title */}
              <div className="form-group">
                <label htmlFor="notice-title" className="form-label">
                  Headline / Title <span className="gold-text">*</span>
                </label>
                <input
                  id="notice-title"
                  type="text"
                  className="form-input"
                  required
                  minLength={3}
                  maxLength={255}
                  value={formData.title}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  placeholder="e.g. Annual Winter Strength Invitational Registration"
                />
              </div>

              {/* Category, Priority & Audience */}
              <div className="form-row-3">
                <div className="form-group">
                  <label htmlFor="notice-cat" className="form-label">Category</label>
                  <select
                    id="notice-cat"
                    className="form-select"
                    value={formData.category}
                    onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                  >
                    {CATEGORIES.map((c) => (
                      <option key={c.value} value={c.value}>{c.label}</option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label htmlFor="notice-prio" className="form-label">Priority</label>
                  <select
                    id="notice-prio"
                    className="form-select"
                    value={formData.priority}
                    onChange={(e) => setFormData({ ...formData, priority: e.target.value })}
                  >
                    {PRIORITIES.map((p) => (
                      <option key={p.value} value={p.value}>{p.label}</option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label htmlFor="notice-aud" className="form-label">Audience Visibility</label>
                  <select
                    id="notice-aud"
                    className="form-select"
                    value={formData.audience}
                    onChange={(e) => setFormData({ ...formData, audience: e.target.value })}
                  >
                    {AUDIENCES.map((a) => (
                      <option key={a.value} value={a.value}>{a.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Branch & Scope */}
              <div className="form-row-2">
                <div className="form-group">
                  <label htmlFor="notice-branch" className="form-label">Target Facility</label>
                  <select
                    id="notice-branch"
                    className="form-select"
                    disabled={formData.isOrgWide || (!isOrgAdmin && !isBranchManager)}
                    value={formData.branchId}
                    onChange={(e) => setFormData({ ...formData, branchId: e.target.value })}
                  >
                    {branches.map((b) => (
                      <option key={b.id} value={b.id}>{b.name}</option>
                    ))}
                  </select>
                </div>

                <div className="form-group checkbox-align">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      disabled={!isOrgAdmin}
                      checked={formData.isOrgWide}
                      onChange={(e) => setFormData({ ...formData, isOrgWide: e.target.checked })}
                    />
                    <span>Organization-Wide (All Branches)</span>
                  </label>
                  <label className="checkbox-label" style={{ marginLeft: '1rem' }}>
                    <input
                      type="checkbox"
                      checked={formData.pinned}
                      onChange={(e) => setFormData({ ...formData, pinned: e.target.checked })}
                    />
                    <span>Pin to Top of Feed</span>
                  </label>
                </div>
              </div>

              {/* Scheduling Dates */}
              <div className="form-row-2">
                <div className="form-group">
                  <label htmlFor="notice-pub-at" className="form-label">Scheduled Publish Time (Optional)</label>
                  <input
                    id="notice-pub-at"
                    type="datetime-local"
                    className="form-input"
                    value={formData.publishAt}
                    onChange={(e) => setFormData({ ...formData, publishAt: e.target.value })}
                  />
                  <span className="field-hint">Leave blank to publish immediately on command.</span>
                </div>

                <div className="form-group">
                  <label htmlFor="notice-exp-at" className="form-label">Expiration Time (Optional)</label>
                  <input
                    id="notice-exp-at"
                    type="datetime-local"
                    className="form-input"
                    value={formData.expiresAt}
                    onChange={(e) => setFormData({ ...formData, expiresAt: e.target.value })}
                  />
                  <span className="field-hint">Notice automatically ceases to display after this time.</span>
                </div>
              </div>

              {/* Image Upload or URL */}
              <div className="form-group">
                <label className="form-label">Optional Banner Image</label>
                <div className="image-upload-row">
                  <input
                    type="text"
                    className="form-input"
                    placeholder="https://... or /uploads/announcements/..."
                    value={formData.imageUrl}
                    onChange={(e) => setFormData({ ...formData, imageUrl: e.target.value })}
                  />
                  <input
                    type="file"
                    ref={fileInputRef}
                    style={{ display: 'none' }}
                    accept="image/jpeg,image/png,image/webp"
                    onChange={handleImageUpload}
                  />
                  <button
                    type="button"
                    className="btn-gold-outline"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploadingImage}
                  >
                    <Upload size={14} className={uploadingImage ? 'spinner-icon' : ''} />
                    <span>{uploadingImage ? 'Uploading...' : 'Upload Image'}</span>
                  </button>
                </div>
                {formData.imageUrl && (
                  <div className="image-preview-box">
                    <img src={formData.imageUrl} alt="Banner preview" className="preview-img" />
                    <button
                      type="button"
                      className="btn-remove-img"
                      onClick={() => setFormData({ ...formData, imageUrl: '' })}
                    >
                      <X size={14} /> Remove
                    </button>
                  </div>
                )}
              </div>

              {/* Body */}
              <div className="form-group">
                <label htmlFor="notice-body" className="form-label">
                  Content Body <span className="gold-text">*</span>
                </label>
                <textarea
                  id="notice-body"
                  className="form-textarea"
                  rows={6}
                  required
                  minLength={5}
                  maxLength={10000}
                  value={formData.body}
                  onChange={(e) => setFormData({ ...formData, body: e.target.value })}
                  placeholder="Provide detailed instructions, rules, operational schedules, or registration instructions..."
                />
              </div>

              {/* Actions Footer */}
              <div className="modal-actions-footer">
                <button
                  type="button"
                  className="btn-gold-outline"
                  onClick={() => setShowEditor(false)}
                  disabled={saving}
                >
                  Cancel
                </button>

                <div className="action-buttons-right">
                  <button
                    type="submit"
                    className="btn-gold-outline"
                    disabled={saving}
                  >
                    <FileText size={16} />
                    <span>{saving ? 'Saving...' : 'Save Draft'}</span>
                  </button>

                  <button
                    type="button"
                    className="btn-gold-solid"
                    onClick={() => handleSave(true)}
                    disabled={saving}
                  >
                    <Send size={16} />
                    <span>{saving ? 'Publishing...' : 'Publish Now'}</span>
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Preview Modal */}
      {previewItem && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Notice Preview">
          <div className="modal-dialog-content preview-content">
            <div className="modal-header-bar">
              <div className="modal-title-row">
                <Eye size={20} className="gold-text" />
                <h4>Notice Preview</h4>
              </div>
              <button
                type="button"
                className="btn-close-modal"
                onClick={() => setPreviewItem(null)}
                aria-label="Close preview"
              >
                <X size={18} />
              </button>
            </div>

            <article className="preview-article">
              {previewItem.imageUrl && (
                <div className="preview-banner-container">
                  <img src={previewItem.imageUrl} alt="" className="preview-banner-img" />
                </div>
              )}

              <div className="preview-meta-row">
                <span className="badge-cat-pill">{previewItem.category}</span>
                <span className="audience-pill">{previewItem.audience.replace('_', ' ')}</span>
                <span className="branch-scope-badge">
                  <Building size={14} className="gold-text inline-icon" />
                  {previewItem.isOrgWide ? 'All Branches' : (previewItem.branchName || previewItem.branchId)}
                </span>
                <span className={`status-pill-indicator status-${previewItem.status}`}>
                  {previewItem.status}
                </span>
              </div>

              <h2 className="preview-headline">{previewItem.title}</h2>

              <div className="preview-body-text">
                {previewItem.body.split('\n').map((para, idx) => (
                  <p key={idx}>{para}</p>
                ))}
              </div>

              <div className="preview-footer-meta">
                {previewItem.authorName && (
                  <span>Posted by: {previewItem.authorName}</span>
                )}
                {previewItem.publishedAt && (
                  <span>Published: {new Date(previewItem.publishedAt).toLocaleString()}</span>
                )}
                {previewItem.expiresAt && (
                  <span className="expiry-warn">Expires: {new Date(previewItem.expiresAt).toLocaleString()}</span>
                )}
              </div>
            </article>

            <div className="modal-actions-footer">
              <button
                type="button"
                className="btn-gold-solid full-width"
                onClick={() => setPreviewItem(null)}
              >
                Close Preview
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
