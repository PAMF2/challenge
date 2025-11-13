"""
Script para importar dados CSV para PostgreSQL
"""
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import json
from typing import Optional
import re
from tqdm import tqdm


class DatabaseImporter:
    """Importa dados CSV para PostgreSQL"""
    
    def __init__(self, connection_string: str):
        """
        Args:
            connection_string: String de conexão PostgreSQL
                Exemplo: "postgresql://user:password@localhost:5432/dbname"
        """
        self.conn_string = connection_string
        self.conn = None
        self.cursor = None
    
    def connect(self):
        """Estabelece conexão com o banco"""
        try:
            self.conn = psycopg2.connect(self.conn_string)
            self.cursor = self.conn.cursor()
            print("✓ Conectado ao PostgreSQL")
        except Exception as e:
            print(f"✗ Erro ao conectar: {e}")
            raise
    
    def disconnect(self):
        """Fecha conexão"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        print("✓ Desconectado do PostgreSQL")
    
    def create_schema(self, schema_file: Path):
        """Executa script SQL de criação do schema"""
        print(f"\n📋 Criando schema a partir de {schema_file}...")
        
        try:
            with open(schema_file, 'r', encoding='utf-8') as f:
                schema_sql = f.read()
            
            self.cursor.execute(schema_sql)
            self.conn.commit()
            print("✓ Schema criado com sucesso")
        except Exception as e:
            self.conn.rollback()
            print(f"✗ Erro ao criar schema: {e}")
            raise
    
    def classify_entity_type(self, company_name: str) -> str:
        """Classifica tipo de entidade da empresa"""
        name_lower = company_name.lower()
        
        # Entidades públicas
        public_indicators = ['município', 'câmara', 'junta', 'freguesia']
        if any(ind in name_lower for ind in public_indicators):
            return 'public'
        
        # Entidades sem fins lucrativos
        nonprofit_indicators = ['fundação', 'associação', 'irmandade', 'ipss', 
                               'misericórdia', 'centro social', 'paroquial']
        if any(ind in name_lower for ind in nonprofit_indicators):
            return 'nonprofit'
        
        # Empresas privadas
        return 'private'
    
    def extract_keywords(self, text: str) -> list:
        """Extrai keywords de um texto"""
        if not text or pd.isna(text):
            return []
        
        # Stopwords portuguesas
        stopwords = {
            'de', 'a', 'o', 'que', 'e', 'do', 'da', 'em', 'um', 'para', 'é', 'com',
            'não', 'uma', 'os', 'no', 'se', 'na', 'por', 'mais', 'as', 'dos'
        }
        
        # Normalizar e tokenizar
        text_lower = text.lower()
        words = re.findall(r'\b[a-záàâãéèêíïóôõöúçñ]+\b', text_lower)
        
        # Filtrar
        keywords = [w for w in words if len(w) >= 3 and w not in stopwords]
        
        # Retornar únicos
        return list(set(keywords))[:50]  # Limitar a 50 keywords
    
    def import_companies(self, csv_path: Path, batch_size: int = 1000):
        """Importa empresas do CSV"""
        print(f"\n📊 Importando empresas de {csv_path}...")
        
        # Ler CSV
        df = pd.read_csv(csv_path)
        print(f"   Total de empresas: {len(df):,}")
        
        # Preparar dados
        companies_data = []
        
        for idx, row in tqdm(df.iterrows(), total=len(df), desc="Processando"):
            # Classificar entidade
            entity_type = self.classify_entity_type(row.get('company_name', ''))
            
            # Texto normalizado
            normalized_text = ' '.join(filter(None, [
                str(row.get('company_name', '')),
                str(row.get('cae_primary_label', '')),
                str(row.get('trade_description_native', ''))
            ])).lower()
            
            # Extrair keywords
            keywords = self.extract_keywords(normalized_text)
            
            companies_data.append((
                idx,  # company_index
                row.get('company_name'),
                row.get('cae_primary_code') if 'cae_primary_code' in row else None,
                row.get('cae_primary_label'),
                row.get('trade_description_native'),
                row.get('website'),
                entity_type,
                normalized_text,
                keywords
            ))
        
        # Inserir em lotes
        print(f"\n   Inserindo {len(companies_data):,} empresas...")
        
        insert_query = """
            INSERT INTO companies (
                company_index, company_name, cae_primary_code, cae_primary_label,
                trade_description_native, website, entity_type, normalized_text, keywords
            ) VALUES %s
            ON CONFLICT (company_index) DO UPDATE SET
                company_name = EXCLUDED.company_name,
                cae_primary_label = EXCLUDED.cae_primary_label,
                trade_description_native = EXCLUDED.trade_description_native,
                entity_type = EXCLUDED.entity_type,
                normalized_text = EXCLUDED.normalized_text,
                keywords = EXCLUDED.keywords,
                updated_at = CURRENT_TIMESTAMP
        """
        
        try:
            for i in range(0, len(companies_data), batch_size):
                batch = companies_data[i:i+batch_size]
                execute_values(self.cursor, insert_query, batch)
                self.conn.commit()
                print(f"   ✓ Lote {i//batch_size + 1}/{(len(companies_data)-1)//batch_size + 1}")
            
            print(f"✓ {len(companies_data):,} empresas importadas")
        except Exception as e:
            self.conn.rollback()
            print(f"✗ Erro ao importar empresas: {e}")
            raise
    
    def import_incentives(self, csv_path: Path, batch_size: int = 100):
        """Importa incentivos do CSV"""
        print(f"\n📊 Importando incentivos de {csv_path}...")
        
        # Ler CSV
        df = pd.read_csv(csv_path)
        print(f"   Total de incentivos: {len(df):,}")
        
        # Preparar dados
        incentives_data = []
        
        for idx, row in tqdm(df.iterrows(), total=len(df), desc="Processando"):
            # Parse eligibility_criteria
            eligibility = row.get('eligibility_criteria')
            eligibility_json = None
            eligible_sectors = []
            entity_types = []
            
            if eligibility and not pd.isna(eligibility):
                try:
                    eligibility_json = json.loads(eligibility) if isinstance(eligibility, str) else eligibility
                    
                    # Extrair setores
                    if isinstance(eligibility_json, dict):
                        sectors = eligibility_json.get('eligibleSectors', '')
                        if isinstance(sectors, list):
                            eligible_sectors = sectors
                        elif isinstance(sectors, str) and sectors:
                            eligible_sectors = [sectors]
                        
                        # Extrair entidades
                        entities = eligibility_json.get('entities', '')
                        if isinstance(entities, list):
                            entity_types = entities
                        elif isinstance(entities, str) and entities:
                            entity_types = [entities]
                except:
                    pass
            
            # Parse all_data
            all_data = row.get('all_data')
            all_data_json = None
            if all_data and not pd.isna(all_data):
                try:
                    all_data_json = json.loads(all_data) if isinstance(all_data, str) else all_data
                except:
                    pass
            
            # Parse geographical_scope
            geo_scope = row.get('geographical_scope')
            geo_json = None
            if geo_scope and not pd.isna(geo_scope):
                try:
                    geo_json = json.loads(geo_scope) if isinstance(geo_scope, str) else geo_scope
                except:
                    pass
            
            # Extrair keywords
            text_for_keywords = ' '.join(filter(None, [
                str(row.get('title', '')),
                str(row.get('description', '')),
                str(row.get('ai_description', ''))
            ]))
            keywords = self.extract_keywords(text_for_keywords)
            
            # Parse document_urls
            doc_urls = row.get('document_urls')
            doc_urls_array = None
            if doc_urls and not pd.isna(doc_urls):
                try:
                    parsed = json.loads(doc_urls) if isinstance(doc_urls, str) else doc_urls
                    if isinstance(parsed, list):
                        doc_urls_array = [d.get('url', '') for d in parsed if isinstance(d, dict)]
                except:
                    pass
            
            incentives_data.append((
                row.get('incentive_project_id'),
                row.get('project_id'),
                row.get('incentive_program'),
                row.get('title'),
                row.get('description'),
                row.get('ai_description'),
                pd.to_datetime(row.get('date_publication')) if pd.notna(row.get('date_publication')) else None,
                pd.to_datetime(row.get('date_start')) if pd.notna(row.get('date_start')) else None,
                pd.to_datetime(row.get('date_end')) if pd.notna(row.get('date_end')) else None,
                float(row.get('total_budget')) if pd.notna(row.get('total_budget')) else None,
                row.get('status'),
                json.dumps(eligibility_json) if eligibility_json else None,
                json.dumps(geo_json) if geo_json else None,
                json.dumps(all_data_json) if all_data_json else None,
                row.get('source_link'),
                doc_urls_array,
                row.get('gcs_document_urls'),
                eligible_sectors,
                entity_types,
                keywords
            ))
        
        # Inserir em lotes
        print(f"\n   Inserindo {len(incentives_data):,} incentivos...")
        
        insert_query = """
            INSERT INTO incentives (
                incentive_project_id, project_id, incentive_program, title, description,
                ai_description, date_publication, date_start, date_end, total_budget,
                status, eligibility_criteria, geographical_scope, all_data, source_link,
                document_urls, gcs_document_urls, eligible_sectors, entity_types, keywords
            ) VALUES %s
            ON CONFLICT (incentive_project_id) DO UPDATE SET
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                ai_description = EXCLUDED.ai_description,
                eligibility_criteria = EXCLUDED.eligibility_criteria,
                eligible_sectors = EXCLUDED.eligible_sectors,
                entity_types = EXCLUDED.entity_types,
                keywords = EXCLUDED.keywords,
                updated_at = CURRENT_TIMESTAMP
        """
        
        try:
            for i in range(0, len(incentives_data), batch_size):
                batch = incentives_data[i:i+batch_size]
                execute_values(self.cursor, insert_query, batch)
                self.conn.commit()
                print(f"   ✓ Lote {i//batch_size + 1}/{(len(incentives_data)-1)//batch_size + 1}")
            
            print(f"✓ {len(incentives_data):,} incentivos importados")
        except Exception as e:
            self.conn.rollback()
            print(f"✗ Erro ao importar incentivos: {e}")
            raise
    
    def verify_import(self):
        """Verifica dados importados"""
        print("\n📊 Verificando importação...")
        
        # Contar empresas
        self.cursor.execute("SELECT COUNT(*) FROM companies")
        companies_count = self.cursor.fetchone()[0]
        print(f"   Empresas: {companies_count:,}")
        
        # Contar incentivos
        self.cursor.execute("SELECT COUNT(*) FROM incentives")
        incentives_count = self.cursor.fetchone()[0]
        print(f"   Incentivos: {incentives_count:,}")
        
        # Estatísticas de empresas por tipo
        self.cursor.execute("""
            SELECT entity_type, COUNT(*) 
            FROM companies 
            GROUP BY entity_type 
            ORDER BY COUNT(*) DESC
        """)
        print("\n   Empresas por tipo:")
        for entity_type, count in self.cursor.fetchall():
            print(f"     - {entity_type}: {count:,}")
        
        # Incentivos por programa
        self.cursor.execute("""
            SELECT incentive_program, COUNT(*) 
            FROM incentives 
            GROUP BY incentive_program 
            ORDER BY COUNT(*) DESC 
            LIMIT 5
        """)
        print("\n   Top 5 programas de incentivos:")
        for program, count in self.cursor.fetchall():
            print(f"     - {program}: {count}")
        
        print("\n✓ Verificação concluída")


def main():
    """Função principal"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Importar dados CSV para PostgreSQL")
    parser.add_argument('--db', required=True, help="String de conexão PostgreSQL")
    parser.add_argument('--create-schema', action='store_true', help="Criar schema antes de importar")
    parser.add_argument('--companies', help="Caminho para companies.csv")
    parser.add_argument('--incentives', help="Caminho para incentives.csv")
    
    args = parser.parse_args()
    
    # Inicializar importer
    importer = DatabaseImporter(args.db)
    
    try:
        importer.connect()
        
        # Criar schema se solicitado
        if args.create_schema:
            schema_file = project_root / 'database' / 'schema.sql'
            importer.create_schema(schema_file)
        
        # Importar empresas
        if args.companies:
            companies_path = Path(args.companies)
            importer.import_companies(companies_path)
        
        # Importar incentivos
        if args.incentives:
            incentives_path = Path(args.incentives)
            importer.import_incentives(incentives_path)
        
        # Verificar
        importer.verify_import()
        
    finally:
        importer.disconnect()
    
    print("\n✅ Importação concluída com sucesso!")


if __name__ == "__main__":
    main()
