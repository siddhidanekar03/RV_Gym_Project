import { useState } from 'react'
import './App.css'

const links = ['Home', 'About', 'Memberships', 'Equipment', 'Trainers', 'Events', 'Gallery', 'Contact']

const plans = [
  { name: 'Monthly', price: '₹1,500', per: '/month', perks: ['Full gym access', 'Locker room', 'Free fitness check'] },
  { name: 'Quarterly', price: '₹4,000', per: '/3 months', perks: ['Full gym access', 'Diet guidance', 'One trainer session'], hot: true },
  { name: 'Yearly', price: '₹12,000', per: '/year', perks: ['Full gym access', 'Personal plan', 'Priority slots'] },
]

const trainers = [
  { name: 'Rohit V.', role: 'Head Coach · Bodybuilding' },
  { name: 'Sneha P.', role: 'Strength & Mobility' },
  { name: 'Amit K.', role: 'Fat Loss & Cardio' },
]

const equipment = ['Free weights up to 60 kg', 'Power racks', 'Cable machines', 'Treadmills & cycles', 'Functional zone', 'Chest, back & leg machines']

export default function App() {
  const [open, setOpen] = useState(false)

  return (
    <>
      <header className="nav">
        <a href="#home" className="brand">
          <span className="logo">RV</span>
          <span>
            <b>RV FITNESS</b>
            <small>NARSOBAWADI</small>
          </span>
        </a>
        <nav className={open ? 'links open' : 'links'}>
          {links.map((l, i) => (
            <a key={l} href={`#${l.toLowerCase()}`} className={i === 0 ? 'active' : ''} onClick={() => setOpen(false)}>{l}</a>
          ))}
        </nav>
        <div className="nav-right">
          <a href="#contact" className="login">Login</a>
          <a href="#memberships" className="btn gold small">Join Now</a>
          <button className="burger" aria-label="Menu" onClick={() => setOpen(!open)}>☰</button>
        </div>
      </header>

      <section id="home" className="hero">
        <div className="hero-inner">
          <span className="pill">● RV FITNESS · NARSOBAWADI</span>
          <h1>
            BUILD YOUR<br />
            <span>STRENGTH.</span><br />
            DEFINE YOURSELF.
          </h1>
          <p>Train with purpose. Transform with discipline.</p>
          <div className="cta">
            <a href="#memberships" className="btn gold">JOIN NOW →</a>
            <a href="#about" className="btn ghost">EXPLORE RV FITNESS</a>
          </div>
        </div>
        <div className="scroll">SCROLL<i /></div>
      </section>

      <section id="about" className="section">
        <h2>About RV Fitness</h2>
        <p className="lead">A serious gym in Narsobawadi for people who want real results. Honest coaching, clean equipment and a crowd that pushes you to show up every day.</p>
        <div className="stats">
          <div><b>500+</b><span>Members</span></div>
          <div><b>3</b><span>Expert trainers</span></div>
          <div><b>6 AM–10 PM</b><span>Open daily</span></div>
        </div>
      </section>

      <section id="memberships" className="section dark">
        <h2>Memberships</h2>
        <div className="grid">
          {plans.map((p) => (
            <div key={p.name} className={p.hot ? 'card hot' : 'card'}>
              <h3>{p.name}</h3>
              <div className="price">{p.price}<small>{p.per}</small></div>
              <ul>{p.perks.map((x) => <li key={x}>{x}</li>)}</ul>
              <a href="#contact" className={p.hot ? 'btn gold' : 'btn ghost'}>Choose {p.name}</a>
            </div>
          ))}
        </div>
      </section>

      <section id="equipment" className="section">
        <h2>Equipment</h2>
        <div className="grid">
          {equipment.map((e) => <div key={e} className="card tick">{e}</div>)}
        </div>
      </section>

      <section id="trainers" className="section dark">
        <h2>Trainers</h2>
        <div className="grid">
          {trainers.map((t) => (
            <div key={t.name} className="card">
              <div className="avatar">{t.name[0]}</div>
              <h3>{t.name}</h3>
              <p className="muted">{t.role}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="events" className="section">
        <h2>Events</h2>
        <div className="grid">
          <div className="card"><h3>Diwali Strength Challenge</h3><p className="muted">Lift, log and win prizes. Open to all members.</p></div>
          <div className="card"><h3>Transformation Contest</h3><p className="muted">90 days. Before and after. Judged by the coaches.</p></div>
        </div>
      </section>

      <section id="gallery" className="section dark">
        <h2>Gallery</h2>
        <div className="grid gal">
          {[1, 2, 3, 4, 5, 6].map((n) => (
            <div key={n} className="shot">Add photo {n}</div>
          ))}
        </div>
      </section>

      <section id="contact" className="section">
        <h2>Contact</h2>
        <p className="lead">RV Fitness, Narsobawadi, Maharashtra<br />Phone: +91 00000 00000</p>
        <form className="form" onSubmit={(e) => { e.preventDefault(); alert('Thanks! We will call you soon.') }}>
          <input placeholder="Your name" required />
          <input placeholder="Phone number" required />
          <button className="btn gold">Send enquiry</button>
        </form>
      </section>

      <footer>© {new Date().getFullYear()} RV Fitness Narsobawadi</footer>
    </>
  )
}