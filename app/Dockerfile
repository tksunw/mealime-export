FROM python:3.12-slim
WORKDIR /app
COPY server.py ingredients.py grocery.py categories.json ./
COPY static/ static/
USER 1000:1000
ENV EXPORT_DIR=/export STATE_DIR=/state PORT=8443
EXPOSE 8443
CMD ["python", "server.py"]
