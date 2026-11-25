FROM python:3.14-slim
# same library versions as the PC venv (ccxt + PyYAML are the only third-party imports)
RUN pip install --no-cache-dir ccxt==4.5.89 PyYAML==6.0.3
WORKDIR /app
