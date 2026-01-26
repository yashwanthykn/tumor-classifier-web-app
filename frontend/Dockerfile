FROM nginx:alpine

# Remove default nginx static files
RUN rm -rf /usr/share/nginx/html/*

# Copy static files (HTML, CSS, JS)
COPY index.html /usr/share/nginx/html/
COPY dashboard.html /usr/share/nginx/html/
COPY style.css /usr/share/nginx/html/
COPY auth.js /usr/share/nginx/html/
COPY dashboard.js /usr/share/nginx/html/

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Create a simple error page
RUN echo '<!DOCTYPE html><html><head><title>Error</title></head><body><h1>Something went wrong</h1><p>Please try again later.</p></body></html>' > /usr/share/nginx/html/50x.html

# Expose port 80
EXPOSE 80


# Start nginx (default command from base image, but explicit is better)
CMD ["nginx", "-g", "daemon off;"]