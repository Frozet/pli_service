FROM python:3.12.13-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       fonts-dejavu-core libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 pli \
    && useradd --system --uid 10001 --gid pli --no-create-home pli \
    && install -d -m 0750 -o pli -g pli /var/lib/pli/uploads

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip check
COPY . .

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/matplotlib
USER pli
EXPOSE 5001
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "2", "--timeout", "50", "--access-logfile", "-", "app:create_app()"]
