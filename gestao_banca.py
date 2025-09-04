# --- gestao_banca.py ---
# Este script contém todas as funções para gerir a nossa banca.

import json
# IMPORTAÇÃO DO NOVO MÓDULO DE UTILITÁRIOS
from utils import salvar_json

# O nome do nosso ficheiro de banca fica definido aqui
ARQUIVO_GESTAO_BANCA = 'gestao_banca.json'

def carregar_banca():
    """
    Carrega os dados da gestão de banca do ficheiro JSON.
    Se o ficheiro não existir ou estiver inválido, cria um novo com valores padrão.
    """
    try:
        with open(ARQUIVO_GESTAO_BANCA, 'r', encoding='utf-8') as f:
            banca = json.load(f)
        # Garante que o ficheiro tem a estrutura mínima
        if "banca_atual" not in banca:
            raise json.JSONDecodeError("Estrutura do JSON inválida", "", 0)
        return banca
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"  -> ⚠️ AVISO: Ficheiro '{ARQUIVO_GESTAO_BANCA}' não encontrado ou inválido. A criar um novo.")
        banca_padrao = {
            "banca_inicial": 100.0,
            "banca_atual": 100.0,
            "stake_padrao_percentual": 5.0,
            "perda_a_recuperar": 0.0
        }
        # Salva o ficheiro padrão para garantir que ele exista na próxima vez
        # Usa a nova função centralizada de salvar_json
        salvar_json(banca_padrao, ARQUIVO_GESTAO_BANCA)
        return banca_padrao

# A função salvar_banca() foi removida pois agora usamos salvar_json() de utils.py

def calcular_stake(odd, dados_banca):
    """
    Calcula o valor da aposta (stake).
    Implementa um sistema de recuperação para perdas.
    """
    stake_padrao_percentual = dados_banca.get('stake_padrao_percentual', 5.0)
    banca_inicial = dados_banca.get('banca_inicial', 100.0)
    perda_a_recuperar = dados_banca.get('perda_a_recuperar', 0.0)

    stake_padrao = banca_inicial * (stake_padrao_percentual / 100.0)

    # Se não há perdas para recuperar, usa a stake padrão
    if perda_a_recuperar == 0:
        return round(stake_padrao, 2)

    # Lógica de recuperação (Martingale modificado)
    # Tenta recuperar a perda + o lucro de uma aposta padrão
    lucro_necessario = perda_a_recuperar + (stake_padrao * (odd - 1))

    if odd <= 1.0: # Evita divisão por zero ou stakes negativas
        return round(stake_padrao, 2)

    stake_necessaria = lucro_necessario / (odd - 1)

    # Limita a stake de recuperação para não quebrar a banca (ex: máximo 3x a stake padrão)
    stake_maxima_recuperacao = stake_padrao * 3
    stake_final = min(stake_necessaria, stake_maxima_recuperacao)

    return round(stake_final, 2)


def registrar_resultado(aposta, resultado_final, placar_casa, placar_fora):
    """
    Atualiza a banca com base no resultado de uma aposta ('GREEN' ou 'RED')
    e retorna a mensagem formatada para o Telegram.
    """
    banca = carregar_banca()
    lucro_ou_prejuizo = 0
    stake_aposta = aposta.get('stake', 0)
    odd_aposta = aposta.get('odd', 0)

    if resultado_final == "GREEN":
        lucro = stake_aposta * (odd_aposta - 1)
        lucro_ou_prejuizo = lucro
        banca['banca_atual'] += lucro
        # Zera as perdas a recuperar pois tivemos um Green
        banca['perda_a_recuperar'] = 0.0
    else: # RED
        prejuizo = stake_aposta
        lucro_ou_prejuizo = -prejuizo
        banca['banca_atual'] -= prejuizo
        banca['perda_a_recuperar'] += prejuizo

    # Arredonda os valores para evitar problemas com casas decimais
    banca['banca_atual'] = round(banca['banca_atual'], 2)
    banca['perda_a_recuperar'] = round(banca['perda_a_recuperar'], 2)

    salvar_json(banca, ARQUIVO_GESTAO_BANCA)
    print(f"  -> 💾 Banca salva com sucesso! Saldo R$ {banca['banca_atual']:.2f}, A recuperar R$ {banca['perda_a_recuperar']:.2f}")

    emoji_resultado = "✅" if resultado_final == "GREEN" else "🔴"
    sinal_lucro = "+" if lucro_ou_prejuizo >= 0 else ""

    # Monta a mensagem para o Telegram
    mercado_str = aposta['mercado']
    if "Mais de" in mercado_str or "Menos de" in mercado_str:
        mercado_str += " Gols"

    linhas_mensagem = [
        f"{emoji_resultado} *RESULTADO DA APOSTA* {emoji_resultado}",
        "",
        f"*⚽ Jogo:* {aposta['nome_jogo']}",
        f"*📈 Mercado:* {mercado_str}",
        f"*🏁 Placar Final:* {placar_casa} x {placar_fora}",
        f"*Resultado:* {resultado_final}",
        "",
        f"*💰 Stake:* R$ {aposta.get('stake', 0):.2f}",
        f"*📊 Lucro/Prejuízo:* {sinal_lucro}R$ {lucro_ou_prejuizo:.2f}",
        f"*🏦 Saldo Atual:* R$ {banca['banca_atual']:.2f}"
    ]
    return "\\n".join(linhas_mensagem)
