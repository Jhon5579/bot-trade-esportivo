# utils.py
"""
Módulo de utilitários com funções de suporte usadas em todo o projeto.
"""
import json

# Lista de arquivos que devem retornar uma lista vazia em caso de erro.
ARQUIVOS_TIPO_LISTA = [
    'apostas_pendentes.json',
    'resultados_do_dia.json',
    'historico_de_apostas.json'
]

def carregar_json(caminho_arquivo):
    """
    Carrega dados de um arquivo JSON de forma segura.

    Args:
        caminho_arquivo (str): O caminho para o arquivo JSON.

    Returns:
        (dict or list): O conteúdo do arquivo JSON. Retorna uma lista vazia ou
                        um dicionário vazio em caso de erro, dependendo do arquivo.
    """
    try:
        with open(caminho_arquivo, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Se o arquivo for um dos que guardam listas de apostas, retorna []
        if caminho_arquivo in ARQUIVOS_TIPO_LISTA:
            return []
        # Para outros arquivos (como mapas e configurações), retorna {}
        return {}

def salvar_json(dados, caminho_arquivo):
    """
    Salva dados em um arquivo JSON com formatação legível.

    Args:
        dados (dict or list): Os dados a serem salvos.
        caminho_arquivo (str): O caminho para o arquivo JSON.
    """
    with open(caminho_arquivo, 'w', encoding='utf-8') as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)