#!/usr/bin/env bash

# Script metadata
SCRIPT_VERSION="1.0.0"
APP_NAME="PowerHouse Membership Platform"
APP_DIR="/opt/powerhouse-membership"
DATA_DIR="/var/lib/powerhouse"
LOG_FILE="/var/log/powerhouse-health.log"

# PowerHouse Membership Platform - Health Monitor
# Monitors all services and sends alerts on failures

set -euo pipefail

# Configuration
ALERT_EMAIL="${ALERT_EMAIL:-}"
BACKEND_URL="http://localhost:8000/api/health"
FRONTEND_URL="http://localhost"
MAX_RETRIES=3
RETRY_DELAY=5

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Status tracking
OVERALL_STATUS=0
ISSUES=()

# Functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

check_service() {
    local service_name=$1
    local retry_count=0
    
    while [ $retry_count -lt $MAX_RETRIES ]; do
        if systemctl is-active --quiet "$service_name"; then
            echo -e "${GREEN}✓${NC} $service_name is running"
            return 0
        fi
        retry_count=$((retry_count + 1))
        sleep $RETRY_DELAY
    done
    
    echo -e "${RED}✗${NC} $service_name is NOT running"
    ISSUES+=("Service $service_name is down")
    OVERALL_STATUS=1
    return 1
}

check_http_endpoint() {
    local name=$1
    local url=$2
    local retry_count=0
    
    while [ $retry_count -lt $MAX_RETRIES ]; do
        if curl -sf "$url" > /dev/null 2>&1; then
            echo -e "${GREEN}✓${NC} $name is responding"
            return 0
        fi
        retry_count=$((retry_count + 1))
        sleep $RETRY_DELAY
    done
    
    echo -e "${RED}✗${NC} $name is NOT responding"
    ISSUES+=("HTTP endpoint $name is unreachable")
    OVERALL_STATUS=1
    return 1
}

check_database() {
    # Load database credentials
    ENV_FILE="$APP_DIR/.env"
    if [ -f "$ENV_FILE" ]; then
        export $(grep -v '^#' "$ENV_FILE" | grep DATABASE_URL | xargs)
    fi
    
    DB_URL="${DATABASE_URL:-}"
    if [ -z "$DB_URL" ]; then
        echo -e "${RED}✗${NC} Database configuration not found"
        ISSUES+=("Database configuration missing")
        OVERALL_STATUS=1
        return 1
    fi
    
    # Parse DATABASE_URL
    DB_USER=$(echo "$DB_URL" | sed -n 's|.*://\([^:]*\):.*|\1|p')
    DB_PASS=$(echo "$DB_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
    DB_HOST=$(echo "$DB_URL" | sed -n 's|.*@\([^:]*\):.*|\1|p')
    DB_PORT=$(echo "$DB_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
    DB_NAME=$(echo "$DB_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')
    
    if PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} PostgreSQL database is accessible"
        return 0
    else
        echo -e "${RED}✗${NC} PostgreSQL database is NOT accessible"
        ISSUES+=("Database connection failed")
        OVERALL_STATUS=1
        return 1
    fi
}

check_redis() {
    if redis-cli ping > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Redis is responding"
        return 0
    else
        echo -e "${RED}✗${NC} Redis is NOT responding"
        ISSUES+=("Redis connection failed")
        OVERALL_STATUS=1
        return 1
    fi
}

check_disk_space() {
    local threshold=90
    local usage=$(df -h "$DATA_DIR" | awk 'NR==2 {print $5}' | sed 's/%//')
    
    if [ "$usage" -lt "$threshold" ]; then
        echo -e "${GREEN}✓${NC} Disk space: ${usage}% used"
        return 0
    else
        echo -e "${YELLOW}⚠${NC} Disk space: ${usage}% used (threshold: ${threshold}%)"
        ISSUES+=("Disk space usage high: ${usage}%")
        OVERALL_STATUS=1
        return 1
    fi
}

check_memory() {
    local threshold=90
    local usage=$(free | awk 'NR==2 {printf "%.0f", $3/$2 * 100}')
    
    if [ "$usage" -lt "$threshold" ]; then
        echo -e "${GREEN}✓${NC} Memory usage: ${usage}%"
        return 0
    else
        echo -e "${YELLOW}⚠${NC} Memory usage: ${usage}% (threshold: ${threshold}%)"
        ISSUES+=("Memory usage high: ${usage}%")
        return 1
    fi
}

send_alert() {
    local subject="$APP_NAME - Health Check FAILED"
    local body="Health check failed at $(date)\n\nIssues detected:\n"
    
    for issue in "${ISSUES[@]}"; do
        body="${body}- $issue\n"
    done
    
    body="${body}\nPlease investigate immediately."
    
    # Log to file
    log "ALERT: Health check failed"
    for issue in "${ISSUES[@]}"; do
        log "  - $issue"
    done
    
    # Send email if configured
    if [ -n "$ALERT_EMAIL" ]; then
        echo -e "$body" | mail -s "$subject" "$ALERT_EMAIL" 2>/dev/null || true
    fi
    
    # Send to syslog
    logger -t powerhouse-health -p user.err "$subject: ${ISSUES[*]}"
}

# Main health check
log "Starting health check..."
echo ""
echo "=== $APP_NAME Health Check ==="
echo "Time: $(date)"
echo ""

echo "--- System Services ---"
check_service "powerhouse-backend"
check_service "powerhouse-cv"
check_service "nginx"
check_service "postgresql"
check_service "redis-server"
echo ""

echo "--- HTTP Endpoints ---"
check_http_endpoint "Backend API" "$BACKEND_URL"
check_http_endpoint "Frontend" "$FRONTEND_URL"
echo ""

echo "--- Database & Cache ---"
check_database
check_redis
echo ""

echo "--- System Resources ---"
check_disk_space
check_memory
echo ""

# Summary
echo "=== Health Check Summary ==="
if [ $OVERALL_STATUS -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed${NC}"
    log "Health check completed: ALL HEALTHY"
    exit 0
else
    echo -e "${RED}✗ ${#ISSUES[@]} issue(s) detected${NC}"
    for issue in "${ISSUES[@]}"; do
        echo -e "  ${RED}•${NC} $issue"
    done
    
    send_alert
    exit 1
fi
