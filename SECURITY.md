# 🔐 SECURITY.md — Guía de Seguridad para FaceGYM

> **Para agentes de IA / desarrolladores:** Este archivo es tu contrato de seguridad. Antes de generar cualquier código que toque autenticación, base de datos, datos biométricos, pagos o variables de entorno, lee la sección correspondiente. No asumas que algo es seguro porque "funciona".

---

## 📋 Índice

1. [Flujo de la Arquitectura](#1-flujo-de-la-arquitectura)
2. [Variables de Entorno y Secretos](#2-variables-de-entorno-y-secretos)
3. [Autenticación JWT y RBAC](#3-autenticación-jwt-y-rbac)
4. [Encriptación y Datos Biométricos](#4-encriptación-y-datos-biométricos)
5. [Validación y Sanitización de Inputs](#5-validación-y-sanitización-de-inputs)
6. [Seguridad del CV Service](#6-seguridad-del-cv-service)
7. [Pagos con Wompi](#7-pagos-con-wompi)
8. [OWASP Top 10 — Aplicado a FaceGYM](#8-owasp-top-10--aplicado-a-facegym)
9. [Procedimiento de Respuesta a Incidentes](#9-procedimiento-de-respuesta-a-incidentes)
10. [Checklist Pre-Deploy](#10-checklist-pre-deploy)
11. [Qué NUNCA hacer](#11-qué-nunca-hacer)

---

## 1. Flujo de la Arquitectura

Entender este flujo es crítico antes de escribir cualquier línea de código.

```
┌─────────────────────────────────────────────────────────────────┐
│                    CLIENTE (Browser / Kiosk)                     │
│                                                                 │
│  - React + Vite + MUI                                           │
│  - Solo ve respuestas de la API, nunca secrets                  │
│  - JWT almacenado en localStorage (auth_token)                  │
│  - Cámara web via HTTPS para enrollment                         │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTPS (Cloudflare Tunnel)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CLOUDFLARE (Edge)                             │
│                                                                 │
│  - TLS termination + HSTS                                       │
│  - DDoS protection                                              │
│  - WAF rules                                                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    NGINX (Reverse Proxy)                         │
│                                                                 │
│  - Rate limiting: 5/min login, 120/min general                  │
│  - Security headers (CSP, X-Frame, HSTS, etc.)                 │
│  - /api/cv/ BLOQUEADO desde exterior (solo localhost)           │
│  - /api/portal/webhook-* sin JWT (server-to-server)             │
└───────────┬──────────────────────────────┬──────────────────────┘
            │                              │
            ▼                              ▼
┌────────────────────────┐   ┌───────────────────────────────────┐
│  FASTAPI (Backend)      │   │  CV SERVICE (Python)              │
│  UVicorn :8000          │   │  UVicorn :8001                    │
│                         │   │                                   │
│  - JWT auth + RBAC      │◄──│  - FaceNet + MTCNN                │
│  - Pydantic validation  │   │  - OpenCV RTSP processing         │
│  - bcrypt passwords     │   │  - Template cache (Redis)         │
│  - AES-256-GCM encrypt  │   │  - API Key auth (configurar!)    │
│                         │   │  - MJPEG stream (/stream/:id)     │
│  ┌────────┐ ┌────────┐ │   │  - WebSocket (/ws/camera/:id)     │
│  │PostgreSQL│ │ Redis  │ │   └───────────────────────────────────┘
│  │         │ │        │ │                  │
│  │Members  │ │Cache   │ │                  │ RTSP
│  │Biometric│ │Tokens  │ │                  ▼
│  │Sales    │ │Rate lim│ │   ┌───────────────────────────────────┐
│  │Audit    │ │Pending │ │   │  CÁMARAS RTSP (Red Local)         │
│  └────────┘ └────────┘ │   │  - Credenciales encriptadas en DB │
│                         │   │  - Acceso solo desde CV Service   │
│  WOMPI ──► Webhook      │   └───────────────────────────────────┘
│  (server-to-server)     │
└─────────────────────────┘
```

**Regla de oro:** Si el código se ejecuta en el browser (React), asume que el usuario puede ver TODO lo que está en ese código. Los secrets solo existen en el servidor.

---

## 2. Variables de Entorno y Secretos

### Tabla de variables

| Variable | Dónde va | Pública? | Propósito |
|----------|----------|----------|-----------|
| `DATABASE_URL` | Backend (.env) | **NO** | Connection string PostgreSQL |
| `REDIS_URL` | Backend (.env) | **NO** | Connection string Redis |
| `JWT_SECRET` | Backend (.env) | **NO** | Firma de tokens JWT (HS256) |
| `ENCRYPTION_KEY` | Backend (.env) | **NO** | Key AES-256 para biometría y RTSP |
| `SECRET_KEY` | Backend (.env) | **NO** | Secret general de la app |
| `EVOLUTION_API_KEY` | Backend (.env) | **NO** | WhatsApp bot API key |
| `SMTP_PASSWORD` | Backend (.env) | **NO** | Password del servidor SMTP |
| `WOMPI_PUBLIC_KEY` | Frontend (.env) | Sí (pub) | Key pública Wompi (widget) |
| `WOMPI_INTEGRITY_SECRET` | Backend (.env) | **NO** | Verificación de firma webhooks |
| `CORS_ORIGINS` | Backend (.env) | N/A | Dominios permitidos |
| `ADMIN_PASSWORD` | Backend (.env) | **NO** | Password inicial del admin |
| `API_KEY` | CV Service (.env) | **NO** | Auth del CV Service |
| `BACKUP_DATABASE_URL` | `/etc/faceapp/backup-db.env` (0600, solo root) | **NO** | Rol `powerhouse_backup` (BYPASSRLS) para respaldos y export de BD |
| `MIGRATE_DATABASE_URL` | `/etc/faceapp/migrate-db.env` (0600, solo root) | **NO** | Rol `powerhouse_migrator`, dueño de las tablas, usado solo por Alembic en el despliegue |

### Separación de privilegios en la base de datos

El rol de tiempo de ejecución (`backend_app`) **no es dueño de ninguna tabla**, y
esto es deliberado. Ser dueño de una tabla permite `DROP TABLE`, permite
`ALTER TABLE ... DISABLE ROW LEVEL SECURITY`, y **omite RLS en toda tabla que no
declare FORCE ROW LEVEL SECURITY** — solo `audit_logs` lo declara; las otras 12
tablas con RLS, incluidas `biometric_templates` y `fingerprint_templates`, no.

Otorgarle esa autoridad al rol expuesto a Internet sería una escalada de
privilegios permanente. Por eso la autoridad DDL vive en un rol separado
(`powerhouse_migrator`, sin superusuario y con `NOBYPASSRLS`) que solo se usa
durante el despliegue. Ver
[`scripts/migrations/002_migration_role.sql`](./scripts/migrations/002_migration_role.sql)
y AGENTS.md trampa 20.

Al agregar una tabla en una migración: los privilegios por defecto cubren los
`GRANT`, **no** la seguridad a nivel de fila. Toda tabla nueva con datos
asociados a un miembro debe habilitar RLS y definir sus políticas explícitamente.

### ⚠️ Defaults peligrosos en config.py

Estos valores hardcoded DEBEN ser reemplazados en producción:

```python
# ❌ PELIGROSO — valores por defecto en código
ADMIN_PASSWORD: str = "admin123"
EVOLUTION_API_KEY: str = "UJrZ7tMU93YaNX"
API_KEY: str = ""  # CV Service auth deshabilitada si está vacío
```

**Acción requerida:** Configurar `.env` con valores seguros. Si la env var no está seteada, el sistema usa estos defaults inseguros.

### .gitignore mínimo requerido

```gitignore
.env
.env.local
.env.*.local
.env.production
*.pem
*.key
*.crt
uploads/
snapshots/
biometric_data/
```

### Para el agente de IA

- **Nunca** hardcodees secrets en código fuente, ni como "placeholder temporal".
- Si agregas un nuevo secret, inclúyelo como `Field(default="")` en config.py y documentalo en esta tabla.
- Verifica que `.env` esté en `.gitignore` antes de hacer commit.

---

## 3. Autenticación JWT y RBAC

### Flujo de autenticación

```
Login Request (username + password)
        │
        ▼
┌─────────────────────────────┐
│  bcrypt.verify_password()    │
│  (passlib, rounds=12)        │
└──────────┬──────────────────┘
           │ OK
           ▼
┌─────────────────────────────┐
│  create_access_token()       │
│  JWT HS256 + expiry 24h     │
│  payload: {sub, exp}        │
└──────────┬──────────────────┘
           │
           ▼
  Response: {access_token, user}
  Frontend guarda en localStorage
```

### Verificación en cada request

```python
# backend/api/deps.py — Verificación en cada endpoint protegido

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(HTTPBearer()),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials

    # 1. Decodificar JWT
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])

    # 2. Verificar blacklist (Redis) — tokens de logout
    if await is_token_blacklisted(token):
        raise HTTPException(401, "Token revocado")

    # 3. Buscar usuario en DB
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(401, "Usuario inactivo")

    return user
```

### Jerarquía de roles

| Dependency | Admin | Staff | Miembro (Portal) |
|---|---|---|---|
| `get_current_user` | ✅ | ✅ | ❌ |
| `require_admin` | ✅ | ❌ | ❌ |
| `require_staff` | ✅ | ✅ | ❌ |
| `require_page("reports")` | ✅ | Si tiene permiso | ❌ |
| `get_current_member` | ❌ | ❌ | ✅ |

### Permisos por página (RBAC granular)

```python
# backend/api/deps.py — Permisos granulares por página

def require_page(page: str):
    async def _require_page(current_user: User = Depends(get_current_user)):
        if current_user.role == "admin":
            return current_user  # Admin tiene acceso total
        pages = current_user.permissions.get("pages", [])
        if "all" not in pages and page not in pages:
            raise HTTPException(403, f"Sin acceso a '{page}'")
        return current_user
    return _require_page
```

```typescript
// frontend/src/components/RequirePermission.tsx — Guard en rutas

export const RequirePermission: React.FC<{ page: string; children: React.ReactNode }> = ({ page, children }) => {
    const { user } = useAuth();
    if (user?.role === "admin") return <>{children}</>;
    const pages = (user as any).permissions?.pages || [];
    if (pages.includes("all") || pages.includes(page)) return <>{children}</>;
    return <Navigate to="/" replace />; // Sin permiso → dashboard
};
```

### Portal de miembros (WhatsApp PIN)

```python
# backend/api/portal_auth.py — Autenticación de miembros via WhatsApp

# Flujo:
# 1. POST /portal/auth/send-pin {phone} → genera PIN 6 dígitos, 5min TTL
# 2. PIN enviado via Evolution API (WhatsApp)
# 3. POST /portal/auth/verify-pin {phone, pin} → JWT con type="member"
# 4. Rate limiting: 60s cooldown, 3 intentos max, 10min lockout
```

### Reglas de autenticación

- **Siempre** usa `get_current_user` (verifica JWT contra servidor), no confíes en datos del cliente.
- El JWT se **revoca activamente** via Redis blacklist en logout.
- Passwords hasheados con **bcrypt** (rounds automáticos de passlib).
- Rate limiting en login: **5 requests/minuto** por IP (Nginx).
- Tokens del portal miembro tienen `type: "member"` — no pueden acceder a endpoints de admin/staff.

---

## 4. Encriptación y Datos Biométricos

### Algoritmo: AES-256-GCM

```python
# backend/core/encryption.py — Encriptación de datos biométricos

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os, base64

def encrypt_biometric_data(data: bytes) -> bytes:
    """
    Encripta datos biométricos (embeddings FaceNet) con AES-256-GCM.

    Retorna: IV (16 bytes) + GCM auth tag (16 bytes) + ciphertext
    - IV aleatorio por cada operación (nunca reutilizar)
    - GCM tag provee integridad + autenticidad
    """
    key = _derive_key()  # 32 bytes desde ENCRYPTION_KEY env var
    iv = os.urandom(16)  # Nonce aleatorio
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, data, None)
    return iv + ciphertext  # IV + tag + encrypted

def encrypt_string(data: str) -> str:
    """Encripta strings (ej. RTSP URLs) → base64 para almacenamiento en DB."""
    encrypted = encrypt_biometric_data(data.encode('utf-8'))
    return base64.b64encode(encrypted).decode('ascii')
```

### Flujo de datos biométricos

```
Enrollment (1 foto → 6 embeddings promediados)
    │
    ▼ embedding (512 floats → JSON bytes)
    │
    ▼ AES-256-GCM encrypt (IV random + key from ENCRYPTION_KEY)
    │
    ▼ Store in DB: biometric_templates.template_data (bytes encrypted)
    │
    │ --- Matching ---
    ▼
    ▼ Decrypt template_data
    ▼ Cosine similarity vs query embedding
    ▼ If score >= threshold → recognized
```

### ⚖️ Habeas Data Colombiano — Datos Biométricos

Los datos faciales (embeddings FaceNet) son **datos biométricos** protegidos por la **Ley 1581 de 2012** (Protección de Datos Personales) y el **Decreto 1377 de 2013**, con consideraciones especiales por ser datos sensibles.

#### Requisitos legales y cómo FaceGYM los cumple

| Requisito Legal | Implementación en FaceGYM |
|---|---|
| **Autorización previa, expresa e informada** (Art. 9, Ley 1581) | Campo `consent_given` en tabla `members`. Checkbox de consentimiento durante enrollment. `consent_given_at` registra timestamp. |
| **Finalidad legítima** (Art. 4) | Solo para control de acceso físico al gimnasio. No se comparte con terceros. |
| **Derecho de acceso** (Art. 8, literal a) | Endpoint `GET /api/members/{id}/enrollment/status` permite consultar si tiene datos biométricos registrados. |
| **Derecho de rectificación** (Art. 8, literal b) | Re-enrollment: `DELETE` + `POST` del template biométrico actualiza los datos. |
| **Derecho de supresión** (Art. 8, literal e) | `DELETE /api/enrollment/{member_id}/enroll` elimina el template biométrico. El miembro puede solicitarlo en cualquier momento. |
| **Medidas de seguridad** (Art. 19, literal f) | AES-256-GCM para datos en reposo. TLS 1.2+ para datos en tránsito. Aislamiento de red para CV Service. |
| **Registro ante la SIC** (Art. 24) | ⚠️ **PENDIENTE:** La base de datos con información biométrica debe registrarse ante la Superintendencia de Industria y Comercio. |
| **Revocatoria de autorización** (Art. 8, literal g) | Al eliminar el enrollment (DELETE), el miembro revoca su autorización. Sistema debe dejar de reconocer al miembro inmediatamente. |
| **Notificación de vulneración** (Art. 22) | Procedimiento de respuesta a incidentes (Sección 9). Notificación a la SIC y al titular dentro de los plazos legales. |
| **Base de datos categories** | Datos biométricos = **datos sensibles** (Art. 5, literal c). Tratamiento requiere autorización expresa, no tácita. |

#### Checklist de cumplimiento Habeas Data

- [x] Autorización expresa del titular antes de capturar datos biométricos
- [x] Encriptación AES-256-GCM de templates en reposo
- [x] TLS 1.2+ para datos en tránsito
- [x] Derecho de supresión implementado (DELETE enrollment)
- [x] Audit log de operaciones sobre datos biométricos
- [ ] Registro de la base de datos ante la SIC
- [ ] Política de privacidad visible para miembros
- [ ] Aviso de privacidad con finalidad específica del tratamiento
- [ ] Designación de Responsable del Tratamiento

### Para el agente de IA

- **Nunca** loguees embeddings biométricos, templates encriptados, o datos faciales.
- **Nunca** expongas endpoints que retornen templates desencriptados fuera de localhost.
- **Siempre** usa `encrypt_template()` antes de almacenar y `decrypt_template()` solo para matching.
- Si modificas el flujo de enrollment, **verifica** que el consentimiento se captura antes de procesar.

---

## 5. Validación y Sanitización de Inputs

### Validación con Pydantic

```python
# backend/schemas/member.py — Validación de datos de miembros

class MemberBase(BaseModel):
    """Schema base con validación."""
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field('', max_length=100)  # Opcional
    id_number: str = Field(..., min_length=3, max_length=50, pattern=r'^[a-zA-Z0-9\-]+$')
    phone: Optional[str] = Field(None, max_length=20, pattern=r'^\+?[0-9\s\-]{7,20}$')
    email: Optional[EmailStr] = None

class MembershipCreate(BaseModel):
    """Schema con validación de fechas."""
    member_id: str = Field(..., min_length=1)
    plan_id: str = Field(..., min_length=1)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    price: Decimal = Field(..., ge=0, max_digits=10, decimal_places=2)
```

### Validación de imágenes en enrollment

```python
# backend/api/enrollment.py — Validación de imagen antes de procesar

contents = await image.read()
nparr = np.frombuffer(contents, np.uint8)
img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

if img is None:
    raise HTTPException(400, "Formato de imagen inválido")

# MTCNN detecta cara y valida calidad
face_roi, quality_score, landmarks = _detect_and_extract_face(img)

if quality_score < 0.4:
    raise HTTPException(400, "Calidad de imagen demasiado baja")

# Limitar tamaño de imagen (defender contra DoS)
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
if len(contents) > MAX_IMAGE_SIZE:
    raise HTTPException(400, "Imagen demasiado grande (máx 10MB)")
```

### Prevención de SQL Injection

SQLAlchemy usa queries parametrizadas por defecto. **Nunca** construyas queries con concatenación:

```python
# ❌ NUNCA hagas esto
db.execute(f"SELECT * FROM members WHERE id_number = '{id_number}'")

# ✅ Usa siempre el ORM de SQLAlchemy
db.query(Member).filter(Member.id_number == id_number).first()
```

---

## 6. Seguridad del CV Service

### Arquitectura de aislamiento

```
                    INTERNET
                       │
                       ▼
                  ┌─────────┐
                  │  NGINX   │  /api/cv/ → deny all (solo 127.0.0.1)
                  └────┬────┘
                       │ localhost only
                       ▼
              ┌──────────────────┐
              │   CV SERVICE     │  :8001 (NO expuesto a internet)
              │                  │
              │  /cameras/start  │  ← API Key requerido
              │  /cameras/stop   │  ← API Key requerido
              │  /reload         │  ← API Key requerido
              │  /stream/:id     │  ⚠️ Sin auth (MJPEG público)
              │  /ws/camera/:id  │  ⚠️ Sin auth (WebSocket)
              │  /invalidate/:id │  🚨 Sin auth (CRÍTICO)
              └──────────────────┘
```

### Configuración de API Key

```python
# cv_service/config.py — Configurar API key OBLIGATORIAMENTE

class CVServiceSettings(BaseSettings):
    api_key: str = Field(default="", alias="API_KEY")  # ⚠️ Vacío = sin auth

# .env del CV Service:
API_KEY=generar-un-secret-aleatorio-seguro-aqui
```

**Acción requerida:** Generar un API key seguro y configurarlo en `.env`. Sin esto, los endpoints de control del CV Service están abiertos.

### Endpoints expuestos sin autenticación

| Endpoint | Riesgo | Mitigación actual |
|---|---|---|
| `GET /stream/{camera_id}` | Stream de video público | Aislado por Nginx (solo localhost) |
| `WS /ws/camera/{camera_id}` | WebSocket sin auth | Aislado por Nginx (solo localhost) |
| `POST /invalidate/{member_id}` | Eliminar template facial | 🚨 Solo Nginx ACL |
| `GET /` | Info del sistema | Solo Nginx ACL |

### Para el agente de IA

- **Nunca** expongas el CV Service directamente a internet (sin Nginx delante).
- Si agregas endpoints nuevos al CV Service, **siempre** protegelos con `verify_api_key`.
- Los streams MJPEG son necesarios para el kiosk pero no deben ser accesibles desde fuera de la red local.

---

## 7. Pagos con Wompi

### Flujo completo del pago

```
┌──────────────────────────────────────────────────────────────────┐
│                     PORTAL DEL MIEMBRO                            │
│                                                                  │
│  1. Miembro se autentica (WhatsApp PIN)                          │
│  2. Selecciona plan → POST /portal/pending-payment               │
│     {plan_id, member_id, amount, wompi_reference}                │
│     Se guarda en Redis con TTL 24h                               │
│  3. Frontend abre Widget de Wompi (usa PUBLIC_KEY)               │
│     └─ Wompi procesa el pago con tarjeta/PSE                     │
│                                                                  │
└────────────────────────────┬─────────────────────────────────────┘
                             │ Wompi envía webhook al completar
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                    BACKEND (Webhook)                              │
│                                                                  │
│  POST /api/portal/webhook-renew                                  │
│  1. Verificar firma HMAC-SHA256 con INTEGRITY_SECRET  ← OBLIG.  │
│  2. Buscar pending payment en Redis por reference                │
│  3. Verificar monto coincida                                     │
│  4. Crear membresía + transacción de venta                       │
│  5. Idempotencia: verificar que reference no exista en DB        │
│  6. Eliminar pending de Redis                                    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Verificación de firma Wompi (OBLIGATORIO)

```python
# backend/api/portal.py — Verificación de integridad del webhook

import hmac
import hashlib

def verify_wompi_signature(payload: dict, signature: str) -> bool:
    """
    Verifica la firma HMAC-SHA256 de Wompi.

    Wompi envía la firma en el header 'X-Signature' o como parte del payload.
    La firma se calcula sobre los campos del evento concatenados.

    Variables requeridas en .env:
        WOMPI_INTEGRITY_SECRET=prod_integrity_xxxxx
    """
    integrity_secret = settings.WOMPI_INTEGRITY_SECRET
    if not integrity_secret:
        logger.error("WOMPI_INTEGRITY_SECRET no configurado!")
        return False

    # Construir string a firmar según docs de Wompi
    # Formato: {id}.{status}.{amount_in_cents}.{currency}.{reference}
    properties = (
        f"{payload.get('data', {}).get('id', '')}"
        f".{payload.get('data', {}).get('status', '')}"
        f".{payload.get('data', {}).get('amount_in_cents', '')}"
        f".{payload.get('data', {}).get('currency', '')}"
        f".{payload.get('data', {}).get('reference', '')}"
    )

    expected = hmac.new(
        integrity_secret.encode('utf-8'),
        properties.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


@router.post("/portal/webhook-renew")
async def webhook_renew(request: Request, db: Session = Depends(get_db)):
    body = await request.json()

    # PASO 1: Verificar firma SIEMPRE
    signature = request.headers.get("x-signature", "")
    if not verify_wompi_signature(body, signature):
        raise HTTPException(403, "Firma inválida")

    # PASO 2: Idempotencia — verificar si ya procesamos este pago
    reference = body.get("data", {}).get("reference", "")
    existing = db.query(SalesTransaction).filter(
        SalesTransaction.notes.contains(reference)
    ).first()
    if existing:
        return {"status": "already_processed"}

    # PASO 3: Buscar pending payment en Redis
    pending = redis.get(f"wompi_pending:{reference}")
    if not pending:
        raise HTTPException(404, "Referencia no encontrada")

    # PASO 4: Verificar monto
    # ...

    # PASO 5: Crear membresía + transacción
    # ...
```

### 🚨 Issues de seguridad actuales en pagos

| Severidad | Issue | Fix requerido |
|---|---|---|
| **CRÍTICO** | Webhook sin verificación de firma → renovaciones forjadas | Implementar `verify_wompi_signature()` con `WOMPI_INTEGRITY_SECRET` |
| **ALTO** | `GET /pending-payment/{reference}` es público → filtra member_id + amount | Requiere autenticación (JWT miembro) o eliminar endpoint |
| **ALTO** | `WOMPI_INTEGRITY_SECRET` no existe en `.env` | Agregar y configurar desde dashboard Wompi |

---

## 8. OWASP Top 10 — Aplicado a FaceGYM

### A01 — Broken Access Control
**Riesgo:** Usuarios staff acceden a funciones de admin. Miembros acceden a endpoints de gestión.
**Mitigación:**
- RBAC implementado en `api/deps.py` con `require_admin`, `require_staff`, `require_page`.
- Rutas frontend protegidas con `RequirePermission` component.
- **Nunca** confiar en `role` enviado desde el cliente — siempre verificar en backend via JWT.

### A02 — Cryptographic Failures
**Riesgo:** Datos biométricos o credenciales expuestos.
**Mitigación:**
- AES-256-GCM para datos biométricos y RTSP URLs en reposo.
- TLS 1.2+ (Cloudflare + Nginx) para datos en tránsito.
- bcrypt para passwords (no MD5, no SHA256 directo).
- **Nunca** loguear datos sensibles (passwords, tokens, embeddings).

### A03 — Injection
**Riesgo:** SQL injection via inputs del usuario.
**Mitigación:**
- SQLAlchemy ORM usa queries parametrizadas automáticamente.
- **Nunca** construir SQL con f-strings o concatenación.
- Pydantic valida tipos y formatos antes de llegar a la DB.
- Inputs de búsqueda sanitizados (solo alfanuméricos + espacios).

### A04 — Insecure Design
**Riesgo:** Flujos de negocio explotables (pagos, enrollment).
**Mitigación:**
- Lógica de pagos y precios siempre en backend — el frontend NO calcula precios.
- Enrollment requiere consentimiento explícito antes de procesar.
- Rate limiting multi-capa (Nginx + SlowAPI + Redis).

### A05 — Security Misconfiguration
**Riesgo:** Defaults inseguros, servicios expuestos.
**Mitigación:**
- Cambiar `admin123` por password fuerte en producción.
- Configurar `API_KEY` del CV Service (no dejar vacío).
- CV endpoints bloqueados desde internet via Nginx (`allow 127.0.0.1; deny all`).
- `server_tokens off` en Nginx (no exponer versión).
- **PENDIENTE:** HTTP→HTTPS redirect en puerto 80.

### A06 — Vulnerable Components
**Riesgo:** Dependencias desactualizadas.
**Mitigación:**
- Ejecutar `npm audit` regularmente (frontend).
- Ejecutar `pip audit` o `safety check` regularmente (backend).
- Mantener `facenet_pytorch`, `torch`, `fastapi` actualizados.
- Usar `dependabot` para actualizaciones automáticas.

### A07 — Authentication Failures
**Riesgo:** Fuerza bruta, sesiones robadas.
**Mitigación:**
- Rate limiting: 5 req/min en login, 3 intentos PIN portal, 10min lockout.
- JWT con blacklist en Redis (logout revoca el token).
- Token expiry: 24 horas.
- bcrypt con rounds automáticos para passwords.

### A08 — Software and Data Integrity Failures
**Riesgo:** Webhooks falsos, código modificado.
**Mitigación:**
- **Verificar firma HMAC de Wompi** en webhooks (implementar).
- `package-lock.json` y `requirements.txt` congelados en repo.
- Audit log para operaciones críticas (enrollment, pagos, cambios de rol).

### A09 — Logging & Monitoring Failures
**Riesgo:** Ataques no detectados.
**Mitigación:**
- Audit log en PostgreSQL (`audit_log` table) con user_id, action, IP, timestamp.
- Nginx access logs con status codes.
- Cloudflare analytics para tráfico anómalo.
- **Nunca** loguear: passwords, tokens JWT, embeddings, datos biométricos.

```python
# ✅ Log seguro
log_action(db, action="login", user_id=str(user.id), ip_address=client_ip)

# 🚫 Log inseguro — NUNCA hacer esto
log_action(db, action="login", details={"password": password, "token": token})
```

### A10 — Server-Side Request Forgery (SSRF)
**Riesgo:** CV Service hace requests a URLs controladas por atacante.
**Mitigación:**
- RTSP URLs validadas contra formatos conocidos (`rtsp://`).
- No hacer `fetch()` a URLs proporcionadas por el usuario sin validación.
- CV Service no tiene endpoints que acepten URLs arbitrarias.

---

## 9. Procedimiento de Respuesta a Incidentes

### Roles y responsabilidades

| Rol | Responsable | Función |
|---|---|---|
| **Líder de Incidentes** | Admin del gimnasio | Coordinación general, comunicación |
| **Admin Técnico** | Desarrollador/Admin sys | Análisis técnico, contención, erradicación |
| **Legal** | Representante legal | Notificación a SIC, comunicación a afectados |
| **Comunicaciones** | Gerencia del gimnasio | Notificación a miembros afectados |

### Niveles de severidad

| Nivel | Ejemplo | Tiempo de respuesta |
|---|---|---|
| **P1 — Crítico** | Data breach de datos biométricos, acceso no autorizado masivo | < 1 hora |
| **P2 — Alto** | Webhook de pagos explotado, acceso admin comprometido | < 4 horas |
| **P3 — Medio** | Endpoint sin auth descubierto, rate limiting evadido | < 24 horas |
| **P4 — Bajo** | CSP debilitado, header faltante | < 1 semana |

### Playbook paso a paso

#### Paso 1: Detección (< 15 min)

```bash
# Verificar accesos sospechosos en audit log
PGPASSWORD=xxx psql -h localhost -U membership -d membership_db -c \
  "SELECT * FROM audit_log WHERE timestamp > NOW() - INTERVAL '1 hour' ORDER BY timestamp DESC"

# Verificar requests en Nginx
tail -100 /var/log/nginx/access.log | grep -E " 4[0-9]{2} | 5[0-9]{2} "

# Verificar estado del CV Service
systemctl status powerhouse-cv
```

#### Paso 2: Contención (< 1 hora)

```bash
# Si el CV Service está comprometido
systemctl stop powerhouse-cv

# Si hay tokens comprometidos — limpiar Redis
redis-cli FLUSHALL

# Si hay cuenta admin comprometida — cambiar password
PGPASSWORD=xxx psql -h localhost -U membership -d membership_db -c \
  "UPDATE users SET password_hash = '\$2b\$12\$NEW_HASH' WHERE username = 'admin'"

# Bloquear IP sospechosa en Nginx
echo "deny XXX.XXX.XXX.XXX;" >> /etc/nginx/blocked.conf
nginx -s reload
```

#### Paso 3: Erradicación (< 4 horas)

- Identificar el vector de ataque (audit logs, nginx logs, Cloudflare dashboard).
- Aplicar fix al código vulnerado.
- Rotar secrets comprometidos: `JWT_SECRET`, `ENCRYPTION_KEY`, `API_KEY`, `EVOLUTION_API_KEY`.
- Si `ENCRYPTION_KEY` fue comprometida: **re-enrolar TODOS los miembros** (los templates existentes son inútiles con key nueva).

#### Paso 4: Recuperación (< 24 horas)

- Restaurar backup de DB si hubo modificación de datos:
```bash
pg_restore -h localhost -U membership -d membership_db /tmp/membership_db_backup.dump
```
- Reiniciar servicios: `systemctl restart powerhouse-backend powerhouse-cv`
- Verificar integridad: login test, enrollment test, payment test.

#### Paso 5: Notificación legal (Habeas Data)

**Si el incidente involucra datos biométricos o datos personales:**

1. **Notificar a la SIC** (Superintendencia de Industria y Comercio) dentro de los plazos legales.
2. **Notificar a los titulares** (miembros afectados) via email/WhatsApp con:
   - Descripción del incidente
   - Datos comprometidos
   - Medidas tomadas
   - Contacto para consultas
3. **Documentar todo** para auditoría legal.

### Template de notificación a miembros

```
Asunto: Notificación de Incidente de Seguridad — [FECHA]

Estimado/a [NOMBRE],

El día [FECHA] detectamos un incidente de seguridad que pudo haber
afectado sus datos personales registrados en PowerHouse Gym.

Datos potencialmente afectados: [TIPO DE DATOS]
Medidas tomadas: [ACCIONES]
Recomendaciones: [QUE DEBE HACER EL MIEMBRO]

Para consultas: seguridad@powerhousegym.co
```

---

## 10. Checklist Pre-Deploy

### Base de datos
- [ ] Backups automáticos configurados (`pg_dump` cron)
- [ ] `ENCRYPTION_KEY` configurada (no default)
- [ ] Conexion PostgreSQL con SSL si es remota
- [ ] No hay secrets en código fuente

### Variables de entorno
- [ ] `JWT_SECRET` es un valor aleatorio seguro (no "secret")
- [ ] `ENCRYPTION_KEY` es base64 o hex de 32 bytes
- [ ] `ADMIN_PASSWORD` fue cambiado de "admin123"
- [ ] `API_KEY` del CV Service está configurada
- [ ] `WOMPI_INTEGRITY_SECRET` configurado (si se usan pagos)
- [ ] `.env` está en `.gitignore`

### Autenticación
- [ ] Rate limiting en login funcional (Nginx + SlowAPI)
- [ ] Tokens JWT con blacklist en Redis (logout funciona)
- [ ] Portal miembro con rate limiting de PIN
- [ ] RBAC por página funcional (RequirePermission en rutas)

### Pagos (Wompi)
- [ ] Webhook verifica firma HMAC-SHA256
- [ ] Idempotencia por `wompi_reference`
- [ ] Montos verificados server-side
- [ ] `WOMPI_INTEGRITY_SECRET` configurado

### CV Service
- [ ] `API_KEY` configurada (no vacía)
- [ ] CV Service no accesible desde internet (solo localhost via Nginx)
- [ ] Endpoints de control protegidos con API key
- [ ] Streams MJPEG solo accesibles desde red local

### Nginx
- [ ] HTTP→HTTPS redirect en puerto 80
- [ ] Security headers configurados (CSP, HSTS, X-Frame)
- [ ] Rate limiting funcional
- [ ] `/api/cv/` bloqueado desde exterior

### Dependencias
- [ ] `npm audit` sin vulnerabilidades críticas
- [ ] `pip audit` sin vulnerabilidades críticas
- [ ] Versiones de Python, Node, torch actualizadas

---

## 11. Qué NUNCA hacer

Lista rápida para el agente de IA y desarrolladores. Si algo de esta lista aparece en el código, es un bug de seguridad crítico:

```
🚫 NUNCA hardcodees secrets en código fuente (API keys, passwords, tokens)
🚫 NUNCA construyas SQL concatenando strings con input del usuario
🚫 NUNCA expongas templates biométricos desencriptados fuera de localhost
🚫 NUNCA loguees passwords, tokens JWT, embeddings faciales, o datos de tarjetas
🚫 NUNCA proceses webhooks de pago sin verificar la firma HMAC
🚫 NUNCA confíes en datos del cliente para determinar permisos o precios
🚫 NUNCA dejes el CV Service sin API key configurada
🚫 NUNCA expongas el CV Service directamente a internet (sin Nginx)
🚫 NUNCA uses endpoints del portal miembro sin JWT verification
🚫 NUNCA almacenes RTSP URLs en texto plano — siempre encrypt_string()
🚫 NUNCA elimines datos biométricos sin registrar en audit_log
🚫 NUNCA proceses enrollment sin verificar consent_given del miembro
🚫 NUNCA renderices HTML de usuarios sin sanitizar
🚫 NUNCA uses HTTP para comunicación entre servicios en producción
🚫 NUNCA hagas fetch a URLs proporcionadas por el usuario sin validación
🚫 NUNCA retornes stack traces o mensajes de error de DB al cliente en producción
```

---

## Referencias

- [FastAPI Security Docs](https://fastapi.tiangolo.com/tutorial/security/)
- [OWASP Top 10 (2021)](https://owasp.org/Top10/)
- [Wompi Webhook Integration](https://docs.wompi.co/docs/webhook)
- [Ley 1581 de 2012 — Protección de Datos Personales (Colombia)](https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=49981)
- [Decreto 1377 de 2013](https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=57503)
- [AES-GCM Best Practices (NIST SP 800-38D)](https://csrc.nist.gov/publications/detail/sp/800-38d/final)
- [OWASP Cheat Sheet — SQL Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)

---

*Este archivo debe mantenerse actualizado con cada cambio significativo en la arquitectura del proyecto. Revisión mínima requerida: cada sprint o antes de cada release.*

*Última actualización: Abril 2026 — Stack: FastAPI + React + PostgreSQL + OpenCV + FaceNet + Wompi*
