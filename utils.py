import json
# Importamos o dicionário aqui para a função poder usá-lo
from config import NIVEIS_DE_RISCO_ODDS 

def carregar_json(nome_arquivo):
    """Carrega dados de um arquivo JSON."""
    try:
        with open(nome_arquivo, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Retorna um dicionário vazio se o arquivo não existir ou for inválido
        return {}

def salvar_json(dados, nome_arquivo):
    """Salva dados em um arquivo JSON."""
    with open(nome_arquivo, 'w', encoding='utf-8') as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)

def classificar_odd(odd_valor):
    """
    Recebe um valor de odd e retorna sua classificação de risco com base no dicionário do config.
    """
    if not isinstance(odd_valor, (int, float)):
        return "Indefinido"

    for nome_risco, faixa in NIVEIS_DE_RISCO_ODDS.items():
        if faixa["min"] <= odd_valor <= faixa["max"]:
            # Retorna o nome formatado, ex: "SUPER FAVORITO"
            return nome_risco.replace("_", " ") 

    return "Fora da Faixa"