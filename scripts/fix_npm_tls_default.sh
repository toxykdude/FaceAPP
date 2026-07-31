#!/bin/bash
# fix_npm_tls_default.sh — stop ERR_SSL_UNRECOGNIZED_NAME_ALERT on the NPM
# gateway (LXC 200 "nginxGYM", 10.162.36.9).
#
# Problem: the NPM default 443 listener shipped with `ssl_reject_handshake on;`
# (default.conf). Any HTTPS connection whose SNI does not exactly match a
# configured proxy host is actively rejected at the TLS layer with an
# `unrecognized_name` alert — Chrome surfaces this as
# ERR_SSL_UNRECOGNIZED_NAME_ALERT. Because real browsers occasionally reach
# the gateway without the exact SNI (IP literals, other hostnames on the same
# IP, an intervening NAT/proxy that strips SNI), the same site "sometimes
# loads, sometimes doesn't".
#
# Fix: make the default 443 listener present the NPM wildcard certificate
# (`*.powerhousegym.co`, npm-1) for ANY hostname and keep `return 444;` for
# unknown HTTP Hosts. nginx still selects the correct proxy host by SNI first;
# when SNI is absent/mismatched the handshake now succeeds with the wildcard
# cert and request routing happens via the HTTP Host header — so the app loads
# instead of the TLS alert. Unknown hostnames still get a closed connection
# (return 444), not content.
#
# NOTE: NPM regenerates files it manages (proxy_host/, default_host/) but this
# static default.conf lives in the container image. If the LXC is ever
# recreated, re-run this script (or set a Default Site in the NPM UI, which
# achieves the same result without ssl_reject_handshake).
set -euo pipefail

CONF=/etc/nginx/conf.d/default.conf
BACKUP=/etc/nginx/conf.d/default.conf.bak-$(date +%Y%m%d%H%M%S)
CERT=/etc/letsencrypt/live/npm-1

[ -f "$CONF" ] || { echo "missing $CONF"; exit 1; }
[ -f "$CERT/fullchain.pem" ] || { echo "missing $CERT/fullchain.pem"; exit 1; }

cp -a "$CONF" "$BACKUP"
echo "backed up $CONF -> $BACKUP"

grep -q 'ssl_reject_handshake on' "$CONF" || { echo "ssl_reject_handshake already removed"; exit 0; }

cat > "$CONF" <<EOF
# "You are not configured" page, which is the default if another default doesn't exist
server {
	listen 80;
	listen [::]:80;

	set \$forward_scheme "http";
	set \$server "127.0.0.1";
	set \$port "80";

	server_name localhost-nginx-proxy-manager;
	access_log /data/logs/fallback_http_access.log standard;
	error_log /data/logs/fallback_http_error.log warn;
	include /etc/nginx/conf.d/include/assets.conf;
	include /etc/nginx/conf.d/include/block-exploits.conf;
	include /etc/nginx/conf.d/include/letsencrypt-acme-challenge.conf;

	location / {
		index index.html;
		root /var/www/html;
	}
}

# Default 443 listener: presents the wildcard cert for ANY SNI (and no-SNI)
# so the TLS handshake never fails with an unrecognized_name alert. Request
# routing still happens per-Host via the matching proxy host; unknown Hosts
# get a connection closed (return 444) rather than content.
server {
	listen 443 ssl default_server;
	listen [::]:443 ssl default_server;

	set \$forward_scheme "https";
	set \$server "127.0.0.1";
	set \$port "443";

	server_name _;
	access_log /data/logs/fallback_http_access.log standard;
	error_log /dev/null crit;
	include /etc/nginx/conf.d/include/ssl-ciphers.conf;
	ssl_certificate $CERT/fullchain.pem;
	ssl_certificate_key $CERT/privkey.pem;

	return 444;
}
EOF

nginx -t
nginx -s reload
echo "OK — default 443 no longer rejects handshakes."