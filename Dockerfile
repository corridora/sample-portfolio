FROM node:22-alpine AS web
WORKDIR /build
COPY package*.json ./
RUN npm ci --no-audit --no-fund
COPY resources resources
COPY scripts/copy-assets.mjs scripts/copy-assets.mjs
COPY public public
RUN npm run build
FROM composer:2.8.12 AS dependencies
WORKDIR /app
COPY composer.* ./
RUN composer install --no-dev --no-interaction --prefer-dist --no-scripts --ignore-platform-req=ext-pdo_sqlite
FROM php:8.4-cli-alpine
RUN apk add --no-cache sqlite-dev oniguruma-dev && docker-php-ext-install pdo_sqlite mbstring
WORKDIR /app
COPY --from=dependencies /app/vendor vendor
COPY app app
COPY bootstrap bootstrap
COPY config config
COPY routes routes
COPY resources/views resources/views
COPY public public
COPY --from=web /build/public/assets public/assets
COPY scripts/router.php scripts/router.php
COPY BUILD_VERSION BUILD_VERSION
RUN mkdir -p storage/logs storage/framework/views storage/framework/cache bootstrap/cache .sample
EXPOSE 4105
CMD ["php","-d","memory_limit=128M","-S","0.0.0.0:4105","-t","public","scripts/router.php"]
