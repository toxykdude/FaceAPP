#!/usr/bin/env bash

# Fix Nginx configuration for blank screen issue
# The problem: Nginx was using 'localhost' which resolves to IPv6 [::1]
# but the backend only listens on IPv4 127.0.0.1

echo "Fixing Nginx configuration..."

# Backup current config
sudo cp /etc/nginx/sites-available/powerhouse /etc/nginx/sites-available/powerhouse.backup

# Create new config
sudo tee /etc/nginx/sites-available/powerhouse > /dev/null <<'EOF'
server {
    listen 80;
    server_name _;
    client_max_body_size 20M;

    # Frontend
    location / {
        root /opt/powerhouse-membership/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # Backend API - Fixed to use 127.0.0.1 instead of localhost
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }

    # API Documentation
    location /docs {
        proxy_pass http://127.0.0.1:8000/docs;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }

    location /openapi.json {
        proxy_pass http://127.0.0.1:8000/openapi.json;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }
}
EOF

# Test configuration
echo "Testing Nginx configuration..."
sudo nginx -t

if [ $? -eq 0 ]; then
    echo "Configuration valid. Reloading Nginx..."
    sudo systemctl reload nginx
    echo "✅ Nginx fixed and reloaded!"
    echo ""
    echo "The blank screen issue should now be resolved."
    echo "Try accessing the web UI again at http://10.166.32.23/"
else
    echo "❌ Configuration test failed. Restoring backup..."
    sudo cp /etc/nginx/sites-available/powerhouse.backup /etc/nginx/sites-available/powerhouse
    exit 1
fi
