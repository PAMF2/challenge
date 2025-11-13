-- ============================================================================
-- PostgreSQL Database Schema - Sistema de Matching Incentivos × Empresas
-- ============================================================================

-- Extensões necessárias
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- Para busca fuzzy/similar
CREATE EXTENSION IF NOT EXISTS "btree_gin"; -- Para índices otimizados

-- ============================================================================
-- TABELA: companies
-- Armazena informações das empresas
-- ============================================================================
CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    company_index INTEGER UNIQUE,
    company_name VARCHAR(500) NOT NULL,
    cae_primary_code VARCHAR(10),
    cae_primary_label TEXT,
    trade_description_native TEXT,
    website VARCHAR(500),
    
    -- Campos derivados/processados
    entity_type VARCHAR(50), -- private, public, nonprofit
    normalized_text TEXT, -- Texto normalizado para busca
    keywords TEXT[], -- Array de keywords extraídas
    
    -- Metadados
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Índices de busca
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('portuguese', 
            coalesce(company_name, '') || ' ' || 
            coalesce(cae_primary_label, '') || ' ' || 
            coalesce(trade_description_native, '')
        )
    ) STORED
);

-- Índices para performance
CREATE INDEX idx_companies_name ON companies USING gin(company_name gin_trgm_ops);
CREATE INDEX idx_companies_cae ON companies(cae_primary_code);
CREATE INDEX idx_companies_entity_type ON companies(entity_type);
CREATE INDEX idx_companies_search_vector ON companies USING gin(search_vector);
CREATE INDEX idx_companies_keywords ON companies USING gin(keywords);

-- ============================================================================
-- TABELA: incentives
-- Armazena informações dos incentivos
-- ============================================================================
CREATE TABLE IF NOT EXISTS incentives (
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
    
    -- Critérios de elegibilidade (JSON)
    eligibility_criteria JSONB,
    geographical_scope JSONB,
    
    -- Dados completos (JSON)
    all_data JSONB,
    
    -- URLs
    source_link TEXT,
    document_urls TEXT[],
    gcs_document_urls TEXT[],
    
    -- Campos derivados
    eligible_sectors TEXT[], -- Array de setores elegíveis
    entity_types TEXT[], -- Array de tipos de entidade
    keywords TEXT[], -- Keywords extraídas
    
    -- Metadados
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Índice de busca
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('portuguese', 
            coalesce(title, '') || ' ' || 
            coalesce(description, '') || ' ' || 
            coalesce(ai_description, '')
        )
    ) STORED
);

-- Índices para performance
CREATE INDEX idx_incentives_program ON incentives(incentive_program);
CREATE INDEX idx_incentives_status ON incentives(status);
CREATE INDEX idx_incentives_date_end ON incentives(date_end);
CREATE INDEX idx_incentives_eligibility ON incentives USING gin(eligibility_criteria);
CREATE INDEX idx_incentives_sectors ON incentives USING gin(eligible_sectors);
CREATE INDEX idx_incentives_search_vector ON incentives USING gin(search_vector);

-- ============================================================================
-- TABELA: matches
-- Armazena os resultados do matching (top 5 por incentivo)
-- ============================================================================
CREATE TABLE IF NOT EXISTS matches (
    id SERIAL PRIMARY KEY,
    incentive_id INTEGER NOT NULL REFERENCES incentives(id) ON DELETE CASCADE,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    
    -- Ranking
    rank INTEGER NOT NULL CHECK (rank >= 1 AND rank <= 5),
    
    -- Scores detalhados
    final_score DECIMAL(5, 2) NOT NULL, -- Score final (0-100)
    keyword_score DECIMAL(5, 2), -- Score de keywords (0-100)
    semantic_score DECIMAL(5, 2), -- Score semântico (0-100)
    llm_score DECIMAL(4, 2), -- Score do LLM (1-10)
    
    -- Detalhes do matching
    matched_keywords JSONB, -- {keyword: count}
    match_count INTEGER, -- Número de keywords correspondentes
    
    -- Justificação
    rationale TEXT, -- Explicação do match
    llm_justification TEXT, -- Justificação detalhada do LLM
    
    -- Critérios expandidos (do enhanced_criteria)
    geo_score DECIMAL(5, 2),
    geo_regions TEXT[],
    size_score DECIMAL(5, 2),
    size_category VARCHAR(50),
    budget_score DECIMAL(5, 2),
    status_score DECIMAL(5, 2),
    innovation_score DECIMAL(5, 2),
    innovation_themes TEXT[],
    
    -- Metadados
    matching_method VARCHAR(50) DEFAULT 'optimized_funnel', -- optimized_funnel, enhanced_criteria, etc.
    processing_time_ms INTEGER, -- Tempo de processamento em ms
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    UNIQUE(incentive_id, company_id),
    UNIQUE(incentive_id, rank)
);

-- Índices para performance
CREATE INDEX idx_matches_incentive ON matches(incentive_id);
CREATE INDEX idx_matches_company ON matches(company_id);
CREATE INDEX idx_matches_rank ON matches(incentive_id, rank);
CREATE INDEX idx_matches_score ON matches(final_score DESC);

-- ============================================================================
-- TABELA: matching_logs
-- Log de execuções do processo de matching
-- ============================================================================
CREATE TABLE IF NOT EXISTS matching_logs (
    id SERIAL PRIMARY KEY,
    incentive_id INTEGER REFERENCES incentives(id) ON DELETE SET NULL,
    
    -- Estatísticas do processo
    total_companies INTEGER,
    phase1_filtered INTEGER, -- Empresas que passaram fase 1
    phase2_candidates INTEGER, -- Candidatas da fase 2
    phase3_analyzed INTEGER, -- Empresas analisadas pelo LLM
    final_matches INTEGER, -- Matches finais
    
    -- Performance
    phase1_time_ms INTEGER,
    phase2_time_ms INTEGER,
    phase3_time_ms INTEGER,
    total_time_ms INTEGER,
    
    -- Configuração
    method VARCHAR(50),
    llm_enabled BOOLEAN,
    llm_model VARCHAR(100),
    
    -- Status
    status VARCHAR(50), -- success, error, partial
    error_message TEXT,
    
    -- Metadados
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_matching_logs_incentive ON matching_logs(incentive_id);
CREATE INDEX idx_matching_logs_created ON matching_logs(created_at DESC);

-- ============================================================================
-- VIEWS: Visualizações úteis
-- ============================================================================

-- View: Top matches com informações completas
CREATE OR REPLACE VIEW v_top_matches AS
SELECT 
    m.id AS match_id,
    m.rank,
    m.final_score,
    m.llm_score,
    m.rationale,
    m.llm_justification,
    
    -- Incentivo
    i.incentive_project_id,
    i.title AS incentive_title,
    i.incentive_program,
    i.status AS incentive_status,
    i.total_budget,
    i.date_end,
    
    -- Empresa
    c.company_index,
    c.company_name,
    c.cae_primary_label,
    c.trade_description_native,
    c.entity_type,
    
    -- Metadados
    m.created_at AS matched_at
FROM matches m
JOIN incentives i ON m.incentive_id = i.id
JOIN companies c ON m.company_id = c.id
ORDER BY i.incentive_project_id, m.rank;

-- View: Estatísticas de matching por incentivo
CREATE OR REPLACE VIEW v_incentive_stats AS
SELECT 
    i.id AS incentive_id,
    i.incentive_project_id,
    i.title,
    i.incentive_program,
    COUNT(m.id) AS total_matches,
    AVG(m.final_score) AS avg_score,
    MAX(m.final_score) AS max_score,
    MIN(m.final_score) AS min_score,
    MAX(m.created_at) AS last_matched_at
FROM incentives i
LEFT JOIN matches m ON i.id = m.incentive_id
GROUP BY i.id, i.incentive_project_id, i.title, i.incentive_program;

-- View: Empresas mais matchadas
CREATE OR REPLACE VIEW v_top_companies AS
SELECT 
    c.id AS company_id,
    c.company_name,
    c.cae_primary_label,
    c.entity_type,
    COUNT(m.id) AS match_count,
    AVG(m.final_score) AS avg_score,
    ARRAY_AGG(DISTINCT i.incentive_program) AS matched_programs
FROM companies c
JOIN matches m ON c.id = m.company_id
JOIN incentives i ON m.incentive_id = i.id
GROUP BY c.id, c.company_name, c.cae_primary_label, c.entity_type
ORDER BY match_count DESC;

-- ============================================================================
-- FUNCTIONS: Funções úteis
-- ============================================================================

-- Função: Atualizar timestamp de updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers para updated_at
CREATE TRIGGER update_companies_updated_at
    BEFORE UPDATE ON companies
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_incentives_updated_at
    BEFORE UPDATE ON incentives
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_matches_updated_at
    BEFORE UPDATE ON matches
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Função: Buscar empresas por texto (full-text search)
CREATE OR REPLACE FUNCTION search_companies(search_query TEXT)
RETURNS TABLE (
    company_id INTEGER,
    company_name VARCHAR(500),
    cae_primary_label TEXT,
    relevance REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.id,
        c.company_name,
        c.cae_primary_label,
        ts_rank(c.search_vector, plainto_tsquery('portuguese', search_query)) AS relevance
    FROM companies c
    WHERE c.search_vector @@ plainto_tsquery('portuguese', search_query)
    ORDER BY relevance DESC
    LIMIT 100;
END;
$$ LANGUAGE plpgsql;

-- Função: Buscar incentivos por texto
CREATE OR REPLACE FUNCTION search_incentives(search_query TEXT)
RETURNS TABLE (
    incentive_id INTEGER,
    title TEXT,
    incentive_program VARCHAR(200),
    relevance REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        i.id,
        i.title,
        i.incentive_program,
        ts_rank(i.search_vector, plainto_tsquery('portuguese', search_query)) AS relevance
    FROM incentives i
    WHERE i.search_vector @@ plainto_tsquery('portuguese', search_query)
    ORDER BY relevance DESC
    LIMIT 50;
END;
$$ LANGUAGE plpgsql;

-- Função: Limpar matches antigos de um incentivo
CREATE OR REPLACE FUNCTION clear_incentive_matches(p_incentive_id INTEGER)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM matches WHERE incentive_id = p_incentive_id;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- COMENTÁRIOS: Documentação das tabelas
-- ============================================================================

COMMENT ON TABLE companies IS 'Empresas do dataset com informações de CAE e atividades';
COMMENT ON TABLE incentives IS 'Incentivos disponíveis com critérios de elegibilidade';
COMMENT ON TABLE matches IS 'Resultados do matching - top 5 empresas por incentivo';
COMMENT ON TABLE matching_logs IS 'Logs de execução do processo de matching';

COMMENT ON COLUMN matches.rank IS 'Posição no ranking (1-5) para o incentivo';
COMMENT ON COLUMN matches.final_score IS 'Score final combinado (0-100)';
COMMENT ON COLUMN matches.llm_score IS 'Score atribuído pelo LLM (1-10)';
COMMENT ON COLUMN matches.matching_method IS 'Método usado: optimized_funnel, enhanced_criteria, etc.';

-- ============================================================================
-- GRANTS: Permissões (ajustar conforme necessário)
-- ============================================================================

-- Criar role para aplicação (se não existir)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
        CREATE ROLE app_user WITH LOGIN PASSWORD 'change_me_in_production';
    END IF;
END
$$;

-- Conceder permissões
GRANT CONNECT ON DATABASE postgres TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO app_user;

-- ============================================================================
-- ÍNDICES ADICIONAIS: Para queries específicas
-- ============================================================================

-- Índice composto para buscar matches ativos
CREATE INDEX idx_matches_active_incentives ON matches(incentive_id, final_score DESC)
    WHERE EXISTS (
        SELECT 1 FROM incentives i 
        WHERE i.id = matches.incentive_id 
        AND i.status = 'Active'
    );

-- Índice para buscar incentivos ativos com budget
CREATE INDEX idx_incentives_active_budget ON incentives(status, total_budget DESC)
    WHERE status = 'Active' AND total_budget IS NOT NULL;

-- ============================================================================
-- FIM DO SCHEMA
-- ============================================================================

-- Verificar criação
SELECT 
    'Tables created: ' || COUNT(*) 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_type = 'BASE TABLE';

SELECT 
    'Views created: ' || COUNT(*) 
FROM information_schema.views 
WHERE table_schema = 'public';

SELECT 
    'Functions created: ' || COUNT(*) 
FROM information_schema.routines 
WHERE routine_schema = 'public' 
AND routine_type = 'FUNCTION';
