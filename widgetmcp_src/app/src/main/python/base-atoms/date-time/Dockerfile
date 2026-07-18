FROM python:3.12-slim
WORKDIR /atom
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
ENV HOST=0.0.0.0 PORT=9010
EXPOSE 9010
CMD ["python", "server.py"]
