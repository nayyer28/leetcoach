FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY leetcoach /app/leetcoach
COPY migrations /app/migrations
COPY main.py /app/main.py
COPY tests /app/tests

RUN python -m pip install --upgrade pip \
    && python -m pip install -e .

ENTRYPOINT ["lch"]
CMD ["--help"]
