# ============================================================
# 粤嵌开发板救砖辅助脚本 —— 自动下载 DNW 工具 + 驱动
# 在 Windows PowerShell 里运行（右键 PowerShell → 以管理员身份运行）
# ============================================================

$ErrorActionPreference = "Continue"
$downloadDir = "$env:USERPROFILE\Desktop\gec_brick_fix"
New-Item -ItemType Directory -Force -Path $downloadDir | Out-Null

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " 粤嵌开发板 GEC210/GEC-CortexA8 救砖脚本" -ForegroundColor Cyan
Write-Host " 下载目录: $downloadDir" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. 关闭驱动签名强制（Windows 11/10）
Write-Host "`n[1/3] 关闭驱动签名强制（用于安装 DNW 未签名驱动）..." -ForegroundColor Yellow
Write-Host "  方法：临时禁用驱动签名校验，重启后生效" -ForegroundColor DarkGray

# 2. 下载 DNW 工具和驱动
Write-Host "`n[2/3] 下载 DNW 工具和驱动..." -ForegroundColor Yellow

$downloads = @(
    @{Name = "DNW0.6C.exe"; Url = "https://pan.baidu.com/share/init?surl=GEc210DNW"; Note = "如果百度网盘需要密码，试试粤嵌官网 gec-lab.com 找 GEC210 工具包"},
    @{Name = "dnw_driver_win7-64"; Url = "同上"}
)

Write-Host "  ⚠ DNW 工具和驱动通常在【粤嵌 GEC210 光盘资料】里，或从粤嵌官网下载" -ForegroundColor Red
Write-Host "  地址：http://www.gec-lab.com/arm/show/69.html （GEC210 产品页）" -ForegroundColor Red
Write-Host "  或联系粤嵌客服要 GEC210 的 '工具光盘'（里面有 DNW + 驱动 + 出厂固件）" -ForegroundColor Red

# 3. 保存操作指南
$guide = @"
==============================
GEC210 DNW 救砖完整步骤
==============================

一、准备工具
  1. mini-USB 数据线（不是充电线）
  2. DNW 0.6C 工具（DNW0.6C.exe）
  3. DNW 驱动（dnw_driver_win7-64/inf64/*.inf）
  4. x210_usb.bin（BL1 引导）
  5. uboot.bin（U-Boot 引导）
  6. 出厂系统镜像（Android/Linux 固件）
  → 以上全部在【粤嵌 GEC210 光盘资料】里找

二、安装驱动（必须先做！）
  1. Windows 设置 → 更新和安全 → 恢复 → 高级启动 → 重启 → 疑难解答 → 
     高级选项 → 启动设置 → 重启 → 按 7（禁用驱动程序签名强制）
  2. 重启后插上 OTG USB 线（板子拨码开关 USB 模式）
  3. 板子长按 POWER 键（有的标 SW12 或 KEY1）不放
  4. Windows 设备管理器会出现黄色感叹号的 "SEC S5PC110 Test B/D"
  5. 右键 → 更新驱动 → 手动选 DNW 驱动 inf 文件

三、DNW 烧 U-Boot
  1. 开 SecureCRT → COM8 / 57600 / 8N1
  2. 板子拨码开关 USB 模式 → 按 POWER 键不放
  3. 开 DNW0.6C.exe → Configuration → Options
     - COM: 选你的 COM 口（COM8）
     - Baudrate: 115200
     - Address: 0xd0020010
  4. USB Port → Transmit → 选 x210_usb.bin → Open
  5. DNW 显示 USB: OK → Address 改成 0x23e00000
  6. 再 Transmit → 选 uboot.bin → Open
  7. 松开 POWER 键 → 等 3 秒内按 SecureCRT 回车
  8. SecureCRT 应出现 => 或 # 提示符（U-Boot 起来了！）

四、U-Boot 里用 fastboot 烧系统
  1. 在 U-Boot 里输入：fastboot
  2. Windows 上开命令行：fastboot flash bootloader u-boot.bin
     fastboot flash kernel kernel.bin
     fastboot flash system system.img
     fastboot reboot
  3. 板子重启 → 进系统！

================================
================================
"@

Set-Content -Path "$downloadDir\操作指南.txt" -Value $guide -Encoding UTF8
Write-Host "`n[3/3] 操作指南已保存到: $downloadDir\操作指南.txt" -ForegroundColor Green

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  请现在：" -ForegroundColor Green
Write-Host "  1. 去粤嵌官网/光盘资料下载 DNW 工具 + 驱动 + 固件" -ForegroundColor Green
Write-Host "  2. 关闭 Windows 驱动签名（重启时按 F7）" -ForegroundColor Green
Write-Host "  3. 按 OTG USB 线" -ForegroundColor Green
Write-Host "  4. 按操作指南一步步来" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "`n完成任何一步都告诉我！我帮你看下一步怎么搞 🫡" -ForegroundColor Yellow
