#!/bin/bash
# FaceGYM — AI-Powered Membership Management Platform
# One-click installer for Ubuntu 22.04+
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}"
echo "============================================"
echo "   FaceGYM — Installer"
echo "   AI-Powered Membership Management"
echo "============================================"
echo -e "${NC}"

# Check root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root: sudo ./install.sh${NC}"
    exit 1
fi

APP_DIR="${APP_DIR:-/opt/powerhouse-membership}"
DB_NAME="${DB_NAME:-membership_db}"
DB_USER="${DB_USER:-membership}"
DB_PASS="${DB_PASS:-$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)}"
DOMAIN="${DOMAIN:-}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-admin123}"

echo -e "${YELLOW}Installing in: ${APP_DIR}${NC}"

# 1. System dependencies
echo -e "${GREEN}[1/8] Installing system dependencies...${NC}"
# samba-client: SMB replication (smbclient) · sshpass: SFTP replication (sshpass -e)
apt-get update
apt-get install -y \
    python3 python3-pip python3-venv \
    nodejs npm \
    postgresql postgresql-contrib \
    nginx \
    libgl1 libglib2.0-0 \
    libsm6 libxext6 libxrender-dev \
    ffmpeg \
    curl wget git \
    python3-pil \
    ufw \
    samba-client sshpass

# 2. Database setup
echo -e "${GREEN}[2/8] Setting up PostgreSQL...${NC}"
sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME};" 2>/dev/null || true
sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';" 2>/dev/null || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};" 2>/dev/null || true

# 3. Application setup
echo -e "${GREEN}[3/8] Installing application...${NC}"
cd "${APP_DIR}"

# Backend
cd backend
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
cd ..

# CV Service
cd cv_service
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt 2>/dev/null || \
    ./venv/bin/pip install fastapi uvicorn opencv-python-headless numpy pillow sqlalchemy psycopg2-binary python-jose[cryptography] passlib[bcrypt] python-multipart apscheduler
cd ..

# Frontend
cd frontend
npm install
npm run build
cd ..

# 4. Environment configuration
echo -e "${GREEN}[4/8] Generating configuration...${NC}"
SECRET_KEY=$(openssl rand -hex 32)
ENCRYPTION_KEY=$(openssl rand -hex 16)
JWT_SECRET=$(openssl rand -hex 32)

cat > backend/.env << EOF
# Database
DATABASE_URL=postgresql://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}

# Security
SECRET_KEY=${SECRET_KEY}
ENCRYPTION_KEY=${ENCRYPTION_KEY}
JWT_SECRET=${JWT_SECRET}

# Admin
ADMIN_USERNAME=${ADMIN_USER}
ADMIN_PASSWORD=${ADMIN_PASS}

# Email (configure later)
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=noreply@facegym.local

# Frontend
FRONTEND_URL=http://localhost
CORS_ORIGINS=http://localhost
EOF

# CV service also needs DB access
cp backend/.env cv_service/.env

# 5. Create directories
echo -e "${GREEN}[5/8] Creating data directories...${NC}"
mkdir -p /var/lib/powerhouse/snapshots
mkdir -p /var/lib/powerhouse/member-photos
mkdir -p /var/lib/powerhouse/uploads

# 6. Initialize database
echo -e "${GREEN}[6/8] Initializing database...${NC}"
cd backend
./venv/bin/python -c "
from core.database import engine, Base
from models import *
Base.metadata.create_all(bind=engine)
print('Database tables created')
" 2>/dev/null || echo "Tables may already exist, continuing..."

# Seed default settings
./venv/bin/python -c "
from core.database import SessionLocal
from models.setting import Setting
db = SessionLocal()
defaults = [
    Setting(key='business_name', value='My Gym', category='general', description='Organization name'),
    Setting(key='currency', value='USD', category='membership', description='Currency code'),
    Setting(key='min_confidence', value=0.75, category='access', description='Min face confidence'),
    Setting(key='door_open_duration', value=5, category='access', description='Door open seconds'),
    Setting(key='passback_cooldown', value=60, category='access', description='Anti-passback cooldown'),
    Setting(key='deny_unknown', value=True, category='access', description='Deny unknown faces'),
    Setting(key='payment_grace_period', value=3, category='membership', description='Grace period days'),
    Setting(key='data_retention_days', value=90, category='system', description='Log retention'),
    Setting(key='debug_mode', value=False, category='system', description='Debug logging'),
]
for s in defaults:
    if not db.query(Setting).filter(Setting.key == s.key).first():
        db.add(s)
db.commit()
print('Default settings seeded')
" 2>/dev/null || echo "Settings may already exist, continuing..."
cd ..

# 7. Systemd services
echo -e "${GREEN}[7/8] Creating systemd services...${NC}"

cat > /etc/systemd/system/facegym-backend.service << EOF
[Unit]
Description=FaceGYM Backend API
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}/backend
ExecStart=${APP_DIR}/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
Environment=PATH=${APP_DIR}/backend/venv/bin:/usr/bin

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/facegym-cv.service << EOF
[Unit]
Description=FaceGYM Computer Vision Service
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}/cv_service
ExecStart=${APP_DIR}/cv_service/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=5
Environment=PATH=${APP_DIR}/cv_service/venv/bin:/usr/bin

[Install]
WantedBy=multi-user.target
EOF

# Backup oneshot service + 30-minute timer (remote-backup spec).
# Units are authored under scripts/systemd/ and copied verbatim so the repo
# remains the single source of truth.
cp "${APP_DIR}/scripts/systemd/powerhouse-backup.service" /etc/systemd/system/ 2>/dev/null || true
cp "${APP_DIR}/scripts/systemd/powerhouse-backup.timer" /etc/systemd/system/ 2>/dev/null || true
chmod 644 /etc/systemd/system/powerhouse-backup.service /etc/systemd/system/powerhouse-backup.timer 2>/dev/null || true

systemctl daemon-reload
systemctl enable facegym-backend facegym-cv
systemctl start facegym-backend facegym-cv
# Arm the scheduled backup timer (OnCalendar=*:0/30, Persistent=true). We
# enable+start the TIMER only — the oneshot service runs on schedule, not now.
systemctl enable --now powerhouse-backup.timer 2>/dev/null || true

# 8. Nginx configuration
echo -e "${GREEN}[8/8] Configuring Nginx...${NC}"

cat > /etc/nginx/sites-available/facegym << 'NGINX'
server {
    listen 80;
    server_name _;

    client_max_body_size 20M;

    # Frontend
    location / {
        root /opt/powerhouse-membership/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # API proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # CV service proxy
    location /cv/ {
        proxy_pass http://127.0.0.1:8001/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }

    # API docs
    location /docs {
        proxy_pass http://127.0.0.1:8000;
    }
    location /openapi.json {
        proxy_pass http://127.0.0.1:8000;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/facegym /etc/nginx/sites-enabled/facegym
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

# Done
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}   FaceGYM installed successfully!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "  URL:      ${YELLOW}http://$(hostname -I | awk '{print $1}')${NC}"
echo -e "  Login:    ${YELLOW}${ADMIN_USER} / ${ADMIN_PASS}${NC}"
echo -e "  Docs:     ${YELLOW}http://$(hostname -I | awk '{print $1}')/docs${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Login and change the admin password"
echo "  2. Go to Settings → set your organization name & logo"
echo "  3. Add your cameras in the Cameras section"
echo "  4. Configure SMTP in backend/.env for email reports"
echo ""
echo -e "${RED}⚠️  IMPORTANT: Change the admin password immediately!${NC}"
echo ""
