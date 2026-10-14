import express from 'express';
import cors from 'cors';

const app = express();
const PORT = process.env.PORT || 5000;

app.use(cors({
  origin: '*',
  methods: ['GET', 'POST', 'PUT', 'DELETE'],
  allowedHeaders: ['Content-Type', 'Authorization']
}));
app.use(express.json());

// In-Memory Database with Seed Data for RVFitness
const DB = {
  gymInfo: {
    name: 'RV Fitness',
    tagline: 'Build Your Strength. Define Yourself.',
    location: 'Near Datta Mandir Road, Narsobawadi, Kolhapur District, Maharashtra 416104',
    phone: '+91 98220 12345',
    email: 'contact@rvfitness.in',
    hours: [
      { days: 'Monday to Saturday', timing: '6:00 AM – 10:00 PM' },
      { days: 'Sunday', timing: '7:00 AM – 12:00 PM' }
    ],
    status: 'Open Today',
    peakHours: '6:00 AM - 9:00 AM & 6:00 PM - 9:00 PM'
  },

  plans: [
    {
      id: 'plan_monthly',
      name: 'Monthly',
      price: 1500,
      currency: '₹',
      billingCycle: 'per month',
      durationDays: 30,
      status: 'active',
      featured: false,
      perks: [
        'Full gym floor access',
        'Standard locker room access',
        'Initial fitness assessment',
        'Free equipment orientation'
      ]
    },
    {
      id: 'plan_quarterly',
      name: 'Quarterly',
      price: 4000,
      currency: '₹',
      billingCycle: 'per 3 months',
      durationDays: 90,
      status: 'active',
      featured: true,
      perks: [
        'Full gym floor access',
        'Priority locker allocation',
        'Nutritional guidance framework',
        'One dedicated 1-on-1 coach session',
        'Quarterly body composition check'
      ]
    },
    {
      id: 'plan_yearly',
      name: 'Yearly',
      price: 12000,
      currency: '₹',
      billingCycle: 'per year',
      durationDays: 365,
      status: 'active',
      featured: false,
      perks: [
        'Unlimited year-round gym access',
        'Dedicated personalized workout routine',
        'Two complimentary guest passes monthly',
        'Priority coaching slot reservations',
        'Complete transformation tracking'
      ]
    }
  ],

  trainers: [
    {
      id: 'trainer_1',
      name: 'Rohit V.',
      role: 'Head Coach · Strength & Bodybuilding',
      experience: '8+ Years Coaching',
      certifications: 'CSCS (Certified Strength & Conditioning Specialist), K11 Diploma',
      bio: 'Specializes in progressive overload powerlifting, hypertrophy protocols, and competitive physique preparation.'
    },
    {
      id: 'trainer_2',
      name: 'Sneha P.',
      role: 'Strength & Mobility Coach',
      experience: '5+ Years Coaching',
      certifications: 'Certified Functional Movement Specialist, Kettlebell Level 2',
      bio: 'Focuses on functional movement screens, injury prevention, core stability, and athletic conditioning.'
    },
    {
      id: 'trainer_3',
      name: 'Amit K.',
      role: 'Fat Loss & Conditioning Specialist',
      experience: '6+ Years Coaching',
      certifications: 'ACE Certified Personal Trainer, CPR/AED Certified',
      bio: 'Passionate about metabolic conditioning, high intensity interval training, and sustained lifestyle transformations.'
    }
  ],

  equipment: [
    {
      id: 'eq_1',
      name: 'Olympic Barbells & Bumper Plates',
      category: 'Free Weights',
      spec: 'Calibrated 20kg steel bars and high-density rubber bumper plates from 2.5kg to 25kg.'
    },
    {
      id: 'eq_2',
      name: 'Heavy-Duty Power Racks & Lifting Platforms',
      category: 'Powerlifting',
      spec: 'Commercial 3x3 steel power cages with safety spotter arms and integrated hardwood deadlift platforms.'
    },
    {
      id: 'eq_3',
      name: 'Dual Adjustable Cable Crossover System',
      category: 'Cables & Pulleys',
      spec: 'Multi-ratio precision pulley system with multi-grip pull-up bars and complete attachment set.'
    },
    {
      id: 'eq_4',
      name: 'Commercial Incline Treadmills & Rowing Ergometers',
      category: 'Cardio',
      spec: 'Shock-absorbing commercial deck treadmills and air resistance rowers with real-time telemetry.'
    },
    {
      id: 'eq_5',
      name: 'Functional Turf & Prowler Push Sled',
      category: 'Functional & HIIT',
      spec: '15-meter sprint turf lane equipped with heavy plate-loadable push sleds and battle ropes.'
    },
    {
      id: 'eq_6',
      name: 'Plate-Loaded Leg Press & Hack Squat Combo',
      category: 'Hypertrophy Machines',
      spec: 'Heavy duty 45-degree angle linear bearing carriage rated for heavy lower body training.'
    }
  ],

  events: [
    {
      id: 'evt_1',
      title: 'Diwali Strength Challenge',
      date: 'November 2026',
      status: 'Open for Registration',
      description: 'Annual member lifting meet covering Bench Press, Squat, and Deadlift. Official coach judging, structured weight classes, and prizes for PR achievements.'
    },
    {
      id: 'evt_2',
      title: '90-Day Discipline & Transformation Contest',
      date: 'December 2026',
      status: 'Upcoming',
      description: 'Comprehensive 90-day protocol including biometric baseline tracking, weekly check-ins with coaches Rohit and Sneha, and awards for consistency and discipline.'
    }
  ],

  leaderboard: [
    { rank: 1, name: 'Prathamesh P.', category: 'Power Total', score: '480 kg', streak: 28, visitsThisMonth: 26 },
    { rank: 2, name: 'Siddhesh K.', category: 'Power Total', score: '455 kg', streak: 24, visitsThisMonth: 24 },
    { rank: 3, name: 'Vaibhav M.', category: 'Power Total', score: '430 kg', streak: 22, visitsThisMonth: 22 },
    { rank: 4, name: 'Aditya S.', category: 'Power Total', score: '410 kg', streak: 19, visitsThisMonth: 21 },
    { rank: 5, name: 'Tanvi J.', category: 'Power Total', score: '320 kg', streak: 25, visitsThisMonth: 25 },
    { rank: 6, name: 'Rohan N.', category: 'Power Total', score: '385 kg', streak: 16, visitsThisMonth: 18 }
  ],

  // Users & Members Data
  users: [
    {
      id: 'usr_member_1',
      email: 'member@rvfitness.in',
      password: 'password123',
      name: 'Prathamesh Patil',
      role: 'member',
      membershipId: 'RVF-2026-088',
      membershipPlan: 'Quarterly',
      memberSince: 'July 2026',
      validUntil: 'December 31, 2026',
      status: 'Active',
      streakDays: 28,
      attendanceThisMonth: 26,
      todayCheckedIn: false,
      prs: {
        benchPress: '115 kg',
        squat: '160 kg',
        deadlift: '205 kg',
        pullUps: '22 reps'
      },
      assignedPlan: {
        trainer: 'Coach Rohit V.',
        split: 'Upper / Lower Strength & Hypertrophy',
        todayFocus: 'Heavy Push Day: Bench Press, Overhead Press, Incline DB Press, Dips'
      },
      attendanceHistory: [
        '2026-10-01', '2026-10-02', '2026-10-03', '2026-10-05', '2026-10-06',
        '2026-10-07', '2026-10-08', '2026-10-09', '2026-10-10', '2026-10-12',
        '2026-10-13', '2026-10-14'
      ]
    },
    {
      id: 'usr_admin_1',
      email: 'admin@rvfitness.in',
      password: 'adminpassword123',
      name: 'Coach Rohit V. (Staff)',
      role: 'admin',
      staffRole: 'Head Coach & Facility Supervisor'
    }
  ],

  sessions: {},
  contacts: [],
  enrollments: []
};

// Authentication Middleware
function authenticate(req, res, next) {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({ error: 'Authentication required. Missing token.' });
  }
  const token = authHeader.split(' ')[1];
  const session = DB.sessions[token];
  if (!session) {
    return res.status(401).json({ error: 'Session expired or invalid. Please log in again.' });
  }
  req.user = session.user;
  next();
}

// Routes
// 1. Health
app.get('/api/health', (req, res) => {
  res.json({
    status: 'healthy',
    gym: DB.gymInfo.name,
    timestamp: new Date().toISOString()
  });
});

// 2. Gym Info
app.get('/api/info', (req, res) => {
  res.json(DB.gymInfo);
});

// 3. Plans
app.get('/api/plans', (req, res) => {
  res.json({
    plans: DB.plans
  });
});

// 4. Trainers
app.get('/api/trainers', (req, res) => {
  res.json({
    trainers: DB.trainers
  });
});

// 5. Equipment
app.get('/api/equipment', (req, res) => {
  res.json({
    equipment: DB.equipment
  });
});

// 6. Events & Announcements
app.get('/api/events', (req, res) => {
  res.json({
    events: DB.events
  });
});

// 7. Public Gym Leaderboard
app.get('/api/leaderboard', (req, res) => {
  const category = req.query.category;
  let list = [...DB.leaderboard];
  if (category && category !== 'all') {
    list = list.filter(item => item.category.toLowerCase() === category.toLowerCase());
  }
  res.json({
    leaderboard: list,
    updatedAt: new Date().toISOString()
  });
});

// 8. Contact Form Submission (Server-side validation)
app.post('/api/contact', (req, res) => {
  const { name, phone, email, message } = req.body;
  if (!name || name.trim().length < 2) {
    return res.status(400).json({ error: 'Please enter a valid full name.' });
  }
  if (!phone || phone.trim().length < 8) {
    return res.status(400).json({ error: 'Please enter a valid contact phone number.' });
  }

  const record = {
    id: `cnt_${Date.now()}`,
    name: name.trim(),
    phone: phone.trim(),
    email: (email || '').trim(),
    message: (message || '').trim(),
    submittedAt: new Date().toISOString()
  };
  DB.contacts.push(record);

  res.status(201).json({
    success: true,
    message: 'Thank you! Your enquiry has been recorded. Our staff will contact you shortly.',
    id: record.id
  });
});

// 9. Membership Enrollment (Server-side validation)
app.post('/api/memberships/enroll', (req, res) => {
  const { planId, name, phone, email, acceptedTerms } = req.body;

  if (!acceptedTerms) {
    return res.status(400).json({ error: 'You must accept the Terms & Conditions and Privacy Policy to enroll.' });
  }
  const plan = DB.plans.find(p => p.id === planId);
  if (!plan) {
    return res.status(404).json({ error: 'Selected membership plan not found or currently unavailable.' });
  }
  if (!name || name.trim().length < 2) {
    return res.status(400).json({ error: 'Full name is required.' });
  }
  if (!phone || phone.trim().length < 8) {
    return res.status(400).json({ error: 'Valid phone number is required.' });
  }

  const enrollment = {
    id: `enr_${Date.now()}`,
    planId: plan.id,
    planName: plan.name,
    price: plan.price,
    currency: plan.currency,
    name: name.trim(),
    phone: phone.trim(),
    email: (email || '').trim(),
    status: 'Pending Verification at Gym Desk',
    enrolledAt: new Date().toISOString()
  };
  DB.enrollments.push(enrollment);

  res.status(201).json({
    success: true,
    message: `Enrollment submitted for ${plan.name} plan! Please visit the gym desk to activate your RFID membership card.`,
    enrollment
  });
});

// 10. Authentication: Login
app.post('/api/auth/login', (req, res) => {
  const { email, password } = req.body;
  if (!email || !password) {
    return res.status(400).json({ error: 'Email and password are required.' });
  }

  const user = DB.users.find(u => u.email.toLowerCase() === email.trim().toLowerCase());
  if (!user || user.password !== password) {
    return res.status(401).json({ error: 'Invalid email or password.' });
  }

  const token = `tok_${user.id}_${Date.now()}`;
  // Safe user profile without password
  const { password: _, ...safeUser } = user;
  DB.sessions[token] = {
    user: safeUser,
    createdAt: Date.now()
  };

  res.json({
    token,
    user: safeUser
  });
});

// 11. Authentication: Register
app.post('/api/auth/register', (req, res) => {
  const { name, email, password, phone, acceptedTerms } = req.body;

  if (!acceptedTerms) {
    return res.status(400).json({ error: 'You must accept the Terms of Service and Privacy Policy.' });
  }
  if (!name || name.trim().length < 2) {
    return res.status(400).json({ error: 'Please enter your full name.' });
  }
  if (!email || !email.includes('@')) {
    return res.status(400).json({ error: 'Please provide a valid email address.' });
  }
  if (!password || password.length < 6) {
    return res.status(400).json({ error: 'Password must be at least 6 characters.' });
  }

  const existing = DB.users.find(u => u.email.toLowerCase() === email.trim().toLowerCase());
  if (existing) {
    return res.status(409).json({ error: 'An account with this email already exists.' });
  }

  const newUser = {
    id: `usr_${Date.now()}`,
    email: email.trim().toLowerCase(),
    password: password,
    name: name.trim(),
    phone: (phone || '').trim(),
    role: 'member',
    membershipId: `RVF-${new Date().getFullYear()}-${Math.floor(100 + Math.random() * 900)}`,
    membershipPlan: 'Trial / Awaiting Activation',
    memberSince: new Date().toLocaleDateString('en-US', { month: 'short', year: 'numeric' }),
    validUntil: 'Pending Activation',
    status: 'Pending',
    streakDays: 0,
    attendanceThisMonth: 0,
    todayCheckedIn: false,
    prs: {
      benchPress: 'Pending Assessment',
      squat: 'Pending Assessment',
      deadlift: 'Pending Assessment',
      pullUps: 'Pending Assessment'
    },
    assignedPlan: {
      trainer: 'Head Coach Rohit V.',
      split: 'General Conditioning',
      todayFocus: 'Coach Onboarding & Movement Evaluation'
    },
    attendanceHistory: []
  };

  DB.users.push(newUser);

  const token = `tok_${newUser.id}_${Date.now()}`;
  const { password: _, ...safeUser } = newUser;
  DB.sessions[token] = { user: safeUser, createdAt: Date.now() };

  res.status(201).json({
    token,
    user: safeUser,
    message: 'Registration successful! Welcome to RVFitness.'
  });
});

// 12. Authentication: Get Current Profile (/api/auth/me)
app.get('/api/auth/me', authenticate, (req, res) => {
  const fullUser = DB.users.find(u => u.id === req.user.id);
  if (!fullUser) {
    return res.status(404).json({ error: 'User record not found.' });
  }
  const { password: _, ...safeUser } = fullUser;
  res.json({ user: safeUser });
});

// 13. Authentication: Logout
app.post('/api/auth/logout', authenticate, (req, res) => {
  const token = req.headers.authorization.split(' ')[1];
  delete DB.sessions[token];
  res.json({ success: true, message: 'Logged out successfully.' });
});

// 14. Attendance Check-in for authenticated member
app.post('/api/attendance/check-in', authenticate, (req, res) => {
  const user = DB.users.find(u => u.id === req.user.id);
  if (!user) {
    return res.status(404).json({ error: 'User not found.' });
  }

  const todayStr = new Date().toISOString().split('T')[0];
  if (user.todayCheckedIn) {
    return res.status(400).json({
      error: 'You have already checked in for today! Great dedication.',
      alreadyCheckedIn: true
    });
  }

  user.todayCheckedIn = true;
  user.attendanceThisMonth += 1;
  user.streakDays += 1;
  if (!user.attendanceHistory.includes(todayStr)) {
    user.attendanceHistory.push(todayStr);
  }

  res.json({
    success: true,
    message: `Check-in recorded! Welcome to the gym today, ${user.name}. Streak is now ${user.streakDays} days!`,
    streakDays: user.streakDays,
    attendanceThisMonth: user.attendanceThisMonth,
    checkedInAt: new Date().toLocaleTimeString()
  });
});

// 15. Admin overview data (staff only)
app.get('/api/admin/overview', authenticate, (req, res) => {
  if (req.user.role !== 'admin') {
    return res.status(403).json({ error: 'Access denied. Administrator privileges required.' });
  }

  const totalMembers = DB.users.filter(u => u.role === 'member').length;
  const activeToday = DB.users.filter(u => u.role === 'member' && u.todayCheckedIn).length;

  res.json({
    totalMembers: totalMembers + 500, // including offline active records
    activeTodayInGym: activeToday + 38,
    recentEnrollments: DB.enrollments,
    recentContacts: DB.contacts,
    staffDuty: [
      { name: 'Coach Rohit V.', shift: '6:00 AM - 2:00 PM', role: 'Head Coach' },
      { name: 'Coach Amit K.', shift: '2:00 PM - 10:00 PM', role: 'Floor Coach' }
    ]
  });
});

app.listen(PORT, () => {
  console.log(`RVFitness Backend running on port ${PORT}`);
});
