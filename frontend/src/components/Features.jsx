import { Dumbbell, Shield, Award, LineChart } from 'lucide-react';

export default function Features() {
  const features = [
    {
      icon: Dumbbell,
      title: 'Strength Training',
      description: 'Progressive barbell and dumbbell protocols focused on foundational compound lifts: squats, deadlifts, presses, and rows.',
      tag: 'Core Discipline'
    },
    {
      icon: Shield,
      title: 'Modern Equipment',
      description: 'Heavy duty commercial power racks, calibrated steel plates, dual cable stations, and dedicated impact-absorbing deadlift platforms.',
      tag: 'Verified Hardware'
    },
    {
      icon: Award,
      title: 'Personal Guidance',
      description: 'Accredited coaching for biomechanical form correction, structured workout programming, and safe progression.',
      tag: 'Certified Staff'
    },
    {
      icon: LineChart,
      title: 'Progress Tracking',
      description: 'Integrated digital attendance check-ins, personal record (PR) milestone monitoring, and direct workout routine access.',
      tag: 'Member Portal'
    }
  ];

  return (
    <section id="about" className="section-container" aria-label="Training Pillars">
      <div className="section-header">
        <span className="section-eyebrow">TRAINING PRINCIPLES</span>
        <h2 className="section-title">Built for Serious Training</h2>
        <p className="section-lead">
          RVFitness delivers the tools, the space, and the coaching needed for members who take their health and performance seriously.
        </p>
      </div>

      <div className="features-grid">
        {features.map((feat) => {
          const Icon = feat.icon;
          return (
            <div key={feat.title} className="feature-card">
              <div className="feature-card-header">
                <div className="feature-icon-wrapper" aria-hidden="true">
                  <Icon size={24} className="gold-text" />
                </div>
                <span className="feature-tag">{feat.tag}</span>
              </div>
              <h3 className="feature-title">{feat.title}</h3>
              <p className="feature-description">{feat.description}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}
