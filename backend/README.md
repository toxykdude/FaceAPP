# PowerHouse Membership Platform - Backend

FastAPI backend for the PowerHouse Membership Platform with facial recognition.

## Features

- **Authentication**: JWT-based authentication with role-based access control (RBAC)
- **Member Management**: CRUD operations for gym members
- **Biometric Security**: AES-256 encryption for facial templates
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Caching**: Redis for active member templates
- **API Documentation**: Auto-generated OpenAPI/Swagger docs

## Project Structure

```
backend/
├── main.py                 # FastAPI application entry point
├── requirements.txt        # Python dependencies
├── init_db.py             # Database initialization script
├── alembic.ini            # Alembic configuration
├── alembic/               # Database migrations
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py
├── api/                   # API endpoints
│   ├── auth.py           # Authentication endpoints
│   ├── members.py        # Members CRUD
│   ├── health.py         # Health checks
│   └── deps.py           # FastAPI dependencies
├── core/                  # Core utilities
│   ├── config.py         # Settings (Pydantic)
│   ├── database.py       # Database session
│   ├── security.py       # Password hashing, JWT
│   └── encryption.py     # AES-256 encryption
├── models/                # SQLAlchemy models
│   ├── user.py
│   ├── member.py
│   ├── membership.py
│   ├── sale.py
│   ├── event.py
│   ├── camera.py
│   └── biometric.py
└── schemas/               # Pydantic schemas
    ├── common.py
    ├── user.py
    └── member.py
```

## Prerequisites

- Python 3.10+
- PostgreSQL 14+
- Redis 6+

## Installation

### 1. Create Virtual Environment

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Create `.env` file in the project root:

```bash
# Database
DATABASE_URL=postgresql://membership:password@localhost:5432/membership_db

# Redis
REDIS_URL=redis://localhost:6379/0

# Security (generate strong keys!)
SECRET_KEY=your-secret-key-min-32-chars
ENCRYPTION_KEY=your-aes-256-key-base64-encoded
JWT_SECRET=your-jwt-secret-key

# Application
DEBUG=false
ENVIRONMENT=production
API_PORT=8000
```

### 4. Initialize Database

```bash
# Run migrations
alembic upgrade head

# Or use init script (creates tables + admin user)
python init_db.py
```

### 5. Run Development Server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## API Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

### Authentication

- `POST /api/auth/login` - Login with username/password
- `POST /api/auth/logout` - Logout
- `GET /api/auth/me` - Get current user info

### Members

- `GET /api/members` - List members (paginated)
- `POST /api/members` - Create member
- `GET /api/members/{id}` - Get member
- `PUT /api/members/{id}` - Update member
- `DELETE /api/members/{id}` - Delete member
- `GET /api/members/{id}/biometric-status` - Check enrollment status

### Health

- `GET /api/health` - Basic health check
- `GET /api/health/db` - Database health
- `GET /api/health/redis` - Redis health
- `GET /api/health/full` - Comprehensive health check

## Database Migrations

### Create New Migration

```bash
alembic revision --autogenerate -m "Description of changes"
```

### Apply Migrations

```bash
alembic upgrade head
```

### Rollback Migration

```bash
alembic downgrade -1
```

## Default Credentials

After running `init_db.py`:

- **Username**: `admin`
- **Password**: `admin123`

⚠️ **Change the admin password immediately in production!**

## Security

### Password Hashing

Passwords are hashed using bcrypt with automatic salt generation.

### JWT Tokens

- Algorithm: HS256
- Expiration: 24 hours (configurable)
- Payload: `{"sub": user_id, "exp": timestamp}`

### Biometric Data Encryption

- Algorithm: AES-256-GCM
- Key: 256-bit key from `ENCRYPTION_KEY` environment variable
- IV: Randomly generated per encryption (16 bytes)
- Authentication tag: Included with ciphertext

## Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html
```

## Production Deployment

### 1. Use Production WSGI Server

```bash
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 2. Enable HTTPS

Configure reverse proxy (Nginx) with SSL/TLS certificates.

### 3. Secure Environment Variables

- Use strong, randomly generated keys
- Never commit `.env` to version control
- Use environment-specific configurations

### 4. Database Connection Pooling

Already configured in `core/database.py`:
- Pool size: 10
- Max overflow: 20
- Pre-ping: Enabled

## Troubleshooting

### Database Connection Error

```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Test connection
psql -U membership -d membership_db
```

### Redis Connection Error

```bash
# Check Redis is running
sudo systemctl status redis-server

# Test connection
redis-cli ping
```

### Import Errors

```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

## Development

### Code Style

```bash
# Format code
black .

# Lint code
flake8 .

# Type checking
mypy .
```

### Adding New Endpoints

1. Create Pydantic schemas in `schemas/`
2. Create API router in `api/`
3. Register router in `main.py`
4. Add tests in `tests/`

## License

Proprietary - PowerHouse Membership Platform

## Support

For issues and questions, refer to:
- [Installation Guide](../docs/INSTALLATION.md)
- [Troubleshooting Guide](../docs/TROUBLESHOOTING.md)
