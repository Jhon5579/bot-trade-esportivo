# gestao_banca.py - VERSÃO COMPLETA E CORRIGIDA

import json
import os
from utils import carregar_json, salvar_json

ARQUIVO_BANCA = 'banca.json' # Padronizando o nome do arquivo para simplicidade

def carregar_banca():
    """
    Carrega os dados da banca a partir do arquivo JSON.
    Se o arquivo não existir, cria um com valores padrão.
    """
    if not os.path.exists(ARQUIVO_BANCA):
        print(f"Arquivo '{ARQUIVO_BANCA}' não encontrado. Criando um novo com valores padrão.")
        dados_iniciais = {
            "banca_inicial": 100.0,
            "banca_atual": 100.0,
            "unidade": 1,
            "stake_fixa": 5.0,
            "total_investido": 0.0,
            "total_retornado": 0.0,
            "lucro_total": 0.0,
            "roi": 0.0,
            "greens": 0,
            "reds": 0
        }
        salvar_json(dados_iniciais, ARQUIVO_BANCA)
        return dados_iniciais

    return carregar_json(ARQUIVO_BANCA)

def calcular_stake(odd, banca):
    """
    Calcula o valor da stake. Por enquanto, usa uma stake fixa.
    """
    # Esta função pode ser melhorada no futuro com gestão de stake variável.
    return banca.get('stake_fixa', 10.0)

def registrar_resultado(aposta, resultado, placar_casa, placar_fora):
    """
    Registra o resultado de uma aposta, atualiza a banca e retorna uma mensagem de resumo.
    """
    banca = carregar_banca()
    stake = aposta.get('stake', 0)
    odd = aposta.get('odd', 0)

    banca['total_investido'] += stake

    if resultado == 'GREEN':
        retorno = stake * odd
        lucro = retorno - stake
        banca['greens'] += 1
        banca['banca_atual'] += lucro
        banca['total_retornado'] += retorno
    else: # RED
        lucro = -stake
        banca['reds'] += 1
        banca['banca_atual'] += lucro

    banca['lucro_total'] = banca['banca_atual'] - banca['banca_inicial']
    if banca['total_investido'] > 0:
        banca['roi'] = (banca['lucro_total'] / banca['total_investido']) * 100

    salvar_json(banca, ARQUIVO_BANCA)
    print(f"  -> Resultado ({resultado}) registrado. Novo saldo da banca: R$ {banca['banca_atual']:.2f}")

    # Monta a mensagem para o Telegram
    resultado_emoji = "✅ GREEN" if resultado == "GREEN" else "🔴 RED"
    mensagem = (
        f"{resultado_emoji}!\n\n"
        f"*{aposta['estrategia']}*\n"
        f"⚽ *Jogo:* {aposta['nome_jogo']}\n"
        f"📈 *Mercado:* {aposta['mercado']}\n"
        f"📊 *Odd:* {odd:.2f}\n"
        f"💰 *Stake:* R$ {stake:.2f}\n"
        f"🏁 *Placar Final:* {placar_casa}x{placar_fora}\n\n"
        f"💸 *Lucro/Prejuízo:* R$ {lucro:.2f}\n"
        f"🏦 *Saldo Atual:* R$ {banca['banca_atual']:.2f}\n"
        f"📈 *ROI Atual:* {banca['roi']:.2f}%"
    )
    return mensagem
