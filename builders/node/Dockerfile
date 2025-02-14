FROM node:20-slim

# Install build dependencies
RUN npm install -g \
    esbuild@0.20.1 \
    postcss-cli@11.0.0 \
    postcss@8.4.35 \
    autoprefixer@10.4.17 \
    tailwindcss@3.4.1

WORKDIR /build

# Create an entrypoint script that will handle different build types
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"] 