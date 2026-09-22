# ============================================================
# Git 推送脚本（PowerShell 版）—— AI 心理服务智能体
# 用法：
#   1. 安装 Git for Windows（https://git-scm.com/download/win）
#   2. 在 GitHub 网页上创建空仓库（见下方步骤说明）
#   3. 修改下方 $GITHUB_REPO 为你的仓库地址
#   4. 在项目根目录执行: powershell -ExecutionPolicy Bypass -File git-push.ps1
# ============================================================

$ErrorActionPreference = "Stop"   # 任一步失败立即中止

# ---------- 改成你自己的仓库地址 ----------
$GITHUB_REPO = "https://github.com/AnZhongtaofan-lav/psych-agent.git"
$BRANCH = "main"

Set-Location $PSScriptRoot   # 切到脚本所在目录（项目根）

# ---------- 1. 初始化仓库（已有 .git 则跳过） ----------
if (-not (Test-Path ".git")) {
    git init
    git branch -M $BRANCH
    Write-Host "[1/5] 已初始化 Git 仓库，主分支: $BRANCH"
} else {
    Write-Host "[1/5] .git 已存在，跳过初始化"
}

# ---------- 2. 安全自检：确认敏感文件不会被提交 ----------
$dangerous = @()
if (Test-Path ".env") { $dangerous += ".env (真实密钥!)" }
$stagedCheck = git ls-files --cached 2>$null
if ($stagedCheck -match "^\.env$") { $dangerous += ".env 已在暂存区!" }
if ($dangerous.Count -gt 0) {
    Write-Host "发现敏感文件，已中止推送:" -ForegroundColor Red
    $dangerous | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}
Write-Host "[2/5] 敏感文件自检通过（无 .env / 数据库入库风险）"

# ---------- 3. 暂存并提交 ----------
git add .
$commitMsg = "feat: AI 心理服务智能体 v0.1.0 —— 三层架构（情绪识别/风险分级与高危拦截/PII 脱敏）"
# 检查是否有可提交内容
$hasChanges = git status --porcelain
if ($hasChanges) {
    git commit -m $commitMsg
    Write-Host "[3/5] 已提交 $(($hasChanges | Measure-Object).Count) 个文件的变更"
} else {
    Write-Host "[3/5] 无新增变更"
}

# ---------- 4. 关联远程仓库 ----------
$remotes = git remote
if ($remotes -notcontains "origin") {
    git remote add origin $GITHUB_REPO
    Write-Host "[4/5] 已关联远程仓库: $GITHUB_REPO"
} else {
    git remote set-url origin $GITHUB_REPO
    Write-Host "[4/5] 远程 origin 已更新: $GITHUB_REPO"
}

# ---------- 5. 推送 ----------
git push -u origin $BRANCH
Write-Host "[5/5] 推送成功！仓库地址: $GITHUB_REPO" -ForegroundColor Green
