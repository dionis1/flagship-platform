FROM nginx:1.30.6-alpine

# The base image still bundles libexpat 2.8.5; pin its patched package.
RUN apk add --no-cache --upgrade 'libexpat=2.9.0-r0'

LABEL org.opencontainers.image.source="https://github.com/dionis1/flagship-platform"
LABEL org.opencontainers.image.description="Demo app for the DevOps flagship platform"
LABEL org.opencontainers.image.licenses="MIT"

COPY index.html /usr/share/nginx/html/index.html

EXPOSE 80
