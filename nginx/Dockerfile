# Use the official lightweight Nginx image.
# Keep the same base image as our existing deployment.
FROM nginx:stable-alpine

# Copy our version-controlled reverse proxy configuration
# directly into the Docker image at build time.
#
# This eliminates the need to mount the configuration
# from the Windows or WSL filesystem at runtime.
COPY default.conf /etc/nginx/conf.d/default.conf

# Document the HTTP port used by Nginx.
EXPOSE 80

# Run Nginx in the foreground so Docker can manage
# the lifecycle of the container.
CMD ["nginx", "-g", "daemon off;"]
