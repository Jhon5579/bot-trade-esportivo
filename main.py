import os
import requests
import json
from datetime import datetime, timezone, timedelta
import time
from thefuzz import fuzz, process
import pandas as pd

# --- IMPORTAÇÃO DOS MÓDULOS DO PROJETO ---
from gestao_banca import carregar_banca, calcular_stake, registrar_resultado
from sofascore_utils import consultar_forma_sofascore, buscar_jogos_ao_vivo, buscar_resultado_sofascore, consultar_classificacao_sofascore
from utils import carregar_json, salvar_json
from config import *
from estrategias import *
from api_externas import buscar_jogos_api_football, buscar_odds_the_odds_api

# --- ARQUIVOS E CONSTANTES ---
ARQUIVO_PENDENTES = 'apostas_pendentes.json'
ARQUIVO_HISTORICO_APOSTAS = 'historico_de_apostas.json'
ARQUIVO_RESULTADOS_DIA = 'resultados_do_dia.json'
ARQUIVO_HISTORICO_CORRIGIDO = 'dados_historicos_corrigido.csv'
ARQUIVO_MAPA_LIGAS = 'mapa_ligas.json'
ARQUIVO_CACHE_SOFASCORE = 'sofascore_cache.json'

# --- FUNÇÕES DE SUPORTE ---

def enviar_alerta_telegram(mensagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("  -> AVISO: Tokens do Telegram não encontrados. Mensagem não enviada.")
        return
    caracteres_especiais = ['_', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in caracteres_especiais:
        mensagem = mensagem.replace(char, f'\\{char}')

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': mensagem, 'parse_mode': 'MarkdownV2'}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("  > Mensagem enviada com sucesso para o Telegram!")
        else:
            print(f"  > ERRO ao enviar para o Telegram: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"  > ERRO de conexão com o Telegram: {e}")

def pre_buscar_dados_sofascore(jogos_do_dia, cache_execucao):
    print("\n--- 🧠 Pré-buscando dados de forma do Sofascore... ---")
    
    times_unicos = set()
    for jogo in jogos_do_dia:
        times_unicos.add(jogo['time_casa'])
        times_unicos.add(jogo['time_fora'])

    print(f"  -> Encontrados {len(times_unicos)} times únicos para buscar dados.")
    
    for i, time_nome in enumerate(list(times_unicos)):
        if time_nome in cache_execucao:
            print(f"  -> [CACHE HIT] Usando dados de forma para: {time_nome}")
            continue
        
        print(f"  -> [CACHE MISS] Buscando dados de forma para: {time_nome} ({i+1}/{len(times_unicos)})")
        relatorio_time = consultar_forma_sofascore(time_nome, cache_execucao)
        if relatorio_time:
            cache_execucao[time_nome] = relatorio_time
        time.sleep(2)

    print("  -> ✅ Pré-busca de dados de forma do Sofascore concluída.")
    return cache_execucao

# --- FUNÇÃO PRINCIPAL ---
def rodar_analise_completa():
    print(f"\n--- 🦅 Iniciando ciclo de análise final... ---")
    
    # ETAPA 1: BUSCAR A LISTA COMPLETA DE JOGOS
    jogos_principais = buscar_jogos_api_football(API_KEY_FOOTBALL)
    if not jogos_principais:
        print("Nenhum jogo encontrado na API-Football. Encerrando o ciclo.")
        return

    # ETAPA 2: BUSCAR AS ODDS DISPONÍVEIS
    jogos_com_odds = buscar_odds_the_odds_api(API_KEY_ODDS, CASA_ALVO)
    
    # ETAPA 3: PREPARAR O CONTEXTO
    contexto = {
        "cache_execucao": {},
        "cache_classificacao": {},
        "mapa_ligas": carregar_json(ARQUIVO_MAPA_LIGAS),
    }
    contexto['cache_execucao'] = pre_buscar_dados_sofascore(jogos_principais, contexto['cache_execucao'])
    
    # (Opcional: carregar dados históricos se for usá-los)
    
    print(f"\n--- 🔬 Analisando os {len(jogos_principais)} jogos encontrados... ---")

    lista_de_funcoes = [
        # Coloque aqui a lista de todas as suas funções de 'estrategias.py'
        # Exemplo:
        # analisar_reacao_gigante,
        # analisar_lider_vs_lanterna,
    ]
    
    for jogo in jogos_principais:
        time_casa = jogo['time_casa']
        time_fora = jogo['time_fora']
        print(f"\n--------------------------------------------------\nAnalisando Jogo: {time_casa} vs {time_fora}")

        # Lógica para cruzar os dados de odds
        jogo['bookmakers'] = []
        if jogos_com_odds:
            melhor_match_odds = None
            maior_pontuacao = 75 # Limiar de confiança
            for jogo_odd in jogos_com_odds:
                pontuacao = fuzz.token_set_ratio(f"{time_casa} {time_fora}", f"{jogo_odd['home_team']} {jogo_odd['away_team']}")
                if pontuacao > maior_pontuacao:
                    maior_pontuacao = pontuacao
                    melhor_match_odds = jogo_odd
            
            if melhor_match_odds:
                print(f"  -> Odds encontradas com {maior_pontuacao}% de confiança.")
                jogo['bookmakers'] = melhor_match_odds.get('bookmakers', [])

        # Loop de estratégias
        for func in lista_de_funcoes:
            oportunidade = func(jogo, contexto)
            
            if not oportunidade: continue

            if oportunidade.get('type') == 'aposta':
                if oportunidade.get('odd'): # Se a estratégia retornou uma odd
                    if oportunidade.get('odd', 0) >= ODD_MINIMA_GLOBAL:
                        print(f"  -> ✅ OPORTUNIDADE COM ODD APROVADA! Estratégia: {oportunidade['nome_estrategia']}")
                        # Aqui entraria a lógica de registrar aposta, calcular stake, etc.
                        # registrar_resultado(...)
                    else:
                        print(f"  -> ❌ OPORTUNIDADE REPROVADA PELA ODD MÍNIMA ({oportunidade.get('odd', 0)} < {ODD_MINIMA_GLOBAL})")
                else: # Se a estratégia retornou uma oportunidade sem odd
                    print(f"  -> ✅ OPORTUNIDADE SEM ODD ENCONTRADA! Estratégia: {oportunidade['nome_estrategia']}")
                    mensagem = f"*{oportunidade.get('emoji', '⚠️')} ENTRADA VALIDADA (SEM ODD) {oportunidade.get('emoji', '⚠️')}*\n\n"
                    mensagem += f"*Estratégia:* {oportunidade.get('nome_estrategia', 'N/A')}\n"
                    mensagem += f"*⚽ JOGO:* {time_casa} vs {time_fora}\n"
                    mensagem += f"*📈 MERCADO SUGERIDO:* {oportunidade.get('mercado', 'N/A')}\n\n"
                    mensagem += f"*🔍 Análise do Falcão:* _{oportunidade.get('motivo', 'N/A')}_\n\n"
                    mensagem += "_NOTA: Verifique a odd na sua casa de apostas e decida se a entrada tem valor._"
                    enviar_alerta_telegram(mensagem)
                
                break # Para na primeira oportunidade encontrada para não sobrecarregar com alertas

# --- PONTO DE ENTRADA ---
if __name__ == "__main__":
    print("--- Iniciando execução única do bot ---")
    rodar_analise_completa()
    print("\n--- Ciclo de análise concluído com sucesso. ---")