# Plain PHP + Apache with mod_php, matching how the factory actually deploys these projects.
#
# Built on the official php:*-apache image rather than assembled from Debian packages, because
# the version has to be the version: ADI's production runs PHP 8.2 and its DEPLOY.md pins that
# deliberately. A newer PHP would produce both false positives (deprecations production never
# sees) and false negatives (code paths that only fail on the deployed version).
ARG PHP_IMAGE=php:8.2-apache
FROM ${PHP_IMAGE}

ARG PHP_EXTS="pdo_pgsql pgsql gd zip intl soap"

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      ca-certificates curl git unzip \
      libpng-dev libjpeg-dev libfreetype6-dev \
      libzip-dev zip \
      libpq-dev libicu-dev libxml2-dev postgresql-client; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    docker-php-ext-configure gd --with-freetype --with-jpeg; \
    docker-php-ext-install -j"$(nproc)" ${PHP_EXTS}

# mod_rewrite is what .htaccess routing depends on; headers is needed by most security configs.
RUN a2enmod rewrite headers

# Composer, for projects that ship a manifest. Copied from the official image rather than
# curl'd through a pipe to a shell.
COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

# Errors go to the log, never to the page. display_errors=On is itself a finding, and worse, it
# would make ZAP report the application's stack traces as its own discovery.
RUN { \
      echo "display_errors=Off"; \
      echo "log_errors=On"; \
      echo "error_log=/dev/stderr"; \
      echo "memory_limit=512M"; \
      echo "upload_max_filesize=64M"; \
      echo "post_max_size=64M"; \
    } > /usr/local/etc/php/conf.d/lab.ini

COPY apache.conf /etc/apache2/sites-enabled/000-default.conf
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 80
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["apache2-foreground"]
