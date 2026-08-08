FROM node:24-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html tsconfig.json vite.config.ts ./
COPY public public
COPY src src
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY runtime/config.template.js /opt/kaos-memos/config.template.js
COPY runtime/40-write-config.sh /docker-entrypoint.d/40-write-config.sh
COPY --from=build /app/dist /usr/share/nginx/html

RUN chmod 0755 /docker-entrypoint.d/40-write-config.sh

EXPOSE 80
