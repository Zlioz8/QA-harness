# Backend runner: Laravel on the exact PHP version the target requires.
# Solves the host "php8.4 without pgsql" problem — extensions are baked in here.
ARG PHP_VERSION=8.4
FROM php:${PHP_VERSION}-cli

# Build deps for the PHP extensions we install.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git unzip libpq-dev libzip-dev libicu-dev libpng-dev libjpeg-dev libfreetype6-dev \
    && docker-php-ext-configure gd --with-freetype --with-jpeg \
    && docker-php-ext-install -j"$(nproc)" pdo_pgsql pgsql gd intl zip bcmath \
    && rm -rf /var/lib/apt/lists/*

# Composer (from the official image).
COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

WORKDIR /app
ENV COMPOSER_ALLOW_SUPERUSER=1

# The repo is mounted at runtime (see docker-compose). Entry is provided by
# compose `command`, keeping this image project-agnostic.
