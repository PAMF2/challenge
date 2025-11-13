# ⚡ Comandos Rápidos - PowerShell

## 🚀 Setup Completo (Copiar e Colar)

```powershell
# 1. Navegar para pasta do projeto
cd "C:\Users\Pichau\Desktop\Projeto Augusta"

# 2. Entrar na pasta database
cd database

# 3. Executar setup automatizado
.\setup.ps1
```

## 📝 Comandos Individuais

### Adicionar PostgreSQL ao PATH

```powershell
# Encontrar PostgreSQL
Get-ChildItem "C:\Program Files" -Filter "PostgreSQL" -Directory -ErrorAction SilentlyContinue

# Adicionar ao PATH (ajustar versão)
$env:Path += ";C:\Program Files\PostgreSQL\16\bin"

# Verificar
psql --version
```

### Criar Database

```powershell
# Criar database
psql -U postgres -c "CREATE DATABASE incentivos_db;"

# Verificar
psql -U postgres -l
```

### Criar Schema

```powershell
# Certifique-se de estar na pasta database
cd "C:\Users\Pichau\Desktop\Projeto Augusta\database"

# Executar schema
psql -U postgres -d incentivos_db -f schema.sql
```

### Instalar Dependências Python

```powershell
pip install psycopg2-binary pandas tqdm tabulate
```

### Importar Dados

```powershell
# Definir conexão (AJUSTAR SENHA!)
$DB_URL = "postgresql://postgres:SUA_SENHA@localhost:5432/incentivos_db"

# Voltar para raiz do projeto
cd ..

# Importar empresas
python database/import_data.py --db $DB_URL --companies "data/companies.csv"

# Importar incentivos
python database/import_data.py --db $DB_URL --incentives "data/incentives.csv"
```

### Executar Matching

```powershell
# Processar 1 incentivo (teste)
python database/matching_service.py --db $DB_URL --incentive-id 3406 --verbose

# Processar 10 incentivos
python database/matching_service.py --db $DB_URL --status Active --limit 10 --verbose

# Processar todos
python database/matching_service.py --db $DB_URL --status Active --verbose
```

### Ver Resultados

```powershell
# Exemplo 1: Top matches de um incentivo
python database/example_usage.py --db $DB_URL --example 1

# Exemplo 2: Buscar empresas
python database/example_usage.py --db $DB_URL --example 2

# Exemplo 3: Estatísticas
python database/example_usage.py --db $DB_URL --example 3

# Todos os exemplos
python database/example_usage.py --db $DB_URL
```

### Consultas SQL Diretas

```powershell
# Conectar ao banco
psql -U postgres -d incentivos_db

# No prompt do psql (após conectar):
```

```sql
-- Ver top matches
SELECT * FROM v_top_matches LIMIT 10;

-- Contar registros
SELECT COUNT(*) FROM companies;
SELECT COUNT(*) FROM incentives;
SELECT COUNT(*) FROM matches;

-- Estatísticas
SELECT * FROM v_incentive_stats LIMIT 10;

-- Empresas mais matchadas
SELECT * FROM v_top_companies LIMIT 10;

-- Sair
\q
```

## 🔧 Troubleshooting

### Erro: "setup.bat não é reconhecido"

```powershell
# ❌ Não funciona
setup.bat

# ✅ Funciona
.\setup.bat
# ou
.\setup.ps1
```

### Erro: "can't open file database/database/..."

```powershell
# Você está em: C:\...\Projeto Augusta\database
# Então use caminhos relativos corretos:

# ❌ Errado (duplica 'database')
python database/import_data.py

# ✅ Correto
python import_data.py

# Ou volte para raiz:
cd ..
python database/import_data.py
```

### Erro: "psql não é reconhecido"

```powershell
# Adicionar PostgreSQL ao PATH
$env:Path += ";C:\Program Files\PostgreSQL\16\bin"

# Verificar
psql --version
```

### Erro: "password authentication failed"

```powershell
# Testar conexão
psql -U postgres

# Se não souber a senha, resetar:
# 1. Parar PostgreSQL
Stop-Service postgresql-x64-16

# 2. Editar pg_hba.conf
notepad "C:\Program Files\PostgreSQL\16\data\pg_hba.conf"
# Mudar "md5" para "trust" nas linhas IPv4/IPv6

# 3. Reiniciar PostgreSQL
Start-Service postgresql-x64-16

# 4. Conectar sem senha e mudar
psql -U postgres
ALTER USER postgres PASSWORD 'nova_senha';
\q

# 5. Reverter pg_hba.conf para "md5"
# 6. Reiniciar PostgreSQL novamente
```

## 📊 Verificação Rápida

```powershell
# Verificar tudo está funcionando
psql -U postgres -d incentivos_db -c "SELECT 'Companies: ' || COUNT(*) FROM companies;"
psql -U postgres -d incentivos_db -c "SELECT 'Incentives: ' || COUNT(*) FROM incentives;"
psql -U postgres -d incentivos_db -c "SELECT 'Matches: ' || COUNT(*) FROM matches;"
```

Resultado esperado:
```
   ?column?    
---------------
 Companies: 250000

   ?column?    
---------------
 Incentives: 500

   ?column?    
---------------
 Matches: 5
```

## 🎯 Workflow Completo (1 Comando)

```powershell
# Tudo de uma vez (ajustar senha)
cd "C:\Users\Pichau\Desktop\Projeto Augusta\database"; `
$env:Path += ";C:\Program Files\PostgreSQL\16\bin"; `
$DB_URL = "postgresql://postgres:SUA_SENHA@localhost:5432/incentivos_db"; `
psql -U postgres -c "CREATE DATABASE incentivos_db;" 2>$null; `
psql -U postgres -d incentivos_db -f schema.sql; `
pip install -q psycopg2-binary pandas tqdm tabulate; `
cd ..; `
python database/import_data.py --db $DB_URL --companies "data/companies.csv"; `
python database/import_data.py --db $DB_URL --incentives "data/incentives.csv"; `
python database/matching_service.py --db $DB_URL --incentive-id 3406 --verbose; `
python database/example_usage.py --db $DB_URL --example 1
```

## 💾 Salvar Configuração

```powershell
# Adicionar ao perfil do PowerShell
if (-not (Test-Path $PROFILE)) {
    New-Item -Path $PROFILE -ItemType File -Force
}

notepad $PROFILE

# Adicionar estas linhas:
$env:Path += ";C:\Program Files\PostgreSQL\16\bin"
$env:DATABASE_URL = "postgresql://postgres:senha@localhost:5432/incentivos_db"

# Recarregar perfil
. $PROFILE

# Agora pode usar:
python database/matching_service.py --db $env:DATABASE_URL --status Active
```

## 📱 Atalhos Úteis

```powershell
# Criar função para facilitar
function Match-Incentive {
    param([int]$Id)
    python database/matching_service.py --db $env:DATABASE_URL --incentive-id $Id --verbose
}

function Show-Matches {
    param([int]$Id)
    python database/example_usage.py --db $env:DATABASE_URL --example 1
}

# Usar:
Match-Incentive -Id 3406
Show-Matches -Id 3406
```

---

**Dica**: Sempre execute comandos da pasta correta!
- Scripts Python: da pasta raiz (`Projeto Augusta`)
- Scripts .ps1/.bat: da pasta `database`
- Comandos psql: de qualquer lugar (se no PATH)
