FROM oven/bun:alpine

# 安装 git (Alpine 使用 apk 包管理器)
RUN apk add --no-cache git

RUN git --version && bun --version

# 设置默认工作目录
WORKDIR /app

CMD ["/bin/sh"]