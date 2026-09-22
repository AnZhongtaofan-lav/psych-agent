#!/usr/bin/env bash
# ============================================================
# Git 推送脚本（Bash 版，Git Bash / macOS / Linux 通用）
# 用法：
#   1. 修改下方 GITHUB_REPO 为你的仓库地址
#   2. 执行: bash git-push.sh
# ============================================================
set -e   # 任一步失败立即中止

# ---------- 改成你自己的仓库地址 ----------
GITHUB_REPO="https://github.com/AnZhongtaofan-lav/psych-agent.git"
BRANCH="main"

cd "$(dirname "$0")"   # 切到脚本所在目录（项目根）

# ---------- 1. 初始化仓库 ----------
if [ ! -d ".git" ]; then
    git init
    git branch -M "$BRANCH"
    echo "[1/5] 已初始化 Git 仓库，主分支: $BRANCH"
else
    echo "[1/5] .git 已存在，跳过初始化"
fi

# ---------- 2. 安全自检 ----------
if [ -f ".env" ]; then
    echo "发现 .env 文件（真实密钥），已中止。请确认其已被 .gitignore 排除后再试。" >&2
    exit 1
fi
echo "[2/5] 敏感文件自检通过"

# ---------- 3. 暂存并提交 ----------
git add .
if ! git diff --cached --quiet; then
    git commit -m "feat: AI 心理服务智能体 v0.1.0 —— 三层架构（情绪识别/风险分级与高危拦截/PII 脱敏）"
    echo "[3/5] 已提交变更"
else
    echo "[3/5] 无新增变更"
fi

# ---------- 4. 关联远程仓库 ----------
if ! git remote | grep -q "^origin$"; then
    git remote add origin "$GITHUB_REPO"
else
    git remote set-url origin "$GITHUB_REPO"
fi
echo "[4/5] 远程仓库: $GITHUB_REPO"

# ---------- 5. 推送 ----------
git push -u origin "$BRANCH"
echo "[5/5] 推送成功！"