FROM python:3.12-slim
WORKDIR /atom
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
ENV HOST=0.0.0.0 PORT=9005
EXPOSE 9005
CMD ["python", "server.py"]
