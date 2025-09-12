# gerenciador_cache.py (Versão de Diagnóstico)

import json
from datetime import datetime, timedelta
import os

CACHE_DIR = 'cache'

def salvar_cache(nome_arquivo, dados):
    """
    Salva os dados em um arquivo JSON junto com a data e hora atual.
    """
    print(f"  -> Tentando salvar o cache no arquivo: {nome_arquivo}")
    
    # --- ETAPA DE DIAGNÓSTICO ---
    try:
        # 1. Verifica se o diretório 'cache' existe
        if not os.path.isdir(CACHE_DIR):
            print(f"  -> Diretório '{CACHE_DIR}' não encontrado. Tentando criar...")
            # 2. Tenta criar o diretório
            os.makedirs(CACHE_DIR)
            print(f"  -> Diretório '{CACHE_DIR}' criado com sucesso.")
        else:
            # Esta mensagem deve aparecer nas execuções seguintes
            print(f"  -> Diretório '{CACHE_DIR}' já existe.")
    except OSError as e:
        print(f"  -> ❌ ERRO CRÍTICO DE PERMISSÃO ao tentar criar o diretório '{CACHE_DIR}': {e}")
        print("  -> O bot não tem permissão para criar pastas neste ambiente. O cache não funcionará.")
        return # Impede a continuação se não conseguir criar a pasta
    except Exception as e:
        print(f"  -> ❌ ERRO INESPERADO ao verificar/criar o diretório: {e}")
        return
    # --- FIM DO DIAGNÓSTICO ---

    cache_data = {
        'timestamp': datetime.now().isoformat(),
        'dados': dados
    }
    
    try:
        with open(nome_arquivo, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=4)
        print(f"  -> ✅ Cache '{nome_arquivo}' salvo com sucesso.")
    except Exception as e:
        print(f"  -> ❌ ERRO ao salvar o arquivo de cache '{nome_arquivo}': {e}")


def ler_cache(nome_arquivo, validade_em_horas):
    """
    Lê o cache. Se o arquivo não existir ou os dados estiverem expirados,
    retorna None. Caso contrário, retorna os dados.
    """
    if not os.path.exists(nome_arquivo):
        return None

    try:
        with open(nome_arquivo, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
            
            timestamp_str = cache_data.get('timestamp')
            dados = cache_data.get('dados')
            
            if not timestamp_str or dados is None:
                return None

            timestamp_cache = datetime.fromisoformat(timestamp_str)
            
            if datetime.now() - timestamp_cache < timedelta(hours=validade_em_horas):
                print(f"  -> Dados encontrados em cache válido: '{nome_arquivo}'")
                return dados
            else:
                print(f"  -> Cache expirado para '{nome_arquivo}'.")
                os.remove(nome_arquivo)
                print(f"  -> Cache antigo '{nome_arquivo}' removido.")
                return None
                
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"  -> ERRO ou cache inválido ao ler '{nome_arquivo}': {e}")
        return None
