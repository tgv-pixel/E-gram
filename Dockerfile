FROM python:3.11-alpine

WORKDIR /app

# Install build dependencies for Alpine
RUN apk add --no-cache g++ gcc musl-dev python3-dev

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

CMD gunicorn server:app --bind 0.0.0.0:$PORT
