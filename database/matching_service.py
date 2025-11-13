"""
Serviço de Matching integrado com PostgreSQL
Identifica as top 5 empresas para cada incentivo usando o funil otimizado
"""
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import pandas as pd
import json
import time
from typing import List, Dict, Optional
from datetime import datetime

from core.optimized_matching import OptimizedMatchingEngine


class DatabaseMatchingService:
    """
    Serviço de matching que:
    1. Carrega dados do PostgreSQL
    2. Executa funil de matching otimizado
    3. Salva resultados no banco
    """
    
    def __init__(
        self,
        connection_string: str,
        gemini_api_key: Optional[str] = None,
        phase2_top_n: int = 10,  # OTIMIZADO: Reduzido de 20 para 10
        final_top_n: int = 5
    ):
        self.conn_string = connection_string
        self.gemini_api_key = gemini_api_key
        self.phase2_top_n = phase2_top_n
        self.final_top_n = final_top_n
        
        self.conn = None
        self.cursor = None
        self.engine = None
    
    def connect(self):
        """Conecta ao banco de dados"""
        try:
            self.conn = psycopg2.connect(
                self.conn_string,
                cursor_factory=RealDictCursor
            )
            self.cursor = self.conn.cursor()
            print("✓ Conectado ao PostgreSQL")
        except Exception as e:
            print(f"✗ Erro ao conectar: {e}")
            raise
    
    def disconnect(self):
        """Desconecta do banco"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        print("✓ Desconectado do PostgreSQL")
    
    def load_companies(self) -> pd.DataFrame:
        """Carrega empresas do banco para DataFrame"""
        print("\n📊 Carregando empresas do banco...")
        
        query = """
            SELECT 
                id,
                company_index,
                company_name,
                cae_primary_label,
                trade_description_native,
                entity_type,
                keywords
            FROM companies
            ORDER BY id
        """
        
        self.cursor.execute(query)
        rows = self.cursor.fetchall()
        
        df = pd.DataFrame(rows)
        print(f"   ✓ {len(df):,} empresas carregadas")
        
        return df
    
    def load_incentives(
        self,
        status_filter: Optional[str] = 'Active',
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """Carrega incentivos do banco para DataFrame"""
        print(f"\n📊 Carregando incentivos do banco...")
        
        query = """
            SELECT 
                id,
                incentive_project_id,
                project_id,
                incentive_program,
                title,
                description,
                ai_description,
                date_end,
                total_budget,
                status,
                eligibility_criteria,
                geographical_scope,
                all_data,
                eligible_sectors,
                entity_types,
                keywords
            FROM incentives
        """
        
        conditions = []
        params = []
        
        if status_filter:
            conditions.append("status = %s")
            params.append(status_filter)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY id"
        
        if limit:
            query += f" LIMIT {limit}"
        
        self.cursor.execute(query, params)
        rows = self.cursor.fetchall()
        
        df = pd.DataFrame(rows)
        
        # Converter JSONB para string/dict
        if 'eligibility_criteria' in df.columns:
            df['eligibility_criteria'] = df['eligibility_criteria'].apply(
                lambda x: json.dumps(x) if isinstance(x, dict) else x
            )
        
        print(f"   ✓ {len(df):,} incentivos carregados")
        
        return df
    
    def initialize_matching_engine(self, companies_df: pd.DataFrame):
        """Inicializa o motor de matching"""
        print("\n🔧 Inicializando motor de matching...")
        
        self.engine = OptimizedMatchingEngine(
            companies_df,
            gemini_api_key=self.gemini_api_key,
            phase2_top_n=self.phase2_top_n,
            final_top_n=self.final_top_n
        )
        
        print("   ✓ Motor inicializado")
    
    def save_matches(
        self,
        incentive_db_id: int,
        matches_df: pd.DataFrame,
        processing_time_ms: int,
        method: str = 'optimized_funnel'
    ):
        """Salva matches no banco de dados"""
        if matches_df.empty:
            return
        
        # Limpar matches anteriores deste incentivo
        self.cursor.execute(
            "DELETE FROM matches WHERE incentive_id = %s",
            (int(incentive_db_id),)
        )
        
        # Preparar dados para inserção
        matches_data = []
        
        for rank, (idx, match) in enumerate(matches_df.iterrows(), start=1):
            # Buscar company_id pelo company_index
            self.cursor.execute(
                "SELECT id FROM companies WHERE company_index = %s",
                (int(match.get('company_index', idx)),)
            )
            company_result = self.cursor.fetchone()
            
            if not company_result:
                continue
            
            company_id = company_result['id']
            
            # Preparar matched_keywords como JSON
            matched_kw = match.get('matched_keywords', {})
            if isinstance(matched_kw, dict):
                matched_kw_json = json.dumps(matched_kw)
            else:
                matched_kw_json = '{}'
            
            matches_data.append((
                int(incentive_db_id),
                int(company_id),
                int(rank),
                float(match.get('keyword_score', 0)) if 'keyword_score' in match else float(match.get('llm_score', 0)) * 10,
                float(match.get('keyword_score', 0)),
                float(match.get('semantic_score', 0)) if 'semantic_score' in match else 0.0,
                float(match.get('llm_score', 0)) if 'llm_score' in match else None,
                matched_kw_json,
                int(match.get('match_count', 0)),
                str(match.get('rationale', '')),
                str(match.get('justificacao', match.get('llm_justification', ''))),
                float(match.get('geo_score', 0)) if 'geo_score' in match else None,
                list(match.get('geo_regions', [])) if 'geo_regions' in match else None,
                float(match.get('size_score', 0)) if 'size_score' in match else None,
                str(match.get('size_category', '')),
                float(match.get('budget_score', 0)) if 'budget_score' in match else None,
                float(match.get('status_score', 0)) if 'status_score' in match else None,
                float(match.get('innovation_score', 0)) if 'innovation_score' in match else None,
                list(match.get('innovation_themes', [])) if 'innovation_themes' in match else None,
                str(method),
                int(processing_time_ms)
            ))
        
        # Inserir matches
        if matches_data:
            insert_query = """
                INSERT INTO matches (
                    incentive_id, company_id, rank, final_score, keyword_score,
                    semantic_score, llm_score, matched_keywords, match_count,
                    rationale, llm_justification, geo_score, geo_regions,
                    size_score, size_category, budget_score, status_score,
                    innovation_score, innovation_themes, matching_method,
                    processing_time_ms
                ) VALUES %s
            """
            
            execute_values(self.cursor, insert_query, matches_data)
            self.conn.commit()
    
    def log_matching_execution(
        self,
        incentive_db_id: int,
        stats: Dict,
        method: str,
        status: str = 'success',
        error_message: Optional[str] = None
    ):
        """Registra log da execução do matching"""
        insert_query = """
            INSERT INTO matching_logs (
                incentive_id, total_companies, phase1_filtered, phase2_candidates,
                phase3_analyzed, final_matches, phase1_time_ms, phase2_time_ms,
                phase3_time_ms, total_time_ms, method, llm_enabled, llm_model,
                status, error_message
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """
        
        self.cursor.execute(insert_query, (
            int(incentive_db_id),
            int(stats.get('total_companies', 0)),
            int(stats.get('phase1_filtered', 0)),
            int(stats.get('phase2_candidates', 0)),
            int(stats.get('phase3_analyzed', 0)),
            int(stats.get('final_matches', 0)),
            int(stats.get('phase1_time_ms', 0)),
            int(stats.get('phase2_time_ms', 0)),
            int(stats.get('phase3_time_ms', 0)),
            int(stats.get('total_time_ms', 0)),
            method,
            self.gemini_api_key is not None,
            'gemini-1.5-flash' if self.gemini_api_key else None,
            status,
            error_message
        ))
        
        self.conn.commit()
    
    def process_single_incentive(
        self,
        incentive_row: pd.Series,
        verbose: bool = False
    ) -> pd.DataFrame:
        """Processa matching para um único incentivo"""
        start_time = time.time()
        
        try:
            print(f"\n🔍 Processando incentivo: {incentive_row.get('title', 'N/A')[:70]}")
            
            # Executar matching COM VERBOSE FORÇADO para debug
            matches = self.engine.find_top_matches(incentive_row, verbose=True)
            
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # Salvar no banco
            incentive_db_id = incentive_row['id']
            self.save_matches(
                incentive_db_id,
                matches,
                processing_time_ms,
                method='optimized_funnel'
            )
            
            # Log
            stats = {
                'total_companies': len(self.engine.companies),
                'phase1_filtered': self.engine.phase1.stats.get('passed_filter', 0),
                'phase2_candidates': min(len(matches), self.phase2_top_n),
                'phase3_analyzed': min(len(matches), self.phase2_top_n),
                'final_matches': len(matches),
                'total_time_ms': processing_time_ms
            }
            
            self.log_matching_execution(
                incentive_db_id,
                stats,
                method='optimized_funnel',
                status='success'
            )
            
            return matches
            
        except Exception as e:
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # Log de erro
            self.log_matching_execution(
                incentive_row['id'],
                {'total_time_ms': processing_time_ms},
                method='optimized_funnel',
                status='error',
                error_message=str(e)
            )
            
            raise
    
    def process_all_incentives(
        self,
        incentives_df: pd.DataFrame,
        verbose: bool = False
    ):
        """Processa matching para todos os incentivos"""
        print(f"\n{'='*80}")
        print(f"PROCESSANDO {len(incentives_df)} INCENTIVOS")
        print(f"{'='*80}\n")
        
        success_count = 0
        error_count = 0
        
        for idx, incentive_row in incentives_df.iterrows():
            try:
                if idx % 10 == 0:
                    print(f"\nProgresso: {idx}/{len(incentives_df)} ({idx/len(incentives_df)*100:.1f}%)")
                
                if verbose:
                    print(f"\n{incentive_row['title'][:60]}...")
                
                matches = self.process_single_incentive(incentive_row, verbose=False)
                
                if verbose:
                    print(f"   ✓ {len(matches)} matches encontrados")
                
                success_count += 1
                
            except Exception as e:
                print(f"   ✗ Erro: {e}")
                error_count += 1
        
        print(f"\n{'='*80}")
        print(f"PROCESSAMENTO CONCLUÍDO")
        print(f"{'='*80}")
        print(f"✓ Sucesso: {success_count}")
        print(f"✗ Erros: {error_count}")
        print(f"Total: {len(incentives_df)}")
    
    def get_matches_for_incentive(self, incentive_project_id: int) -> pd.DataFrame:
        """Busca matches salvos para um incentivo"""
        query = """
            SELECT 
                m.rank,
                m.final_score,
                m.keyword_score,
                m.llm_score,
                m.rationale,
                m.llm_justification,
                c.company_name,
                c.cae_primary_label,
                c.trade_description_native,
                m.matched_keywords,
                m.match_count,
                m.created_at
            FROM matches m
            JOIN companies c ON m.company_id = c.id
            JOIN incentives i ON m.incentive_id = i.id
            WHERE i.incentive_project_id = %s
            ORDER BY m.rank
        """
        
        self.cursor.execute(query, (incentive_project_id,))
        rows = self.cursor.fetchall()
        
        return pd.DataFrame(rows)
    
    def run(
        self,
        status_filter: str = 'Active',
        limit: Optional[int] = None,
        verbose: bool = False
    ):
        """Executa pipeline completo de matching"""
        try:
            self.connect()
            
            # Carregar dados
            companies_df = self.load_companies()
            incentives_df = self.load_incentives(status_filter, limit)
            
            # Inicializar engine
            self.initialize_matching_engine(companies_df)
            
            # Processar
            self.process_all_incentives(incentives_df, verbose)
            
        finally:
            self.disconnect()


def main():
    """Função principal"""
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description="Serviço de Matching com PostgreSQL")
    parser.add_argument('--db', required=True, help="String de conexão PostgreSQL")
    parser.add_argument('--status', default='Active', help="Filtrar por status do incentivo")
    parser.add_argument('--limit', type=int, help="Limitar número de incentivos")
    parser.add_argument('--incentive-id', type=int, help="Processar apenas um incentivo específico")
    parser.add_argument('--llm', action='store_true', help="Habilitar LLM (requer GEMINI_API_KEY)")
    parser.add_argument('--verbose', action='store_true', help="Modo verbose")
    
    args = parser.parse_args()
    
    # API Key
    api_key = os.getenv('GEMINI_API_KEY') if args.llm else None
    
    # Inicializar serviço
    service = DatabaseMatchingService(
        args.db,
        gemini_api_key=api_key,
        phase2_top_n=20,
        final_top_n=5
    )
    
    if args.incentive_id:
        # Processar apenas um incentivo
        try:
            service.connect()
            companies_df = service.load_companies()
            incentives_df = service.load_incentives(status_filter=None)
            
            # Filtrar incentivo específico
            incentive_row = incentives_df[
                incentives_df['incentive_project_id'] == args.incentive_id
            ]
            
            if incentive_row.empty:
                print(f"✗ Incentivo {args.incentive_id} não encontrado")
                return
            
            incentive_row = incentive_row.iloc[0]
            
            service.initialize_matching_engine(companies_df)
            matches = service.process_single_incentive(incentive_row, verbose=True)
            
            print(f"\n✓ {len(matches)} matches salvos no banco")
            
        finally:
            service.disconnect()
    else:
        # Processar todos
        service.run(
            status_filter=args.status,
            limit=args.limit,
            verbose=args.verbose
        )


if __name__ == "__main__":
    main()
