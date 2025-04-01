# This is a demo image for Python 3.12 to run user code in a sandboxed environment.
FROM python:3.13-slim

WORKDIR /app

# Create a non-root user
RUN useradd sandbox -m -s /bin/bash

# Install the required packages
RUN apt-get update && apt-get install -y && \
    pip3 install --upgrade pip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install numpy pandas

WORKDIR /app
