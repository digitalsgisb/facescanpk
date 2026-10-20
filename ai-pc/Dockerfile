FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY index.html vite.config.js ./
COPY src ./src
COPY public ./public
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    groupadd --gid 10001 attendance && \
    useradd --uid 10001 --gid attendance --no-create-home attendance && \
    mkdir -p /app/runtime /app/data && chown attendance:attendance /app/runtime
COPY server.py manage.py employee_admin.py testing_operations.py ./
COPY data/employees.example.json ./data/employees.example.json
COPY --from=frontend /build/dist ./dist
USER attendance
EXPOSE 8765
CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "8765"]
