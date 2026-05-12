# 使用 Python 3.10 瘦身版
FROM python:3.10-slim

WORKDIR /app

# 安装必要的系统库（如 curl 用于健康检查）
RUN apt-get update && apt-get install -y curl gosu && rm -rf /var/lib/apt/lists/*



# 预安装常用的 Agent 开发包 + Web 服务依赖
RUN pip install --no-cache-dir \
    langchain \
    langchain-openai \
    python-dotenv \
    duckduckgo-search \
    openai \
    pyyaml \
    fastapi \
    "uvicorn[standard]" \
    httpx

# 暴露 Web API 端口
EXPOSE 9090

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 默认启动命令
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "server.py"]
