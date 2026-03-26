# ========================================================
# D-Bot 毕设实战启动脚本 (PowerShell)
# ========================================================
# 使用方法: 在项目根目录执行 .\start_all.ps1
# ========================================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  D-Bot 毕设实战系统启动中..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 获取项目根目录
$ProjectRoot = $PSScriptRoot
Write-Host "[INFO] 项目目录: $ProjectRoot" -ForegroundColor Gray

# ========================================================
# 1. 端口占用检测
# ========================================================
Write-Host "`n[步骤0] 端口占用检测..." -ForegroundColor Yellow

$Port7861 = Get-NetTCPConnection -LocalPort 7861 -ErrorAction SilentlyContinue
$Port3000 = Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue
$Port5432 = Get-NetTCPConnection -LocalPort 5432 -ErrorAction SilentlyContinue

if ($Port7861) {
    Write-Host "  [WARNING] 端口 7861 已被占用 (后端服务)" -ForegroundColor Yellow
    Write-Host "  解决方案: Stop-Process -Id $($Port7861.OwningProcess) -Force" -ForegroundColor Gray
}

if ($Port3000) {
    Write-Host "  [WARNING] 端口 3000 已被占用 (前端服务)" -ForegroundColor Yellow
    Write-Host "  解决方案: Stop-Process -Id $($Port3000.OwningProcess) -Force" -ForegroundColor Gray
}

if ($Port5432) {
    Write-Host "  [OK] 端口 5432 已被监听 (PostgreSQL)" -ForegroundColor Green
} else {
    Write-Host "  [WARNING] 端口 5432 未被监听 (PostgreSQL 可能未启动)" -ForegroundColor Yellow
}

# ========================================================
# 2. 前置条件检查
# ========================================================
Write-Host "`n[步骤1] 前置条件检查..." -ForegroundColor Yellow

# 检查 Python
$PythonCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCmd = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $PythonCmd = "python3"
} else {
    Write-Host "[ERROR] 未找到 Python，请先安装 Python 3.8+" -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] Python: $PythonCmd" -ForegroundColor Green

# 检查 Node.js
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] 未找到 Node.js，请先安装 Node.js 18+" -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] Node.js: $(node -v)" -ForegroundColor Green

# ========================================================
# 3. 数据库连接测试
# ========================================================
Write-Host "`n[步骤2] 数据库连接测试..." -ForegroundColor Yellow

$DbTestScript = Join-Path $ProjectRoot "test_db_connection.py"
if (Test-Path $DbTestScript) {
    $DbTestResult = & $PythonCmd $DbTestScript 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] 数据库连接成功" -ForegroundColor Green
    } else {
        Write-Host "  [WARNING] 数据库连接失败，将使用 Mock 数据" -ForegroundColor Yellow
    }
} else {
    Write-Host "  [WARNING] 测试脚本不存在，跳过数据库测试" -ForegroundColor Yellow
}

# ========================================================
# 4. 知识库加载测试
# ========================================================
Write-Host "`n[步骤3] 知识库加载测试..." -ForegroundColor Yellow

$KbTestScript = Join-Path $ProjectRoot "test_knowledge_loader.py"
if (Test-Path $KbTestScript) {
    $KbTestResult = & $PythonCmd $KbTestScript 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] 知识库加载成功" -ForegroundColor Green
    } else {
        Write-Host "  [WARNING] 知识库加载失败" -ForegroundColor Yellow
    }
} else {
    Write-Host "  [WARNING] 测试脚本不存在，跳过知识库测试" -ForegroundColor Yellow
}

# ========================================================
# 5. 检查依赖
# ========================================================
Write-Host "`n[步骤4] 检查依赖..." -ForegroundColor Yellow

# 检查 psycopg2
$Psycopg2Check = & $PythonCmd -c "import psycopg2; print('OK')" 2>$null
if ($Psycopg2Check -eq "OK") {
    Write-Host "  [OK] psycopg2 已安装" -ForegroundColor Green
} else {
    Write-Host "  [WARNING] psycopg2 未安装，正在安装..." -ForegroundColor Yellow
    & $PythonCmd -m pip install psycopg2-binary --quiet
}

# 检查前端依赖
$WebuiDir = Join-Path $ProjectRoot "webui-react"
$NodeModules = Join-Path $WebuiDir "node_modules"
if (-not (Test-Path $NodeModules)) {
    Write-Host "  [INFO] 安装前端依赖..." -ForegroundColor Yellow
    Push-Location $WebuiDir
    npm install
    Pop-Location
} else {
    Write-Host "  [OK] 前端依赖已存在" -ForegroundColor Green
}

# ========================================================
# 6. 启动后端
# ========================================================
Write-Host "`n[步骤5] 启动后端服务..." -ForegroundColor Yellow

$BackendScript = Join-Path $ProjectRoot "server\api.py"
if (-not (Test-Path $BackendScript)) {
    Write-Host "[ERROR] 后端入口文件不存在: $BackendScript" -ForegroundColor Red
    exit 1
}

# 启动后端 (后台运行)
$BackendJob = Start-Job -ScriptBlock {
    param($Dir, $Python)
    Set-Location $Dir
    & $Python server/api.py --host 0.0.0.0 --port 7861
} -ArgumentList $ProjectRoot, $PythonCmd

Write-Host "  [OK] 后端服务已启动 (PID: $($BackendJob.Id))" -ForegroundColor Green
Write-Host "  [INFO] 后端地址: http://localhost:7861" -ForegroundColor Gray
Write-Host "  [INFO] API 文档: http://localhost:7861/docs" -ForegroundColor Gray

# 等待后端启动
Write-Host "  [INFO] 等待后端初始化..." -ForegroundColor Gray
Start-Sleep -Seconds 5

# ========================================================
# 7. 启动前端
# ========================================================
Write-Host "`n[步骤6] 启动前端服务..." -ForegroundColor Yellow

Push-Location $WebuiDir

# 启动前端 (后台运行)
$FrontendJob = Start-Job -ScriptBlock {
    param($Dir)
    Set-Location $Dir
    npm run dev
} -ArgumentList $WebuiDir

Pop-Location

Write-Host "  [OK] 前端服务已启动 (PID: $($FrontendJob.Id))" -ForegroundColor Green
Write-Host "  [INFO] 前端地址: http://localhost:3000" -ForegroundColor Gray

# ========================================================
# 8. 全链路连通性报告
# ========================================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  全链路连通性报告" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan

Start-Sleep -Seconds 3

# 测试后端 API
Write-Host "`n[连通性测试] 后端 API..." -ForegroundColor Yellow
try {
    $ApiResponse = Invoke-WebRequest -Uri "http://localhost:7861/docs" -TimeoutSec 5 -ErrorAction Stop
    Write-Host "  [OK] 后端 API 响应正常 (状态码: $($ApiResponse.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "  [WARNING] 后端 API 未就绪: $($_.Exception.Message)" -ForegroundColor Yellow
}

# 测试前端
Write-Host "`n[连通性测试] 前端服务..." -ForegroundColor Yellow
try {
    $FrontendResponse = Invoke-WebRequest -Uri "http://localhost:3000" -TimeoutSec 5 -ErrorAction Stop
    Write-Host "  [OK] 前端服务响应正常 (状态码: $($FrontendResponse.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "  [WARNING] 前端服务未就绪: $($_.Exception.Message)" -ForegroundColor Yellow
}

# 测试 Dashboard API
Write-Host "`n[连通性测试] Dashboard API..." -ForegroundColor Yellow
try {
    $DashboardResponse = Invoke-RestMethod -Uri "http://localhost:7861/api/dashboard/metrics" -TimeoutSec 5 -ErrorAction Stop
    if ($DashboardResponse.code -eq 200) {
        Write-Host "  [OK] Dashboard API 正常" -ForegroundColor Green
        if ($DashboardResponse.data.database_status.connected) {
            Write-Host "  [OK] 数据库已连接 (真实数据模式)" -ForegroundColor Green
        } else {
            Write-Host "  [INFO] 数据库未连接 (Mock 数据模式)" -ForegroundColor Gray
        }
    }
} catch {
    Write-Host "  [WARNING] Dashboard API 未就绪: $($_.Exception.Message)" -ForegroundColor Yellow
}

# ========================================================
# 9. 输出启动信息
# ========================================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  D-Bot 系统启动完成!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan

Write-Host ""
Write-Host "访问地址:" -ForegroundColor White
Write-Host "  - 前端界面: http://localhost:3000" -ForegroundColor Gray
Write-Host "  - 后端 API: http://localhost:7861" -ForegroundColor Gray
Write-Host "  - API 文档: http://localhost:7861/docs" -ForegroundColor Gray
Write-Host ""
Write-Host "数据库配置:" -ForegroundColor White
Write-Host "  - 类型: PostgreSQL" -ForegroundColor Gray
Write-Host "  - 地址: 127.0.0.1:5432" -ForegroundColor Gray
Write-Host "  - 数据库: dbgpt_metadata" -ForegroundColor Gray
Write-Host "  - 用户: postgres" -ForegroundColor Gray
Write-Host ""
Write-Host "知识库:" -ForegroundColor White
Write-Host "  - 路径: doc2knowledge/root_causes_dbmind.jsonl" -ForegroundColor Gray
Write-Host "  - 根因数量: 37 种" -ForegroundColor Gray
Write-Host ""
Write-Host "停止服务:" -ForegroundColor White
Write-Host "  - 执行: Get-Job | Remove-Job -Force" -ForegroundColor Gray
Write-Host ""
Write-Host "按 Ctrl+C 停止所有服务..." -ForegroundColor Yellow

# ========================================================
# 10. 保持运行
# ========================================================
try {
    while ($true) {
        Start-Sleep -Seconds 10
    }
}
catch {
    Write-Host "`n[INFO] 正在停止服务..." -ForegroundColor Yellow
}
finally {
    Get-Job | Remove-Job -Force -ErrorAction SilentlyContinue
    Write-Host "[OK] 服务已停止" -ForegroundColor Green
}