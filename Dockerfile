# Используем образ Python
FROM python:3.12-slim

COPY requirements.txt requirements.txt
# Устанавливаем зависимости для wkhtmltopdf и PostgreSQL
RUN apt-get update -y && apt-get install -y \
    python3-pip \
    libpq-dev \
    wkhtmltopdf \
    xfonts-75dpi \
    xfonts-base \
    && rm -rf /var/lib/apt/lists/*

# Указываем рабочую директорию
WORKDIR /app

# Копируем все файлы в контейнер
COPY . /app

# Устанавливаем зависимости из requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем переменную окружения для wkhtmltopdf
ENV WKHTMLTOPDF_PATH=/usr/bin/wkhtmltopdf

# Указываем порт, на котором будет работать приложение
EXPOSE 5000

CMD ["python", "createdb.py"]

# Команда для запуска приложения
CMD ["python", "app.py"]