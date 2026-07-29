# The platform baseline: the Moodle the project is actually deployed on, not a generic one.
#
# Why this image exists at all — measured, not assumed. Auditing local_slider_form against a
# stock Moodle 4.5 reported four endpoints as broken, because they require
# $CFG->dirroot.'/cache/lib.php', a file 4.5 no longer ships. The target platform runs 4.3.3+,
# where that file is present and the endpoints work. A generic image produces both false
# positives (breaks what production runs) and false negatives (cannot reach what production
# exposes). The version under audit has to be THE version.
#
# Built on php:8.2-apache with the extension set the platform needs. The Moodle tree is not
# baked in: it arrives as the baseline's code.tar.zst, so one image serves every snapshot.
FROM php:8.2-apache

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      ca-certificates curl zstd \
      libpng-dev libjpeg-dev libfreetype6-dev \
      libzip-dev zip unzip \
      libpq-dev libicu-dev libxml2-dev postgresql-client; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    docker-php-ext-configure gd --with-freetype --with-jpeg; \
    docker-php-ext-install -j"$(nproc)" gd zip pdo pdo_pgsql pgsql intl soap exif opcache

RUN a2enmod rewrite headers

# Moodle refuses to install with the stock limits, and max_input_vars in particular breaks the
# admin forms silently — the page saves, the setting does not.
RUN { \
      echo "memory_limit=1024M"; \
      echo "max_input_vars=20000"; \
      echo "upload_max_filesize=500M"; \
      echo "post_max_size=500M"; \
      echo "max_execution_time=300"; \
    } > /usr/local/etc/php/conf.d/moodle.ini

COPY apache.conf /etc/apache2/sites-enabled/000-default.conf
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 80
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["apache2-foreground"]
