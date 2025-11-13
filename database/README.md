# 🗄️ Base de Dados PostgreSQL - Sistema de Matching

## Visão Geral

Sistema completo de matching entre incentivos e empresas usando PostgreSQL como base de dados central, integrado com o funil de matching otimizado de 3 fases.

## 📋 Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                    PostgreSQL Database                       │
├─────────────────────────────────────────────────────────────┤
│  Tables:                                                     │
│  ├─ companies (250,000 registros)                          │
│  ├─ incentives (500 registros)                             │
│  ├─ matches (top 5 por incentivo)                          │
│  └─ matching_logs (histórico de execuções)                 │
│                                                              │
│  Views:                                                      │
│  ├─ v_top_matches (matches com info completa)              │
│  ├─ v_incentive_stats (estatísticas por incentivo)         │
│  └─ v_top_companies (empresas mais matchadas)              │
└─────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────┐
│              Matching Service (Python)                       │
├─────────────────────────────────────────────────────────────┤
│  1. Carrega dados do PostgreSQL                            │
│  2. Executa funil otimizado de 3 fases                     │
│  3. Salva top 5 matches na tabela 'matches'                │
│  4. Registra logs de execução                              │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Setup Rápido

### 1. Instalar PostgreSQL

```bash
# Windows (via Chocolatey)
choco install postgresql

# Ou baixar de: https://www.postgresql.org/download/windows/
```

### 2. Criar Banco de Dados

```bash
# Conectar ao PostgreSQL
psql -U postgres

# Criar database
CREATE DATABASE incentivos_db;

# Conectar ao database
\c incentivos_db
```

### 3. Criar Schema

```bash
# Executar script de schema
psql -U postgres -d incentivos_db -f database/schema.sql
```

### 4. Instalar Dependências Python

```bash
pip install psycopg2-binary pandas tqdm
```

### 5. Importar Dados

```bash
# Importar empresas e incentivos
python database/import_data.py \
    --db "postgresql://postgres:password@localhost:5432/incentivos_db" \
    --create-schema \
    --companies "data/companies.csv" \
    --incentives "data/incentives.csv"
```

### 6. Executar Matching

```bash
# Processar todos os incentivos ativos
python database/matching_service.py \
    --db "postgresql://postgres:password@localhost:5432/incentivos_db" \
    --status Active \
    --verbose

# Ou processar apenas um incentivo
python database/matching_service.py \
    --db "postgresql://postgres:password@localhost:5432/incentivos_db" \
    --incentive-id 3406 \
    --verbose
```

## 📊 Estrutura do Banco

### Tabela: `companies`

Armazena informações das empresas com campos derivados para otimização.

```sql
CREATE TABLE companies (
    id SERIAL PRIMARY KEY,
    company_index INTEGER UNIQUE,
    company_name VARCHAR(500) NOT NULL,
    cae_primary_code VARCHAR(10),
    cae_primary_label TEXT,
    trade_description_native TEXT,
    website VARCHAR(500),
    
    -- Campos derivados
    entity_type VARCHAR(50),        -- private, public, nonprofit
    normalized_text TEXT,           -- Texto normalizado
    keywords TEXT[],                -- Array de keywords
    search_vector tsvector,         -- Índice de busca full-text
    
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

**Índices**:
- `idx_companies_name`: Busca fuzzy por nome
- `idx_companies_cae`: Busca por código CAE
- `idx_companies_search_vector`: Full-text search
- `idx_companies_keywords`: Busca por keywords

### Tabela: `incentives`

Armazena incentivos com critérios de elegibilidade estruturados.

```sql
CREATE TABLE incentives (
    id SERIAL PRIMARY KEY,
    incentive_project_id INTEGER UNIQUE,
    project_id VARCHAR(100),
    incentive_program VARCHAR(200),
    title TEXT NOT NULL,
    description TEXT,
    ai_description TEXT,
    
    -- Datas
    date_publication TIMESTAMP,
    date_start TIMESTAMP,
    date_end TIMESTAMP,
    
    -- Financeiro
    total_budget DECIMAL(15, 2),
    status VARCHAR(50),
    
    -- Critérios (JSONB)
    eligibility_criteria JSONB,
    geographical_scope JSONB,
    all_data JSONB,
    
    -- Campos derivados
    eligible_sectors TEXT[],
    entity_types TEXT[],
    keywords TEXT[],
    
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### Tabela: `matches`

Armazena os resultados do matching (top 5 por incentivo).

```sql
CREATE TABLE matches (
    id SERIAL PRIMARY KEY,
    incentive_id INTEGER REFERENCES incentives(id),
    company_id INTEGER REFERENCES companies(id),
    
    rank INTEGER CHECK (rank >= 1 AND rank <= 5),
    
    -- Scores
    final_score DECIMAL(5, 2),      -- 0-100
    keyword_score DECIMAL(5, 2),    -- 0-100
    semantic_score DECIMAL(5, 2),   -- 0-100
    llm_score DECIMAL(4, 2),        -- 1-10
    
    -- Detalhes
    matched_keywords JSONB,
    match_count INTEGER,
    rationale TEXT,
    llm_justification TEXT,
    
    -- Critérios expandidos
    geo_score DECIMAL(5, 2),
    geo_regions TEXT[],
    size_score DECIMAL(5, 2),
    size_category VARCHAR(50),
    
    matching_method VARCHAR(50),
    processing_time_ms INTEGER,
    
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    
    UNIQUE(incentive_id, company_id),
    UNIQUE(incentive_id, rank)
);
```

### Tabela: `matching_logs`

Registra histórico de execuções do matching.

```sql
CREATE TABLE matching_logs (
    id SERIAL PRIMARY KEY,
    incentive_id INTEGER REFERENCES incentives(id),
    
    -- Estatísticas
    total_companies INTEGER,
    phase1_filtered INTEGER,
    phase2_candidates INTEGER,
    phase3_analyzed INTEGER,
    final_matches INTEGER,
    
    -- Performance
    phase1_time_ms INTEGER,
    phase2_time_ms INTEGER,
    phase3_time_ms INTEGER,
    total_time_ms INTEGER,
    
    -- Configuração
    method VARCHAR(50),
    llm_enabled BOOLEAN,
    llm_model VARCHAR(100),
    
    status VARCHAR(50),
    error_message TEXT,
    created_at TIMESTAMP
);
```

## 🔍 Queries Úteis

### Buscar Top 5 Matches de um Incentivo

```sql
SELECT 
    m.rank,
    c.company_name,
    c.cae_primary_label,
    m.final_score,
    m.llm_score,
    m.rationale
FROM matches m
JOIN companies c ON m.company_id = c.id
JOIN incentives i ON m.incentive_id = i.id
WHERE i.incentive_project_id = 3406
ORDER BY m.rank;
```

### Estatísticas de Matching por Incentivo

```sql
SELECT * FROM v_incentive_stats
WHERE total_matches > 0
ORDER BY avg_score DESC
LIMIT 10;
```

### Empresas Mais Matchadas

```sql
SELECT * FROM v_top_companies
LIMIT 20;
```

### Histórico de Execuções

```sql
SELECT 
    i.title,
    l.total_companies,
    l.final_matches,
    l.total_time_ms,
    l.status,
    l.created_at
FROM matching_logs l
JOIN incentives i ON l.incentive_id = i.id
ORDER BY l.created_at DESC
LIMIT 10;
```

### Buscar Empresas por Texto

```sql
SELECT * FROM search_companies('tecnologia digital');
```

### Buscar Incentivos por Texto

```sql
SELECT * FROM search_incentives('inovação sustentabilidade');
```

## 🛠️ Scripts Disponíveis

### 1. `schema.sql`

Cria estrutura completa do banco:
- 4 tabelas principais
- 3 views úteis
- Funções de busca
- Índices otimizados
- Triggers

```bash
psql -U postgres -d incentivos_db -f database/schema.sql
```

### 2. `import_data.py`

Importa dados CSV para PostgreSQL:

```bash
# Uso completo
python database/import_data.py \
    --db "postgresql://user:pass@host:port/dbname" \
    --create-schema \
    --companies "data/companies.csv" \
    --incentives "data/incentives.csv"

# Apenas empresas
python database/import_data.py \
    --db "postgresql://..." \
    --companies "data/companies.csv"

# Apenas incentivos
python database/import_data.py \
    --db "postgresql://..." \
    --incentives "data/incentives.csv"
```

**Funcionalidades**:
- Importação em lotes (batch processing)
- Classificação automática de entity_type
- Extração de keywords
- Normalização de texto
- Parsing de JSON (eligibility_criteria, all_data)
- Progress bar com tqdm
- Verificação pós-importação

### 3. `matching_service.py`

Executa matching e salva resultados:

```bash
# Processar todos os incentivos ativos
python database/matching_service.py \
    --db "postgresql://..." \
    --status Active

# Processar com limite
python database/matching_service.py \
    --db "postgresql://..." \
    --limit 10

# Processar um incentivo específico
python database/matching_service.py \
    --db "postgresql://..." \
    --incentive-id 3406 \
    --verbose

# Com LLM (requer GEMINI_API_KEY)
export GEMINI_API_KEY=your_key_here
python database/matching_service.py \
    --db "postgresql://..." \
    --llm \
    --verbose
```

**Funcionalidades**:
- Integração com funil otimizado de 3 fases
- Salvamento automático de matches
- Logging de execuções
- Suporte a LLM opcional
- Processamento em lote
- Tratamento de erros

## 📈 Performance

### Importação

- **Empresas**: ~250,000 registros em ~2 minutos
- **Incentivos**: ~500 registros em ~5 segundos
- **Batch size**: 1000 (empresas), 100 (incentivos)

### Matching

- **Por incentivo**: ~2s (sem LLM) ou ~12s (com LLM)
- **500 incentivos**: ~17 minutos (sem LLM) ou ~1.7h (com LLM)
- **Redução de chamadas LLM**: 99.99%

### Queries

- **Buscar matches**: < 10ms (com índices)
- **Full-text search**: < 50ms
- **Agregações**: < 100ms

## 🔐 Segurança

### Configuração de Usuário

```sql
-- Criar usuário para aplicação
CREATE USER app_user WITH PASSWORD 'strong_password_here';

-- Conceder permissões
GRANT CONNECT ON DATABASE incentivos_db TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
```

### String de Conexão

```python
# Desenvolvimento
conn_string = "postgresql://app_user:password@localhost:5432/incentivos_db"

# Produção (usar variáveis de ambiente)
import os
conn_string = os.getenv('DATABASE_URL')
```

## 🔄 Workflow Completo

### 1. Setup Inicial

```bash
# Criar banco
createdb -U postgres incentivos_db

# Criar schema
psql -U postgres -d incentivos_db -f database/schema.sql

# Importar dados
python database/import_data.py \
    --db "postgresql://postgres:password@localhost:5432/incentivos_db" \
    --companies "data/companies.csv" \
    --incentives "data/incentives.csv"
```

### 2. Executar Matching

```bash
# Processar todos os incentivos
python database/matching_service.py \
    --db "postgresql://postgres:password@localhost:5432/incentivos_db" \
    --status Active \
    --verbose
```

### 3. Consultar Resultados

```sql
-- Ver top matches
SELECT * FROM v_top_matches LIMIT 20;

-- Estatísticas
SELECT * FROM v_incentive_stats;

-- Logs
SELECT * FROM matching_logs ORDER BY created_at DESC LIMIT 10;
```

### 4. Atualizar Dados

```bash
# Re-importar incentivos atualizados
python database/import_data.py \
    --db "postgresql://..." \
    --incentives "data/incentives_updated.csv"

# Re-executar matching
python database/matching_service.py \
    --db "postgresql://..." \
    --status Active
```

## 📊 Exemplo de Resultado

### Query

```sql
SELECT 
    i.title AS incentivo,
    m.rank,
    c.company_name AS empresa,
    m.final_score,
    m.rationale
FROM matches m
JOIN incentives i ON m.incentive_id = i.id
JOIN companies c ON m.company_id = c.id
WHERE i.incentive_project_id = 3406
ORDER BY m.rank;
```

### Resultado

```
incentivo                                           | rank | empresa                                    | final_score | rationale
---------------------------------------------------|------|--------------------------------------------|-----------|-----------
Igreja católica - Apoio religioso                  | 1    | CENTRO COMUNITÁRIO PAROQUIAL DE RIO MOURO | 52.3      | Score: 52.3/100 | Base: Keywords: 52%, Semântica: 0% | Tamanho: nonprofit
Igreja católica - Apoio religioso                  | 2    | CENTRO SOCIAL PAROQUIAL DA S. S. TRINDADE | 31.3      | Score: 31.3/100 | Base: Keywords: 31%, Semântica: 0% | Tamanho: nonprofit
...
```

## 🚨 Troubleshooting

### Erro: "relation does not exist"

```bash
# Re-criar schema
psql -U postgres -d incentivos_db -f database/schema.sql
```

### Erro: "connection refused"

```bash
# Verificar se PostgreSQL está rodando
pg_ctl status

# Iniciar PostgreSQL
pg_ctl start
```

### Erro: "permission denied"

```sql
-- Conceder permissões
GRANT ALL PRIVILEGES ON DATABASE incentivos_db TO app_user;
```

### Performance lenta

```sql
-- Recriar índices
REINDEX DATABASE incentivos_db;

-- Atualizar estatísticas
ANALYZE;
```

## 📚 Documentação Adicional

- **Schema completo**: `database/schema.sql`
- **Guia de matching**: `docs/OPTIMIZED_MATCHING_GUIDE.md`
- **README principal**: `README_MATCHING.md`

## ✅ Checklist de Implementação

- [x] Schema PostgreSQL completo
- [x] Script de importação de dados
- [x] Serviço de matching integrado
- [x] Views e funções úteis
- [x] Índices otimizados
- [x] Logging de execuções
- [x] Documentação completa
- [ ] API REST (futuro)
- [ ] Interface web (futuro)
- [ ] Backup automático (futuro)

---

**Versão**: 1.0  
**Data**: Novembro 2025  
**Licença**: MIT
