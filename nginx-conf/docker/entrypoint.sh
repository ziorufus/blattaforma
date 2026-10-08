#!/bin/sh
set -eu
: "${BLATTAFORMA_HOST:?BLATTAFORMA_HOST is required}"
: "${BLATTAFORMA_PORT:=5173}"
case "$BLATTAFORMA_PORT" in ''|*[!0-9]*) echo "Invalid BLATTAFORMA_PORT" >&2; exit 1;; esac
: "${OLLAMA_CODE:?OLLAMA_CODE is required}"
if [ -n "${DOMAIN:-}" ]; then
    case "$DOMAIN" in *[!a-zA-Z0-9.-]*|.*|*..*|*.) echo "Invalid DOMAIN" >&2; exit 1;; esac
fi

# The repository is cloned at container startup.
rm -rf /tmp/blattaforma
git clone --depth 1 https://github.com/ziorufus/blattaforma.git /tmp/blattaforma
SRC=/tmp/blattaforma/nginx-conf
[ -d "$SRC" ] || { echo "Missing $SRC" >&2; exit 1; }
mkdir -p /etc/nginx/servers /etc/nginx/snippets /etc/nginx/js
# Copy the repository hierarchy; nginx.conf is intentionally provided here.
cp -a "$SRC"/. /etc/nginx/
cp /tmp/blattaforma/nginx-conf/nginx.conf /etc/nginx/nginx.conf
# Avoid a repository nginx.conf accidentally overriding this custom entrypoint's conventions.
# Find all js files and flatten them into the js_path directory.
find "$SRC" -type f -name '*.js' -exec cp -f '{}' /etc/nginx/js/ \;
[ -f /etc/nginx/js/ollama_guard.js ] || { echo 'Missing ollama_guard.js' >&2; exit 1; }
# Accept server configs in repository root as well as under servers/.
for name in ollama.conf; do
    if [ ! -f "/etc/nginx/servers/$name" ]; then
        src=$(find "$SRC" -type f -name "$name" -print -quit)
        [ -n "$src" ] || { echo "Missing $name" >&2; exit 1; }
        cp "$src" "/etc/nginx/servers/$name"
    fi
done
# Optional write endpoint MUST NOT be included unless API_TOKEN is set.
rm -f /etc/nginx/servers/ollama-auth-w.conf
find_template() { find "$SRC" -type f -name "$1" -print -quit; }
upstream=$(find_template ollama-auth-upstream.conf.template)
[ -n "$upstream" ] || { echo 'Missing ollama-auth-upstream.conf.template' >&2; exit 1; }
envsubst '${BLATTAFORMA_HOST} ${OLLAMA_CODE}' < "$upstream" > /etc/nginx/snippets/ollama-auth-upstream.conf
if [ -n "${API_TOKEN:-}" ]; then
    writeconf=$(find_template ollama-auth-w.conf)
    [ -n "$writeconf" ] || { echo 'Missing ollama-auth-w.conf' >&2; exit 1; }
    cp "$writeconf" /etc/nginx/servers/ollama-auth-w.conf
    token_template=$(find_template ollama-auth-check-w.conf.template)
    [ -n "$token_template" ] || { echo 'Missing ollama-auth-check-w.conf.template' >&2; exit 1; }
    umask 077
    envsubst '${API_TOKEN}' < "$token_template" > /etc/nginx/snippets/ollama-auth-check-w.conf
fi
# Domain config: two phases, since HTTPS cannot start without a certificate.
if [ -n "${DOMAIN:-}" ]; then
    envsubst '${DOMAIN}' < /tmp/blattaforma/nginx-conf/domain/domain.conf.template > /etc/nginx/servers/00-domain.conf
    if [ -s "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ] && [ -s "/etc/letsencrypt/live/$DOMAIN/privkey.pem" ]; then
        envsubst '${DOMAIN} ${BLATTAFORMA_PORT}' < /tmp/blattaforma/nginx-conf/domain/domain-ssl.conf.template > /etc/nginx/servers/01-domain-ssl.conf
    fi
fi
nginx -t
nginx
if [ -n "${DOMAIN:-}" ] && [ ! -f /etc/nginx/servers/01-domain-ssl.conf ]; then
    if [ -n "${CERTBOT_EMAIL:-}" ]; then
        certbot certonly --webroot -w /var/www/letsencrypt -d "$DOMAIN" --non-interactive --agree-tos -m "$CERTBOT_EMAIL"
    else
        certbot certonly --webroot -w /var/www/letsencrypt -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email
    fi
    envsubst '${DOMAIN} ${BLATTAFORMA_PORT}' < /tmp/blattaforma/nginx-conf/domain/domain-ssl.conf.template > /etc/nginx/servers/01-domain-ssl.conf
    nginx -t && nginx -s reload
fi
# Certbot renew is harmless without a certificate; reload only on successful renewal.
(while :; do
    sleep 43200
    if [ -n "${DOMAIN:-}" ]; then
        certbot renew --quiet --deploy-hook 'nginx -t && nginx -s reload' || echo 'Certificate renewal failed' >&2
    fi
done) &
trap 'nginx -s quit; exit 0' TERM INT
while kill -0 "$(cat /run/nginx.pid)" 2>/dev/null; do sleep 5 & wait $! || :; done
exit 1
