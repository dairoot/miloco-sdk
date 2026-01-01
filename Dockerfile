FROM python:3.12-slim

ENV LANG=C.UTF-8 TZ=Asia/Shanghai

MAINTAINER dairoot

WORKDIR /app

# 更新源
RUN sed -i "s@http://deb.debian.org@https://mirrors.163.com@g" /etc/apt/sources.list.d/debian.sources

RUN apt-get update && \
    apt-get install -y --no-install-recommends iputils-ping && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*


ENV PIP_INDEX_URL=https://mirrors.tencent.com/pypi/simple
ENV PIP_TRUSTED_HOST=mirrors.tencent.com

COPY . .

RUN  pip install -U pip && pip install -e .

# 运行命令
# docker build -t miloco-sdk .
# docker run -it --network bridge -v $(pwd):/app miloco-sdk bash
