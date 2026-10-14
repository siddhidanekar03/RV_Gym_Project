import { Camera, MapPin } from 'lucide-react';

export default function Gallery() {
  const facilityAreas = [
    {
      id: 'gal_1',
      zone: 'Main Free Weights Floor',
      description: 'Heavy dumbbell wall from 2.5kg to 60kg and adjustable commercial incline benches.',
      status: 'In Active Use'
    },
    {
      id: 'gal_2',
      zone: 'Powerlifting Cage Arena',
      description: 'Dual commercial 3x3 steel power cages with calibrated steel plates and deadlift jacks.',
      status: 'In Active Use'
    },
    {
      id: 'gal_3',
      zone: 'Cable & Pulley Suite',
      description: 'Precision dual adjustable pulley station with lat pulldown and low row stations.',
      status: 'In Active Use'
    },
    {
      id: 'gal_4',
      zone: 'Cardio & Conditioning Row',
      description: 'Incline commercial treadmills and air resistance rowers with telemetry displays.',
      status: 'In Active Use'
    },
    {
      id: 'gal_5',
      zone: 'Functional Turf & Sprint Track',
      description: '15-meter sprint turf lane equipped for prowler sled pushes and kettlebell work.',
      status: 'In Active Use'
    },
    {
      id: 'gal_6',
      zone: 'Locker & Member Recovery',
      description: 'Secured personal lockers, sanitized changing areas, and post-workout recovery zone.',
      status: 'In Active Use'
    }
  ];

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
            {/* Clearly Identified Replacement Placeholder */}
            <div className="gallery-media-frame">
              <div className="media-placeholder-graphic">
                <Camera size={32} className="placeholder-icon-gold" aria-hidden="true" />
                <span className="placeholder-badge">
                  [Pending Authorized Gym Photography: {area.zone}]
                </span>
                <span className="placeholder-subtext">
                  Scheduled for official photoshoot upload
                </span>
              </div>
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
