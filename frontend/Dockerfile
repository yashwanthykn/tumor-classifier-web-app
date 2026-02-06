FROM nginx:alpine

RUN rm -rf /usr/share/nginx/html/*

COPY index.html /usr/share/nginx/html/
COPY dashboard.html /usr/share/nginx/html/
COPY style.css /usr/share/nginx/html/
COPY auth.js /usr/share/nginx/html/
COPY dashboard.js /usr/share/nginx/html/

COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]