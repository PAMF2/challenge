#!/usr/bin/env python
"""
🤖 SISTEMA RAG PARA CHATBOT DE INCENTIVOS
Sistema de Retrieval-Augmented Generation integrado com matching
"""

import os
import sys
import json
import time
import re
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np
from dataclasses import dataclass
import chromadb
from chromadb.config import Settings
import google.generativeai as genai
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine, text

# Configurações
CHROMA_PERSIST_DIR = "./chroma_db"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # Modelo leve e eficiente
MAX_CHUNKS_RETRIEVED = 60
SIMILARITY_THRESHOLD = 0.10  # Reduzido de 0.15 para aceitar mais resultados

@dataclass
class RAGDocument:
    """Documento para indexação RAG"""
    id: str
    content: str
    metadata: Dict[str, Any]
    doc_type: str  # 'incentive', 'company', 'match'

class RAGKnowledgeBase:
    """Base de conhecimento vetorial para RAG"""
    
    def __init__(self, persist_directory: str = CHROMA_PERSIST_DIR):
        self.persist_directory = persist_directory
        self.embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        
        # Carregar cache de embeddings de empresas (250k pré-computados)
        self.precomputed_embeddings = None
        self.precomputed_ids = None
        self.id_to_index = None
        try:
            import pickle
            self.precomputed_embeddings = np.load('embeddings_cache/company_embeddings.npy')
            self.precomputed_ids = np.load('embeddings_cache/company_ids.npy')
            with open('embeddings_cache/id_to_index.pkl', 'rb') as f:
                self.id_to_index = pickle.load(f)
            print(f"✓ Cache de embeddings carregado: {len(self.precomputed_ids):,} empresas")
        except Exception as e:
            print(f"⚠️ Cache de embeddings não disponível: {e}")
        
        # Inicializar ChromaDB
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Coleções por tipo de documento
        self.collections = {
            'incentives': self._get_or_create_collection('incentives'),
            'companies': self._get_or_create_collection('companies'),
            'matches': self._get_or_create_collection('matches')
        }
        
        print(f"✅ RAG Knowledge Base inicializada: {self.persist_directory}")
    
    def _get_or_create_collection(self, name: str):
        """Criar ou obter coleção ChromaDB"""
        try:
            return self.client.get_collection(name)
        except:
            return self.client.create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"}
            )
    
    def _chunk_text(self, text: str, max_length: int = 500) -> List[str]:
        """Dividir texto em chunks semanticamente coerentes"""
        if len(text) <= max_length:
            return [text]
        
        # Dividir por frases
        sentences = text.split('. ')
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk + sentence) <= max_length:
                current_chunk += sentence + ". "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _embed_documents(self, documents: List[str]) -> List[List[float]]:
        """Gerar embeddings com SentenceTransformer (mais rápido que ONNX default)."""
        if not documents:
            return []
        embeddings = self.embedding_model.encode(
            documents,
            batch_size=64,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True
        )
        return embeddings.tolist()
    
    def index_incentives(self, incentives_df: pd.DataFrame):
        """Indexar incentivos na base de conhecimento"""
        print("📊 Indexando incentivos...")
        
        # Limpar coleção antes de reindexar
        try:
            self.collections['incentives'].delete()
            self.collections['incentives'] = self._get_or_create_collection('incentives')
        except Exception:
            pass

        documents = []
        metadatas = []
        ids = []

        for _, incentive in incentives_df.iterrows():
            incentive_id = str(incentive.get('incentive_project_id', incentive.get('id', '')))

            main_content = f"""
            Título: {incentive.get('title', 'N/A')}
            Programa: {incentive.get('incentive_program', 'N/A')}
            Descrição: {incentive.get('description', 'N/A')}
            Critérios: {incentive.get('eligibility_criteria', 'N/A')}
            Objetivo: {incentive.get('objetivoEspecificoDesignacao', 'N/A')}
            """.strip()

            chunks = self._chunk_text(main_content)

            for i, chunk in enumerate(chunks):
                documents.append(chunk)
                ids.append(f"incentive_{incentive_id}_{i}")
                metadatas.append({
                    'doc_type': 'incentive',
                    'incentive_id': incentive_id,
                    'title': incentive.get('title', 'N/A')[:100],
                    'program': incentive.get('incentive_program', 'N/A'),
                    'chunk_index': i
                })

        chunks_added = 0
        batch_size = 500
        for start in range(0, len(documents), batch_size):
            batch_docs = documents[start:start + batch_size]
            batch_metas = metadatas[start:start + batch_size]
            batch_ids = ids[start:start + batch_size]

            self.collections['incentives'].add(
                documents=batch_docs,
                metadatas=batch_metas,
                ids=batch_ids,
                embeddings=self._embed_documents(batch_docs)
            )
            chunks_added += len(batch_docs)

        print(f"✅ {chunks_added} chunks de incentivos indexados", flush=True)

    def index_companies(self, companies_df: pd.DataFrame, chunk_size: int = 1000):
        """Indexar empresas na base de conhecimento em lotes"""
        print("🏢 Indexando empresas (lotes completos)...")

        if companies_df.empty:
            print("⚠️ Nenhuma empresa para indexar")
            return

        total = len(companies_df)

        try:
            self.collections['companies'].delete()
            self.collections['companies'] = self._get_or_create_collection('companies')
        except Exception:
            pass

        processed = 0
        for start in range(0, total, chunk_size):
            batch = companies_df.iloc[start:start + chunk_size]
            documents = []
            metadatas = []
            ids = []

            for _, company in batch.iterrows():
                company_id = str(company.get('id', ''))
                content = f"""
                Empresa: {company.get('company_name', 'N/A')}
                CAE: {company.get('cae_primary_label', 'N/A')}
                Descrição: {company.get('trade_description_native', 'N/A')}
                Tipo: {company.get('entity_type', 'N/A')}
                """.strip()

                documents.append(content)
                ids.append(f"company_{company_id}")
                metadatas.append({
                    'doc_type': 'company',
                    'company_id': company_id,
                    'company_name': company.get('company_name', 'N/A')[:100],
                    'cae_label': company.get('cae_primary_label', 'N/A')[:100]
                })

            self.collections['companies'].add(
                documents=documents,
                metadatas=metadatas,
                ids=ids,
                embeddings=self._embed_documents(documents)
            )

            processed += len(documents)
            print(f"   → {processed}/{total} empresas indexadas", flush=True)

        print(f"✅ {processed} empresas indexadas", flush=True)
    
    def index_matches(self, matches_df: pd.DataFrame):
        """Indexar resultados de matching com tratamento robusto de erros"""
        print("🎯 Indexando matches...")
        
        if matches_df.empty:
            print("⚠️ Nenhum match para indexar")
            return
        
        documents = []
        metadatas = []
        ids = []
        errors = 0
        
        for idx, match in matches_df.iterrows():
            try:
                # Validar dados essenciais
                incentive_id = str(match.get('incentive_id', ''))
                company_id = str(match.get('company_id', ''))
                
                if not incentive_id or not company_id:
                    errors += 1
                    continue
                
                match_id = f"{incentive_id}_{company_id}"
                
                # Limpar e validar scores
                keyword_score = match.get('keyword_score', 'N/A')
                llm_score = match.get('llm_score', 'N/A')
                
                # Converter scores para display
                if pd.notna(keyword_score) and str(keyword_score).replace('.', '').isdigit():
                    keyword_display = f"{float(keyword_score):.1f}"
                else:
                    keyword_display = "N/A"
                
                if pd.notna(llm_score) and str(llm_score).replace('.', '').isdigit():
                    llm_display = f"{float(llm_score):.1f}/10"
                    llm_numeric = float(llm_score)
                else:
                    llm_display = "N/A"
                    llm_numeric = 0.0
                
                # Texto estruturado do match
                content = f"""
                Match Resultado: {match.get('company_name', 'N/A')} ↔ {match.get('incentive_title', 'N/A')}
                Programa: {match.get('incentive_program', 'N/A')}
                CAE Empresa: {match.get('cae_primary_label', 'N/A')}
                Score Keywords: {keyword_display}
                Score LLM: {llm_display}
                Justificação LLM: {match.get('llm_justification', 'Sem justificação disponível')}
                Qualidade Match: {'Excelente' if llm_numeric >= 8 else 'Boa' if llm_numeric >= 6 else 'Moderada' if llm_numeric >= 4 else 'Baixa'}
                """.strip()
                
                documents.append(content)
                ids.append(f"match_{match_id}")
                metadatas.append({
                    'doc_type': 'match',
                    'incentive_id': incentive_id,
                    'company_id': company_id,
                    'company_name': str(match.get('company_name', 'N/A'))[:100],
                    'incentive_title': str(match.get('incentive_title', 'N/A'))[:100],
                    'program': str(match.get('incentive_program', 'N/A'))[:50],
                    'llm_score': llm_numeric,
                    'keyword_score': float(keyword_score) if pd.notna(keyword_score) and str(keyword_score).replace('.', '').isdigit() else 0.0
                })
                
            except Exception as e:
                errors += 1
                print(f"⚠️ Erro ao processar match {idx}: {e}")
                continue
        
        # Adicionar à coleção em lotes
        if documents:
            try:
                # Limpar coleção existente
                try:
                    self.collections['matches'].delete()
                    self.collections['matches'] = self._get_or_create_collection('matches')
                except:
                    pass
                
                # Adicionar em lotes de 100
                batch_size = 100
                for i in range(0, len(documents), batch_size):
                    batch_docs = documents[i:i+batch_size]
                    batch_metas = metadatas[i:i+batch_size]
                    batch_ids = ids[i:i+batch_size]
                    
                    self.collections['matches'].add(
                        documents=batch_docs,
                        metadatas=batch_metas,
                        ids=batch_ids,
                        embeddings=self._embed_documents(batch_docs)
                    )
                    
                    print(f"✅ {len(batch_docs)} matches indexados", flush=True)
                
                print(f"✅ {len(documents)} matches indexados com sucesso")
                if errors > 0:
                    print(f"⚠️ {errors} matches com erros foram ignorados")
                    
            except Exception as e:
                print(f"❌ Erro ao indexar matches: {e}")
        else:
            print("⚠️ Nenhum match válido para indexar")
    
    def retrieve_documents(self, query: str, max_results: int = MAX_CHUNKS_RETRIEVED) -> List[Dict[str, Any]]:
        """Recuperar documentos relevantes para uma query"""
        
        filtered_results = []
        raw_results = []
        
        # Buscar em todas as coleções
        for collection_name, collection in self.collections.items():
            try:
                results = collection.query(
                    query_texts=[query],
                    n_results=min(max_results // 3, 10),  # Distribuir entre coleções
                    include=['documents', 'metadatas', 'distances']
                )
                
                # Processar resultados
                for i, (doc, metadata, distance) in enumerate(zip(
                    results['documents'][0],
                    results['metadatas'][0],
                    results['distances'][0]
                )):
                    # Filtrar por similaridade
                    similarity = 1 - distance
                    candidate = {
                        'content': doc,
                        'metadata': metadata,
                        'similarity': similarity,
                        'collection': collection_name
                    }

                    raw_results.append(candidate)

                    if similarity >= SIMILARITY_THRESHOLD:
                        filtered_results.append(candidate)
                        
            except Exception as e:
                print(f"⚠️ Erro ao buscar em {collection_name}: {e}")
        
        if filtered_results:
            filtered_results.sort(key=lambda x: x['similarity'], reverse=True)
            return filtered_results[:max_results]

        # Fallback: usar melhores resultados mesmo abaixo do threshold
        if raw_results:
            raw_results.sort(key=lambda x: x['similarity'], reverse=True)
            return raw_results[:max_results]

        return []

    def search_collection(
        self,
        collection_name: str,
        query: str,
        limit: int,
        min_similarity: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """Buscar em uma coleção específica com fallback automático."""
        if limit <= 0:
            return []
        min_similarity = SIMILARITY_THRESHOLD if min_similarity is None else min_similarity
        collection = self.collections.get(collection_name)
        if not collection:
            return []
        try:
            results = collection.query(
                query_texts=[query],
                n_results=limit,
                include=['documents', 'metadatas', 'distances']
            )
        except Exception as e:
            print(f"⚠️ Erro ao buscar na coleção {collection_name}: {e}")
            return []

        filtered = []
        fallback = []
        for doc, metadata, distance in zip(
            results.get('documents', [[]])[0],
            results.get('metadatas', [[]])[0],
            results.get('distances', [[]])[0]
        ):
            similarity = 1 - distance
            candidate = {
                'content': doc,
                'metadata': metadata,
                'similarity': similarity,
                'collection': collection_name
            }
            fallback.append(candidate)
            if similarity >= min_similarity:
                filtered.append(candidate)

        dataset = filtered if filtered else fallback
        dataset.sort(key=lambda x: x['similarity'], reverse=True)
        return dataset[:limit]

class RAGChatbot:
    """Chatbot com RAG para incentivos"""
    
    def __init__(self, knowledge_base: RAGKnowledgeBase, gemini_api_key: str):
        self.kb = knowledge_base
        self.gemini_api_key = gemini_api_key
        self.db_engine = None
        self._setup_database_engine()
        
        # Configurar Gemini
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
            self.model = genai.GenerativeModel('gemini-2.0-flash')
            self.enabled = True
            print("✅ RAG Chatbot inicializado com Gemini 2.0 Flash")
        else:
            self.enabled = False
            print("⚠️ RAG Chatbot sem API key - modo desabilitado")

    def _setup_database_engine(self):
        db_url = os.getenv('DATABASE_URL')
        if not db_url:
            print("⚠️ DATABASE_URL não definido - matches dinâmicos indisponíveis")
            return
        try:
            self.db_engine = create_engine(db_url, pool_pre_ping=True)
        except Exception as e:
            print(f"⚠️ Erro ao inicializar engine do banco: {e}")
            self.db_engine = None

    def _analyze_query(self, query: str) -> Dict[str, Any]:
        """Identificar intenção da pergunta para orientar o retrieval."""
        text = query.lower()
        import re

        incentive_ids = re.findall(r"\b\d{3,6}\b", text)
        has_incentive_terms = any(word in text for word in [
            "incentivo", "incentivos", "programa", "apoio", "financiamento"
        ])
        has_company_terms = any(word in text for word in [
            "empresa", "empresas", "sociedade", "negócio", "cae", "setor"
        ])
        has_match_terms = any(word in text for word in [
            "match", "correspondência", "combina", "candidata", "candidatas"
        ])

        keywords = [token for token in re.split(r"[^\w]+", text) if len(token) > 3]

        intent = "general"
        if incentive_ids or has_match_terms:
            intent = "match"
        elif has_company_terms:
            intent = "company"
        elif has_incentive_terms:
            intent = "incentive"

        return {
            'intent': intent,
            'incentive_ids': list(dict.fromkeys(incentive_ids)),  # manter ordem e unicidade
            'focus_incentives': intent in {"match", "incentive", "general"},
            'focus_companies': intent in {"match", "company", "general"},
            'focus_matches': intent in {"match", "general"},
            'keywords': keywords
        }

    def _predict_retrieval_budget(self, query: str, analysis: Dict[str, Any]) -> Dict[str, int]:
        """Utilizar o máximo de documentos disponíveis por coleção quando relevantes."""
        max_incentives = 20
        max_companies = 20
        max_matches = 15

        return {
            'incentives': max_incentives if analysis['focus_incentives'] else 0,
            'companies': max_companies if analysis['focus_companies'] else 0,
            'matches': max_matches if analysis['focus_matches'] else 0,
        }

    def _extract_focus_filters(self, query: str) -> Dict[str, set[str]]:
        """Construir filtros temáticos (keywords, CAE, regiões, entidades)."""
        normalized = query.lower()
        tokens = {token for token in re.split(r"[^\w]+", normalized) if token}

        stopwords = {
            'quais', 'qual', 'quaisquer', 'para', 'como', 'sobre', 'isso', 'essa', 'este', 'esta',
            'melhor', 'melhores', 'poderia', 'poder', 'preciso', 'precisa', 'quero', 'queria',
            'incentivo', 'incentivos', 'empresa', 'empresas', 'startup', 'startups', 'qualquer',
            'melhores', 'lista', 'listar', 'ajuda', 'procurar', 'busca', 'achar', 'encontrar'
        }

        thematic_sets = {
            'energia': {
                'triggers': {
                    'energia', 'energias', 'renovavel', 'renovável', 'renovaveis', 'renováveis',
                    'solar', 'fotovoltaica', 'fotovoltaico', 'eolica', 'eólica', 'hidrogenio', 'hidrogénio',
                    'hidroeletrica', 'hidroeléctrica', 'biomassa', 'geotermica', 'geotérmica'
                },
                'expansion': {
                    'energia', 'energias', 'renovavel', 'renovável', 'renovaveis', 'renováveis',
                    'solar', 'fotovoltaica', 'fotovoltaico', 'fotovoltaicos', 'fotovoltaicas',
                    'eolica', 'eólicas', 'eólico', 'eólica', 'hidrogenio', 'hidrogénio',
                    'hidroeletrica', 'hidroeléctrica', 'biomassa', 'geotermica', 'geotérmica',
                    'autoconsumo', 'microgeracao', 'microgeração', 'eficiencia energetica', 'eficiência energética'
                }
            },
            'sustentabilidade': {
                'triggers': {
                    'sustentavel', 'sustentável', 'descarbonizacao', 'descarbonização', 'netzero', 'clima',
                    'carbono', 'hipocarbónica', 'hipocarbônica'
                },
                'expansion': {
                    'sustentavel', 'sustentável', 'descarbonizacao', 'descarbonização', 'netzero',
                    'clima', 'carbono', 'hipocarbónica', 'hipocarbônica', 'economia verde', 'economia verde'
                }
            },
            'inovacao': {
                'triggers': {
                    'inovacao', 'inovação', 'investigacao', 'investigação', 'i&d', 'iad', 'tecnologia',
                    'tecnologias', 'prototipo', 'prototipagem', 'laboratorio', 'laboratórios', 'digital'
                },
                'expansion': {
                    'inovacao', 'inovação', 'investigacao', 'investigação', 'i&d', 'iad', 'tecnologia',
                    'tecnologias', 'prototipo', 'prototipagem', 'laboratorio', 'laboratórios', 'digital',
                    'transformacao digital', 'transformação digital'
                }
            },
        }

        keywords: set[str] = set()
        matched_themes: set[str] = set()
        theme_keywords_map: Dict[str, set[str]] = {}
        for name, theme in thematic_sets.items():
            if tokens & theme['triggers']:
                matched_themes.add(name)
                theme_keywords_map[name] = theme['expansion']
                keywords.update(theme['expansion'])

        keywords.update({token for token in tokens if len(token) >= 4 and token not in stopwords})

        cae_codes = {token for token in tokens if token.isdigit() and 2 <= len(token) <= 5}
        energia_theme = thematic_sets.get('energia', {})
        energia_signals = energia_theme.get('triggers', set()) | energia_theme.get('expansion', set())
        if energia_signals and tokens & energia_signals:
            cae_codes.update({'35', '351', '352', '353', '271', '272'})

        region_map = {
            'lisboa': {'lisboa', 'lisbon', 'aml', 'area metropolitana de lisboa', 'grande lisboa'},
            'porto': {'porto', 'oporto'},
            'norte': {'norte', 'northern'},
            'centro': {'centro', 'central'},
            'alentejo': {'alentejo'},
            'algarve': {'algarve'},
            'madeira': {'madeira'},
            'acores': {'acores', 'açores', 'azores'},
        }
        regions: set[str] = set()
        for key, synonyms in region_map.items():
            if tokens & synonyms:
                regions.update(synonyms)

        entity_map = {
            'pme': {'pme', 'pmes', 'micro', 'pequena', 'pequenas', 'media', 'média', 'medias', 'médias'},
            'publica': {'publica', 'pública', 'publicas', 'públicas', 'municipio', 'município', 'municipal'},
            'privada': {'privada', 'privadas'},
            'cooperativa': {'cooperativa', 'cooperativas'},
            'associacao': {'associacao', 'associação', 'associacoes', 'associações'},
        }
        entity_types: set[str] = set()
        for synonyms in entity_map.values():
            if tokens & synonyms:
                entity_types.update(synonyms)

        return {
            'keywords': keywords,
            'cae_codes': cae_codes,
            'regions': regions,
            'entity_types': entity_types,
            'theme_names': matched_themes,
            'theme_keywords': theme_keywords_map,
        }

    def _filter_docs_by_focus(self, docs: List[Dict[str, Any]], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Aplicar filtros temáticos/estruturados aos documentos recuperados."""
        if not docs:
            return docs

        keywords = filters.get('keywords', set())
        cae_codes = filters.get('cae_codes', set())
        regions = filters.get('regions', set())
        entity_types = filters.get('entity_types', set())
        theme_names = filters.get('theme_names', set())
        theme_keywords_map = filters.get('theme_keywords', {}) or {}
        aggregated_theme_keywords = {
            keyword
            for name in theme_names
            for keyword in theme_keywords_map.get(name, set())
        }

        def metadata_values(metadata: Dict[str, Any], *fields: str) -> List[str]:
            collected: List[str] = []
            for field in fields:
                value = metadata.get(field)
                if isinstance(value, str):
                    collected.append(value.lower())
                elif isinstance(value, (list, tuple, set)):
                    collected.append(' '.join(str(item).lower() for item in value))
            return collected

        filtered_docs: List[Dict[str, Any]] = []
        for doc in docs:
            metadata = doc.get('metadata', {})
            doc_type = metadata.get('doc_type', '')
            combined_text = ' '.join([
                doc.get('content', '').lower(),
                *metadata_values(
                    metadata,
                    'title', 'description', 'program', 'company_name', 'cae_label', 'cae_primary_label',
                    'keywords', 'eligibleSectors', 'matched_keywords', 'incentive_program', 'entity_type',
                    'regiao', 'regions', 'geographic_scope', 'location', 'region'
                )
            ])

            # Keywords check
            keyword_hits = sum(1 for keyword in keywords if keyword in combined_text)
            if keywords and not keyword_hits:
                continue

            theme_keyword_hits = sum(1 for keyword in aggregated_theme_keywords if keyword in combined_text)
            if (
                doc_type in {'incentive', 'incentive_db'}
                and aggregated_theme_keywords
                and theme_keyword_hits == 0
            ):
                continue

            # CAE check
            if cae_codes:
                cae_fields = metadata_values(
                    metadata,
                    'cae_primary_code', 'cae_code', 'cae', 'cae_primary_label', 'sector_code'
                )
                cae_match_count = 0
                for code in cae_codes:
                    prefix = code.lower()
                    if any(prefix in field for field in cae_fields) or f"cae {prefix}" in combined_text:
                        cae_match_count += 1
                if not cae_match_count:
                    continue
            else:
                cae_match_count = 0

            # Region check
            if regions:
                region_fields = metadata_values(
                    metadata,
                    'regiao', 'regions', 'geographic_scope', 'location', 'region', 'eligible_regions'
                )
                region_matches = {
                    region
                    for region in regions
                    if any(region in field for field in region_fields)
                }
                if not region_matches:
                    continue
            else:
                region_matches = set()

            # Entity type check
            if entity_types:
                entity_fields = metadata_values(
                    metadata,
                    'entity_type', 'tipo_de_promotor', 'eligible_entities', 'beneficiaries', 'applicant_partnership'
                )
                entity_matches = {
                    ent
                    for ent in entity_types
                    if any(ent in field for field in entity_fields)
                }
                if not entity_matches:
                    continue
            else:
                entity_matches = set()

            if (
                doc_type not in {'incentive', 'incentive_db'}
                and keywords
                and keyword_hits < 2
                and cae_match_count == 0
                and not region_matches
                and not entity_matches
            ):
                continue

            score = (
                float(keyword_hits)
                + 1.2 * float(theme_keyword_hits)
                + 2.5 * float(cae_match_count)
                + 1.8 * float(len(region_matches))
                + 1.5 * float(len(entity_matches))
            )
            if metadata.get('similarity') is not None:
                try:
                    score += float(metadata['similarity'])
                except (TypeError, ValueError):
                    pass

            doc['_focus_score'] = round(score, 3)
            filtered_docs.append(doc)

        if filtered_docs:
            filtered_docs.sort(key=lambda item: item.get('_focus_score', 0.0), reverse=True)
            return filtered_docs

        return docs

    def _retrieve_context(self, query: str, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Trazer documentos relevantes com base na intenção."""
        docs: List[Dict[str, Any]] = []

        budgets = self._predict_retrieval_budget(query, analysis)
        incentives_limit = budgets['incentives']
        companies_limit = budgets['companies']
        matches_limit = budgets['matches']

        focus_filters = self._extract_focus_filters(query)

        incentive_docs = self.kb.search_collection('incentives', query, incentives_limit)
        incentive_docs = self._filter_docs_by_focus(incentive_docs, focus_filters)
        docs.extend(incentive_docs)

        if analysis['focus_companies']:
            company_docs = self.kb.search_collection('companies', query, companies_limit, min_similarity=0.1)
            company_docs = self._filter_docs_by_focus(company_docs, focus_filters)
            docs.extend(company_docs)

        if analysis['focus_matches']:
            match_docs = self.kb.search_collection('matches', query, matches_limit, min_similarity=0.1)
            match_docs = self._filter_docs_by_focus(match_docs, focus_filters)
            docs.extend(match_docs)

        return self._deduplicate_docs(docs)

    def _deduplicate_docs(self, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        unique_docs = []
        for doc in docs:
            metadata = doc.get('metadata', {})
            key = (
                doc.get('collection'),
                metadata.get('incentive_id'),
                metadata.get('company_id'),
                metadata.get('doc_type'),
                metadata.get('chunk_index')
            )
            if key not in seen:
                seen.add(key)
                unique_docs.append(doc)
        return unique_docs

    def _discover_cae_codes(self, search_terms: List[str]) -> List[str]:
        """Descobrir códigos CAE relevantes buscando em múltiplos campos."""
        if not self.db_engine or not search_terms:
            return []
        
        try:
            with self.db_engine.connect() as conn:
                # Buscar CAEs em: label, description, keywords (array convertido para texto)
                conditions = []
                for term in search_terms:
                    if len(term) > 2:  # Ignorar termos muito curtos
                        term_lower = term.lower()
                        conditions.append(f"""(
                            LOWER(cae_primary_label) LIKE '%{term_lower}%' OR
                            LOWER(trade_description_native) LIKE '%{term_lower}%' OR
                            LOWER(array_to_string(keywords, ' ')) LIKE '%{term_lower}%'
                        )""")
                
                if not conditions:
                    return []
                
                where_clause = ' OR '.join(conditions)
                query = text(f"""
                    SELECT cae_primary_code, cae_primary_label, COUNT(*) as count
                    FROM companies
                    WHERE ({where_clause}) 
                      AND cae_primary_code IS NOT NULL 
                      AND cae_primary_label IS NOT NULL
                    GROUP BY cae_primary_code, cae_primary_label
                    ORDER BY count DESC
                    LIMIT 15
                """)
                
                rows = conn.execute(query).fetchall()
                
                # Pegar apenas os 2 primeiros dígitos do CAE (categoria principal)
                cae_codes = []
                for row in rows:
                    if row.cae_primary_code and len(row.cae_primary_code) >= 2:
                        cae_codes.append(row.cae_primary_code[:2])
                
                # Remover duplicatas mantendo ordem
                cae_codes = list(dict.fromkeys(cae_codes))
                
                if cae_codes:
                    # Mostrar os 3 CAEs mais relevantes com labels
                    top_labels = []
                    seen_codes = set()
                    for row in rows:
                        if row.cae_primary_code and row.cae_primary_code[:2] not in seen_codes:
                            top_labels.append(f"{row.cae_primary_code[:2]}xx: {row.cae_primary_label[:40]}")
                            seen_codes.add(row.cae_primary_code[:2])
                            if len(top_labels) >= 3:
                                break
                    
                    print(f"🔍 CAEs descobertos: {', '.join(top_labels)}...")
                
                return cae_codes[:10]  # Limitar a 10 CAEs principais
                
        except Exception as e:
            print(f"⚠️ Erro ao descobrir CAEs: {e}")
            return []
    
    def _search_companies_by_cae(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Buscar empresas usando embeddings pré-computados (CACHE ULTRA-RÁPIDO)."""
        if self.kb.precomputed_embeddings is None or not self.db_engine:
            print("⚠️ Cache de embeddings ou DB não disponível")
            return []
        
        try:
            # 1. Calcular embedding da query
            print(f"🔍 Busca semântica com cache (250k empresas): '{query[:50]}...'")
            query_embedding = self.kb.embedding_model.encode(
                [query],
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False
            )[0]
            
            # 2. Calcular similaridades com TODAS as empresas (instantâneo!)
            similarities = np.dot(self.kb.precomputed_embeddings, query_embedding)
            
            # 3. Pegar top empresas por similaridade
            top_indices = np.argsort(similarities)[::-1][:limit * 2]
            top_scores = similarities[top_indices]
            top_ids = self.kb.precomputed_ids[top_indices]
            
            print(f"📊 Top similaridades: min={top_scores[-1]:.3f}, max={top_scores[0]:.3f}")
            
            # 4. Buscar detalhes das empresas no banco
            with self.db_engine.connect() as conn:
                # Usar parametrização segura ao invés de f-string
                placeholders = ','.join([':id' + str(i) for i in range(len(top_ids))])
                params = {f'id{i}': int(top_ids[i]) for i in range(len(top_ids))}
                params['limit'] = limit
                
                query_sql = text(f"""
                    SELECT id, company_name, cae_primary_code, cae_primary_label, 
                           trade_description_native, entity_type, keywords
                    FROM companies
                    WHERE id IN ({placeholders})
                    LIMIT :limit
                """)
                
                rows = conn.execute(query_sql, params).fetchall()
                print(f"📊 {len(rows)} empresas recuperadas do cache")
                
                company_docs = []
                for row in rows:
                    # Converter keywords array para string se necessário
                    keywords_str = row.keywords
                    if isinstance(keywords_str, list):
                        keywords_str = ', '.join(keywords_str)
                    
                    content = (
                        f"Empresa: {row.company_name}\n"
                        f"CAE Primário: {row.cae_primary_label or 'N/A'}\n"
                        f"Código CAE: {row.cae_primary_code or 'N/A'}\n"
                        f"Tipo de Entidade: {row.entity_type or 'N/A'}\n"
                        f"Palavras-chave: {keywords_str or 'N/A'}\n"
                        f"Descrição completa: {row.trade_description_native or 'N/A'}"
                    )
                    company_docs.append({
                        'content': content,
                        'metadata': {
                            'doc_type': 'company_db',
                            'company_id': str(row.id),
                            'company_name': row.company_name[:100],
                            'cae_primary_label': row.cae_primary_label,
                            'cae_primary_code': row.cae_primary_code,
                        },
                        'similarity': 0.85,  # Score alto para matches diretos de CAE
                        'collection': 'companies_db'
                    })
                
                return company_docs
                
        except Exception as e:
            print(f"⚠️ Erro ao buscar empresas com cache: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _augment_with_db_details(self, retrieved_docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Adicionar detalhes atualizados diretamente do banco para empresas e incentivos."""
        if not self.db_engine:
            return retrieved_docs

        additional_docs: List[Dict[str, Any]] = []
        seen_company_ids = set()
        seen_incentive_ids = set()

        try:
            with self.db_engine.connect() as conn:
                for doc in retrieved_docs:
                    metadata = doc.get('metadata', {})
                    doc_type = metadata.get('doc_type')

                    if doc_type == 'company':
                        company_id = metadata.get('company_id')
                        if company_id and company_id not in seen_company_ids:
                            row = conn.execute(
                                text(
                                    """
                                    SELECT company_name, cae_primary_label, trade_description_native,
                                           entity_type, keywords
                                    FROM companies
                                    WHERE id = :company_id
                                    """
                                ),
                                {"company_id": int(company_id)}
                            ).fetchone()

                            if row:
                                seen_company_ids.add(company_id)
                                content = (
                                    f"Empresa: {row.company_name}\n"
                                    f"CAE Primário: {row.cae_primary_label or 'N/A'}\n"
                                    f"Tipo de Entidade: {row.entity_type or 'N/A'}\n"
                                    f"Palavras-chave: {row.keywords or 'N/A'}\n"
                                    f"Descrição completa: {row.trade_description_native or 'N/A'}"
                                )
                                additional_docs.append({
                                    'content': content,
                                    'metadata': {
                                        'doc_type': 'company_db',
                                        'company_id': company_id,
                                        'company_name': row.company_name[:100],
                                        'cae_primary_label': row.cae_primary_label,
                                    },
                                    'similarity': doc.get('similarity', 0.9),
                                    'collection': 'companies_db'
                                })

                    elif doc_type == 'incentive':
                        incentive_id = metadata.get('incentive_id')
                        if incentive_id and incentive_id not in seen_incentive_ids:
                            row = conn.execute(
                                text(
                                    """
                                    SELECT title, description, eligibility_criteria,
                                           incentive_program, status
                                    FROM incentives
                                    WHERE incentive_project_id = :incentive_id
                                    """
                                ),
                                {"incentive_id": incentive_id}
                            ).fetchone()

                            if row:
                                seen_incentive_ids.add(incentive_id)
                                content = (
                                    f"Incentivo: {row.title}\n"
                                    f"Programa: {row.incentive_program or 'N/A'}\n"
                                    f"Status: {row.status or 'N/A'}\n"
                                    f"Critérios: {row.eligibility_criteria or 'N/A'}\n"
                                    f"Descrição: {row.description or 'N/A'}"
                                )
                                additional_docs.append({
                                    'content': content,
                                    'metadata': {
                                        'doc_type': 'incentive_db',
                                        'incentive_id': incentive_id,
                                        'title': row.title[:100],
                                        'program': row.incentive_program,
                                    },
                                    'similarity': doc.get('similarity', 0.9),
                                    'collection': 'incentives_db'
                                })
        except Exception as e:
            print(f"⚠️ Erro ao buscar detalhes no banco: {e}")

        if additional_docs:
            retrieved_docs = self._deduplicate_docs(retrieved_docs + additional_docs)

        return retrieved_docs
    
    def _create_rag_prompt(
        self,
        query: str,
        retrieved_docs: List[Dict[str, Any]],
        history: Optional[List[Tuple[str, str]]] = None
    ) -> str:
        """Criar prompt RAG otimizado com contexto estruturado"""
        
        # Organizar documentos por tipo
        context_sections = {
            'incentives': [],
            'companies': [],
            'matches': [],
            'company_db': [],
            'incentive_db': []
        }
        
        for doc in retrieved_docs:
            doc_type = doc['metadata'].get('doc_type', 'unknown')
            if doc_type in context_sections:
                context_sections[doc_type].append(doc)
        
        # Construir contexto formatado estruturado
        context = "[INÍCIO DO CONTEXTO]\n\n"
        
        # Seção de Incentivos
        if context_sections['incentives']:
            context += "--- INFORMAÇÕES DE INCENTIVOS ---\n"
            for i, doc in enumerate(context_sections['incentives'][:8], 1):
                metadata = doc['metadata']
                incentive_id = metadata.get('incentive_id', 'N/A')
                title = metadata.get('title', 'N/A')
                program = metadata.get('program', 'N/A')
                
                context += f"[Incentivo {incentive_id}]: {title}\n"
                context += f"  Programa: {program}\n"
                context += f"  Detalhes: {doc['content'][:300]}...\n\n"
        
        # Seção de Empresas
        if context_sections['companies']:
            context += "--- INFORMAÇÕES DE EMPRESAS ---\n"
            for i, doc in enumerate(context_sections['companies'][:6], 1):
                metadata = doc['metadata']
                company_id = metadata.get('company_id', 'N/A')
                company_name = metadata.get('company_name', 'N/A')
                cae_label = metadata.get('cae_label', 'N/A')
                
                context += f"[Empresa {company_id}]: {company_name}\n"
                context += f"  CAE Primário: {cae_label}\n"
                context += f"  Descrição: {doc['content'][:200]}...\n\n"

        if context_sections['company_db']:
            context += "--- DETALHES COMPLETOS DE EMPRESAS (BASE DE DADOS) ---\n"
            for i, doc in enumerate(context_sections['company_db'][:6], 1):
                metadata = doc['metadata']
                company_id = metadata.get('company_id', 'N/A')
                company_name = metadata.get('company_name', 'N/A')
                context += f"[Empresa DB {company_id}]: {company_name}\n"
                context += f"  Dados detalhados:\n    {doc['content']}\n\n"

        if context_sections['incentive_db']:
            context += "--- DETALHES COMPLETOS DE INCENTIVOS (BASE DE DADOS) ---\n"
            for i, doc in enumerate(context_sections['incentive_db'][:6], 1):
                metadata = doc['metadata']
                incentive_id = metadata.get('incentive_id', 'N/A')
                title = metadata.get('title', 'N/A')
                context += f"[Incentivo DB {incentive_id}]: {title}\n"
                context += f"  Dados detalhados:\n    {doc['content']}\n\n"
        
        # Seção de Matches (mais importante)
        if context_sections['matches']:
            context += "--- RESULTADOS DO MATCHING (EMPRESA + INCENTIVO) ---\n"
            for i, doc in enumerate(context_sections['matches'][:6], 1):
                metadata = doc['metadata']
                incentive_id = metadata.get('incentive_id', 'N/A')
                company_name = metadata.get('company_name', 'N/A')
                llm_score = metadata.get('llm_score', 0)
                
                context += f"[Match {i}]: {company_name} <-> Incentivo {incentive_id}\n"
                context += f"  Score LLM: {llm_score}/10\n"
                context += f"  Análise Completa: {doc['content']}\n\n"
        
        context += "[FIM DO CONTEXTO]\n"
        
        conversation_snippet = ""
        if history:
            formatted_turns = []
            for user_text, assistant_text in history[-3:]:  # usar últimas 3 interações
                formatted_turns.append(
                    f"Utilizador: {user_text}\nAssistente: {assistant_text}"
                )
            conversation_snippet = "\n\n**Resumo das últimas interações:**\n" + "\n".join(formatted_turns)
        
        # Template do prompt otimizado
        prompt = f"""Você é um consultor especializado em incentivos e setores empresariais portugueses. Use criteriosamente o contexto fornecido para responder à pergunta do utilizador.

**Contexto Recuperado:**
---
{context}
---

**Pergunta do Utilizador:**
{query}{conversation_snippet}

**Instruções para Resposta:**

1. **Utilize os dados das empresas** (incluindo os detalhes extraídos da base) para sugerir e justificar respostas. Aponte explicitamente CAE, descrição da atividade, palavras-chave e qualquer dado adicional relevante.

2. **Relacione incentivos relevantes** sempre que possível, destacando critérios, programas e alinhamento com o setor mencionado pelo utilizador.

3. **Indique candidatas adequadas** mesmo na ausência de matches pré-calculados, explicando por que cada empresa parece promissora para o contexto da pergunta.

4. Se não houver informação suficiente para recomendar empresas específicas, explique claramente o que está em falta e sugira quais dados seriam necessários.

5. A resposta deve ser em português, estruturada de forma clara (parágrafos curtos ou listas) e baseada exclusivamente no contexto fornecido. Não invente informação externa.

**RESPOSTA:**"""

        return prompt
    
    def _expand_query_with_llm(self, query: str) -> Dict[str, Any]:
        """Usar LLM para entender e expandir a query antes do retrieval."""
        if not self.enabled:
            return {'enhanced_query': query, 'search_terms': [], 'cae_codes': [], 'sectors': []}
        
        expansion_prompt = f"""Você é um especialista em análise de queries para busca de incentivos e empresas portuguesas.

**Query Original:**
"{query}"

**Tarefa:**
Analise a query e retorne um JSON com:
1. `intent`: tipo de busca ("incentivo", "empresa", "setor", "match", "geral")
2. `enhanced_query`: query reformulada com termos mais específicos para busca semântica
3. `search_terms`: lista de termos-chave relevantes (português)
4. `cae_codes`: códigos CAE relevantes - SEMPRE inclua os códigos numéricos quando o setor for mencionado
5. `sectors`: setores específicos mencionados ou inferidos
6. `regions`: regiões geográficas mencionadas
7. `entity_types`: tipos de entidade (PME, startup, pública, privada, etc.)

**TABELA DE CAE OBRIGATÓRIA - Use estes códigos:**
- Eletricidade/energia/elétrica: ["35", "351", "352", "353"]
- Manufatura/produção/industrial: ["10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31", "32", "33"]
- Consultoria/gestão: ["70", "71", "62"]
- Tecnologia/software/TI: ["62", "63"]
- Construção/obras: ["41", "42", "43"]
- Comércio: ["45", "46", "47"]
- Saúde: ["86", "87", "88"]
- Educação: ["85"]
- Agricultura: ["01", "02", "03"]
- Turismo/hotelaria: ["55", "56", "79"]

**EXEMPLOS:**
Query: "qual melhor empresa de eletricidade?"
→ cae_codes: ["35", "351", "352", "353"]

Query: "empresas de produção de manufaturados"
→ cae_codes: ["10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31", "32", "33"]

**Formato de Resposta (JSON apenas):**
{{
  "intent": "empresa",
  "enhanced_query": "empresa setor eletricidade produção distribuição energia",
  "search_terms": ["eletricidade", "energia", "produção", "distribuição"],
  "cae_codes": ["35", "351", "352", "353"],
  "sectors": ["energia", "eletricidade"],
  "regions": [],
  "entity_types": []
}}

IMPORTANTE: Sempre inclua cae_codes quando a query mencionar um setor específico. Responda APENAS com o JSON, sem texto adicional."""
        
        try:
            response = self.model.generate_content(expansion_prompt)
            # Extrair JSON da resposta
            import json
            import re
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response.text, re.DOTALL)
            if json_match:
                expansion = json.loads(json_match.group())
                print(f"🧠 Query expandida: {expansion.get('enhanced_query', query)[:80]}...")
                if expansion.get('cae_codes'):
                    print(f"📋 CAEs identificados: {expansion['cae_codes']}")
                else:
                    print(f"⚠️ Nenhum CAE identificado pela LLM")
                return expansion
        except Exception as e:
            print(f"⚠️ Erro ao expandir query: {e}")
        
        # Fallback para query original
        return {
            'intent': 'geral',
            'enhanced_query': query,
            'search_terms': [],
            'cae_codes': [],
            'sectors': [],
            'regions': [],
            'entity_types': []
        }
    
    def chat(
        self,
        query: str,
        history: Optional[List[Tuple[str, str]]] = None
    ) -> Dict[str, Any]:
        """Processar pergunta do utilizador com RAG"""
        
        if not self.enabled:
            return {
                'response': "❌ Chatbot não disponível (sem API key)",
                'retrieved_docs': [],
                'processing_time': 0
            }
        
        start_time = time.time()
        
        try:
            # Passo 0: Expansão da query com LLM
            print(f"🔍 Analisando query: {query[:50]}...")
            expansion = self._expand_query_with_llm(query)
            
            # Usar query expandida para busca
            search_query = expansion.get('enhanced_query', query)
            
            # Passo 1: Recuperação com query expandida
            print(f"🔍 Recuperando documentos para: {search_query[:50]}...")
            analysis = self._analyze_query(search_query)
            
            # Enriquecer análise com informações da LLM
            if expansion.get('cae_codes'):
                analysis['cae_codes'] = expansion['cae_codes']
            if expansion.get('sectors'):
                analysis['sectors'] = expansion['sectors']
            
            retrieved_docs = self._retrieve_context(search_query, analysis)
            
            # Descobrir CAEs dinamicamente se for uma busca de empresas
            cae_codes_to_search = []
            
            # 1. CAEs identificados pela LLM (tabela fixa)
            if expansion.get('cae_codes'):
                cae_codes_to_search.extend(expansion['cae_codes'])
                print(f"📋 CAEs da tabela LLM: {expansion['cae_codes']}")
            
            # 2. CAEs descobertos dinamicamente no banco (SEMPRE para maior cobertura)
            if expansion.get('search_terms') or expansion.get('sectors'):
                discovery_terms = expansion.get('search_terms', []) + expansion.get('sectors', [])
                discovered_caes = self._discover_cae_codes(discovery_terms)
                if discovered_caes:
                    cae_codes_to_search.extend(discovered_caes)
            
            # Buscar empresas usando cache de embeddings (sempre)
            print(f"🎯 Buscando empresas com embeddings...")
            cae_companies = self._search_companies_by_cae(search_query, limit=20)
            
            # Remover empresas da busca vetorial e usar apenas as de cache
            retrieved_docs = [doc for doc in retrieved_docs if doc.get('metadata', {}).get('doc_type') not in {'company', 'company_db'}]
            retrieved_docs.extend(cae_companies)
            print(f"✅ {len(cae_companies)} empresas encontradas via cache")
            
            retrieved_docs = self._augment_with_db_details(retrieved_docs)

            # Limitar quantidade total
            retrieved_docs = sorted(
                retrieved_docs,
                key=lambda x: x.get('similarity', 0),
                reverse=True
            )[:MAX_CHUNKS_RETRIEVED]
            
            if not retrieved_docs:
                return {
                    'response': "❓ Não encontrei informação relevante para a tua pergunta.",
                    'retrieved_docs': [],
                    'processing_time': time.time() - start_time
                }
            
            # Debug: mostrar distribuição de tipos de documentos
            doc_types = {}
            for doc in retrieved_docs:
                doc_type = doc.get('metadata', {}).get('doc_type', 'unknown')
                doc_types[doc_type] = doc_types.get(doc_type, 0) + 1
            print(f"📊 Distribuição de documentos: {doc_types}")
            
            # Passo 2: Geração com rate limiting
            print(f"🤖 Gerando resposta com {len(retrieved_docs)} documentos...")
            prompt = self._create_rag_prompt(query, retrieved_docs, history)
            
            # Rate limiting com retry exponencial (DELAYS AUMENTADOS)
            max_retries = 3
            base_delay = 8  # Aumentado de 2s para 8s
            
            for attempt in range(max_retries):
                try:
                    response = self.model.generate_content(prompt)
                    break
                except Exception as e:
                    if "429" in str(e) or "quota" in str(e).lower():
                        if attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt)
                            print(f"⏳ Rate limit atingido, aguardando {delay}s...")
                            time.sleep(delay)
                            continue
                    raise e
            
            processing_time = time.time() - start_time
            
            return {
                'response': response.text,
                'retrieved_docs': retrieved_docs,
                'processing_time': processing_time,
                'num_docs_used': len(retrieved_docs)
            }
            
        except Exception as e:
            return {
                'response': f"❌ Erro ao processar pergunta: {str(e)}",
                'retrieved_docs': [],
                'processing_time': time.time() - start_time
            }

def initialize_rag_system(db_url: str, gemini_api_key: str) -> Tuple[RAGKnowledgeBase, RAGChatbot]:
    """Inicializar sistema RAG completo"""
    
    print("🚀 Inicializando Sistema RAG...")
    
    # Criar base de conhecimento
    kb = RAGKnowledgeBase()
    
    # Verificar se já está indexada
    try:
        incentives_count = kb.collections['incentives'].count()
        companies_count = kb.collections['companies'].count()
        matches_count = kb.collections['matches'].count()
        
        if incentives_count > 0 or companies_count > 0 or matches_count > 0:
            print(f"📚 Base existente: {incentives_count} incentivos, {companies_count} empresas, {matches_count} matches")
        else:
            print("📚 Base vazia - será necessário indexar dados")
            
    except Exception as e:
        print(f"⚠️ Erro ao verificar base: {e}")
    
    # Criar chatbot
    chatbot = RAGChatbot(kb, gemini_api_key)
    
    return kb, chatbot

if __name__ == "__main__":
    # Teste básico
    from dotenv import load_dotenv
    load_dotenv('../config.env')
    
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    
    kb, chatbot = initialize_rag_system("", GEMINI_API_KEY)
    
    # Teste de chat
    if chatbot.enabled:
        result = chatbot.chat("Quais são os melhores incentivos para empresas de tecnologia?")
        print(f"\n🤖 Resposta: {result['response']}")
        print(f"⏱️ Tempo: {result['processing_time']:.1f}s")
