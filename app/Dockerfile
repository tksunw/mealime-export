FROM python:3.12-slim
WORKDIR /app
COPY server.py ingredients.py categories.json ./
COPY static/ static/
USER 1000:1000
ENV EXPORT_DIR=/export PORT=8443
EXPOSE 8443
CMD ["python", "server.py"]
