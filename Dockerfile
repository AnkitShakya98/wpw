FROM python:3.11.7-slim

RUN apt-get update -y && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
        ffmpeg \
        aria2 \
        python3-pip \
        wget \
        curl \
        tar \
        make \
        g++ \
        cmake \
        unzip \
    && wget -q https://github.com/axiomatic-systems/Bento4/archive/v1.6.0-639.zip \
    && unzip v1.6.0-639.zip \
    && cd Bento4-1.6.0-639 \
    && mkdir build \
    && cd build \
    && cmake .. \
    && make -j$(nproc) \
    && cp mp4decrypt /usr/local/bin/ \
    && cd ../.. \
    && rm -rf Bento4-1.6.0-639 v1.6.0-639.zip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
    

    
WORKDIR /app

COPY requirements.txt /app/
# RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium
    
COPY . .


EXPOSE 1000

CMD gunicorn app:app & python3 pw.py
