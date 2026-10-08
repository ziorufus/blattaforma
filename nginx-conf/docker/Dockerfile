FROM debian:bookworm AS build
ARG NGINX_VERSION=1.31.3
RUN apt-get update && apt-get install -y --no-install-recommends build-essential ca-certificates curl git libpcre2-dev zlib1g-dev libssl-dev libxml2-dev libxslt1-dev libgd-dev libgeoip-dev libperl-dev perl && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone --depth 1 https://github.com/nginx/njs.git && \
    curl -fL "https://nginx.org/download/nginx-${NGINX_VERSION}.tar.gz" -o nginx.tar.gz && \
    mkdir nginx-src && tar -xzf nginx.tar.gz -C nginx-src --strip-components=1
WORKDIR /src/nginx-src
RUN ./configure \
  --prefix=/opt/nginx --sbin-path=/opt/nginx/sbin/nginx \
  --modules-path=/opt/nginx/modules --conf-path=/etc/nginx/nginx.conf \
  --error-log-path=/var/log/nginx/error.log --http-log-path=/var/log/nginx/access.log \
  --pid-path=/run/nginx.pid --lock-path=/var/lock/nginx.lock \
  --http-client-body-temp-path=/var/lib/nginx/body \
  --http-proxy-temp-path=/var/lib/nginx/proxy \
  --http-fastcgi-temp-path=/var/lib/nginx/fastcgi \
  --http-uwsgi-temp-path=/var/lib/nginx/uwsgi \
  --http-scgi-temp-path=/var/lib/nginx/scgi \
  --user=www-data --group=www-data --build='Debian custom njs' \
  --with-compat --with-threads --with-debug --with-pcre-jit \
  --with-http_ssl_module --with-http_v2_module --with-http_realip_module \
  --with-http_addition_module --with-http_auth_request_module --with-http_dav_module \
  --with-http_flv_module --with-http_gunzip_module --with-http_gzip_static_module \
  --with-http_mp4_module --with-http_random_index_module --with-http_secure_link_module \
  --with-http_slice_module --with-http_stub_status_module --with-http_sub_module \
  --with-http_geoip_module=dynamic --with-http_image_filter_module=dynamic \
  --with-http_perl_module=dynamic --with-http_xslt_module=dynamic \
  --with-mail=dynamic --with-mail_ssl_module --with-stream=dynamic \
  --with-stream_geoip_module=dynamic --with-stream_realip_module \
  --with-stream_ssl_module --with-stream_ssl_preread_module \
  --add-dynamic-module=/src/njs/nginx && \
  make -j "$(nproc)" && make install

FROM debian:bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git curl certbot gettext-base libpcre2-8-0 zlib1g libssl3 libxml2 libxslt1.1 libgd3 libgeoip1 libperl5.36 perl && rm -rf /var/lib/apt/lists/*
COPY --from=build /opt/nginx /opt/nginx
RUN ln -s /opt/nginx/sbin/nginx /usr/local/sbin/nginx && \
    mkdir -p /etc/nginx /var/log/nginx /var/lib/nginx/body /var/lib/nginx/proxy /var/lib/nginx/fastcgi /var/lib/nginx/uwsgi /var/lib/nginx/scgi /var/www/letsencrypt && \
    chown -R www-data:www-data /var/lib/nginx
RUN cp /opt/nginx/conf/mime.types /etc/nginx/mime.types
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
EXPOSE 11435 11436 80 443
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
