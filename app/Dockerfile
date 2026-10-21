FROM python:3.12-slim
WORKDIR /app
# build context is the repo root (compose: context: .., dockerfile: app/Dockerfile) so the
# markdown writer from the exporter ships too
COPY app/server.py app/ingredients.py app/grocery.py app/importer.py app/categories.json mealime_export.py ./
COPY app/static/ static/
USER 1000:1000
ENV EXPORT_DIR=/export STATE_DIR=/state PORT=8443
EXPOSE 8443
CMD ["python", "server.py"]
