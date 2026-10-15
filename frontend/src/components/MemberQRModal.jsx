import { useState, useEffect, useRef } from 'react';
import { X, RefreshCw, AlertCircle, ShieldCheck, Clock, QrCode } from 'lucide-react';
import QRCode from 'qrcode';
import { getAttendanceQRToken } from '../api';

export default function MemberQRModal({ member, onClose }) {
  const [tokenData, setTokenData] = useState(null);
  const [secondsLeft, setSecondsLeft] = useState(120);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const canvasRef = useRef(null);

  const fetchToken = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getAttendanceQRToken();
      setTokenData(data);
      setSecondsLeft(data.secondsValid || 120);
    } catch (err) {
      setError(err.message || 'Unable to generate dynamic entry QR code.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let active = true;
    getAttendanceQRToken()
      .then((data) => {
        if (active) {
          setTokenData(data);
          setSecondsLeft(data.secondsValid || 120);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (active) {
          setError(err.message || 'Unable to generate dynamic entry QR code.');
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  // Render QR to canvas whenever tokenData updates
  useEffect(() => {
    if (tokenData?.qrToken && canvasRef.current) {
      QRCode.toCanvas(
        canvasRef.current,
        tokenData.qrToken,
        {
          width: 260,
          margin: 2,
          color: {
            dark: '#08090b',
            light: '#ffffff',
          },
        },
        (err) => {
          if (err) setError('Failed to draw QR code canvas.');
        }
      );
    }
  }, [tokenData]);

  // Countdown timer
  useEffect(() => {
    if (secondsLeft <= 0) return;
    const interval = setInterval(() => {
      setSecondsLeft((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [secondsLeft]);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const isExpired = secondsLeft <= 0;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Member Entry QR Code">
      <div className="member-qr-modal-card">
        {/* Header */}
        <div className="qr-modal-header">
          <div className="qr-title-wrap">
            <QrCode size={22} className="gold-text" />
            <h3 className="qr-modal-title">Gym Access Entry QR</h3>
          </div>
          <button
            type="button"
            className="qr-close-btn"
            onClick={onClose}
            aria-label="Close Entry QR modal"
          >
            <X size={20} />
          </button>
        </div>

        {/* Member Info */}
        <div className="qr-member-badge">
          <div>
            <strong className="qr-member-name">{member?.name || 'Member'}</strong>
            <span className="qr-member-id">ID: {member?.membership_id || member?.membershipId || 'RVF-MEMBER'}</span>
          </div>
          <span className="qr-status-pill">{member?.status || 'Active'}</span>
        </div>

        {/* QR Display Area */}
        <div className="qr-canvas-wrapper">
          {loading && (
            <div className="qr-loading-box">
              <RefreshCw size={36} className="spinner-icon gold-text" />
              <p>Signing cryptographic entry token...</p>
            </div>
          )}

          {error && (
            <div className="qr-error-box">
              <AlertCircle size={32} className="danger-text" />
              <p>{error}</p>
              <button type="button" className="btn-refresh-gold" onClick={fetchToken}>
                Retry Generation
              </button>
            </div>
          )}

          {!loading && !error && (
            <div className={`canvas-container ${isExpired ? 'expired-overlay' : ''}`}>
              <canvas ref={canvasRef} className="qr-canvas-element" />
              {isExpired && (
                <div className="qr-expired-notice">
                  <Clock size={28} className="gold-text" />
                  <strong>QR Token Expired</strong>
                  <p>Dynamic entry codes expire after 120 seconds to prevent replay.</p>
                  <button type="button" className="btn-refresh-gold" onClick={fetchToken}>
                    <RefreshCw size={16} /> Generate Fresh QR
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Timer Bar & Anti-Replay Security Notice */}
        {!loading && !error && !isExpired && (
          <div className="qr-timer-section">
            <div className="timer-text-row">
              <span className="timer-label">Token Validity</span>
              <strong className={`timer-digits ${secondsLeft < 30 ? 'urgent' : ''}`}>
                {Math.floor(secondsLeft / 60)}:{(secondsLeft % 60).toString().padStart(2, '0')} remaining
              </strong>
            </div>
            <div className="timer-progress-track">
              <div
                className={`timer-progress-fill ${secondsLeft < 30 ? 'urgent' : ''}`}
                style={{ width: `${(secondsLeft / 120) * 100}%` }}
              />
            </div>
          </div>
        )}

        <div className="qr-security-footer">
          <ShieldCheck size={16} className="gold-text" />
          <span>
            Single-use cryptographic nonce. Scanned at front desk or turnstile via 2D optical reader.
          </span>
        </div>
      </div>
    </div>
  );
}
