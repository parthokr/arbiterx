FROM python:3.13-slim

ARG GID=995
RUN useradd -ms /bin/bash app && \
    groupadd -g $GID docker && \
    usermod -aG docker app

WORKDIR /home/app

COPY . .

ENV POETRY_HOME="/opt/poetry"
ENV PATH="$POETRY_HOME/bin:$PATH"

RUN apt-get update && apt-get install -y curl \
                                        docker.io && \
    curl -sSL https://install.python-poetry.org | python3 - && \
    chown -R app:app /opt/poetry && \
    chown -R app:app /home/app && \
    poetry config virtualenvs.create false && \
    apt clean && \
    apt autoremove && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /home/app/submissions && \
    chown -R app:app /home/app/submissions

USER app

RUN poetry install --no-interaction --no-ansi && \
    poetry run pip install -U pip

CMD ["poetry", "run", "python3", "examples/python_code_executor_in_docker.py"]

