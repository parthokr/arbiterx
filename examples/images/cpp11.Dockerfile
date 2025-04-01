# This is a demo image for C++ 11 to run user code in a sandboxed environment.

FROM gcc:11.2.0

WORKDIR /app

# Create a non-root user
RUN useradd sandbox -m -s /bin/bash

# Install the required packages
RUN apt-get update && apt-get install -y && \
    apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
