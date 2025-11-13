@echo off
REM ============================================================================
REM Script de Setup Automatizado - Sistema de Matching PostgreSQL
REM ============================================================================

echo.
echo ================================================================================
echo   SETUP: Sistema de Matching Incentivos x Empresas
echo ================================================================================
echo.

REM Verificar se PostgreSQL está instalado
where psql >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] PostgreSQL nao encontrado!
    echo Por favor, instale PostgreSQL primeiro:
    echo https://www.postgresql.org/download/windows/
    exit /b 1
)

echo [OK] PostgreSQL encontrado
echo.

REM Configurações (ajustar conforme necessário)
set DB_USER=postgres
set DB_NAME=incentivos_db
set DB_HOST=localhost
set DB_PORT=5432

REM Solicitar senha
set /p DB_PASSWORD="Digite a senha do PostgreSQL (usuario %DB_USER%): "

REM String de conexão
set DB_URL=postgresql://%DB_USER%:%DB_PASSWORD%@%DB_HOST%:%DB_PORT%/%DB_NAME%

echo.
echo ================================================================================
echo   PASSO 1: Criar Database
echo ================================================================================
echo.

REM Criar database (ignora erro se já existir)
psql -U %DB_USER% -h %DB_HOST% -p %DB_PORT% -c "CREATE DATABASE %DB_NAME%;" 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [OK] Database '%DB_NAME%' criado
) else (
    echo [INFO] Database '%DB_NAME%' ja existe
)

echo.
echo ================================================================================
echo   PASSO 2: Criar Schema
echo ================================================================================
echo.

psql -U %DB_USER% -h %DB_HOST% -p %DB_PORT% -d %DB_NAME% -f schema.sql
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Falha ao criar schema
    exit /b 1
)

echo [OK] Schema criado com sucesso

echo.
echo ================================================================================
echo   PASSO 3: Verificar Dependencias Python
echo ================================================================================
echo.

python -c "import psycopg2" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Instalando psycopg2-binary...
    pip install psycopg2-binary
)

python -c "import pandas" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Instalando pandas...
    pip install pandas
)

python -c "import tqdm" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Instalando tqdm...
    pip install tqdm
)

echo [OK] Dependencias verificadas

echo.
echo ================================================================================
echo   PASSO 4: Importar Dados
echo ================================================================================
echo.

set /p IMPORT_DATA="Deseja importar os dados agora? (s/n): "
if /i "%IMPORT_DATA%"=="s" (
    echo.
    echo Importando empresas...
    python import_data.py --db "%DB_URL%" --companies "../data/companies.csv"
    
    echo.
    echo Importando incentivos...
    python import_data.py --db "%DB_URL%" --incentives "../data/incentives.csv"
    
    echo.
    echo [OK] Dados importados
) else (
    echo [INFO] Importacao pulada
)

echo.
echo ================================================================================
echo   PASSO 5: Executar Matching (Opcional)
echo ================================================================================
echo.

set /p RUN_MATCHING="Deseja executar o matching agora? (s/n): "
if /i "%RUN_MATCHING%"=="s" (
    echo.
    set /p LIMIT="Quantos incentivos processar? (deixe vazio para todos): "
    
    if "%LIMIT%"=="" (
        python matching_service.py --db "%DB_URL%" --status Active --verbose
    ) else (
        python matching_service.py --db "%DB_URL%" --status Active --limit %LIMIT% --verbose
    )
    
    echo.
    echo [OK] Matching concluido
) else (
    echo [INFO] Matching pulado
)

echo.
echo ================================================================================
echo   SETUP CONCLUIDO!
echo ================================================================================
echo.
echo Database: %DB_NAME%
echo Host: %DB_HOST%:%DB_PORT%
echo User: %DB_USER%
echo.
echo String de conexao:
echo %DB_URL%
echo.
echo Proximos passos:
echo   1. Executar matching: python matching_service.py --db "%DB_URL%"
echo   2. Ver exemplos: python example_usage.py --db "%DB_URL%"
echo   3. Consultar dados: psql -U %DB_USER% -d %DB_NAME%
echo.
echo ================================================================================

pause
