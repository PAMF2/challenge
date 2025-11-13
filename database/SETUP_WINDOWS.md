# 🪟 Guia de Setup - Windows PowerShell

## Problemas Comuns e Soluções

### 1. Executar .bat no PowerShell

```powershell
# ❌ Não funciona
setup.bat

# ✅ Funciona
.\setup.bat
# ou
cmd /c setup.bat
```

### 2. Caminhos de Arquivo

```powershell
# ❌ Caminho duplicado (você está em database/)
python database/import_data.py

# ✅ Caminho correto
python import_data.py
# ou volte para raiz
cd ..
python database/import_data.py
```

### 3. PostgreSQL não está no PATH

```powershell
# Verificar se PostgreSQL está instalado
Get-Command psql -ErrorAction SilentlyContinue

# Se não encontrar, adicionar ao PATH temporariamente
$env:Path += ";C:\Program Files\PostgreSQL\16\bin"

# Ou permanentemente (como Admin)
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\Program Files\PostgreSQL\16\bin", "Machine")
```

## 🚀 Setup Passo a Passo (PowerShell)

### Passo 1: Instalar PostgreSQL

```powershell
# Opção 1: Via Chocolatey
choco install postgresql

# Opção 2: Download manual
# https://www.postgresql.org/download/windows/
# Instalar e anotar a senha do usuário postgres
```

### Passo 2: Verificar Instalação

```powershell
# Adicionar PostgreSQL ao PATH (ajustar versão)
$env:Path += ";C:\Program Files\PostgreSQL\16\bin"

# Testar
psql --version
```

### Passo 3: Criar Database

```powershell
# Conectar como postgres
psql -U postgres

# No prompt do psql:
CREATE DATABASE incentivos_db;
\c incentivos_db
\q
```

### Passo 4: Criar Schema

```powershell
# Voltar para raiz do projeto
cd "C:\Users\Pichau\Desktop\Projeto Augusta"

# Executar schema
psql -U postgres -d incentivos_db -f database/schema.sql
```

### Passo 5: Instalar Dependências Python

```powershell
pip install psycopg2-binary pandas tqdm tabulate
```

### Passo 6: Importar Dados

```powershell
# Definir string de conexão (ajustar senha)
$DB_URL = "postgresql://postgres:SUA_SENHA@localhost:5432/incentivos_db"

# Importar empresas
python database/import_data.py --db $DB_URL --companies "data/companies.csv"

# Importar incentivos
python database/import_data.py --db $DB_URL --incentives "data/incentives.csv"
```

### Passo 7: Executar Matching

```powershell
# Processar um incentivo de teste
python database/matching_service.py --db $DB_URL --incentive-id 3406 --verbose

# Processar todos (limite de 10 para teste)
python database/matching_service.py --db $DB_URL --status Active --limit 10 --verbose
```

### Passo 8: Consultar Resultados

```powershell
# Via Python
python database/example_usage.py --db $DB_URL --example 1

# Via psql
psql -U postgres -d incentivos_db

# No prompt do psql:
SELECT * FROM v_top_matches WHERE incentive_project_id = 3406;
\q
```

## 📝 Script PowerShell Completo

Salve como `setup.ps1`:

```powershell
# Setup Automatizado - PowerShell
Write-Host "`n================================================================================" -ForegroundColor Cyan
Write-Host "  SETUP: Sistema de Matching Incentivos x Empresas" -ForegroundColor Cyan
Write-Host "================================================================================`n" -ForegroundColor Cyan

# Configurações
$DB_USER = "postgres"
$DB_NAME = "incentivos_db"
$DB_HOST = "localhost"
$DB_PORT = "5432"

# Solicitar senha
$DB_PASSWORD = Read-Host "Digite a senha do PostgreSQL (usuario $DB_USER)" -AsSecureString
$BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($DB_PASSWORD)
$DB_PASSWORD_PLAIN = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)

$DB_URL = "postgresql://${DB_USER}:${DB_PASSWORD_PLAIN}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

# Verificar PostgreSQL
Write-Host "`n[1/6] Verificando PostgreSQL..." -ForegroundColor Yellow
$psqlCmd = Get-Command psql -ErrorAction SilentlyContinue
if (-not $psqlCmd) {
    Write-Host "[ERRO] PostgreSQL não encontrado no PATH!" -ForegroundColor Red
    Write-Host "Adicione PostgreSQL ao PATH ou instale: https://www.postgresql.org/download/windows/" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] PostgreSQL encontrado" -ForegroundColor Green

# Criar database
Write-Host "`n[2/6] Criando database..." -ForegroundColor Yellow
$createDbCmd = "CREATE DATABASE $DB_NAME;"
$env:PGPASSWORD = $DB_PASSWORD_PLAIN
psql -U $DB_USER -h $DB_HOST -p $DB_PORT -c $createDbCmd 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Database '$DB_NAME' criado" -ForegroundColor Green
} else {
    Write-Host "[INFO] Database '$DB_NAME' já existe" -ForegroundColor Yellow
}

# Criar schema
Write-Host "`n[3/6] Criando schema..." -ForegroundColor Yellow
psql -U $DB_USER -h $DB_HOST -p $DB_PORT -d $DB_NAME -f "database/schema.sql"
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Schema criado" -ForegroundColor Green
} else {
    Write-Host "[ERRO] Falha ao criar schema" -ForegroundColor Red
    exit 1
}

# Instalar dependências
Write-Host "`n[4/6] Verificando dependências Python..." -ForegroundColor Yellow
pip install -q psycopg2-binary pandas tqdm tabulate
Write-Host "[OK] Dependências instaladas" -ForegroundColor Green

# Importar dados
Write-Host "`n[5/6] Importando dados..." -ForegroundColor Yellow
$importData = Read-Host "Deseja importar os dados agora? (s/n)"
if ($importData -eq "s") {
    Write-Host "Importando empresas..." -ForegroundColor Cyan
    python database/import_data.py --db $DB_URL --companies "data/companies.csv"
    
    Write-Host "Importando incentivos..." -ForegroundColor Cyan
    python database/import_data.py --db $DB_URL --incentives "data/incentives.csv"
    
    Write-Host "[OK] Dados importados" -ForegroundColor Green
} else {
    Write-Host "[INFO] Importação pulada" -ForegroundColor Yellow
}

# Executar matching
Write-Host "`n[6/6] Executando matching..." -ForegroundColor Yellow
$runMatching = Read-Host "Deseja executar o matching agora? (s/n)"
if ($runMatching -eq "s") {
    $limit = Read-Host "Quantos incentivos processar? (deixe vazio para todos)"
    
    if ($limit) {
        python database/matching_service.py --db $DB_URL --status Active --limit $limit --verbose
    } else {
        python database/matching_service.py --db $DB_URL --status Active --verbose
    }
    
    Write-Host "[OK] Matching concluído" -ForegroundColor Green
} else {
    Write-Host "[INFO] Matching pulado" -ForegroundColor Yellow
}

# Resumo
Write-Host "`n================================================================================" -ForegroundColor Cyan
Write-Host "  SETUP CONCLUÍDO!" -ForegroundColor Cyan
Write-Host "================================================================================`n" -ForegroundColor Cyan
Write-Host "Database: $DB_NAME" -ForegroundColor White
Write-Host "Host: ${DB_HOST}:${DB_PORT}" -ForegroundColor White
Write-Host "User: $DB_USER`n" -ForegroundColor White
Write-Host "Próximos passos:" -ForegroundColor Yellow
Write-Host "  1. Ver exemplos: python database/example_usage.py --db `"$DB_URL`" --example 1" -ForegroundColor White
Write-Host "  2. Consultar dados: psql -U $DB_USER -d $DB_NAME" -ForegroundColor White
Write-Host "`n================================================================================" -ForegroundColor Cyan

# Limpar senha da memória
Remove-Variable DB_PASSWORD_PLAIN
```

## 🎯 Comandos Rápidos (Copiar e Colar)

### Setup Completo

```powershell
# 1. Navegar para projeto
cd "C:\Users\Pichau\Desktop\Projeto Augusta"

# 2. Adicionar PostgreSQL ao PATH (ajustar versão)
$env:Path += ";C:\Program Files\PostgreSQL\16\bin"

# 3. Criar database
psql -U postgres -c "CREATE DATABASE incentivos_db;"

# 4. Criar schema
psql -U postgres -d incentivos_db -f database/schema.sql

# 5. Instalar dependências
pip install psycopg2-binary pandas tqdm tabulate

# 6. Definir conexão (AJUSTAR SENHA!)
$DB_URL = "postgresql://postgres:SUA_SENHA@localhost:5432/incentivos_db"

# 7. Importar dados
python database/import_data.py --db $DB_URL --companies "data/companies.csv"
python database/import_data.py --db $DB_URL --incentives "data/incentives.csv"

# 8. Executar matching (teste com 1 incentivo)
python database/matching_service.py --db $DB_URL --incentive-id 3406 --verbose

# 9. Ver resultados
python database/example_usage.py --db $DB_URL --example 1
```

### Consultas Rápidas

```powershell
# Ver top matches
python -c "import psycopg2; import pandas as pd; conn = psycopg2.connect('$DB_URL'); df = pd.read_sql('SELECT * FROM v_top_matches LIMIT 10', conn); print(df)"

# Ou via psql
psql -U postgres -d incentivos_db -c "SELECT * FROM v_top_matches LIMIT 10;"
```

## 🔧 Troubleshooting

### Erro: "psql não é reconhecido"

```powershell
# Encontrar instalação do PostgreSQL
Get-ChildItem "C:\Program Files" -Filter "PostgreSQL" -Directory -Recurse -ErrorAction SilentlyContinue

# Adicionar ao PATH (ajustar caminho)
$env:Path += ";C:\Program Files\PostgreSQL\16\bin"

# Verificar
psql --version
```

### Erro: "can't open file database/database/..."

```powershell
# Você está em database/, então use:
python import_data.py --db $DB_URL --companies "../data/companies.csv"

# Ou volte para raiz:
cd ..
python database/import_data.py --db $DB_URL --companies "data/companies.csv"
```

### Erro: "connection refused"

```powershell
# Verificar se PostgreSQL está rodando
Get-Service -Name postgresql*

# Iniciar serviço
Start-Service postgresql-x64-16  # Ajustar nome do serviço
```

### Erro: "password authentication failed"

```powershell
# Verificar senha
psql -U postgres

# Se esqueceu a senha, resetar:
# 1. Editar pg_hba.conf (C:\Program Files\PostgreSQL\16\data\pg_hba.conf)
# 2. Mudar "md5" para "trust" temporariamente
# 3. Reiniciar PostgreSQL
# 4. Conectar e mudar senha: ALTER USER postgres PASSWORD 'nova_senha';
# 5. Reverter pg_hba.conf para "md5"
```

## ✅ Verificação Final

```powershell
# Testar tudo
psql -U postgres -d incentivos_db -c "SELECT COUNT(*) FROM companies;"
psql -U postgres -d incentivos_db -c "SELECT COUNT(*) FROM incentives;"
psql -U postgres -d incentivos_db -c "SELECT COUNT(*) FROM matches;"
```

Resultado esperado:
```
 count  
--------
 250000
(1 row)

 count 
-------
   500
(1 row)

 count 
-------
     5
(1 row)
```

---

**Dica**: Salve a string de conexão em variável de ambiente:

```powershell
# Adicionar ao perfil do PowerShell
notepad $PROFILE

# Adicionar linha:
$env:DATABASE_URL = "postgresql://postgres:senha@localhost:5432/incentivos_db"

# Usar:
python database/matching_service.py --db $env:DATABASE_URL --status Active
```
