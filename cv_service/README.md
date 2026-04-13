# PowerHouse Membership Platform - Computer Vision Service

Real-time facial recognition service for RTSP camera streams.

## Features

- **Face Detection**: MTCNN or Haar Cascade
- **Face Recognition**: FaceNet embeddings with 512-dimensional vectors
- **RTSP Stream Processing**: Multi-camera support with configurable FPS
- **Redis Caching**: Fast template matching with cached member embeddings
- **Access Validation**: Rule-based access control (time, day, location)
- **GPU Acceleration**: Optional CUDA support for faster processing

## Project Structure

```
cv_service/
├── main.py                     # Main service entry point
├── config.py                   # Configuration
├── requirements.txt            # Dependencies
├── detection/                  # Face detection
│   ├── face_detector.py       # MTCNN/Haar detector
│   └── quality_assessor.py    # Quality metrics
├── recognition/                # Face recognition
│   ├── face_recognizer.py     # FaceNet embeddings
│   ├── template_cache.py      # Redis cache
│   └── template_matcher.py    # Matching engine
├── stream/                     # RTSP processing
│   └── rtsp_processor.py      # Stream handler
├── validation/                 # Access validation
│   └── access_validator.py    # Rule engine
└── api/                        # Backend integration
    └── backend_client.py      # HTTP client
```

## Prerequisites

- Python 3.10+
- Redis 6+
- CUDA (optional, for GPU acceleration)

## Installation

### 1. Create Virtual Environment

```bash
cd cv_service
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Create `.env` file:

```bash
# Backend API
BACKEND_API_URL=http://localhost:8000/api

# Redis
REDIS_URL=redis://localhost:6379/0

# Face Recognition
FACE_DETECTION_MODEL=mtcnn  # or haar
CONFIDENCE_THRESHOLD=0.85
USE_GPU=false

# RTSP
DEFAULT_FPS=5

# Logging
LOG_LEVEL=INFO
```

## Usage

### Start Service

```bash
python main.py
```

### GPU Acceleration

To enable GPU acceleration:

```bash
# Install CUDA-enabled PyTorch
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# Enable in .env
USE_GPU=true
CUDA_DEVICE=0
```

## Architecture

### Recognition Pipeline

```
RTSP Stream → Frame Extraction → Face Detection → 
Quality Assessment → Embedding Generation → 
Template Matching → Access Validation → Event Logging
```

### Performance

- **Face Detection**: ~20-50ms (MTCNN), ~5-10ms (Haar)
- **Embedding Generation**: ~50-100ms (GPU), ~200-300ms (CPU)
- **Template Matching**: ~50-200ms (1000 members)
- **Total Latency**: < 1 second (target)

### Caching Strategy

Member templates are cached in Redis with:
- **TTL**: 24 hours
- **Auto-refresh**: On successful match
- **Invalidation**: On member deactivation

## Integration

### Backend API

The CV service communicates with the backend API for:
- Creating access events
- Fetching member data
- Validating memberships

### Redis Cache

Templates are stored in Redis as:
```json
{
  "template": [0.123, -0.456, ...],
  "member_id": "uuid",
  "name": "John Doe",
  "status": "active",
  "membership_status": "active"
}
```

## Configuration

### Face Detection Models

**MTCNN** (Recommended):
- More accurate
- Better for varying lighting
- Slower (~20-50ms)

**Haar Cascade**:
- Faster (~5-10ms)
- Less accurate
- Good for controlled environments

### Confidence Thresholds

- **Recognition**: 0.85 (default)
- **Enrollment**: 0.90 (higher quality required)

Adjust in `.env`:
```bash
CONFIDENCE_THRESHOLD=0.85
ENROLLMENT_QUALITY_THRESHOLD=0.90
```

## Troubleshooting

### RTSP Connection Failed

```bash
# Test RTSP URL
ffplay rtsp://camera-url

# Check camera is accessible
ping camera-ip
```

### Low Recognition Accuracy

1. Improve lighting conditions
2. Increase camera resolution
3. Re-enroll members with better quality
4. Lower confidence threshold (with caution)

### High CPU Usage

1. Reduce FPS per camera
2. Enable GPU acceleration
3. Reduce number of active cameras
4. Use Haar Cascade instead of MTCNN

### Redis Connection Error

```bash
# Check Redis is running
redis-cli ping

# Test connection
redis-cli -u redis://localhost:6379/0
```

## Development

### Adding New Detection Model

1. Create detector class in `detection/`
2. Implement `detect_faces()` method
3. Update `FaceDetector` to support new model
4. Add model selection in config

### Adding New Recognition Model

1. Create recognizer class in `recognition/`
2. Implement `generate_embedding()` method
3. Update `FaceRecognizer` to support new model
4. Update embedding dimensions if needed

## Testing

```bash
# Run tests
pytest

# Test with single camera
python -c "
from main import CVService
import asyncio

async def test():
    service = CVService()
    await service.start_camera(
        'test-camera',
        'rtsp://camera-url',
        fps=5
    )
    await asyncio.sleep(60)
    await service.shutdown()

asyncio.run(test())
"
```

## Performance Optimization

### GPU Acceleration

- **5-10x faster** embedding generation
- Requires CUDA-capable GPU
- Recommended for production

### Batch Processing

When multiple faces detected:
- Batch preprocessing
- Single model inference
- Parallel template matching

### Cache Warming

Pre-load active member templates on startup:
```python
# Load all active members into cache
await cache.warm_cache()
```

## Security

- RTSP URLs encrypted in database
- Templates encrypted at rest
- No raw images stored
- Audit logs for all access events

## License

Proprietary - PowerHouse Membership Platform
