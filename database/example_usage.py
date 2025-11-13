"""
Exemplo de Uso Completo do Sistema de Matching com PostgreSQL
"""
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
from tabulate import tabulate


def example_1_query_matches(conn_string: str):
    """Exemplo 1: Consultar matches de um incentivo"""
    print("\n" + "="*80)
    print("EXEMPLO 1: Consultar Top 5 Matches de um Incentivo")
    print("="*80)
    
    conn = psycopg2.connect(conn_string, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    # Buscar matches do incentivo 3406 (Igreja católica)
    query = """
        SELECT 
            m.rank,
            c.company_name,
            c.cae_primary_label,
            m.final_score,
            m.keyword_score,
            m.llm_score,
            m.match_count,
            m.rationale
        FROM matches m
        JOIN companies c ON m.company_id = c.id
        JOIN incentives i ON m.incentive_id = i.id
        WHERE i.incentive_project_id = 3406
        ORDER BY m.rank
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    if results:
        # Converter para DataFrame para melhor visualização
        df = pd.DataFrame(results)
        print(f"\nIncentivo: Igreja católica - Apoio religioso")
        print(f"Total de matches: {len(df)}\n")
        print(tabulate(df, headers='keys', tablefmt='psql', showindex=False))
    else:
        print("Nenhum match encontrado. Execute o matching primeiro.")
    
    cursor.close()
    conn.close()


def example_2_search_companies(conn_string: str):
    """Exemplo 2: Buscar empresas por texto"""
    print("\n" + "="*80)
    print("EXEMPLO 2: Buscar Empresas por Texto (Full-Text Search)")
    print("="*80)
    
    conn = psycopg2.connect(conn_string, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    search_term = "tecnologia digital software"
    
    # Usar função de busca
    cursor.execute("SELECT * FROM search_companies(%s)", (search_term,))
    results = cursor.fetchall()
    
    if results:
        df = pd.DataFrame(results)
        print(f"\nBusca: '{search_term}'")
        print(f"Resultados: {len(df)}\n")
        print(tabulate(df.head(10), headers='keys', tablefmt='psql', showindex=False))
    else:
        print(f"Nenhuma empresa encontrada para '{search_term}'")
    
    cursor.close()
    conn.close()


def example_3_incentive_stats(conn_string: str):
    """Exemplo 3: Estatísticas de matching por incentivo"""
    print("\n" + "="*80)
    print("EXEMPLO 3: Estatísticas de Matching por Incentivo")
    print("="*80)
    
    conn = psycopg2.connect(conn_string, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    # Usar view de estatísticas
    query = """
        SELECT 
            incentive_program,
            title,
            total_matches,
            ROUND(avg_score::numeric, 2) as avg_score,
            ROUND(max_score::numeric, 2) as max_score,
            last_matched_at
        FROM v_incentive_stats
        WHERE total_matches > 0
        ORDER BY avg_score DESC
        LIMIT 10
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    if results:
        df = pd.DataFrame(results)
        print(f"\nTop 10 Incentivos por Score Médio\n")
        print(tabulate(df, headers='keys', tablefmt='psql', showindex=False))
    else:
        print("Nenhuma estatística disponível")
    
    cursor.close()
    conn.close()


def example_4_top_companies(conn_string: str):
    """Exemplo 4: Empresas mais matchadas"""
    print("\n" + "="*80)
    print("EXEMPLO 4: Empresas Mais Matchadas")
    print("="*80)
    
    conn = psycopg2.connect(conn_string, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    # Usar view de top companies
    query = """
        SELECT 
            company_name,
            cae_primary_label,
            entity_type,
            match_count,
            ROUND(avg_score::numeric, 2) as avg_score,
            matched_programs
        FROM v_top_companies
        LIMIT 15
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    if results:
        df = pd.DataFrame(results)
        print(f"\nTop 15 Empresas por Número de Matches\n")
        print(tabulate(df, headers='keys', tablefmt='psql', showindex=False))
    else:
        print("Nenhuma empresa matchada ainda")
    
    cursor.close()
    conn.close()


def example_5_matching_logs(conn_string: str):
    """Exemplo 5: Histórico de execuções"""
    print("\n" + "="*80)
    print("EXEMPLO 5: Histórico de Execuções de Matching")
    print("="*80)
    
    conn = psycopg2.connect(conn_string, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    query = """
        SELECT 
            i.title,
            l.total_companies,
            l.phase1_filtered,
            l.phase2_candidates,
            l.final_matches,
            l.total_time_ms,
            l.llm_enabled,
            l.status,
            l.created_at
        FROM matching_logs l
        JOIN incentives i ON l.incentive_id = i.id
        ORDER BY l.created_at DESC
        LIMIT 10
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    if results:
        df = pd.DataFrame(results)
        print(f"\nÚltimas 10 Execuções\n")
        print(tabulate(df, headers='keys', tablefmt='psql', showindex=False))
    else:
        print("Nenhum log de execução disponível")
    
    cursor.close()
    conn.close()


def example_6_custom_query(conn_string: str):
    """Exemplo 6: Query customizada - Matches com score alto"""
    print("\n" + "="*80)
    print("EXEMPLO 6: Matches com Score Alto (>70)")
    print("="*80)
    
    conn = psycopg2.connect(conn_string, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    query = """
        SELECT 
            i.title as incentivo,
            i.incentive_program,
            c.company_name as empresa,
            m.rank,
            m.final_score,
            m.matched_keywords,
            m.rationale
        FROM matches m
        JOIN incentives i ON m.incentive_id = i.id
        JOIN companies c ON m.company_id = c.id
        WHERE m.final_score > 70
        ORDER BY m.final_score DESC
        LIMIT 20
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    if results:
        print(f"\nTotal de matches com score > 70: {len(results)}\n")
        
        for result in results[:10]:  # Mostrar top 10
            print(f"Score: {result['final_score']:.1f}")
            print(f"Incentivo: {result['incentivo'][:60]}...")
            print(f"Empresa: {result['empresa']}")
            print(f"Rank: {result['rank']}")
            print(f"Rationale: {result['rationale'][:100]}...")
            print("-" * 80)
    else:
        print("Nenhum match com score > 70 encontrado")
    
    cursor.close()
    conn.close()


def example_7_export_to_csv(conn_string: str):
    """Exemplo 7: Exportar matches para CSV"""
    print("\n" + "="*80)
    print("EXEMPLO 7: Exportar Todos os Matches para CSV")
    print("="*80)
    
    conn = psycopg2.connect(conn_string, cursor_factory=RealDictCursor)
    
    query = """
        SELECT 
            i.incentive_project_id,
            i.title as incentive_title,
            i.incentive_program,
            i.status as incentive_status,
            m.rank,
            c.company_name,
            c.cae_primary_label,
            m.final_score,
            m.keyword_score,
            m.llm_score,
            m.match_count,
            m.rationale,
            m.created_at as matched_at
        FROM matches m
        JOIN incentives i ON m.incentive_id = i.id
        JOIN companies c ON m.company_id = c.id
        ORDER BY i.incentive_project_id, m.rank
    """
    
    df = pd.read_sql_query(query, conn)
    
    if not df.empty:
        output_file = project_root / 'matches_export.csv'
        df.to_csv(output_file, index=False, encoding='utf-8-sig')
        
        print(f"\n✓ {len(df)} matches exportados para: {output_file}")
        print(f"\nPrimeiras linhas:\n")
        print(tabulate(df.head(10), headers='keys', tablefmt='psql', showindex=False))
    else:
        print("Nenhum match para exportar")
    
    conn.close()


def main():
    """Executa todos os exemplos"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Exemplos de Uso do Sistema")
    parser.add_argument('--db', required=True, help="String de conexão PostgreSQL")
    parser.add_argument('--example', type=int, help="Executar apenas um exemplo específico (1-7)")
    
    args = parser.parse_args()
    
    examples = {
        1: example_1_query_matches,
        2: example_2_search_companies,
        3: example_3_incentive_stats,
        4: example_4_top_companies,
        5: example_5_matching_logs,
        6: example_6_custom_query,
        7: example_7_export_to_csv
    }
    
    if args.example:
        if args.example in examples:
            examples[args.example](args.db)
        else:
            print(f"Exemplo {args.example} não existe. Escolha entre 1-7.")
    else:
        # Executar todos
        for example_func in examples.values():
            try:
                example_func(args.db)
            except Exception as e:
                print(f"Erro: {e}")
            print("\n")


if __name__ == "__main__":
    main()
