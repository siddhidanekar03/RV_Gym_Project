import { useState, useEffect } from 'react';
import { Camera, MapPin } from 'lucide-react';
import { fetchPublicGallery } from '../api';

const DEFAULT_FACILITY_AREAS = [
  {
    id: 'gal_1',
    zone: 'Main Free Weights Floor',
    description: 'Heavy dumbbell wall from 2.5kg to 60kg and adjustable commercial incline benches.',
    status: 'In Active Use',
    image_url: '',
  },
  {
    id: 'gal_2',
    zone: 'Powerlifting Cage Arena',
    description: 'Dual commercial 3x3 steel power cages with calibrated steel plates and deadlift jacks.',
    status: 'In Active Use',
    image_url: '',
  },
  {
    id: 'gal_3',
    zone: 'Cable & Pulley Suite',
    description: 'Precision dual adjustable pulley station with lat pulldown and low row stations.',
    status: 'In Active Use',
    image_url: '',
  },
  {
    id: 'gal_4',
    zone: 'Cardio & Conditioning Row',
    description: 'Incline commercial treadmills and air resistance rowers with telemetry displays.',
    status: 'In Active Use',
    image_url: '',
  },
  {
    id: 'gal_5',
    zone: 'Functional Turf & Sprint Track',
    description: '15-meter sprint turf lane equipped for prowler sled pushes and kettlebell work.',
    status: 'In Active Use',
    image_url: '',
  },
  {
    id: 'gal_6',
    zone: 'Locker & Member Recovery',
    description: 'Secured personal lockers, sanitized changing areas, and post-workout recovery zone.',
    status: 'In Active Use',
    image_url: '',
  },
];

export default function Gallery() {
  const [facilityAreas, setFacilityAreas] = useState(DEFAULT_FACILITY_AREAS);

  useEffect(() => {
    fetchPublicGallery()
      .then((data) => {
        if (data && data.gallery && data.gallery.length > 0) {
          setFacilityAreas(data.gallery);
        }
      })
      .catch(() => {});
  }, []);

  return (
    <section id="gallery" className="section-container dark-surface" aria-label="Facility Gallery">
      <div className="section-header">
        <span className="section-eyebrow">FACILITY OVERVIEW</span>
        <h2 className="section-title">Gym Floor & Training Zones</h2>
        <p className="section-lead">
          Structured training zones arranged for optimal flow, hygiene, and progressive athletic development.
        </p>
      </div>

      <div className="gallery-grid">
        {facilityAreas.map((area) => (
          <div key={area.id} className="gallery-card">
            {/* Photography Display or Verified Area Placeholder */}
            <div className="gallery-media-frame">
              {area.image_url ? (
                <img
                  src={area.image_url}
                  alt={area.zone}
                  className="gallery-photo-img"
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                />
              ) : (
                <div className="media-placeholder-graphic">
                  <Camera size={32} className="placeholder-icon-gold" aria-hidden="true" />
                  <span className="placeholder-badge">
                    [Pending Authorized Gym Photography: {area.zone}]
                  </span>
                  <span className="placeholder-subtext">
                    Scheduled for official photoshoot upload
                  </span>
                </div>
              )}
            </div>

            <div className="gallery-card-content">
              <div className="zone-header">
                <h3 className="zone-title">{area.zone}</h3>
                <span className="zone-status-badge">
                  <MapPin size={12} className="gold-text" />
                  <span>{area.status}</span>
                </span>
              </div>
              <p className="zone-desc">{area.description}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
