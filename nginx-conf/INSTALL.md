Appunti per installazione e ricompilazione di nginx.

```
sudo apt install -y build-essential ca-certificates curl git libpcre2-dev zlib1g-dev libssl-dev libxml2-dev libxslt1-dev  libgd-dev  libgeoip-dev  libperl-dev perl
mkdir -p "$HOME/src/nginx-njs"
cd "$HOME/src/nginx-njs"
git clone https://github.com/nginx/njs.git
curl --fail --location --remote-name  https://nginx.org/download/nginx-1.31.3.tar.gz
tar xzf nginx-1.31.3.tar.gz
cd nginx-1.31.3

./configure --prefix=/opt/nginx-1.31.3 \
  --sbin-path=/opt/nginx-1.31.3/sbin/nginx \
  --modules-path=/opt/nginx-1.31.3/modules \
  --conf-path=/etc/nginx/nginx.conf \
  --error-log-path=/var/log/nginx/error.log \
  --http-log-path=/var/log/nginx/access.log \
  --pid-path=/run/nginx.pid \
  --lock-path=/var/lock/nginx.lock \
  --http-client-body-temp-path=/var/lib/nginx/body \
  --http-proxy-temp-path=/var/lib/nginx/proxy \
  --http-fastcgi-temp-path=/var/lib/nginx/fastcgi \
  --http-uwsgi-temp-path=/var/lib/nginx/uwsgi \
  --http-scgi-temp-path=/var/lib/nginx/scgi \
  --user=www-data \
  --group=www-data \
  --build="Ubuntu custom njs" \
  --with-compat \
  --with-threads \
  --with-debug \
  --with-pcre-jit \
  --with-http_ssl_module \
  --with-http_v2_module \
  --with-http_realip_module \
  --with-http_addition_module \
  --with-http_auth_request_module \
  --with-http_dav_module \
  --with-http_flv_module \
  --with-http_gunzip_module \
  --with-http_gzip_static_module \
  --with-http_mp4_module \
  --with-http_random_index_module \
  --with-http_secure_link_module \
  --with-http_slice_module \
  --with-http_stub_status_module \
  --with-http_sub_module \
  --with-http_geoip_module=dynamic \
  --with-http_image_filter_module=dynamic \
  --with-http_perl_module=dynamic \
  --with-http_xslt_module=dynamic \
  --with-mail=dynamic \
  --with-mail_ssl_module \
  --with-stream=dynamic \
  --with-stream_geoip_module=dynamic \
  --with-stream_realip_module \
  --with-stream_ssl_module \
  --with-stream_ssl_preread_module \
  --add-dynamic-module="$HOME/src/nginx-njs/njs/nginx"
make -j"$(nproc)"
sudo make install
sudo install -d -o root -g root -m 0755 /var/log/nginx /var/lib/nginx
sudo install -d -o www-data -g www-data -m 0700 /var/lib/nginx/body /var/lib/nginx/fastcgi /var/lib/nginx/proxy /var/lib/nginx/scgi /var/lib/nginx/uwsgi
/opt/nginx-1.31.3/sbin/nginx -V
sudo systemctl disable --now nginx-retry.timer
sudo systemctl stop nginx
cd /etc/
sudo mv nginx nginx.old

# Qui la configurazione viene copiata da un'altra macchina e solo modificata,
# ma nel mio caso vorrei usare ollama-auth-upstream.conf.template e il comando
# envsubst per partire dai file di Github e sostituire le informazioni
sudo scp -rp 10.216.20.142:/etc/nginx/* /etc/nginx/
sudo nano nginx/snippets/ollama-auth-upstream.conf

sudo /opt/nginx-1.31.3/sbin/nginx -t
sudo apt remove -y libnginx-mod-http-js libnginx-mod-stream libnginx-mod-stream-js nginx nginx-abi-1.24.0-1 nginx-common nginx-core nginx-doc nginx-extras nginx-light
sudo ln -sfn /opt/nginx-1.31.3 /opt/nginx
sudo ln -sfn /opt/nginx/sbin/nginx /usr/local/sbin/nginx

sudo tee /etc/systemd/system/nginx.service >/dev/null <<'EOF'
[Unit]
Description=nginx web server with njs
Documentation=https://nginx.org/en/docs/
After=network-online.target
Wants=network-online.target

[Service]
Type=forking
PIDFile=/run/nginx.pid

ExecStartPre=/opt/nginx/sbin/nginx -t -q
ExecStart=/opt/nginx/sbin/nginx
ExecReload=/opt/nginx/sbin/nginx -s reload
ExecStop=/opt/nginx/sbin/nginx -s quit

TimeoutStopSec=30
KillSignal=SIGQUIT
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now nginx
sudo systemctl status nginx --no-pager
sudo systemctl enable --now nginx-retry.timer

# Se ci sono problemi con Tailscale
sudo journalctl -u nginx -n 100 --no-pager
sudo readlink -f /proc/"$(cat /run/nginx.pid)"/exe
sudo tailscale set --accept-dns=false
tailscale debug prefs | grep -i corpDNS

# Altri comandi vari
sudo systemctl is-enabled nginx
sudo systemctl is-active nginx
sudo systemctl enable --now nginx-retry.timer
```
