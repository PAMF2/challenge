# ============================================================================
# Setup Automatizado - PowerShell
# Sistema de Matching Incentivos x Empresas
# ============================================================================

Write-Host "`n================================================================================" -ForegroundColor Cyan
Write-Host "  SETUP: Sistema de Matching Incentivos x Empresas" -ForegroundColor Cyan
Write-Host "================================================================================`n" -ForegroundColor Cyan

# Configurações
$DB_USER = "postgres"
$DB_NAME = "incentivos_db"
$DB_HOST = "localhost"
$DB_PORT = "5432"

# Verificar se estamos na pasta correta
if (-not (Test-Path "schema.sql")) {
    Write-Host "[ERRO] Execute este script da pasta 'database'" -ForegroundColor Red
    Write-Host "Use: cd database; .\setup.ps1" -ForegroundColor Yellow
    exit 1
}

# Solicitar senha
$DB_PASSWORD = Read-Host "Digite a senha do PostgreSQL (usuario $DB_USER)" -AsSecureString
$BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($DB_PASSWORD)
$DB_PASSWORD_PLAIN = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)

$DB_URL = "postgresql://${DB_USER}:${DB_PASSWORD_PLAIN}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

# ============================================================================
# PASSO 1: Verificar PostgreSQL
# ============================================================================
Write-Host "`n[1/6] Verificando PostgreSQL..." -ForegroundColor Yellow

$psqlCmd = Get-Command psql -ErrorAction SilentlyContinue
if (-not $psqlCmd) {
    Write-Host "[AVISO] PostgreSQL não encontrado no PATH!" -ForegroundColor Yellow
    Write-Host "Tentando localizar instalação..." -ForegroundColor Yellow
    
    # Tentar encontrar PostgreSQL
    $pgPaths = @(
        "C:\Program Files\PostgreSQL\16\bin",
        "C:\Program Files\PostgreSQL\15\bin",
        "C:\Program Files\PostgreSQL\14\bin",
        "C:\Program Files (x86)\PostgreSQL\16\bin",
        "C:\Program Files (x86)\PostgreSQL\15\bin"
    )
    
    $foundPath = $null
    foreach ($path in $pgPaths) {
        if (Test-Path "$path\psql.exe") {
            $foundPath = $path
            break
        }
    }
    
    if ($foundPath) {
        Write-Host "[OK] PostgreSQL encontrado em: $foundPath" -ForegroundColor Green
        $env:Path += ";$foundPath"
    } else {
        Write-Host "[ERRO] PostgreSQL não encontrado!" -ForegroundColor Red
        Write-Host "Instale de: https://www.postgresql.org/download/windows/" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[OK] PostgreSQL encontrado" -ForegroundColor Green
}

# ============================================================================
# PASSO 2: Criar Database
# ============================================================================
Write-Host "`n[2/6] Criando database..." -ForegroundColor Yellow

$env:PGPASSWORD = $DB_PASSWORD_PLAIN
$createDbCmd = "CREATE DATABASE $DB_NAME;"

psql -U $DB_USER -h $DB_HOST -p $DB_PORT -c $createDbCmd 2>$null

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Database '$DB_NAME' criado" -ForegroundColor Green
} else {
    Write-Host "[INFO] Database '$DB_NAME' já existe (ou erro de conexão)" -ForegroundColor Yellow
}

# ============================================================================
# PASSO 3: Criar Schema
# ============================================================================
Write-Host "`n[3/6] Criando schema..." -ForegroundColor Yellow

psql -U $DB_USER -h $DB_HOST -p $DB_PORT -d $DB_NAME -f "schema.sql"

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Schema criado com sucesso" -ForegroundColor Green
} else {
    Write-Host "[ERRO] Falha ao criar schema" -ForegroundColor Red
    Write-Host "Verifique a senha e se o PostgreSQL está rodando" -ForegroundColor Yellow
    exit 1
}

# ============================================================================
# PASSO 4: Instalar Dependências Python
# ============================================================================
Write-Host "`n[4/6] Verificando dependências Python..." -ForegroundColor Yellow

$packages = @("psycopg2-binary", "pandas", "tqdm", "tabulate")
foreach ($pkg in $packages) {
    Write-Host "  Instalando $pkg..." -ForegroundColor Cyan
    pip install -q $pkg
}

Write-Host "[OK] Dependências instaladas" -ForegroundColor Green

# ============================================================================
# PASSO 5: Importar Dados
# ============================================================================
Write-Host "`n[5/6] Importando dados..." -ForegroundColor Yellow

$importData = Read-Host "Deseja importar os dados agora? (s/n)"

if ($importData -eq "s" -or $importData -eq "S") {
    Write-Host "`nImportando empresas (pode levar ~2 minutos)..." -ForegroundColor Cyan
    python import_data.py --db $DB_URL --companies "../data/companies.csv"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Empresas importadas" -ForegroundColor Green
    } else {
        Write-Host "[ERRO] Falha ao importar empresas" -ForegroundColor Red
    }
    
    Write-Host "`nImportando incentivos..." -ForegroundColor Cyan
    python import_data.py --db $DB_URL --incentives "../data/incentives.csv"
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Incentivos importados" -ForegroundColor Green
    } else {
        Write-Host "[ERRO] Falha ao importar incentivos" -ForegroundColor Red
    }
} else {
    Write-Host "[INFO] Importação pulada" -ForegroundColor Yellow
}

# ============================================================================
# PASSO 6: Executar Matching
# ============================================================================
Write-Host "`n[6/6] Executando matching..." -ForegroundColor Yellow

$runMatching = Read-Host "Deseja executar o matching agora? (s/n)"

if ($runMatching -eq "s" -or $runMatching -eq "S") {
    $limit = Read-Host "Quantos incentivos processar? (deixe vazio para todos, recomendado: 10 para teste)"
    
    if ($limit) {
        Write-Host "`nProcessando $limit incentivos..." -ForegroundColor Cyan
        python matching_service.py --db $DB_URL --status Active --limit $limit --verbose
    } else {
        Write-Host "`nProcessando todos os incentivos (pode levar ~17 minutos)..." -ForegroundColor Cyan
        python matching_service.py --db $DB_URL --status Active --verbose
    }
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Matching concluído" -ForegroundColor Green
    } else {
        Write-Host "[ERRO] Falha no matching" -ForegroundColor Red
    }
} else {
    Write-Host "[INFO] Matching pulado" -ForegroundColor Yellow
}

# ============================================================================
# RESUMO FINAL
# ============================================================================
Write-Host "`n================================================================================" -ForegroundColor Cyan
Write-Host "  SETUP CONCLUÍDO!" -ForegroundColor Cyan
Write-Host "================================================================================`n" -ForegroundColor Cyan

Write-Host "Database: $DB_NAME" -ForegroundColor White
Write-Host "Host: ${DB_HOST}:${DB_PORT}" -ForegroundColor White
Write-Host "User: $DB_USER`n" -ForegroundColor White

Write-Host "String de conexão:" -ForegroundColor Yellow
Write-Host "`$DB_URL = `"$DB_URL`"`n" -ForegroundColor Gray

Write-Host "Próximos passos:" -ForegroundColor Yellow
Write-Host "  1. Ver exemplos:" -ForegroundColor White
Write-Host "     python example_usage.py --db `"$DB_URL`" --example 1`n" -ForegroundColor Gray

Write-Host "  2. Consultar via psql:" -ForegroundColor White
Write-Host "     psql -U $DB_USER -d $DB_NAME" -ForegroundColor Gray
Write-Host "     SELECT * FROM v_top_matches LIMIT 10;`n" -ForegroundColor Gray

Write-Host "  3. Processar mais incentivos:" -ForegroundColor White
Write-Host "     python matching_service.py --db `"$DB_URL`" --status Active --limit 50`n" -ForegroundColor Gray

Write-Host "  4. Exportar resultados:" -ForegroundColor White
Write-Host "     python example_usage.py --db `"$DB_URL`" --example 7`n" -ForegroundColor Gray

Write-Host "================================================================================" -ForegroundColor Cyan

# Limpar senha da memória
Remove-Variable DB_PASSWORD_PLAIN -ErrorAction SilentlyContinue
Remove-Variable BSTR -ErrorAction SilentlyContinue

Write-Host "`nPressione qualquer tecla para sair..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
