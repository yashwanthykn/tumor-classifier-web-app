FROM python:3.10-slim
ENV PYTHONDONTWRITEBYTECODE=1
# DOESNT CREATES .PYC FILES 
ENV PYTHONUNBUFFERED=1
# MAKE OUTPUT APPERS IN THE LOGS INMEDIATLY
WORKDIR /app

#These are OS-level native dependencies required by TensorFlow and image-processing libraries. They provide shared system libraries that Python packages rely on at runtime but cannot install themselves.

#pip installs Python code.
#apt installs the operating system libraries that Python code depends on.

#“Because ML frameworks like TensorFlow depend on native Linux shared libraries for image processing and numerical computation. When using minimal base images, these dependencies are not present by default, so they must be explicitly installed to ensure stable runtime behavior


#Linux shell command
#apt-get update gets the packeges index which is metadata i.e..package name available version size and dependencies

#“The base image contains the repository configuration. apt-get update uses that configuration to download the latest package lists from the repositories.”

#advance packaging tool

RUN apt-get update && apt-get install -y \
     build-essential \
     #installs c and c++ compiler  for native code 
     libglib2.0-0 \
     #for event looping and threading
     libsm6 \
     #X11 Session Management library used by openCV
     libxext6 \
     libxrender-dev \
     libmagic1 \
     #for detecting files type
     && rm -rf /var/lib/apt/lists/*
# cleans up installation files to reduce image size

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000 
#DOCUMENTS THE PORT THE CONTAINER LISTENS ON AT RUNTIME

CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
