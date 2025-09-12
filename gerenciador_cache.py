# gerenciador_cache.py

import json
from datetime import datetime, timedelta
import os

def salvar_cache(nome_arquivo, dados):
    """
    Salva os dados em um arquivo JSON junto com a data e hora atual.
    """
    if not os.path.exists('cache'):
        os.makedirs('cache')

    cache_data = {
        'timestamp': datetime.now().isoformat(),
        'dados': dados
    }
    
    try:
        with open(nome_arquivo, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=4)
        print(f"  -> Cache '{nome_arquivo}' salvo com sucesso.")
    except Exception as e:
        print(f"  -> ERRO ao salvar cache '{nome_arquivo}': {e}")


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
                return None
                
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"  -> ERRO ou cache inválido ao ler '{nome_arquivo}': {e}")
        return None
