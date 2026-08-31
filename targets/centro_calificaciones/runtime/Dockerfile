# Centro de Calificaciones — Apache + PHP 8.2 (lo que EXIGE el manual §1: PHP 8.2, no el 8.1 del host)
# con ext-mongodb (PECL) que lmsActividad necesita. Sirve las DOS apps como hermanas bajo un
# DocumentRoot, que es el modelo del manual (/var/www/html/{lmsActividad,lms-califica}).
FROM php:8.2-apache

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      ca-certificates curl git unzip \
      libpng-dev libjpeg-dev libfreetype6-dev libzip-dev zip \
      libpq-dev libicu-dev libxml2-dev postgresql-client \
      libssl-dev pkg-config; \
    rm -rf /var/lib/apt/lists/*
RUN set -eux; \
    docker-php-ext-configure gd --with-freetype --with-jpeg; \
    docker-php-ext-install -j"$(nproc)" pdo_pgsql pgsql gd zip intl soap
# ext-mongodb via PECL (no es una extensión nativa docker-php-ext-install)
RUN pecl install mongodb && docker-php-ext-enable mongodb
RUN a2enmod rewrite headers
COPY --from=composer:2 /usr/bin/composer /usr/bin/composer
RUN { echo "display_errors=Off"; echo "log_errors=On"; echo "error_log=/dev/stderr"; \
      echo "memory_limit=512M"; } > /usr/local/etc/php/conf.d/lab.ini
EXPOSE 80
