FROM nginx:alpine

RUN rm -rf /usr/share/nginx/html/*

# Shared design system
COPY clinical.css        /usr/share/nginx/html/
COPY tailwind.config.js  /usr/share/nginx/html/

# Pages
COPY index.html          /usr/share/nginx/html/
COPY dashboard.html      /usr/share/nginx/html/
COPY chat.html           /usr/share/nginx/html/

# Page-specific stylesheets
COPY index.css           /usr/share/nginx/html/
COPY dashboard.css       /usr/share/nginx/html/
COPY chat.css            /usr/share/nginx/html/

# JavaScript
COPY auth.js             /usr/share/nginx/html/
COPY dashboard.js        /usr/share/nginx/html/
COPY chat.js             /usr/share/nginx/html/

# Nginx config
COPY nginx.conf          /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]