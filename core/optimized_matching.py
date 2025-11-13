"""
Optimized 3-Phase Matching Funnel
Sistema de matching eficiente com uso cirúrgico de LLM

Fase 1: Filtragem Rígida (regras estruturadas)
Fase 2: Pontuação Preliminar (keywords)
Fase 3: Re-ranking Semântico (LLM focado)
"""
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
import json
import re
from typing import List, Dict, Set, Tuple, Optional
from collections import Counter
import time

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


class Phase1RigidFilter:
    """
    Fase 1: Filtragem Rígida por Critérios Obrigatórios
    Elimina empresas claramente inelegíveis usando dados estruturados
    """
    
    # Indicadores de tipo de entidade
    PRIVATE_COMPANY_INDICATORS = ['lda', 'ld', 's.a.', 'sa', 'unipessoal', 'sgps']
    PUBLIC_ENTITY_INDICATORS = ['município', 'câmara', 'junta', 'freguesia', 'ministério']
    NONPROFIT_INDICATORS = ['fundação', 'associação', 'irmandade', 'ipss', 'misericórdia', 
                           'centro social', 'paroquial', 'santa casa']
    
    def __init__(self):
        self.stats = {
            'total_companies': 0,
            'filtered_by_sector': 0,
            'filtered_by_entity': 0,
            'passed_filter': 0
        }
        
        # Inicializar embeddings para validação semântica de setores
        try:
            from sentence_transformers import SentenceTransformer
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            
            # Exemplos de setores VÁLIDOS (atividades empresariais)
            self.valid_sector_examples = [
                "agricultura", "pecuária", "pesca", "aquicultura", "silvicultura",
                "indústria", "manufatura", "construção", "obras",
                "comércio", "retalho", "grossista", "vendas",
                "transporte", "logística", "mobilidade", "freight", "cargo",
                "turismo", "hotelaria", "restauração", "hospedagem",
                "tecnologia", "software", "digital", "informática", "tech",
                "saúde", "medicina", "farmácia", "clínica", "hospital",
                "educação", "ensino", "formação", "escola",
                "energia", "eletricidade", "renováveis", "solar", "eólica",
                "cultura", "arte", "design", "criativo", "espetáculo"
            ]
            
            # Calcular embeddings dos exemplos (CACHE)
            self.sector_embeddings = self.embedding_model.encode(
                self.valid_sector_examples,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False
            )
            self.use_semantic_validation = True
        except:
            self.embedding_model = None
            self.use_semantic_validation = False
    
    def is_valid_sector(self, word: str, threshold: float = 0.70) -> bool:
        """Valida se uma palavra é um setor válido usando APENAS embeddings (100% dinâmico, threshold ULTRA rigoroso)"""
        if not self.use_semantic_validation or len(word) < 5:
            return False
        
        import numpy as np
        
        # Embedding da palavra
        word_embedding = self.embedding_model.encode(
            [word],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False
        )[0]
        
        # Similaridade com exemplos de setores válidos (agricultura, pesca, transporte, etc.)
        similarities = np.dot(self.sector_embeddings, word_embedding)
        max_similarity = similarities.max()
        
        # Threshold alto (0.50) = apenas setores muito similares aos exemplos
        return max_similarity > threshold
    
    def extract_eligible_sectors(
        self,
        eligibility_criteria: Optional[str],
        title: str = '',
        description: str = ''
    ) -> Set[str]:
        """
        Extrai setores elegíveis DINAMICAMENTE usando embeddings.
        Valida semanticamente se cada palavra é um setor empresarial válido.
        """
        if not title and not eligibility_criteria:
            return set()
        
        text_to_analyze = title or eligibility_criteria or ''
        
        if text_to_analyze:
            title_lower = text_to_analyze.lower()
            
            # Extrair palavras de 5+ caracteres
            words = re.findall(r'\b\w{5,}\b', title_lower)
            
            # Validar cada palavra usando embeddings
            eligible = set()
            for word in words:
                if self.is_valid_sector(word):
                    eligible.add(word)
            
            # Se não encontrou setores válidos, retornar vazio
            if not eligible:
                return set()
            
            # Limitar a 3 setores mais relevantes
            if len(eligible) > 3:
                eligible = set(list(eligible)[:3])
            
            return eligible
        
        return set()
    
    def extract_entity_types(self, eligibility_criteria: str, all_data: Optional[str] = None) -> Set[str]:
        """Extrai tipos de entidade elegíveis - retorna vazio se não houver restrição clara"""
        entity_types = set()
        
        # Parse eligibility_criteria
        if eligibility_criteria and not pd.isna(eligibility_criteria):
            try:
                criteria = json.loads(eligibility_criteria) if isinstance(eligibility_criteria, str) else eligibility_criteria
                if isinstance(criteria, dict):
                    entities = criteria.get('entities', '')
                    
                    if entities:
                        entities_lower = str(entities).lower()
                        
                        # Detectar restrições EXPLÍCITAS
                        if 'município' in entities_lower or 'municipal' in entities_lower:
                            entity_types.add('municipal')
                        elif 'ipss' in entities_lower or 'misericórdia' in entities_lower:
                            entity_types.add('nonprofit')
                        # Se menciona PME ou empresas, não adicionar restrição (deixar aberto)
                        # Isso permite que empresas privadas sejam consideradas
            except:
                pass
        
        return entity_types
    
    def classify_company_entity_type(self, company_name: str) -> str:
        """Classifica o tipo de entidade da empresa"""
        name_lower = company_name.lower()
        
        # Verificar entidades públicas
        if any(indicator in name_lower for indicator in self.PUBLIC_ENTITY_INDICATORS):
            return 'public'
        
        # Verificar entidades sem fins lucrativos
        if any(indicator in name_lower for indicator in self.NONPROFIT_INDICATORS):
            return 'nonprofit'
        
        # Verificar empresas privadas
        if any(indicator in name_lower for indicator in self.PRIVATE_COMPANY_INDICATORS):
            return 'private'
        
        # Default: assumir privada
        return 'private'
    
    def matches_sector(self, company_cae: str, eligible_sectors: Set[str]) -> bool:
        """Verifica se o CAE da empresa corresponde aos setores - 100% DINÂMICO"""
        if not eligible_sectors:
            return True  # Sem restrição de setor (aceita tudo)
        
        if not company_cae or pd.isna(company_cae):
            return False
        
        cae_lower = company_cae.lower()
        
        # Mapeamento de expansão para palavras-chave comuns (mínimo)
        expansions = {
            'mobilidade': ['transport', 'mobility', 'automotive', 'vehicle', 'veículo', 'taxi', 'uber', 'logistic'],
            'digital': ['software', 'technology', 'informatic', 'digital', 'it', 'tech'],
            'saúde': ['health', 'healthcare', 'medical', 'hospital', 'clinic'],
            'energia': ['energy', 'electricity', 'power', 'renewable', 'solar'],
            'turismo': ['tourism', 'hotel', 'hospitality', 'travel'],
        }
        
        # Match DIRETO ou EXPANDIDO
        for sector_word in eligible_sectors:
            sector_lower = sector_word.lower()
            
            # Palavras para procurar
            search_terms = [sector_lower]
            if sector_lower in expansions:
                search_terms.extend(expansions[sector_lower])
            
            for term in search_terms:
                # Match de palavra completa EXATO (palavra inteira no início)
                # Aceita variações (fishing, pescadores, etc)
                pattern = r'\b' + re.escape(term[:5]) + r'\w*\b' if len(term) >= 5 else r'\b' + re.escape(term) + r'\b'
                if re.search(pattern, cae_lower):
                    return True
        
        return False
    
    def matches_entity_type(self, company_type: str, required_types: Set[str]) -> bool:
        """Verifica se o tipo de entidade da empresa corresponde aos requisitos"""
        if not required_types:
            return True  # Sem restrição de tipo
        
        # Mapeamento de tipos
        type_mapping = {
            'municipal': ['public'],
            'pme': ['private'],
            'nonprofit': ['nonprofit'],
            'private': ['private'],
            'public': ['public']
        }
        
        for required in required_types:
            allowed_types = type_mapping.get(required, [required])
            if company_type in allowed_types:
                return True
        
        return False
    
    def filter_companies(
        self,
        companies_df: pd.DataFrame,
        incentive_row: pd.Series
    ) -> pd.DataFrame:
        """
        Aplica filtragem rígida e retorna empresas elegíveis
        
        Returns:
            DataFrame com empresas que passaram no filtro
        """
        self.stats['total_companies'] = len(companies_df)
        
        # Extrair critérios do incentivo (com fallback para título/descrição)
        eligible_sectors = self.extract_eligible_sectors(
            incentive_row.get('eligibility_criteria'),
            title=str(incentive_row.get('title', '')),
            description=str(incentive_row.get('description', ''))
        )
        
        required_entity_types = self.extract_entity_types(
            incentive_row.get('eligibility_criteria'),
            incentive_row.get('all_data')
        )
        
        # Classificar tipo de entidade de cada empresa
        companies_df['_entity_type'] = companies_df['company_name'].apply(
            self.classify_company_entity_type
        )
        
        # Filtro 1: Setor (CAE)
        if eligible_sectors:
            companies_df['_sector_match'] = companies_df['cae_primary_label'].apply(
                lambda cae: self.matches_sector(cae, eligible_sectors)
            )
        else:
            companies_df['_sector_match'] = True
        
        # Filtro 2: Tipo de Entidade
        companies_df['_entity_match'] = companies_df['_entity_type'].apply(
            lambda t: self.matches_entity_type(t, required_entity_types)
        )
        
        # Aplicar filtros
        mask_sector = companies_df['_sector_match']
        mask_entity = companies_df['_entity_match']
        
        filtered = companies_df[mask_sector & mask_entity].copy()
        
        # FALLBACK: Se filtrou TUDO (0 empresas), não passar nenhuma
        if len(filtered) == 0 and len(eligible_sectors) > 0:
            print(f"  ⚠️ Nenhuma empresa elegível para setores: {', '.join(list(eligible_sectors)[:5])}")
            # Retornar DataFrame vazio ao invés de passar todas
            filtered = pd.DataFrame()
        
        # Atualizar estatísticas
        self.stats['filtered_by_sector'] = (~mask_sector).sum()
        self.stats['filtered_by_entity'] = (~mask_entity).sum()
        self.stats['passed_filter'] = len(filtered)
        
        # Limpar colunas temporárias
        if not filtered.empty:
            filtered = filtered.drop(columns=['_entity_type', '_sector_match', '_entity_match'])
        
        return filtered


class Phase2KeywordScorer:
    """
    Fase 2: Ranking Semântico com Embeddings
    Usa sentence-transformers para comparação semântica
    """
    
    def __init__(self):
        """Inicializa modelo de embeddings e carrega cache"""
        try:
            from sentence_transformers import SentenceTransformer
            import pickle
            
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            
            # Tentar carregar embeddings pré-computados
            try:
                self.precomputed_embeddings = np.load('embeddings_cache/company_embeddings.npy')
                self.precomputed_ids = np.load('embeddings_cache/company_ids.npy')
                with open('embeddings_cache/id_to_index.pkl', 'rb') as f:
                    self.id_to_index = pickle.load(f)
                
                self.use_precomputed = True
                print("  - ⚡ Embeddings PRÉ-COMPUTADOS: Ativado")
                print(f"  - 📊 Cache: {len(self.precomputed_ids):,} empresas")
            except:
                self.use_precomputed = False
                print("  - 🔍 Embeddings semânticos: Ativado (tempo real)")
                print("  - 💡 Dica: Execute 'python precompute_embeddings.py' para acelerar 60x")
            
            self.use_embeddings = True
        except:
            self.embedding_model = None
            self.use_embeddings = False
            self.use_precomputed = False
            print("  - 📋 Fallback: Keywords simples")
    
    # Stopwords portuguesas (fallback)
    STOPWORDS = {
        'de', 'a', 'o', 'que', 'e', 'do', 'da', 'em', 'um', 'para', 'é', 'com',
        'não', 'uma', 'os', 'no', 'se', 'na', 'por', 'mais', 'as', 'dos', 'como',
        'mas', 'foi', 'ao', 'ele', 'das', 'tem', 'à', 'seu', 'sua', 'ou', 'ser',
        'quando', 'muito', 'há', 'nos', 'já', 'está', 'eu', 'também', 'só', 'pelo',
        'pela', 'até', 'isso', 'ela', 'entre', 'era', 'depois', 'sem', 'mesmo',
        'aos', 'ter', 'seus', 'quem', 'nas', 'me', 'esse', 'eles', 'estão', 'você',
        'tinha', 'foram', 'essa', 'num', 'nem', 'suas', 'meu', 'às', 'minha', 'têm',
        'numa', 'pelos', 'elas', 'havia', 'seja', 'qual', 'será', 'nós', 'tenho',
        'lhe', 'deles', 'essas', 'esses', 'pelas', 'este', 'fosse', 'dele'
    }
    
    def extract_keywords(self, text: str, min_length: int = 3) -> List[str]:
        """Extrai palavras-chave relevantes de um texto"""
        if not text or pd.isna(text):
            return []
        
        # Normalizar e tokenizar
        text_lower = text.lower()
        words = re.findall(r'\b[a-záàâãéèêíïóôõöúçñ]+\b', text_lower)
        
        # Filtrar stopwords e palavras curtas
        keywords = [
            word for word in words
            if len(word) >= min_length and word not in self.STOPWORDS
        ]
        
        return keywords
    
    def calculate_keyword_score(
        self,
        company_description: str,
        incentive_keywords: List[str]
    ) -> Tuple[float, Dict[str, int]]:
        """
        Calcula score baseado em correspondência de keywords
        
        Returns:
            (score, matched_keywords_count)
        """
        if not incentive_keywords:
            return 0.0, {}
        
        company_keywords = self.extract_keywords(company_description)
        
        if not company_keywords:
            return 0.0, {}
        
        # Contar matches
        company_keyword_set = set(company_keywords)
        incentive_keyword_set = set(incentive_keywords)
        
        matches = company_keyword_set & incentive_keyword_set
        
        # Contar frequência de cada match
        company_counter = Counter(company_keywords)
        match_counts = {kw: company_counter[kw] for kw in matches}
        
        # Score baseado em:
        # - Número de keywords únicas que fazem match
        # - Frequência total de matches
        # - Proporção de keywords do incentivo que foram encontradas
        
        unique_matches = len(matches)
        total_frequency = sum(match_counts.values())
        coverage = unique_matches / len(incentive_keyword_set) if incentive_keyword_set else 0
        
        # Score normalizado (0-100) - MELHORADO
        score = (
            0.5 * (unique_matches / max(len(incentive_keyword_set), 1)) * 100 +  # Coverage (aumentado)
            0.3 * min(total_frequency / 5, 1) * 100 +  # Frequency (cap reduzido = mais pontos)
            0.2 * min(unique_matches / 3, 1) * 100  # Absolute matches (cap reduzido)
        )
        
        return score, match_counts
    
    def score_companies(
        self,
        companies_df: pd.DataFrame,
        incentive_row: pd.Series,
        top_n: int = 20
    ) -> pd.DataFrame:
        """
        Pontua empresas usando EMBEDDINGS SEMÂNTICOS PUROS (otimizado)
        
        Returns:
            DataFrame com top N empresas ordenadas por score
        """
        title = str(incentive_row.get('title', ''))
        
        if not title:
            return pd.DataFrame()
        
        # APENAS EMBEDDINGS SEMÂNTICOS
        if self.use_embeddings and self.embedding_model:
            # Usar embeddings pré-computados se disponível
            if self.use_precomputed:
                return self._score_with_precomputed(companies_df, title, top_n)
            else:
                return self._score_with_embeddings(companies_df, title, top_n)
        else:
            # Fallback para keywords se embeddings não disponível
            return self._score_with_keywords(companies_df, title, top_n)
    
    def _score_with_embeddings(
        self,
        companies_df: pd.DataFrame,
        incentive_title: str,
        top_n: int
    ) -> pd.DataFrame:
        """Pontua usando similaridade de embeddings (ULTRA OTIMIZADO)"""
        import numpy as np
        from sklearn.metrics.pairwise import cosine_similarity
        import time
        
        start = time.time()
        
        # Embedding do incentivo (cache se possível)
        incentive_embedding = self.embedding_model.encode(
            [incentive_title],
            show_progress_bar=False,
            convert_to_numpy=True
        )[0]
        
        # Preparar textos - CAE + descrição (completo)
        company_texts = []
        valid_indices = []
        
        for idx, company_row in companies_df.iterrows():
            cae = str(company_row.get('cae_primary_label', ''))
            desc = str(company_row.get('trade_description_native', ''))
            
            # CAE tem mais peso (repetido 2x) + descrição
            company_text = f"{cae} {cae} {desc}" if desc and desc != 'nan' else cae
            
            if company_text and company_text.strip():
                company_texts.append(company_text)
                valid_indices.append(idx)
        
        if not company_texts:
            return pd.DataFrame()
        
        # BATCH ENCODING ULTRA-OTIMIZADO
        print(f"  🔄 Calculando embeddings para {len(company_texts):,} empresas...")
        
        company_embeddings = self.embedding_model.encode(
            company_texts,
            batch_size=1024,  # MÁXIMO batch size (2x mais rápido)
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True  # Normalizar = cosine mais rápido
        )
        
        # Calcular similaridades (com embeddings normalizados = dot product)
        similarities = np.dot(company_embeddings, incentive_embedding)
        
        # Criar scores apenas para os melhores (pré-filtrar com numpy)
        threshold = 0.12  # 12% de similaridade
        relevant_mask = similarities > threshold
        relevant_indices = np.where(relevant_mask)[0]
        
        scores = []
        for i in relevant_indices:
            idx = valid_indices[i]
            similarity = similarities[i]
            semantic_score = similarity * 100
            
            company_row = companies_df.loc[idx]
            scores.append({
                'company_index': idx,
                'company_name': company_row.get('company_name'),
                'cae_primary_label': company_row.get('cae_primary_label'),
                'trade_description_native': company_row.get('trade_description_native'),
                'keyword_score': semantic_score,
                'matched_keywords': {},
                'match_count': 0
            })
        
        elapsed = time.time() - start
        
        if not scores:
            return pd.DataFrame()
        
        print(f"  ✓ {len(scores):,} empresas relevantes encontradas em {elapsed:.1f}s")
        
        # Ordenar por similaridade
        scored_df = pd.DataFrame(scores)
        scored_df = scored_df.sort_values('keyword_score', ascending=False)
        
        return scored_df.head(top_n).reset_index(drop=True)
    
    def _score_with_precomputed(
        self,
        companies_df: pd.DataFrame,
        incentive_title: str,
        top_n: int
    ) -> pd.DataFrame:
        """Pontua usando embeddings PRÉ-COMPUTADOS (ULTRA RÁPIDO - 60x)"""
        import time
        
        start = time.time()
        
        # Embedding do incentivo (apenas 1!)
        incentive_embedding = self.embedding_model.encode(
            [incentive_title],
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True
        )[0]
        
        # Pegar IDs das empresas filtradas
        if 'id' not in companies_df.columns:
            print("  ⚠️ Coluna 'id' não encontrada, usando índice")
            company_ids = companies_df.index.tolist()
        else:
            company_ids = companies_df['id'].tolist()
        
        # Mapear IDs para índices no cache
        valid_indices = []
        valid_company_indices = []
        
        for i, company_id in enumerate(company_ids):
            if company_id in self.id_to_index:
                cache_idx = self.id_to_index[company_id]
                valid_indices.append(cache_idx)
                valid_company_indices.append(i)
        
        if not valid_indices:
            print("  ⚠️ Nenhuma empresa encontrada no cache")
            return pd.DataFrame()
        
        # Buscar embeddings do cache (INSTANTÂNEO!)
        cached_embeddings = self.precomputed_embeddings[valid_indices]
        
        # Calcular similaridades (dot product - MUITO RÁPIDO)
        similarities = np.dot(cached_embeddings, incentive_embedding)
        
        # Criar scores
        scores = []
        threshold = 0.12
        
        for i, sim in enumerate(similarities):
            if sim > threshold:
                company_idx = valid_company_indices[i]
                company_row = companies_df.iloc[company_idx]
                
                scores.append({
                    'company_index': company_row.name,
                    'company_name': company_row.get('company_name'),
                    'cae_primary_label': company_row.get('cae_primary_label'),
                    'trade_description_native': company_row.get('trade_description_native'),
                    'keyword_score': sim * 100,
                    'matched_keywords': {},
                    'match_count': 0
                })
        
        elapsed = time.time() - start
        
        if not scores:
            return pd.DataFrame()
        
        print(f"  ⚡ {len(scores):,} empresas encontradas em {elapsed:.2f}s (cache)")
        
        # Ordenar
        scored_df = pd.DataFrame(scores)
        scored_df = scored_df.sort_values('keyword_score', ascending=False)
        
        return scored_df.head(top_n).reset_index(drop=True)
    
    def _score_with_keywords(
        self,
        companies_df: pd.DataFrame,
        title: str,
        top_n: int
    ) -> pd.DataFrame:
        """Pré-filtragem rápida por keywords + expansões semânticas"""
        incentive_keywords = self.extract_keywords(title, min_length=5)[:10]
        
        if not incentive_keywords:
            return pd.DataFrame()
        
        # Expansões semânticas para keywords comuns
        expansions = {
            'mobilidade': ['transport', 'mobility', 'taxi', 'vehicle', 'automotive', 'logistics', 'cargo', 'freight'],
            'digital': ['software', 'technology', 'tech', 'informatic', 'data', 'cloud', 'cyber'],
            'saúde': ['health', 'medical', 'hospital', 'clinic', 'pharma', 'care'],
            'energia': ['energy', 'power', 'electricity', 'renewable', 'solar', 'wind'],
            'turismo': ['tourism', 'hotel', 'hospitality', 'travel', 'accommodation'],
        }
        
        # Expandir keywords
        expanded_keywords = set(incentive_keywords)
        for kw in incentive_keywords:
            kw_lower = kw.lower()
            if kw_lower in expansions:
                expanded_keywords.update(expansions[kw_lower])
        
        scores = []
        for idx, company_row in companies_df.iterrows():
            cae = str(company_row.get('cae_primary_label', '')).lower()
            desc = str(company_row.get('trade_description_native', '')).lower()
            
            total_score = 0
            matched_terms = set()
            
            for keyword in expanded_keywords:
                kw_lower = keyword.lower()
                
                # Match no CAE (peso 4x)
                if kw_lower in cae:
                    total_score += 40
                    matched_terms.add(keyword)
                
                # Match na descrição (peso 1x)
                elif kw_lower in desc:
                    total_score += 10
                    matched_terms.add(keyword)
            
            # Bonus para múltiplos matches
            if len(matched_terms) >= 2:
                total_score *= 1.3
            
            if total_score > 5:  # Threshold mínimo
                scores.append({
                    'company_index': idx,
                    'company_name': company_row.get('company_name'),
                    'cae_primary_label': company_row.get('cae_primary_label'),
                    'trade_description_native': company_row.get('trade_description_native'),
                    'keyword_score': total_score,
                    'matched_keywords': {kw: 1 for kw in matched_terms},
                    'match_count': len(matched_terms)
                })
        
        if not scores:
            return pd.DataFrame()
        
        scored_df = pd.DataFrame(scores)
        scored_df = scored_df.sort_values('keyword_score', ascending=False)
        
        return scored_df.head(top_n).reset_index(drop=True)


class Phase3LLMReranker:
    """
    Fase 3: Re-ranking e Análise Semântica com LLM Focado
    Aplica LLM apenas às top candidatas
    """
    
    def __init__(self, api_key: Optional[str] = None, model_name: str = 'gemini-1.5-flash'):
        self.api_key = api_key
        self.model_name = model_name
        self.enabled = GEMINI_AVAILABLE and api_key is not None
        self.request_count = 0
        self.last_request_time = 0.0
        # Gemini Flash: 15 req/min = 4s/req, com 2 threads = ~2s cada
        self.min_request_interval = 2.0  # Aumentado para evitar rate limit
        self.max_retries = 5
        self.retry_backoff = [30, 45, 60, 90, 150]
        
        if self.enabled:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(model_name)
            print(f"✓ LLM Reranker inicializado: {model_name}")
        else:
            print("⚠ LLM Reranker desabilitado (sem API key ou biblioteca)")
    
    def _wait_for_rate_limit(self):
        """Garante intervalo mínimo entre chamadas ao LLM."""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.min_request_interval:
            wait_time = self.min_request_interval - elapsed
            time.sleep(wait_time)
        self.last_request_time = time.time()
        self.request_count += 1

    def _get_backoff_delay(self, attempt: int) -> float:
        if attempt < len(self.retry_backoff):
            return self.retry_backoff[attempt]
        return self.retry_backoff[-1] * 2 ** (attempt - len(self.retry_backoff) + 1)

    def build_batch_prompt(
        self,
        incentive_row: pd.Series,
        companies_df: pd.DataFrame
    ) -> str:
        """Constrói prompt para análise em LOTE de múltiplas empresas"""
        
        title = str(incentive_row.get('title', 'N/A'))
        
        # Criar lista de empresas
        companies_list = []
        for idx, company_row in companies_df.iterrows():
            companies_list.append(f"""
{idx + 1}. {company_row.get('company_name', 'N/A')}
   CAE: {company_row.get('cae_primary_label', 'N/A')}
   Atividade: {company_row.get('trade_description_native', 'N/A')}""")
        
        companies_text = "\n".join(companies_list)
        
        prompt = f"""Você é um especialista em elegibilidade para incentivos públicos portugueses. Avalie TODAS as empresas abaixo para o incentivo.

**INCENTIVO:**
Título: "{title}"
Programa: "{incentive_row.get('incentive_program', 'N/A')}"
Descrição: "{incentive_row.get('description', 'N/A')[:300]}..."

**EMPRESAS CANDIDATAS ({len(companies_df)}):**
{companies_text}

**CRITÉRIOS DE AVALIAÇÃO (RIGOROSOS):**

**Score 8-10 (EXCELENTE):** 
- Atividade PRINCIPAL da empresa é EXATAMENTE o foco do incentivo
- Match DIRETO entre setor da empresa e requisitos do incentivo
- Exemplo: Incentivo para "pesca" + Empresa de "Marine fishing" = 9/10

**Score 5-7 (BOM - ACEITÁVEL):**
- Atividade da empresa está CLARAMENTE relacionada ao incentivo
- Match SUBSTANCIAL, empresa pode se beneficiar diretamente
- Exemplo: Incentivo para "energia renovável" + Empresa de "Solar panel installation" = 6/10
- Exemplo: Incentivo para "digitalização" + Empresa de "IT consulting" = 6/10

**Score 3-4 (MARGINAL):**
- Match INDIRETO mas ainda relevante
- Empresa tem capacidade mas não é foco principal
- Exemplo: Incentivo para "turismo" + Empresa de "restaurantes" = 4/10

**Score 1-2 (INADEQUADO - REJEITAR):**
- Sem relação clara com o incentivo
- Atividades completamente diferentes
- Exemplo: Incentivo para "pesca" + Empresa de "software development" = 1/10

**INSTRUÇÕES CRÍTICAS:**
1. PRIORIZE o match de SETOR: Se o CAE está relacionado ao título do incentivo → Score mínimo 5/10
2. Empresas de "Local government" ou "Central government" → Score 1/10 (exceto se incentivo for ESPECIFICAMENTE para governo)
3. Se CAE + título têm palavras-chave em comum (ex: "construção" em ambos) → Score 6-8/10
4. Incentivos genéricos (PME, crescimento, etc.) SEM setor específico → Aceite empresas de qualquer setor (score 4-6)
5. Score 7-10 para matches perfeitos entre setor da empresa e foco do incentivo
6. Score 1-2 APENAS para matches obviamente errados (ex: pesca + software)

**Responda em JSON ARRAY com TODAS as empresas:**
[
  {{
    "empresa_numero": 1,
    "pontuacao": <1 a 10, inteiro>,
    "justificacao": "<breve explicação>"
  }},
  {{
    "empresa_numero": 2,
    "pontuacao": <1 a 10, inteiro>,
    "justificacao": "<breve explicação>"
  }}
  ...
]

IMPORTANTE: Responda APENAS o JSON array, sem texto adicional."""
        
        return prompt
    
    def parse_llm_response(self, response_text: str) -> Dict:
        """Parse da resposta do LLM"""
        try:
            # Tentar extrair JSON da resposta
            json_match = re.search(r'\{[^}]+\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            
            # Fallback: tentar parse direto
            return json.loads(response_text)
        except:
            # Fallback: retornar score neutro
            return {
                'pontuacao': 5,
                'justificacao': 'Erro ao processar resposta do LLM'
            }
    
    def rerank_companies(
        self,
        companies_df: pd.DataFrame,
        incentive_row: pd.Series
    ) -> pd.DataFrame:
        """
        Aplica LLM para re-ranking das candidatas (BATCH - 1 chamada para todas)
        
        Returns:
            DataFrame com scores LLM e justificações
        """
        if not self.enabled:
            # Sem LLM: retornar com score baseado apenas em keywords
            companies_df['llm_score'] = companies_df['keyword_score'] / 10  # Normalizar para 1-10
            companies_df['justificacao'] = 'Score baseado em correspondência de palavras-chave'
            return companies_df
        
        # OTIMIZAÇÃO: 1 ÚNICA chamada ao LLM com todas as empresas
        try:
            # Construir prompt batch
            prompt = self.build_batch_prompt(incentive_row, companies_df)
            
            # Fazer chamada única ao LLM
            for attempt in range(self.max_retries):
                try:
                    self._wait_for_rate_limit()
                    response = self.model.generate_content(prompt)
                    
                    # Parse resposta JSON array
                    response_text = response.text
                    # Extrair JSON array
                    json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
                    if not json_match:
                        raise ValueError("Resposta não contém JSON array")
                    
                    evaluations = json.loads(json_match.group())
                    
                    # Mapear avaliações para empresas
                    results = []
                    for idx, company_row in companies_df.iterrows():
                        company_dict = company_row.to_dict()
                        
                        # Encontrar avaliação correspondente (por número)
                        evaluation = next(
                            (ev for ev in evaluations if ev.get('empresa_numero') == idx + 1),
                            None
                        )
                        
                        if evaluation:
                            company_dict['llm_score'] = evaluation.get('pontuacao', 5)
                            company_dict['justificacao'] = evaluation.get('justificacao', 'N/A')
                        else:
                            # Fallback se não encontrou avaliação
                            company_dict['llm_score'] = 5
                            company_dict['justificacao'] = 'Avaliação não encontrada na resposta'
                        
                        results.append(company_dict)
                    
                    # Criar DataFrame e ordenar por score
                    reranked_df = pd.DataFrame(results)
                    reranked_df = reranked_df.sort_values('llm_score', ascending=False)
                    
                    return reranked_df.reset_index(drop=True)
                    
                except Exception as call_error:
                    error_text = str(call_error)
                    if '429' in error_text or 'quota' in error_text.lower():
                        wait_time = self._get_backoff_delay(attempt)
                        print(f"  ⚠️ Quota temporariamente excedida. Aguardando {wait_time:.0f}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise call_error
            
            # Se chegou aqui, esgotou tentativas
            raise RuntimeError("Limite de tentativas excedido")
            
        except Exception as e:
            print(f"⚠️ Erro ao processar batch com LLM: {e}")
            # Fallback: usar keyword scores
            companies_df['llm_score'] = companies_df['keyword_score'] / 10
            companies_df['justificacao'] = f'Erro no LLM (batch): {str(e)}'
            return companies_df


class OptimizedMatchingEngine:
    """
    Motor de Matching Otimizado com Funil de 3 Fases
    """
    
    def __init__(
        self,
        companies_df: pd.DataFrame,
        gemini_api_key: Optional[str] = None,
        gemini_model: str = 'gemini-2.0-flash',
        phase2_top_n: int = 10,  # OTIMIZADO: Reduzido de 20 para 10
        final_top_n: int = 5
    ):
        self.companies = companies_df.copy()
        self.phase2_top_n = phase2_top_n
        self.final_top_n = final_top_n
        
        # Inicializar fases
        self.phase1 = Phase1RigidFilter()  # Filtros rígidos
        self.phase2 = Phase2KeywordScorer()  # Embeddings semânticos
        self.phase3 = Phase3LLMReranker(api_key=gemini_api_key, model_name=gemini_model)  # LLM final
        
        print(f"✓ Optimized Matching Engine inicializado")
        print(f"  - {len(self.companies):,} empresas carregadas")
        print(f"  - Phase 2 top N: {phase2_top_n}")
        print(f"  - Final top N: {final_top_n}")
    
    def find_top_matches(
        self,
        incentive_row: pd.Series,
        verbose: bool = False
    ) -> pd.DataFrame:
        """
        Executa funil completo de 3 fases
        
        Returns:
            DataFrame com top N matches finais
        """
        start_time = time.time()
        
        if verbose:
            print(f"\n{'='*80}")
            print(f"Processando: {incentive_row.get('title', 'N/A')[:60]}...")
            print(f"{'='*80}")
        
        # FASE 1: Filtragem Rígida
        phase1_start = time.time()
        eligible_companies = self.phase1.filter_companies(self.companies, incentive_row)
        phase1_time = time.time() - phase1_start
        
        if verbose:
            print(f"\n✓ Fase 1 (Filtragem Rígida): {phase1_time:.2f}s")
            print(f"  - Total empresas: {self.phase1.stats['total_companies']:,}")
            
            # Debug: mostrar setores detectados (max 5 para não poluir)
            eligible_sectors_debug = self.phase1.extract_eligible_sectors(
                incentive_row.get('eligibility_criteria'),
                title=str(incentive_row.get('title', '')),
                description=str(incentive_row.get('description', ''))
            )
            
            if eligible_sectors_debug:
                # Mostrar apenas primeiros 5 setores + total
                sectors_list = sorted(eligible_sectors_debug)
                if len(sectors_list) <= 5:
                    print(f"  - Setores detectados: {', '.join(sectors_list)}")
                else:
                    print(f"  - Setores detectados ({len(sectors_list)}): {', '.join(sectors_list[:5])}...")
            else:
                print(f"  - ⚠ Nenhum setor detectado (aceita todas as empresas)")
            
            print(f"  - Filtradas por setor: {self.phase1.stats['filtered_by_sector']:,}")
            print(f"  - Filtradas por entidade: {self.phase1.stats['filtered_by_entity']:,}")
            print(f"  - Elegíveis: {self.phase1.stats['passed_filter']:,}")
        
        if eligible_companies.empty:
            if verbose:
                print("  ⚠ Nenhuma empresa elegível encontrada")
            return pd.DataFrame()
        
        # FASE 2: Scoring com embeddings/keywords
        phase2_start = time.time()
        top_candidates = self.phase2.score_companies(
            eligible_companies,
            incentive_row,
            top_n=self.phase2_top_n  # Usa configuração (padrão: 10)
        )
        phase2_time = time.time() - phase2_start
        
        if verbose:
            method = "Embeddings Semânticos" if self.phase2.use_embeddings else "Keywords"
            print(f"\n✓ Fase 2 ({method}): {phase2_time:.2f}s")
            print(f"  - Candidatas com score > 0: {len(top_candidates)}")
            if not top_candidates.empty:
                # Mostrar distribuição de scores
                max_score = top_candidates['keyword_score'].max()
                min_score = top_candidates['keyword_score'].min()
                avg_score = top_candidates['keyword_score'].mean()
                print(f"  - Similaridade: min={min_score:.1f}, max={max_score:.1f}, média={avg_score:.1f}")
            print(f"  - Top {min(len(top_candidates), self.phase2_top_n)} selecionadas para Fase 3")
        
        if top_candidates.empty:
            if verbose:
                print("  ⚠ Nenhuma candidata com keywords relevantes")
            return pd.DataFrame()
        
        # FASE 3: Re-ranking com LLM
        phase3_start = time.time()
        final_matches = self.phase3.rerank_companies(top_candidates, incentive_row)
        phase3_time = time.time() - phase3_start
        
        if verbose:
            print(f"\n✓ Fase 3 (Re-ranking LLM): {phase3_time:.2f}s")
            print(f"  - Empresas analisadas pelo LLM: {len(final_matches)}")
        
        # FILTRO DE QUALIDADE: Rejeitar scores inadequados (< 3.5)
        MIN_ACCEPTABLE_SCORE = 3.5  # Threshold equilibrado - aceita matches razoáveis
        
        # DEBUG: Mostrar distribuição de scores
        if not final_matches.empty:
            scores_debug = final_matches['llm_score'].describe()
            print(f"\n📊 Distribuição de scores LLM:")
            print(f"   Min: {scores_debug['min']:.1f} | Max: {scores_debug['max']:.1f} | Média: {scores_debug['mean']:.1f}")
        
        quality_matches = final_matches[final_matches['llm_score'] >= MIN_ACCEPTABLE_SCORE].copy()
        
        if len(quality_matches) < len(final_matches):
            rejected = len(final_matches) - len(quality_matches)
            print(f"  ⚠ {rejected} empresas rejeitadas (score < {MIN_ACCEPTABLE_SCORE})")
            
            # DEBUG: Mostrar as 3 piores avaliações
            if not final_matches.empty:
                worst = final_matches.nsmallest(3, 'llm_score')[['company_name', 'llm_score', 'justificacao']]
                print(f"\n🔻 Top 3 scores mais baixos:")
                for idx, row in worst.iterrows():
                    print(f"   {row['company_name'][:40]}: {row['llm_score']:.1f}/10")
                    print(f"      → {row['justificacao'][:80]}...")
        
        # Retornar top N finais (apenas com score aceitável)
        final_results = quality_matches.head(self.final_top_n).reset_index(drop=True)
        
        total_time = time.time() - start_time
        
        if verbose:
            print(f"\n✓ Total: {total_time:.2f}s")
            print(f"  - Top {len(final_results)} matches finais")
        
        return final_results
    
    def generate_full_report(
        self,
        incentives_df: pd.DataFrame,
        output_path: str = 'matching_optimized_report.csv'
    ) -> pd.DataFrame:
        """
        Gera relatório completo para todos os incentivos
        """
        all_matches = []
        
        print(f"\n{'='*80}")
        print(f"GERANDO RELATÓRIO COMPLETO")
        print(f"{'='*80}")
        print(f"Total de incentivos: {len(incentives_df)}")
        print(f"Iniciando processamento...\n")
        
        for idx, incentive_row in incentives_df.iterrows():
            if idx % 10 == 0:
                print(f"Progresso: {idx}/{len(incentives_df)} ({idx/len(incentives_df)*100:.1f}%)")
            
            matches = self.find_top_matches(incentive_row, verbose=False)
            
            if not matches.empty:
                # Adicionar informações do incentivo
                matches['incentive_id'] = incentive_row.get('incentive_project_id')
                matches['incentive_title'] = incentive_row.get('title')
                matches['incentive_program'] = incentive_row.get('incentive_program')
                
                all_matches.append(matches)
        
        if not all_matches:
            print("\n⚠ Nenhum match encontrado!")
            return pd.DataFrame()
        
        # Consolidar
        consolidated = pd.concat(all_matches, ignore_index=True)
        
        # Reordenar colunas
        column_order = [
            'incentive_id', 'incentive_title', 'incentive_program',
            'company_name', 'cae_primary_label',
            'llm_score', 'keyword_score', 'match_count',
            'justificacao', 'matched_keywords'
        ]
        
        consolidated = consolidated[[col for col in column_order if col in consolidated.columns]]
        
        # Salvar
        consolidated.to_csv(output_path, index=False, encoding='utf-8-sig')
        
        print(f"\n{'='*80}")
        print(f"✓ Relatório salvo: {output_path}")
        print(f"✓ Total de matches: {len(consolidated):,}")
        print(f"✓ Incentivos com matches: {consolidated['incentive_id'].nunique()}")
        print(f"{'='*80}")
        
        return consolidated


if __name__ == "__main__":
    print("Optimized Matching Engine - Use via import ou test script")
