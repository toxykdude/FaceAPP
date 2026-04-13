<div align="center">

# 🏋️ FaceGYM

### AI-Powered Gym Access Control with Facial Recognition

[![Platform](https://img.shields.io/badge/platform-Linux-blue)](https://github.com/toxykdude/FaceGYM)
[![Backend](https://img.shields.io/badge/backend-FastAPI-009688?logo=python)](https://fastapi.tiangolo.com)
[![Frontend](https://img.shields.io/badge/frontend-React-61DAFB?logo=react)](https://react.dev)
[![CV](https://img.shields.io/badge/CV-FaceNet-EE4C2C?logo=pytorch)](https://github.com/timesler/facenet-pytorch)
[![License](https://img.shields.io/badge/license-Proprietary-red)]()

**FaceGYM** is a production-ready access control system that uses facial recognition to manage gym member entry. Members are identified in real-time via RTSP cameras, their membership status is validated, and access is granted or denied automatically.

[Features](#-features) · [Architecture](#-architecture) · [Tech Stack](#-tech-stack) · [Getting Started](#-getting-started) · [API](#-api-reference) · [Security](#-security)

</div>

---

## ✨ Features

| Category | Details |
|----------|---------|
| **Facial Recognition** | FaceNet 512-d embeddings, cosine similarity matching, real-time RTSP processing |
| **Access Control** | Membership validation, time/day/location rules, automatic grant/deny |
| **Member Management** | Full CRUD, enrollment status tracking, consent management |
| **Membership Plans** | Plan templates with duration & pricing, auto-calculated end dates |
| **Multi-Camera** | Multiple simultaneous RTSP streams, configurable FPS per camera |
| **Biometric Security** | AES-256-GCM encrypted templates, key versioning, secure storage |
| **Admin Dashboard** | React SPA with MUI, charts, member & camera management |
| **Kiosk Mode** | Dedicated full-screen access terminal for member check-in |

---

## 🏗 Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Nginx (reverse proxy)                  │
│              ┌─────────────┬──────────────┐              │
│              │  Frontend   │  Backend API │              │
│              │  (React)    │  (FastAPI)   │              │
│              └─────────────┴──────┬───────┘              │
└──────────────────────────────────┼───────────────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
              ┌─────▼───┐   ┌─────▼────┐   ┌────▼─────┐
              │PostgreSQL│   │  Redis   │   │CV Service│
              │          │   │ (cache)  │   │ (FaceNet)│
              │ Members  │   │ Templates│   │          │
              │ Sales    │   │ Queue    │   │ Detect   │
              │ Events   │   │          │   │ Recognize│
              └──────────┘   └──────────┘   │ Validate │
                                            └────┬─────┘
                                                 │
                                    ┌────────────┼────────────┐
                                    │            │            │
                              ┌─────▼──┐   ┌────▼───┐  ┌────▼───┐
                              │Camera 1│   │Camera 2│  │Camera N│
                              │ (RTSP) │   │ (RTSP) │  │ (RTSP) │
                              └────────┘   └────────┘  └────────┘
```

### Recognition Pipeline

```
RTSP Stream → Frame Extraction → Face Detection (Haar Cascade)
    → Quality Assessment → FaceNet Embedding (512-d)
    → Template Matching (cosine similarity ≥ 0.85)
    → Access Validation (member status + membership + rules)
    → Event Log → Access Granted / Denied
```

---

## 🛠 Tech Stack

### Backend
| Technology | Purpose |
|-----------|---------|
| **FastAPI 0.109** | REST API framework |
| **SQLAlchemy 2.0** | ORM with PostgreSQL |
| **Alembic** | Database migrations |
| **Pydantic v2** | Data validation & settings |
| **python-jose** | JWT authentication |
| **cryptography** | AES-256-GCM biometric encryption |
| **Redis** | Template caching & queue |
| **OpenCV** | Image processing |

### Computer Vision Service
| Technology | Purpose |
|-----------|---------|
| **FaceNet (PyTorch)** | 512-d face embeddings via InceptionResnetV1 |
| **VGGFace2** | Pretrained weights |
| **OpenCV** | Face detection (Haar Cascade), video processing |
| **Redis** | Template cache for real-time matching |
| **RTSP** | Multi-camera stream processing |

### Frontend
| Technology | Purpose |
|-----------|---------|
| **React 18** | UI framework |
| **TypeScript** | Type safety |
| **MUI v5** | Material Design components |
| **TanStack Query** | Server state management |
| **React Hook Form + Zod** | Form validation |
| **Recharts / Chart.js** | Analytics & charts |
| **Vite** | Build tool |

### Infrastructure
| Technology | Purpose |
|-----------|---------|
| **PostgreSQL 14** | Primary database |
| **Redis** | Cache & message queue |
| **Nginx** | Reverse proxy & static files |
| **Systemd** | Service management |
| **Ubuntu Server** | Host OS |

---

## 🚀 Getting Started

### Prerequisites

- Ubuntu Server 22.04+ (or similar Linux)
- PostgreSQL 14+
- Redis 6+
- Python 3.10+
- Node.js 18+

### Environment Setup

Each component needs its own `.env` file.

**Backend** (`backend/.env`):
```env
DATABASE_URL=postgresql://user:pass@localhost:5432/facegym
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=<generate-with-openssl-rand-hex-32>
ENCRYPTION_KEY=<generate-with-openssl-rand-hex-32>
JWT_SECRET=<generate-with-openssl-rand-hex-32>
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<change-me>
CORS_ORIGINS=http://yourdomain.com
```

**Frontend** (`frontend/.env`):
```env
VITE_API_URL=http://yourdomain.com/api
```

### Installation

#### Backend
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Initialize database
python init_db.py

# Run migrations
alembic upgrade head

# Start server
uvicorn main:app --host 0.0.0.0 --port 8000
```

#### Frontend
```bash
cd frontend
npm install
npm run build    # Production build -> dist/
npm run dev      # Development server -> localhost:3000
```

#### CV Service
```bash
cd cv_service
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start service
python main.py
```

### Systemd Services

```bash
# Start all services
systemctl start powerhouse-backend powerhouse-cv nginx

# Enable on boot
systemctl enable powerhouse-backend powerhouse-cv nginx

# Check status
systemctl status powerhouse-backend
systemctl status powerhouse-cv
```

---

## 📁 Project Structure

```
FaceGYM/
├── backend/                    # FastAPI backend
│   ├── main.py                # App entry point, routers, middleware
│   ├── api/                   # API endpoints
│   │   ├── auth.py           # JWT login/token
│   │   ├── members.py        # Member CRUD
│   │   ├── memberships.py    # Membership management
│   │   ├── membership_plans.py # Plan templates
│   │   ├── enrollment.py     # Face enrollment + verification
│   │   ├── cameras.py        # Camera CRUD
│   │   ├── events.py         # Access events
│   │   ├── sales.py          # Sales transactions
│   │   ├── users.py          # User management
│   │   ├── settings.py       # App settings
│   │   ├── cv_internal.py    # Internal CV endpoints (no auth)
│   │   └── health.py         # Health checks
│   ├── core/                  # Core utilities
│   │   ├── config.py         # Pydantic settings
│   │   ├── database.py       # SQLAlchemy session
│   │   ├── security.py       # JWT + bcrypt
│   │   └── encryption.py     # AES-256-GCM
│   ├── models/                # SQLAlchemy models
│   │   ├── member.py         # Member (status, enrollment tracking)
│   │   ├── biometric.py      # Encrypted face templates
│   │   ├── membership.py     # Memberships + plans
│   │   ├── camera.py         # RTSP cameras
│   │   ├── event.py          # Access events
│   │   ├── sale.py           # Sales transactions
│   │   ├── setting.py        # App settings
│   │   └── user.py           # Admin users
│   ├── schemas/               # Pydantic request/response schemas
│   ├── alembic/               # Database migrations
│   ├── init_db.py            # DB initialization + admin user
│   ├── reset_admin_password.py
│   └── requirements.txt
│
├── cv_service/                 # Computer Vision service
│   ├── main.py                # FastAPI + CV service orchestrator
│   ├── config.py              # CV settings
│   ├── detection/
│   │   ├── face_detector.py  # Haar Cascade face detection
│   │   └── quality_assessor.py # Image quality metrics
│   ├── recognition/
│   │   ├── face_recognizer.py    # FaceNet embedding generation
│   │   ├── template_cache.py     # Redis template cache
│   │   └── template_matcher.py   # Cosine similarity matching
│   ├── stream/
│   │   └── rtsp_processor.py     # RTSP multi-camera handler
│   ├── validation/
│   │   └── access_validator.py   # Member + membership rules engine
│   ├── api/
│   │   └── backend_client.py     # Backend HTTP client
│   └── requirements.txt
│
├── frontend/                   # React SPA
│   ├── src/
│   │   ├── App.tsx            # Routes (dashboard, members, kiosk, etc.)
│   │   ├── api/               # Axios API clients
│   │   ├── components/        # Layout, ProtectedRoute, UserManagement
│   │   ├── contexts/          # AuthContext
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Login.tsx
│   │   │   ├── Members/       # List, Form, FaceEnrollment
│   │   │   ├── Memberships/   # List, Form
│   │   │   ├── Cameras/       # CamerasList
│   │   │   ├── Kiosk/         # Kiosk (access terminal)
│   │   │   ├── Reports/       # Reports & analytics
│   │   │   └── Settings/      # App settings
│   │   └── theme/             # MUI theme
│   ├── package.json
│   └── vite.config.ts
│
├── scripts/                    # Operational scripts
│   ├── backup.sh              # DB + data backup
│   ├── restore.sh             # Backup restoration
│   ├── health_monitor.sh      # Service health monitoring
│   └── fix_nginx.sh           # Nginx config repair
│
└── .gitignore
```

---

## 📡 API Reference

The backend exposes a RESTful API with auto-generated documentation:

| URL | Description |
|-----|-------------|
| `/docs` | Swagger UI (interactive) |
| `/redoc` | ReDoc documentation |

### Key Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| **Auth** | | |
| `POST` | `/api/auth/login` | Login, returns JWT token |
| **Members** | | |
| `GET` | `/api/members` | List members (paginated) |
| `POST` | `/api/members` | Create member |
| `GET` | `/api/members/{id}` | Get member details |
| `PUT` | `/api/members/{id}` | Update member |
| `DELETE` | `/api/members/{id}` | Delete member |
| **Enrollment** | | |
| `POST` | `/api/enrollment/{id}/enroll` | Enroll face from image upload |
| `POST` | `/api/enrollment/{id}/enroll/camera` | Enroll face from RTSP camera |
| `DELETE` | `/api/enrollment/{id}/enroll` | Remove biometric enrollment |
| `POST` | `/api/enrollment/{id}/verify` | Verify face against enrollment |
| **Memberships** | | |
| `GET` | `/api/memberships` | List memberships |
| `POST` | `/api/memberships` | Create membership |
| `GET` | `/api/membership-plans` | List membership plan templates |
| **Cameras** | | |
| `GET` | `/api/cameras` | List cameras |
| `POST` | `/api/cameras` | Add camera |
| **Events** | | |
| `GET` | `/api/events` | List access events |
| **CV Internal** (no auth) | | |
| `GET` | `/api/cv/templates` | Sync face templates to CV service |
| `GET` | `/api/cv/cameras` | Get enabled cameras for CV service |
| `GET` | `/api/cv/members/{id}/membership` | Check member membership |
| **Health** | | |
| `GET` | `/api/health` | Basic health check |
| `GET` | `/api/health/full` | Full system health (DB, Redis) |

---

## 🔒 Security

### Biometric Data Protection
- **AES-256-GCM** encryption for all facial templates at rest
- Random IV per encryption operation
- Authentication tags for tamper detection
- Key versioning (`encryption_key_id`) for rotation
- Templates stored separately from member PII

### Authentication
- **JWT** (HS256) with configurable expiration (24h default)
- **bcrypt** password hashing
- Token-based protected routes in frontend
- Role-based access control (RBAC)

### API Security
- Rate limiting (120 req/min via SlowAPI)
- CORS configured per environment
- Nginx reverse proxy with body size limits
- Internal CV endpoints (localhost only, no auth)

### Data Privacy
- Member consent tracking (`consent_given_at`)
- Biometric data deletion support
- Audit logging for all access events

---

## ⚙️ Configuration

### Key Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `SECRET_KEY` | App secret key | Required |
| `ENCRYPTION_KEY` | AES-256 key for biometrics | Required |
| `JWT_SECRET` | JWT signing key | Required |
| `FACE_CONFIDENCE_THRESHOLD` | Recognition match threshold | `0.85` |
| `ENROLLMENT_QUALITY_THRESHOLD` | Min quality for enrollment | `0.90` |
| `USE_GPU` | Enable CUDA for CV service | `false` |
| `CORS_ORIGINS` | Allowed origins (comma-separated) | `http://localhost` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT token lifetime | `1440` (24h) |

### Generating Secure Keys
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## 📊 Database Schema

```
users ──────────────────────────────────────────
members ───┬── biometric_templates (1:1)
           ├── memberships (1:N) ─── membership_plans
           ├── sales_transactions (1:N)
           └── access_events (1:N)
cameras ───┴── access_events (1:N)
settings ───────────────────────────────────────
```

---

## 🔧 Operational Scripts

| Script | Purpose |
|--------|---------|
| `scripts/backup.sh` | Automated DB + data backup with retention |
| `scripts/restore.sh` | Restore from backup |
| `scripts/health_monitor.sh` | Monitor service health |
| `scripts/fix_nginx.sh` | Repair Nginx configuration |

---

## 📋 Status

| Component | Completion |
|-----------|-----------|
| Backend API | ~85% |
| Frontend UI | ~75% |
| CV Service | ~65% |
| Database Schema | ~95% |
| Deployment | ~95% |
| Testing | ~30% |

---

## 📝 License

Proprietary — All rights reserved.

<div align="center">
Built for PowerHouse Gym Manizales
</div>
