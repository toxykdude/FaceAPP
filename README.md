# FaceGYM — AI-Powered Membership Management Platform

> Facial recognition-based gym membership management system with real-time access control, payment tracking, and automated reporting.

## 🏋️ Features

### Core
- **Facial Recognition Access Control** — FaceNet-based recognition with configurable confidence thresholds
- **Member Management** — Full CRUD with biometric enrollment (photo upload or webcam capture)
- **Membership Plans** — Flexible plans with auto-calculated expiration dates
- **Payment Tracking** — Cash/transfer payments with partial payment support
- **Multi-Camera Support** — RTSP cameras + USB webcams via browser WebSocket streaming
- **Automated Email Reports** — Periodic reports every 2 hours with sales, new members, and expired access alerts

### Kiosk Terminal
- Full-screen welcome screen with live camera feed
- Green glow (access granted) / Red glow (access denied) recognition feedback
- Auto-reset after 3 seconds, ready for next member

### Administration
- **Role-Based Access Control (RBAC)** — Per-page permissions for staff users
- **Dark/Light Theme** — Toggle in sidebar and settings
- **Spanish/English i18n** — Full translation with language toggle
- **Custom Branding** — Upload your logo and set your organization name
- **Dashboard Analytics** — Revenue trends, member growth, peak hours, check-in tracking
- **Reports** — Interactive charts with time range filtering (7d/30d/90d/year)

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Proxmox LXC Container                 │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │ Nginx    │  │ Backend  │  │ CV Service           │  │
│  │ :80/:443 │  │ :8000    │  │ :8001                │  │
│  │ SSL/WS   │──│ FastAPI  │  │ OpenCV + FaceNet     │  │
│  └──────────┘  │ SQLAlchemy│  │ RTSP + WebSocket     │  │
│                └────┬─────┘  └──────────┬───────────┘  │
│                     │                    │              │
│                ┌────▼─────┐              │              │
│                │PostgreSQL│              │              │
│                │ :5432    │              │              │
│                └──────────┘              │              │
└──────────────────────────────────────────┼──────────────┘
                                           │
              ┌────────────────────────────┼────────────────────┐
              │                            │                    │
    ┌─────────▼─────────┐       ┌─────────▼──────────┐         │
    │  RTSP Camera      │       │  Kiosk PCs (LAN)   │         │
    │  (Reception Door) │       │  USB Camera → Browser│        │
    │  Direct stream    │       │  WebSocket → CV Svc  │        │
    └───────────────────┘       └─────────────────────┘         │
```

### Tech Stack
| Component | Technology |
|-----------|-----------|
| Backend | Python 3.11, FastAPI, SQLAlchemy, Alembic |
| CV Service | Python 3.11, OpenCV, FaceNet (InsightFace), FastAPI |
| Frontend | React 18, TypeScript, Vite, MUI 6, TanStack Query |
| Database | PostgreSQL 15 |
| Reverse Proxy | Nginx with SSL, WebSocket proxy |
| Container | Proxmox LXC (Ubuntu 22.04) |

## 🚀 Installation

### Prerequisites
- Ubuntu 22.04+ (bare metal, VM, or LXC)
- Python 3.11+
- Node.js 18+
- PostgreSQL 15+
- Nginx
- At least 2GB RAM, 10GB disk

### Quick Install

```bash
git clone https://github.com/toxykdude/FaceGYM.git
cd FaceGYM
chmod +x install.sh
sudo ./install.sh
```

The installer will:
1. Install system dependencies (Python, Node.js, PostgreSQL, Nginx)
2. Create the database and user
3. Install Python dependencies (backend + CV service)
4. Build the React frontend
5. Configure Nginx with SSL (self-signed by default)
6. Create systemd services for auto-start
7. Generate a `.env` file with random secrets

### Post-Installation

1. Access the app at `http://your-server-ip`
2. Default login: `admin` / `admin123` — **change this immediately!**
3. Go to Settings → General to set your organization name and upload your logo
4. Go to Cameras to add your RTSP camera(s)
5. Open `/kiosk` on a kiosk PC with USB camera for facial check-in

### Environment Variables

Copy `.env.example` to `.env` and configure:

```env
# Database
DATABASE_URL=postgresql://membership:YOUR_PASSWORD@localhost:5432/membership_db

# Security
SECRET_KEY=your-secret-key-here
ENCRYPTION_KEY=your-32-byte-encryption-key
JWT_SECRET=your-jwt-secret

# Email (optional, for reports)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your@email.com
SMTP_PASSWORD=your-password
SMTP_FROM_EMAIL=noreply@yourdomain.com
SMTP_USE_SSL=false

# Admin
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
```

## 📱 Usage Guide

### Adding Members
1. Navigate to **Members** → **New Member**
2. Fill in name, ID (cédula), and contact info
3. Click **Create Member**
4. Assign a membership plan (auto-calculates end date)
5. Enroll face via webcam or photo upload (minimum quality score: 0.9)

### Kiosk Setup
1. Open `http://your-server/kiosk` on a dedicated PC
2. Select camera → toggle **USB Camera** mode
3. Browser will request camera permission — approve
4. The kiosk shows live feed with recognition overlay
5. Members see green glow (granted) or red glow (expired)

### Managing Memberships
1. Go to a member's page → **Membership History**
2. Click **Renew** to extend with same plan (start = last end date + 1 day)
3. Or click **+ New Membership** to assign a different plan
4. Set payment method (cash/transfer) and amount
5. Partial payments supported — shows remaining balance

### Email Reports
- Automatic reports every 2 hours to admin email(s)
- Includes: sales summary, new members, recognized expired members
- Manual trigger: Settings → or `POST /api/reports-email/send-now`

### User Roles & Permissions
- **Admin**: Full access to all features
- **Staff**: Configurable per-page access
  - Go to Settings → Users → Edit user → set permissions
  - Toggle: Dashboard, Members, Memberships, Cameras, Sales, Reports

### Custom Branding
1. Go to **Settings** → **General**
2. Change **Organization Name** — appears in sidebar, login, reports
3. Upload **Logo** — appears in sidebar and login page
4. Changes apply immediately after save

## 🔧 API Reference

The backend exposes a REST API at `/api/`. Full docs available at:
- Swagger UI: `http://your-server/docs`
- ReDoc: `http://your-server/redoc`

### Key Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/login` | POST | Authenticate and get JWT |
| `/api/members` | GET/POST | List/create members |
| `/api/members/{id}/photo` | GET | Get member face photo |
| `/api/members/{id}/enroll` | POST | Enroll face biometric |
| `/api/memberships` | GET/POST | List/create memberships |
| `/api/membership-plans` | GET/POST | Manage plans |
| `/api/sales` | GET/POST | Sales transactions |
| `/api/sales/dashboard` | GET | Aggregated report data |
| `/api/events` | GET | Access events log |
| `/api/events/today-recognized` | GET | Today's recognized members |
| `/api/cameras` | GET/POST | Camera management |
| `/api/settings` | GET/PUT | System settings |
| `/api/settings/upload-logo` | POST | Upload custom logo |
| `/api/reports-email/send-now` | POST | Trigger email report |
| `/cv/health` | GET | CV service health |
| `/cv/stream/{id}` | GET | MJPEG camera stream |
| `/cv/ws/camera/{id}` | WS | WebSocket for browser camera |

## 📁 Project Structure

```
FaceGYM/
├── backend/                  # FastAPI backend
│   ├── api/                  # API endpoints
│   │   ├── auth.py           # Authentication
│   │   ├── members.py        # Member CRUD + photo endpoint
│   │   ├── memberships.py    # Membership management
│   │   ├── membership_plans.py
│   │   ├── sales.py          # Sales + dashboard reports
│   │   ├── events.py         # Access events + today-recognized
│   │   ├── cameras.py        # Camera management
│   │   ├── enrollment.py     # Face enrollment (upload + camera)
│   │   ├── settings.py       # System settings + logo upload
│   │   ├── reports_email.py  # Scheduled email reports
│   │   └── users.py          # User management
│   ├── core/                 # Core modules
│   │   ├── config.py         # Settings from .env
│   │   ├── database.py       # SQLAlchemy setup
│   │   ├── security.py       # JWT + password hashing
│   │   ├── encryption.py     # AES encryption for biometrics
│   │   └── email.py          # SMTP email service
│   ├── models/               # SQLAlchemy models
│   ├── schemas/              # Pydantic schemas
│   ├── main.py               # FastAPI app entry
│   └── requirements.txt
├── cv_service/               # Computer vision service
│   ├── main.py               # FastAPI app + WebSocket handler
│   ├── stream/               # RTSP + V4L2 stream processor
│   ├── detection/            # Face detection + quality + liveness
│   ├── recognition/          # FaceNet recognizer + template matcher
│   └── api/                  # Backend client
├── frontend/                 # React frontend
│   ├── src/
│   │   ├── api/              # API clients
│   │   ├── components/       # Shared components
│   │   ├── contexts/         # Auth + Theme contexts
│   │   ├── i18n/             # Translations (ES/EN)
│   │   ├── pages/            # Page components
│   │   └── main.tsx          # Entry point
│   ├── public/               # Static assets (logo, favicon)
│   └── package.json
├── install.sh                # One-click installer
├── .env.example              # Environment template
└── README.md                 # This file
```

## 🔒 Security

- AES-256 encryption for biometric template data at rest
- JWT authentication with token blacklisting
- Rate limiting on auth endpoints (Nginx)
- CORS configuration
- Helmet-style security headers
- Encrypted camera RTSP URLs in database
- Face enrollment quality threshold (0.9) prevents low-quality enrollments
- Anti-passback cooldown prevents duplicate check-ins

## 📄 License

MIT License — feel free to use, modify, and deploy for your own gym or business.
