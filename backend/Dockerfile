FROM python:3.12-slim

# Рабочая директория
WORKDIR /app

# Системные зависимости + Node.js 20 + claude CLI (интернет-разведка верификации via WebSearch)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    ca-certificates \
    gnupg \
    fonts-dejavu-core \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Предзагружаем эмбеддинг-модель для семантического поиска (в кэш fastembed)
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"

# Копируем код приложения
COPY . .

# Создаём папку для файлов
RUN mkdir -p /app/storage

# Команда по умолчанию
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]