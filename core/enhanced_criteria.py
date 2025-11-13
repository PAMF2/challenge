"""
Enhanced Matching Criteria
Critérios expandidos para matching mais robusto e objetivo
"""
import json
import re
from datetime import datetime
from typing import Dict, Set, List, Optional, Tuple
import pandas as pd


# Regiões NUTS de Portugal
PORTUGAL_REGIONS = {
    'Norte': ['Porto', 'Braga', 'Viana do Castelo', 'Vila Real', 'Bragança'],
    'Centro': ['Coimbra', 'Aveiro', 'Viseu', 'Guarda', 'Castelo Branco', 'Leiria'],
    'Lisboa': ['Lisboa', 'Setúbal'],
    'Alentejo': ['Évora', 'Beja', 'Portalegre', 'Alto Alentejo', 'Alentejo Litoral', 'Alentejo Central', 'Baixo Alentejo'],
    'Algarve': ['Faro', 'Algarve'],
    'Açores': ['Açores', 'Azores'],
    'Madeira': ['Madeira', 'Funchal']
}

# Keywords para inferir tamanho de empresa
PME_INDICATORS = [
    'pme', 'micro', 'pequena', 'média empresa', 'startup', 'empreendedor',
    'artesanal', 'familiar', 'individual', 'unipessoal'
]

LARGE_COMPANY_INDICATORS = [
    'sa', 's.a.', 'sociedade anónima', 'sgps', 'holding', 'grupo',
    'multinacional', 'internacional', 'corporation'
]

# Keywords para inovação e sustentabilidade
INNOVATION_KEYWORDS = {
    'digital': ['digital', 'digitalização', 'tecnologia', 'software', 'app', 'plataforma', 
                'ia', 'inteligência artificial', 'machine learning', 'automação', 'robotica'],
    'sustentabilidade': ['sustentável', 'sustentabilidade', 'verde', 'ecológico', 'eco-friendly',
                         'renovável', 'solar', 'eólica', 'energia limpa', 'reciclagem', 'circular'],
    'inovação': ['inovação', 'inovador', 'r&d', 'investigação', 'desenvolvimento', 'patente',
                 'startup', 'disruptivo', 'tecnológico'],
    'exportação': ['exportação', 'internacional', 'global', 'mercados externos', 'export'],
}


class EnhancedCriteriaScorer:
    """Calcula scores para critérios expandidos de matching"""
    
    def __init__(self):
        self.current_date = datetime.now()
    
    def score_geographic_match(
        self, 
        company_text: str, 
        incentive_geo_scope: Optional[str],
        incentive_all_data: Optional[str]
    ) -> Tuple[float, List[str]]:
        """
        Score baseado em localização geográfica
        Returns: (score, matched_regions)
        """
        if not incentive_geo_scope and not incentive_all_data:
            return 0.5, []  # Neutro se não há restrição geográfica
        
        company_text_lower = company_text.lower()
        matched_regions = []
        
        # Extrair regiões do incentivo
        incentive_regions = set()
        
        # Parse geographical_scope se existir
        if incentive_geo_scope:
            try:
                geo_data = json.loads(incentive_geo_scope) if isinstance(incentive_geo_scope, str) else incentive_geo_scope
                if isinstance(geo_data, dict):
                    incentive_regions.update(geo_data.get('regions', []))
                    incentive_regions.update(geo_data.get('nuts', []))
                elif isinstance(geo_data, list):
                    incentive_regions.update(geo_data)
            except:
                pass
        
        # Parse all_data para regiões
        if incentive_all_data:
            try:
                all_data = json.loads(incentive_all_data) if isinstance(incentive_all_data, str) else incentive_all_data
                # Procurar por campos relacionados a região
                all_data_str = str(all_data).lower()
                for region in PORTUGAL_REGIONS.keys():
                    if region.lower() in all_data_str:
                        incentive_regions.add(region)
            except:
                pass
        
        # Se não há restrição geográfica específica, score neutro
        if not incentive_regions:
            return 0.5, []
        
        # Verificar match entre empresa e regiões do incentivo
        for region, cities in PORTUGAL_REGIONS.items():
            if region in incentive_regions or any(city.lower() in str(incentive_regions).lower() for city in cities):
                # Verificar se a empresa menciona essa região
                if region.lower() in company_text_lower or any(city.lower() in company_text_lower for city in cities):
                    matched_regions.append(region)
        
        if matched_regions:
            return 1.0, matched_regions  # Match exato
        
        # Match parcial: empresa não menciona região mas incentivo é nacional/múltiplas regiões
        if len(incentive_regions) >= 3:  # Incentivo abrangente
            return 0.7, []
        
        return 0.0, []  # Sem match geográfico
    
    def score_company_size(
        self,
        company_name: str,
        company_description: str,
        incentive_entities: Optional[str],
        incentive_criteria: Optional[str]
    ) -> Tuple[float, str]:
        """
        Score baseado no tamanho da empresa
        Returns: (score, size_category)
        """
        company_text = f"{company_name} {company_description}".lower()
        
        # Inferir tamanho da empresa
        is_pme = any(indicator in company_text for indicator in PME_INDICATORS)
        is_large = any(indicator in company_text for indicator in LARGE_COMPANY_INDICATORS)
        
        # Heurística adicional: nome curto e sem SA/SGPS = provavelmente PME
        if not is_large and len(company_name.split()) <= 4:
            is_pme = True
        
        company_size = 'PME' if is_pme else 'Grande' if is_large else 'Média'
        
        # Verificar preferência do incentivo
        incentive_text = f"{incentive_entities or ''} {incentive_criteria or ''}".lower()
        
        prefers_pme = any(term in incentive_text for term in ['pme', 'micro', 'pequena', 'média empresa'])
        prefers_large = any(term in incentive_text for term in ['grande empresa', 'multinacional'])
        
        # Calcular score
        if prefers_pme and company_size == 'PME':
            return 1.0, company_size
        elif prefers_large and company_size == 'Grande':
            return 1.0, company_size
        elif not prefers_pme and not prefers_large:
            return 0.5, company_size  # Sem preferência específica
        elif company_size == 'Média':
            return 0.7, company_size  # Média empresa geralmente elegível
        else:
            return 0.3, company_size  # Mismatch
    
    def score_budget_alignment(
        self,
        company_description: str,
        incentive_budget: Optional[float]
    ) -> Tuple[float, str]:
        """
        Score baseado no alinhamento de orçamento
        Returns: (score, alignment_reason)
        """
        if not incentive_budget or incentive_budget == 0:
            return 0.5, "Orçamento não especificado"
        
        # Inferir escala da empresa pela descrição
        desc_length = len(company_description.split())
        
        # Heurística: descrição mais longa = empresa maior
        if desc_length > 100:
            company_scale = 'Grande'
            estimated_capacity = 1000000  # 1M+
        elif desc_length > 50:
            company_scale = 'Média'
            estimated_capacity = 500000  # 500k
        else:
            company_scale = 'Pequena'
            estimated_capacity = 100000  # 100k
        
        # Comparar com orçamento do incentivo
        ratio = abs(incentive_budget - estimated_capacity) / max(incentive_budget, estimated_capacity)
        
        if ratio < 0.2:  # Muito alinhado
            return 1.0, f"Orçamento alinhado ({company_scale})"
        elif ratio < 0.5:  # Razoavelmente alinhado
            return 0.7, f"Orçamento parcialmente alinhado ({company_scale})"
        elif incentive_budget > estimated_capacity * 2:  # Incentivo muito grande
            return 0.4, f"Incentivo pode ser muito grande ({company_scale})"
        else:
            return 0.5, f"Alinhamento neutro ({company_scale})"
    
    def score_incentive_status(
        self,
        status: Optional[str],
        date_end: Optional[str]
    ) -> Tuple[float, str]:
        """
        Score baseado no status do incentivo
        Returns: (score, status_reason)
        """
        if not status:
            return 0.5, "Status desconhecido"
        
        status_lower = status.lower()
        
        # Verificar se está ativo
        if status_lower != 'active':
            return 0.0, f"Incentivo não ativo ({status})"
        
        # Verificar data de fim
        if date_end:
            try:
                if isinstance(date_end, str):
                    # Parse diferentes formatos de data
                    end_date = pd.to_datetime(date_end)
                else:
                    end_date = pd.Timestamp(date_end)
                
                if end_date < pd.Timestamp(self.current_date):
                    return 0.0, "Incentivo expirado"
                
                days_remaining = (end_date - pd.Timestamp(self.current_date)).days
                
                if days_remaining < 30:
                    return 0.6, f"Expira em breve ({days_remaining} dias)"
                elif days_remaining < 90:
                    return 0.8, f"Prazo moderado ({days_remaining} dias)"
                else:
                    return 1.0, f"Prazo adequado ({days_remaining} dias)"
            except:
                return 0.8, "Ativo (data de fim inválida)"
        
        return 1.0, "Ativo e sem data de fim"
    
    def score_innovation_sustainability(
        self,
        company_description: str,
        incentive_description: str,
        incentive_ai_description: Optional[str]
    ) -> Tuple[float, List[str]]:
        """
        Score baseado em inovação e sustentabilidade
        Returns: (score, matched_themes)
        """
        company_text = company_description.lower()
        incentive_text = f"{incentive_description} {incentive_ai_description or ''}".lower()
        
        matched_themes = []
        theme_scores = []
        
        for theme, keywords in INNOVATION_KEYWORDS.items():
            company_has = any(kw in company_text for kw in keywords)
            incentive_wants = any(kw in incentive_text for kw in keywords)
            
            if company_has and incentive_wants:
                matched_themes.append(theme)
                theme_scores.append(1.0)
            elif company_has or incentive_wants:
                theme_scores.append(0.3)  # Bonus parcial
            else:
                theme_scores.append(0.0)
        
        if not theme_scores:
            return 0.5, []
        
        avg_score = sum(theme_scores) / len(theme_scores)
        return avg_score, matched_themes
    
    def calculate_enhanced_score(
        self,
        company_row: pd.Series,
        incentive_row: pd.Series,
        base_keyword_score: float,
        base_semantic_score: float
    ) -> Dict:
        """
        Calcula score combinado com todos os critérios
        
        Pesos:
        - 30% keyword matching
        - 30% semantic similarity
        - 15% geographic match
        - 10% company size
        - 10% budget alignment
        - 5% incentive status
        - (bonus) innovation/sustainability
        """
        # Critérios expandidos
        geo_score, geo_regions = self.score_geographic_match(
            company_row.get('trade_description_native', ''),
            incentive_row.get('geographical_scope'),
            incentive_row.get('all_data')
        )
        
        size_score, size_category = self.score_company_size(
            company_row.get('company_name', ''),
            company_row.get('trade_description_native', ''),
            incentive_row.get('entities'),
            incentive_row.get('eligibility_criteria')
        )
        
        budget_score, budget_reason = self.score_budget_alignment(
            company_row.get('trade_description_native', ''),
            incentive_row.get('total_budget')
        )
        
        status_score, status_reason = self.score_incentive_status(
            incentive_row.get('status'),
            incentive_row.get('date_end')
        )
        
        innovation_score, innovation_themes = self.score_innovation_sustainability(
            company_row.get('trade_description_native', ''),
            incentive_row.get('description', ''),
            incentive_row.get('ai_description')
        )
        
        # Score combinado (normalizado para 0-100)
        combined_score = (
            0.30 * base_keyword_score +
            0.30 * base_semantic_score +
            0.15 * geo_score +
            0.10 * size_score +
            0.10 * budget_score +
            0.05 * status_score
        ) * 100
        
        # Bonus por inovação/sustentabilidade (até +10 pontos)
        innovation_bonus = innovation_score * 10
        final_score = min(100, combined_score + innovation_bonus)
        
        return {
            'final_score': final_score,
            'base_keyword_score': base_keyword_score,
            'base_semantic_score': base_semantic_score,
            'geo_score': geo_score,
            'geo_regions': geo_regions,
            'size_score': size_score,
            'size_category': size_category,
            'budget_score': budget_score,
            'budget_reason': budget_reason,
            'status_score': status_score,
            'status_reason': status_reason,
            'innovation_score': innovation_score,
            'innovation_themes': innovation_themes,
            'innovation_bonus': innovation_bonus
        }
    
    def format_enhanced_rationale(self, score_details: Dict) -> str:
        """Formata a razão do match com todos os critérios"""
        parts = []
        
        parts.append(f"Score Final: {score_details['final_score']:.1f}/100")
        
        # Componentes principais
        components = []
        if score_details['base_keyword_score'] > 0:
            components.append(f"Keywords: {score_details['base_keyword_score']*100:.0f}%")
        if score_details['base_semantic_score'] > 0:
            components.append(f"Semântica: {score_details['base_semantic_score']*100:.0f}%")
        
        if components:
            parts.append(f"Base: {', '.join(components)}")
        
        # Critérios expandidos
        if score_details['geo_regions']:
            parts.append(f"Região: {', '.join(score_details['geo_regions'])}")
        
        if score_details['size_category']:
            parts.append(f"Tamanho: {score_details['size_category']}")
        
        if score_details['budget_reason']:
            parts.append(score_details['budget_reason'])
        
        if score_details['status_reason']:
            parts.append(score_details['status_reason'])
        
        if score_details['innovation_themes']:
            parts.append(f"Temas: {', '.join(score_details['innovation_themes'])} (+{score_details['innovation_bonus']:.0f} bonus)")
        
        return " | ".join(parts)
