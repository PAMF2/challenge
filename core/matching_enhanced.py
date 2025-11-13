"""
Enhanced Matching Engine
Sistema de matching robusto com critérios expandidos e objetivos
"""
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from difflib import SequenceMatcher
import json

try:
    from sentence_transformers import SentenceTransformer, util
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    print("Warning: sentence-transformers not available. Semantic matching disabled.")

from core.enhanced_criteria import EnhancedCriteriaScorer


class EnhancedMatchingEngine:
    """
    Motor de matching com critérios expandidos:
    - Keyword matching (fuzzy)
    - Semantic similarity (embeddings)
    - Geographic matching
    - Company size alignment
    - Budget alignment
    - Incentive status validation
    - Innovation/sustainability themes
    """
    
    def __init__(
        self,
        companies_df: pd.DataFrame,
        use_embeddings: bool = True,
        embedding_model: str = 'all-MiniLM-L6-v2'
    ):
        self.companies = companies_df.copy()
        self.use_embeddings = use_embeddings and EMBEDDINGS_AVAILABLE
        self.criteria_scorer = EnhancedCriteriaScorer()
        
        # Inicializar modelo de embeddings
        if self.use_embeddings:
            try:
                self.model = SentenceTransformer(embedding_model)
                print(f"✓ Modelo de embeddings carregado: {embedding_model}")
            except Exception as e:
                print(f"⚠ Erro ao carregar embeddings: {e}")
                self.use_embeddings = False
        
        # Pré-processar empresas
        self._preprocess_companies()
    
    def _preprocess_companies(self):
        """Pré-processa dados das empresas"""
        # Criar texto combinado para matching
        self.companies['_combined_text'] = (
            self.companies['company_name'].fillna('') + ' ' +
            self.companies['cae_primary_label'].fillna('') + ' ' +
            self.companies['trade_description_native'].fillna('')
        )
        
        # Gerar embeddings se disponível
        if self.use_embeddings:
            print("Gerando embeddings para empresas...")
            self.companies['_embedding'] = self.companies['_combined_text'].apply(
                lambda x: self.model.encode(x, convert_to_tensor=False)
            )
            print(f"✓ Embeddings gerados para {len(self.companies)} empresas")
    
    def _calculate_keyword_score(
        self,
        company_text: str,
        incentive_criteria: str,
        incentive_sectors: Optional[str] = None
    ) -> float:
        """Calcula score de keyword matching usando fuzzy matching"""
        # Combinar critérios e setores
        incentive_text = incentive_criteria
        if incentive_sectors:
            try:
                sectors_data = json.loads(incentive_sectors) if isinstance(incentive_sectors, str) else incentive_sectors
                if isinstance(sectors_data, dict):
                    sectors_str = ' '.join(str(v) for v in sectors_data.values())
                else:
                    sectors_str = str(sectors_data)
                incentive_text = f"{incentive_text} {sectors_str}"
            except:
                pass
        
        # Fuzzy matching
        score = SequenceMatcher(None, company_text.lower(), incentive_text.lower()).ratio()
        return score
    
    def _calculate_semantic_score(
        self,
        company_embedding: np.ndarray,
        incentive_text: str
    ) -> float:
        """Calcula score de similaridade semântica"""
        if not self.use_embeddings:
            return 0.0
        
        try:
            incentive_embedding = self.model.encode(incentive_text, convert_to_tensor=False)
            similarity = util.cos_sim(company_embedding, incentive_embedding)[0][0].item()
            return max(0.0, similarity)  # Normalizar para [0, 1]
        except Exception as e:
            print(f"Erro no cálculo semântico: {e}")
            return 0.0
    
    def find_top_matches(
        self,
        incentive_row: pd.Series,
        top_n: int = 5,
        min_score: float = 20.0
    ) -> pd.DataFrame:
        """
        Encontra as top N empresas para um incentivo
        
        Args:
            incentive_row: Linha do DataFrame de incentivos
            top_n: Número de matches a retornar
            min_score: Score mínimo para considerar (0-100)
        
        Returns:
            DataFrame com top matches e scores detalhados
        """
        # Preparar texto do incentivo
        incentive_text = ' '.join(filter(None, [
            str(incentive_row.get('title', '')),
            str(incentive_row.get('description', '')),
            str(incentive_row.get('ai_description', '')),
            str(incentive_row.get('eligibility_criteria', ''))
        ]))
        
        matches = []
        
        for idx, company_row in self.companies.iterrows():
            # Score base: keyword matching
            keyword_score = self._calculate_keyword_score(
                company_row['_combined_text'],
                incentive_text,  # Usar texto completo do incentivo
                str(incentive_row.get('eligibility_criteria', ''))
            )
            
            # Score semântico
            semantic_score = 0.0
            if self.use_embeddings and '_embedding' in company_row:
                semantic_score = self._calculate_semantic_score(
                    company_row['_embedding'],
                    incentive_text
                )
            
            # Filtro inicial mais permissivo: pelo menos um dos scores deve ser > 0.15
            if keyword_score < 0.15 and semantic_score < 0.15:
                continue
            
            # Calcular score expandido com todos os critérios
            score_details = self.criteria_scorer.calculate_enhanced_score(
                company_row,
                incentive_row,
                keyword_score,
                semantic_score
            )
            
            # Aplicar filtro de score mínimo
            if score_details['final_score'] < min_score:
                continue
            
            # Formatar rationale
            rationale = self.criteria_scorer.format_enhanced_rationale(score_details)
            
            matches.append({
                'company_name': company_row.get('company_name'),
                'company_index': idx,
                'cae_primary_label': company_row.get('cae_primary_label'),
                'match_score': score_details['final_score'],
                'keyword_score': keyword_score * 100,
                'semantic_score': semantic_score * 100,
                'geo_score': score_details['geo_score'] * 100,
                'size_score': score_details['size_score'] * 100,
                'budget_score': score_details['budget_score'] * 100,
                'status_score': score_details['status_score'] * 100,
                'innovation_bonus': score_details['innovation_bonus'],
                'geo_regions': ', '.join(score_details['geo_regions']) if score_details['geo_regions'] else '',
                'size_category': score_details['size_category'],
                'innovation_themes': ', '.join(score_details['innovation_themes']) if score_details['innovation_themes'] else '',
                'rationale': rationale
            })
        
        # Converter para DataFrame e ordenar
        if not matches:
            return pd.DataFrame(columns=[
                'company_name', 'company_index', 'cae_primary_label', 'match_score',
                'keyword_score', 'semantic_score', 'geo_score', 'size_score',
                'budget_score', 'status_score', 'innovation_bonus', 'geo_regions',
                'size_category', 'innovation_themes', 'rationale'
            ])
        
        results_df = pd.DataFrame(matches)
        results_df = results_df.sort_values('match_score', ascending=False)
        results_df = results_df.head(top_n).reset_index(drop=True)
        
        return results_df
    
    def generate_full_matching_report(
        self,
        incentives_df: pd.DataFrame,
        output_path: str = 'matching_enhanced_report.csv',
        top_n: int = 5
    ) -> pd.DataFrame:
        """
        Gera relatório completo de matching para todos os incentivos
        
        Args:
            incentives_df: DataFrame com incentivos
            output_path: Caminho para salvar CSV
            top_n: Número de matches por incentivo
        
        Returns:
            DataFrame consolidado com todos os matches
        """
        all_matches = []
        
        print(f"\nProcessando {len(incentives_df)} incentivos...")
        
        for idx, incentive_row in incentives_df.iterrows():
            if idx % 10 == 0:
                print(f"Progresso: {idx}/{len(incentives_df)}")
            
            matches = self.find_top_matches(incentive_row, top_n=top_n)
            
            if not matches.empty:
                # Adicionar informações do incentivo
                matches['incentive_id'] = incentive_row.get('incentive_project_id')
                matches['incentive_title'] = incentive_row.get('title')
                matches['incentive_program'] = incentive_row.get('incentive_program')
                matches['incentive_budget'] = incentive_row.get('total_budget')
                matches['incentive_status'] = incentive_row.get('status')
                
                all_matches.append(matches)
        
        if not all_matches:
            print("⚠ Nenhum match encontrado!")
            return pd.DataFrame()
        
        # Consolidar resultados
        consolidated = pd.concat(all_matches, ignore_index=True)
        
        # Reordenar colunas
        column_order = [
            'incentive_id', 'incentive_title', 'incentive_program', 'incentive_budget', 'incentive_status',
            'company_name', 'cae_primary_label', 'match_score',
            'keyword_score', 'semantic_score', 'geo_score', 'size_score', 'budget_score', 'status_score',
            'innovation_bonus', 'geo_regions', 'size_category', 'innovation_themes', 'rationale'
        ]
        
        consolidated = consolidated[[col for col in column_order if col in consolidated.columns]]
        
        # Salvar CSV
        consolidated.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"\n✓ Relatório salvo em: {output_path}")
        print(f"✓ Total de matches: {len(consolidated)}")
        print(f"✓ Incentivos com matches: {consolidated['incentive_id'].nunique()}")
        
        return consolidated


def main():
    """Função principal para teste"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Enhanced Matching Engine")
    parser.add_argument('--incentive-id', type=int, help="ID do incentivo para testar")
    parser.add_argument('--full-report', action='store_true', help="Gerar relatório completo")
    parser.add_argument('--no-embeddings', action='store_true', help="Desabilitar embeddings")
    parser.add_argument('--top-n', type=int, default=5, help="Número de matches por incentivo")
    
    args = parser.parse_args()
    
    # Carregar dados
    print("Carregando dados...")
    companies_df = pd.read_csv(project_root / 'data' / 'companies.csv')
    incentives_df = pd.read_csv(project_root / 'data' / 'incentives.csv')
    
    print(f"✓ {len(companies_df)} empresas carregadas")
    print(f"✓ {len(incentives_df)} incentivos carregados")
    
    # Inicializar engine
    engine = EnhancedMatchingEngine(
        companies_df,
        use_embeddings=not args.no_embeddings
    )
    
    if args.full_report:
        # Gerar relatório completo
        engine.generate_full_matching_report(
            incentives_df,
            output_path='matching_enhanced_full.csv',
            top_n=args.top_n
        )
    elif args.incentive_id is not None:
        # Testar incentivo específico
        incentive_row = incentives_df[
            incentives_df['incentive_project_id'] == args.incentive_id
        ].iloc[0]
        
        print(f"\n{'='*80}")
        print(f"INCENTIVO: {incentive_row['title']}")
        print(f"Programa: {incentive_row['incentive_program']}")
        print(f"{'='*80}\n")
        
        matches = engine.find_top_matches(incentive_row, top_n=args.top_n)
        
        if matches.empty:
            print("Nenhum match encontrado.")
        else:
            for idx, match in matches.iterrows():
                print(f"{idx + 1}. {match['company_name']}")
                print(f"   Score: {match['match_score']:.1f}/100")
                print(f"   CAE: {match['cae_primary_label']}")
                print(f"   Rationale: {match['rationale']}")
                print()
    else:
        # Teste padrão com primeiro incentivo
        incentive_row = incentives_df.iloc[0]
        print(f"\nTestando com: {incentive_row['title']}\n")
        
        matches = engine.find_top_matches(incentive_row, top_n=5)
        
        for idx, match in matches.iterrows():
            print(f"{idx + 1}. {match['company_name']} - Score: {match['match_score']:.1f}")


if __name__ == "__main__":
    main()
