import os
import requests
import json
from datetime import datetime, timezone, timedelta
import time
from thefuzz import process
import pandas as pd

# --- 1. CONFIGURAÇÕES GERAIS ---
API_KEY_ODDS = os.environ.get('API_KEY_ODDS')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

ARQUIVO_PENDENTES = 'apostas_pendentes.json'
ARQUIVO_HISTORICO_APOSTAS = 'historico_de_apostas.json'
ARQUIVO_RESULTADOS_DIA = 'resultados_do_dia.json'
ARQUIVO_HISTORICO_CORRIGIDO = 'dados_historicos_corrigido.csv'
CASA_ALVO = 'pinnacle'
ARQUIVO_CACHE_IDS = 'sofascore_id_cache.json'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

# --- CONFIGURAÇÕES DAS ESTRATÉGIAS ---
SUPER_FAVORITO_MAX_ODD = 1.55
FAVORITO_MAX_ODD = 1.65
ODD_MINIMA_FAVORITO = 1.30
JOGO_EQUILIBRADO_MIN_ODD = 2.40
ODD_MINIMA_UNDER_Tatico = 1.80
MERCADO_OTIMISTA_MAX_ODD = 1.75
ODD_MINIMA_OVER_Otimista = 1.30
CONSENSO_FAVORITO_MAX_ODD = 1.55
CONSENSO_MERCADO_OVER_MAX_ODD = 1.80
CONSENSO_OVER_MIN_ODD_VALOR = 1.70
CONSENSO_EMPATE_MAX_ODD = 3.20
CONSENSO_MERCADO_UNDER_MAX_ODD = 1.80
CONSENSO_UNDER_MIN_ODD_VALOR = 1.70
LINHA_ESTICADA_OVER_2_5_MAX_ODD = 1.50
LINHA_ESTICADA_UNDER_3_5_MIN_ODD = 1.70
ZEBRA_VALOROSA_FAVORITO_MAX_ODD, ZEBRA_VALOROSA_EMPATE_MIN_ODD, ZEBRA_VALOROSA_EMPATE_MAX_ODD = 1.35, 3.50, 5.00
MERCADO_CONGELADO_RANGE_MIN, MERCADO_CONGELADO_RANGE_MAX = 1.85, 1.95
MERCADO_CONGELADO_BTTS_MIN_ODD = 1.70
FAVORITO_CONSERVADOR_MAX_ODD = 1.55
FAVORITO_CONSERVADOR_OVER_1_5_MIN_ODD = 1.30
PRESSAO_MERCADO_OVER_2_5_MIN_ODD = 1.70
PRESSAO_MERCADO_OVER_2_5_MAX_ODD = 1.85
MIN_JOGOS_HISTORICO = 6
GOLEADOR_CASA_MIN_AVG_GOLS = 1.75
GOLEADOR_CASA_MIN_ODD_OVER_1_5 = 1.30
VISITANTE_FRACO_MIN_PERC_DERROTAS = 58.0
VISITANTE_FRACO_ODD_CASA_MIN = 1.50
VISITANTE_FRACO_ODD_CASA_MAX = 2.50
MIN_JOGOS_H2H = 3
CLASSICO_GOLS_MIN_AVG = 3.0
CLASSICO_GOLS_MIN_ODD_OVER_2_5 = 1.70
FORTALEZA_DEFENSIVA_MAX_AVG_GOLS_SOFRIDOS = 0.85
FORTALEZA_DEFENSIVA_MIN_ODD_UNDER_2_5 = 1.70
GIGANTE_MIN_PERC_VITORIAS = 60.0
GIGANTE_MIN_ODD_VITORIA = 1.40

# --- 2. FUNÇÕES DAS ESTRATÉGIAS ---
def extrair_odds_principais(jogo):
    try:
        bookmaker_data = jogo.get('bookmakers', [])[0]['markets']
        odds = {'h2h': {}, 'totals_1_5': {}, 'totals_2_5': {}, 'totals_3_5': {}}
        for market in bookmaker_data:
            if market['key'] == 'h2h': odds['h2h'] = {o['name']: o['price'] for o in market['outcomes']}
            elif market['key'] == 'totals':
                point = market['outcomes'][0].get('point')
                if point == 1.5: odds['totals_1_5'] = {o['name']: o['price'] for o in market['outcomes']}
                elif point == 2.5: odds['totals_2_5'] = {o['name']: o['price'] for o in market['outcomes']}
                elif point == 3.5: odds['totals_3_5'] = {o['name']: o['price'] for o in market['outcomes']}
        return odds
    except (IndexError, KeyError): return None

def analisar_reacao_gigante(jogo, cache_execucao, stats_individuais, stats_h2h):
    times_no_jogo = [jogo['home_team'], jogo['away_team']]
    for time_analisado in times_no_jogo:
        stats_time = stats_individuais.get(time_analisado)
        if stats_time and stats_time.get('perc_vitorias_geral', 0) >= GIGANTE_MIN_PERC_VITORIAS and stats_time.get('resultado_ultimo_jogo') == 'D':
            print(f"  -> Jogo pré-qualificado para 'Reação do Gigante': {time_analisado} (Vem de derrota)")
            odds = extrair_odds_principais(jogo)
            if not odds or not odds.get('h2h'): return None
            odd_vitoria = odds.get('h2h', {}).get(time_analisado)
            if odd_vitoria and odd_vitoria >= GIGANTE_MIN_ODD_VITORIA:
                print(f"  -> ✅ Validação de Odd APROVADA! Odd para {time_analisado} vencer: {odd_vitoria}")
                motivo = f"O time ({time_analisado}) é um 'gigante' histórico ({stats_time.get('perc_vitorias_geral', 0):.1f}% de vitórias) e vem de uma derrota, indicando uma forte tendência de recuperação."
                return {"mercado": f"Resultado Final - {time_analisado}", "odd": odd_vitoria, "emoji": '⚡', "nome_estrategia": "REAÇÃO DO GIGANTE (HISTÓRICO)", "motivo": motivo}
            else:
                print(f"  -> ❌ Validação de Odd REPROVADA. Odd da vitória: {odd_vitoria if odd_vitoria else 'N/A'}")
    return None

def analisar_fortaleza_defensiva(jogo, cache_execucao, stats_individuais, stats_h2h):
    time_casa = jogo['home_team']
    stats_time = stats_individuais.get(time_casa)
    if not stats_time or stats_time.get('total_jogos_casa', 0) < MIN_JOGOS_HISTORICO: return None
    avg_gols_sofridos = stats_time.get('avg_gols_sofridos_casa', 99)
    if avg_gols_sofridos <= FORTALEZA_DEFENSIVA_MAX_AVG_GOLS_SOFRIDOS:
        print(f"  -> Jogo pré-qualificado para 'Fortaleza Defensiva': {time_casa} (Média Sofrida: {avg_gols_sofridos:.2f} gols/jogo)")
        odds = extrair_odds_principais(jogo)
        if not odds: return None
        odd_under_2_5 = odds.get('totals_2_5', {}).get('Under')
        if odd_under_2_5 and odd_under_2_5 >= FORTALEZA_DEFENSIVA_MIN_ODD_UNDER_2_5:
            print(f"  -> ✅ Validação de Odd APROVADA! Odd Under 2.5: {odd_under_2_5}")
            motivo = f"O time da casa ({time_casa}) possui uma defesa historicamente sólida em seus domínios, sofrendo em média apenas {avg_gols_sofridos:.2f} gols por jogo."
            return {"mercado": "Menos de 2.5", "odd": odd_under_2_5, "emoji": '🛡️', "nome_estrategia": "FORTALEZA DEFENSIVA (HISTÓRICO)", "motivo": motivo}
        else:
            print(f"  -> ❌ Validação de Odd REPROVADA. Odd Under 2.5: {odd_under_2_5 if odd_under_2_5 else 'N/A'}")
    return None

def analisar_classico_de_gols(jogo, cache_execucao, stats_individuais, stats_h2h):
    time_casa, time_fora = jogo['home_team'], jogo['away_team']
    h2h_key = '|'.join(sorted([time_casa, time_fora]))
    stats_confronto = stats_h2h.get(h2h_key)
    if not stats_confronto or stats_confronto.get('total_jogos_h2h', 0) < MIN_JOGOS_H2H: return None
    avg_gols = stats_confronto.get('avg_gols_h2h', 0)
    if avg_gols >= CLASSICO_GOLS_MIN_AVG:
        print(f"  -> Jogo pré-qualificado para 'Clássico de Gols': {time_casa} vs {time_fora} (Média H2H: {avg_gols:.2f} gols)")
        odds = extrair_odds_principais(jogo)
        if not odds: return None
        odd_over_2_5 = odds.get('totals_2_5', {}).get('Over')
        if odd_over_2_5 and odd_over_2_5 >= CLASSICO_GOLS_MIN_ODD_OVER_2_5:
            print(f"  -> ✅ Validação de Odd APROVADA! Odd Over 2.5: {odd_over_2_5}")
            motivo = f"O confronto direto entre essas equipes tem um histórico de muitos gols, com uma média de {avg_gols:.2f} gols por partida."
            return {"mercado": "Mais de 2.5", "odd": odd_over_2_5, "emoji": '💥', "nome_estrategia": "CLÁSSICO DE GOLS (HISTÓRICO)", "motivo": motivo}
        else:
            print(f"  -> ❌ Validação de Odd REPROVADA. Odd Over 2.5: {odd_over_2_5 if odd_over_2_5 else 'N/A'}")
    return None

def analisar_goleador_casa(jogo, cache_execucao, stats_individuais, stats_h2h):
    time_casa = jogo['home_team']
    stats_time = stats_individuais.get(time_casa)
    if not stats_time or stats_time.get('total_jogos_casa', 0) < MIN_JOGOS_HISTORICO: return None
    avg_gols_marcados = stats_time.get('avg_gols_marcados_casa', 0)
    if avg_gols_marcados >= GOLEADOR_CASA_MIN_AVG_GOLS:
        print(f"  -> Jogo pré-qualificado para 'Goleador da Casa': {time_casa} (Média: {avg_gols_marcados:.2f} gols/jogo)")
        odds = extrair_odds_principais(jogo)
        if not odds: return None
        odd_over_1_5 = odds.get('totals_1_5', {}).get('Over')
        if odd_over_1_5 and odd_over_1_5 >= GOLEADOR_CASA_MIN_ODD_OVER_1_5:
            print(f"  -> ✅ Validação de Odd APROVADA! Odd Over 1.5: {odd_over_1_5}")
            motivo = f"O time da casa ({time_casa}) possui um forte histórico ofensivo em seus domínios, com uma média de {avg_gols_marcados:.2f} gols por jogo."
            return {"mercado": "Mais de 1.5", "odd": odd_over_1_5, "emoji": '🏠', "nome_estrategia": "GOLEADOR DA CASA (HISTÓRICO)", "motivo": motivo}
        else:
            print(f"  -> ❌ Validação de Odd REPROVADA. Odd Over 1.5: {odd_over_1_5 if odd_over_1_5 else 'N/A'}")
    return None

def analisar_visitante_fraco(jogo, cache_execucao, stats_individuais, stats_h2h):
    time_casa, time_fora = jogo['home_team'], jogo['away_team']
    stats_time_fora = stats_individuais.get(time_fora)
    if not stats_time_fora or stats_time_fora.get('total_jogos_fora', 0) < MIN_JOGOS_HISTORICO: return None
    perc_derrotas = stats_time_fora.get('perc_derrotas_fora', 0)
    if perc_derrotas >= VISITANTE_FRACO_MIN_PERC_DERROTAS:
        print(f"  -> Jogo pré-qualificado para 'Visitante Fraco': {time_fora} ({perc_derrotas:.2f}% de derrotas fora)")
        odds = extrair_odds_principais(jogo)
        if not odds or not odds.get('h2h'): return None
        odd_casa = odds.get('h2h', {}).get(time_casa)
        if odd_casa and VISITANTE_FRACO_ODD_CASA_MIN <= odd_casa <= VISITANTE_FRACO_ODD_CASA_MAX:
            print(f"  -> ✅ Validação de Odd APROVADA! Odd para {time_casa} vencer: {odd_casa}")
            motivo = f"O time visitante ({time_fora}) tem um histórico ruim fora de casa, perdendo {perc_derrotas:.1f}% de suas partidas nesta condição."
            return {"mercado": f"Resultado Final - {time_casa}", "odd": odd_casa, "emoji": '📉', "nome_estrategia": "VISITANTE FRACO (HISTÓRICO)", "motivo": motivo}
        else:
            print(f"  -> ❌ Validação de Odd REPROVADA. Odd da casa: {odd_casa if odd_casa else 'N/A'}")
    return None

def analisar_favoritos_em_niveis(jogo, cache_execucao, stats_individuais, stats_h2h):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['h2h']: return None
    odds_h2h = {k: v for k, v in odds['h2h'].items() if k != 'Draw'}
    if not odds_h2h: return None
    nome_favorito, odd_favorito = min(odds_h2h, key=odds_h2h.get), min(odds_h2h.values())
    nivel = "SUPER FAVORITO" if odd_favorito <= SUPER_FAVORITO_MAX_ODD else ("FAVORITO" if odd_favorito <= FAVORITO_MAX_ODD else None)
    odd_over_1_5 = odds.get('totals_1_5', {}).get('Over')
    if not (nivel and odd_over_1_5 and odd_over_1_5 > ODD_MINIMA_FAVORITO): return None
    print(f"  -> Jogo pré-qualificado para 'Ataque do {nivel}': {nome_favorito}")
    relatorio = consultar_forma_sofascore(nome_favorito, cache_execucao); time.sleep(2)
    if relatorio and relatorio['forma'].count('V') >= 3:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Forma: {relatorio['forma']}")
        motivo = f"O time favorito ({nome_favorito}) está em boa forma recente, com {relatorio['forma'].count('V')} vitórias nos últimos {len(relatorio['forma'])} jogos."
        return {"mercado": "Mais de 1.5", "odd": odd_over_1_5, "emoji": '👑', "nome_estrategia": f"ATAQUE DO {nivel} (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA. Forma: {relatorio['forma'] if relatorio else 'N/A'}")
    return None

def analisar_duelo_tatico(jogo, cache_execucao, stats_individuais, stats_h2h):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['h2h'] or not odds['totals_2_5']: return None
    odd_casa, odd_fora, odd_under_2_5 = odds['h2h'].get(jogo['home_team']), odds['h2h'].get(jogo['away_team']), odds['totals_2_5'].get('Under')
    if not (odd_casa and odd_fora and odd_under_2_5 and odd_casa > JOGO_EQUILIBRADO_MIN_ODD and odd_fora > JOGO_EQUILIBRADO_MIN_ODD and odd_under_2_5 > ODD_MINIMA_UNDER_Tatico): return None
    print(f"  -> Jogo pré-qualificado para 'Duelo Tático': {jogo['home_team']} vs {jogo['away_team']}")
    relatorio_casa, relatorio_fora = consultar_forma_sofascore(jogo['home_team'], cache_execucao), consultar_forma_sofascore(jogo['away_team'], cache_execucao); time.sleep(2)
    if relatorio_casa and relatorio_fora and relatorio_casa['media_gols_partida'] < 2.6 and relatorio_fora['media_gols_partida'] < 2.6:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Média de gols (C|F): {relatorio_casa['media_gols_partida']:.2f} | {relatorio_fora['media_gols_partida']:.2f}")
        motivo = f"Ambas as equipes vêm de jogos com poucos gols. A média de gols recente do time da casa é {relatorio_casa['media_gols_partida']:.2f} e do visitante é {relatorio_fora['media_gols_partida']:.2f}."
        return {"mercado": "Menos de 2.5", "odd": odd_under_2_5, "emoji": '♟️', "nome_estrategia": "DUELO TÁTICO (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA.")
    return None

def analisar_mercado_otimista(jogo, cache_execucao, stats_individuais, stats_h2h):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['totals_1_5'] or not odds['totals_2_5']: return None
    odd_over_2_5, odd_over_1_5 = odds['totals_2_5'].get('Over'), odds.get('totals_1_5', {}).get('Over')
    if not (odd_over_2_5 and odd_over_1_5 and odd_over_2_5 <= MERCADO_OTIMISTA_MAX_ODD and odd_over_1_5 > ODD_MINIMA_OVER_Otimista): return None
    print(f"  -> Jogo pré-qualificado para 'Mercado Otimista': {jogo['home_team']} vs {jogo['away_team']}")
    relatorio_casa, relatorio_fora = consultar_forma_sofascore(jogo['home_team'], cache_execucao), consultar_forma_sofascore(jogo['away_team'], cache_execucao); time.sleep(2)
    if relatorio_casa and relatorio_fora and relatorio_casa['media_gols_partida'] > 2.7 and relatorio_fora['media_gols_partida'] > 2.7:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Média de gols (C|F): {relatorio_casa['media_gols_partida']:.2f} | {relatorio_fora['media_gols_partida']:.2f}")
        motivo = f"Ambas as equipes vêm de jogos com muitos gols. A média de gols recente do time da casa é {relatorio_casa['media_gols_partida']:.2f} e do visitante é {relatorio_fora['media_gols_partida']:.2f}."
        return {"mercado": "Mais de 1.5", "odd": odd_over_1_5, "emoji": '📈', "nome_estrategia": "MERCADO OTIMISTA (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA.")
    return None

def analisar_consenso_de_gols(jogo, cache_execucao, stats_individuais, stats_h2h):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['h2h'] or not odds['totals_2_5']: return None
    odds_h2h = {k: v for k, v in odds['h2h'].items() if k != 'Draw'}
    if not odds_h2h: return None
    nome_favorito, odd_favorito = min(odds_h2h, key=odds_h2h.get), min(odds_h2h.values())
    odd_over_2_5 = odds['totals_2_5'].get('Over')
    if not (odd_favorito <= CONSENSO_FAVORITO_MAX_ODD and odd_over_2_5 and odd_over_2_5 <= CONSENSO_MERCADO_OVER_MAX_ODD and odd_over_2_5 > CONSENSO_OVER_MIN_ODD_VALOR): return None
    print(f"  -> Jogo pré-qualificado para 'Consenso de Gols': {jogo['home_team']} vs {jogo['away_team']}")
    relatorio_fav, relatorio_outro = consultar_forma_sofascore(nome_favorito, cache_execucao), consultar_forma_sofascore(next(iter(k for k in odds_h2h if k != nome_favorito)), cache_execucao); time.sleep(2)
    if relatorio_fav and relatorio_outro and relatorio_fav['forma'].count('V') >= 3 and (relatorio_fav['media_gols_partida'] + relatorio_outro['media_gols_partida']) / 2 > 2.8:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Forma do Fav: {relatorio_fav['forma']}, Média Gols: {(relatorio_fav['media_gols_partida'] + relatorio_outro['media_gols_partida']) / 2:.2f}")
        motivo = f"O favorito ({nome_favorito}) está em boa forma ({relatorio_fav['forma'].count('V')} vitórias recentes) e a média de gols combinada das equipes é alta ({(relatorio_fav['media_gols_partida'] + relatorio_outro['media_gols_partida']) / 2:.2f})."
        return {"mercado": "Mais de 2.5", "odd": odd_over_2_5, "emoji": '🎯', "nome_estrategia": "CONSENSO DE GOLS (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA.")
    return None

def analisar_consenso_de_defesa(jogo, cache_execucao, stats_individuais, stats_h2h):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['h2h'] or not odds['totals_2_5']: return None
    odd_empate, odd_under_2_5 = odds['h2h'].get('Draw'), odds['totals_2_5'].get('Under')
    if not (odd_empate and odd_under_2_5 and odd_empate <= CONSENSO_EMPATE_MAX_ODD and odd_under_2_5 <= CONSENSO_MERCADO_UNDER_MAX_ODD and odd_under_2_5 > CONSENSO_UNDER_MIN_ODD_VALOR): return None
    print(f"  -> Jogo pré-qualificado para 'Consenso de Defesa': {jogo['home_team']} vs {jogo['away_team']}")
    relatorio_casa, relatorio_fora = consultar_forma_sofascore(jogo['home_team'], cache_execucao), consultar_forma_sofascore(jogo['away_team'], cache_execucao); time.sleep(2)
    if relatorio_casa and relatorio_fora and relatorio_casa['media_gols_partida'] < 2.5 and relatorio_fora['media_gols_partida'] < 2.5:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Média de gols (C|F): {relatorio_casa['media_gols_partida']:.2f} | {relatorio_fora['media_gols_partida']:.2f}")
        motivo = f"O mercado aponta para um jogo equilibrado (odd do empate baixa) e as equipes têm uma média de gols recente baixa ({relatorio_casa['media_gols_partida']:.2f} e {relatorio_fora['media_gols_partida']:.2f})."
        return {"mercado": "Menos de 2.5", "odd": odd_under_2_5, "emoji": '🛡️', "nome_estrategia": "CONSENSO DE DEFESA (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA.")
    return None

def analisar_linha_esticada(jogo, cache_execucao, stats_individuais, stats_h2h):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['totals_2_5'] or not odds['totals_3_5']: return None
    odd_over_2_5, odd_under_3_5 = odds['totals_2_5'].get('Over'), odds['totals_3_5'].get('Under')
    if not (odd_over_2_5 and odd_under_3_5 and odd_over_2_5 < LINHA_ESTICADA_OVER_2_5_MAX_ODD and odd_under_3_5 > LINHA_ESTICADA_UNDER_3_5_MIN_ODD): return None
    print(f"  -> Jogo pré-qualificado para 'Linha Esticada': {jogo['home_team']} vs {jogo['away_team']}")
    relatorio_casa, relatorio_fora = consultar_forma_sofascore(jogo['home_team'], cache_execucao), consultar_forma_sofascore(jogo['away_team'], cache_execucao); time.sleep(2)
    if relatorio_casa and relatorio_fora and relatorio_casa['media_gols_partida'] < 3.5 and relatorio_fora['media_gols_partida'] < 3.5:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Média de gols (C|F): {relatorio_casa['media_gols_partida']:.2f} | {relatorio_fora['media_gols_partida']:.2f}")
        motivo = f"O mercado espera muitos gols (odd Over 2.5 baixa), mas a média de gols recente das equipes ({relatorio_casa['media_gols_partida']:.2f} e {relatorio_fora['media_gols_partida']:.2f}) sugere que a linha de 3.5 gols está exagerada."
        return {"mercado": "Menos de 3.5", "odd": odd_under_3_5, "emoji": '📏', "nome_estrategia": "LINHA ESTICADA (VALIDADA)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA.")
    return None

def analisar_zebra_valorosa(jogo, cache_execucao, stats_individuais, stats_h2h):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['h2h']: return None
    odds_h2h = {k: v for k, v in odds['h2h'].items() if k != 'Draw'}
    if not odds_h2h: return None
    nome_favorito, odd_favorito = min(odds_h2h, key=odds_h2h.get), min(odds_h2h.values())
    odd_empate = odds['h2h'].get('Draw')
    if not (odd_favorito < ZEBRA_VALOROSA_FAVORITO_MAX_ODD and odd_empate and ZEBRA_VALOROSA_EMPATE_MIN_ODD <= odd_empate <= ZEBRA_VALOROSA_EMPATE_MAX_ODD): return None
    print(f"  -> Jogo pré-qualificado para 'Zebra Valorosa', favorito: {nome_favorito}")
    relatorio_fav = consultar_forma_sofascore(nome_favorito, cache_execucao); time.sleep(2)
    if relatorio_fav and ('D' in relatorio_fav['forma'] or 'E' in relatorio_fav['forma']):
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Forma do favorito tem brechas: {relatorio_fav['forma']}")
        motivo = f"Apesar do favoritismo esmagador, o time favorito ({nome_favorito}) mostrou instabilidade recente ({relatorio_fav['forma']}), o que aumenta o valor da aposta no empate."
        return {"mercado": "Empate", "odd": odd_empate, "emoji": '🦓', "nome_estrategia": "ZEBRA VALOROSA (VALIDADA)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA. Favorito está 100% vitorioso recentemente.")
    return None

def analisar_mercado_congelado(jogo, cache_execucao, stats_individuais, stats_h2h):
    return None # Desativado pois requer mercado BTTS

def analisar_favorito_conservador(jogo, cache_execucao, stats_individuais, stats_h2h):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['h2h'] or not odds['totals_1_5']: return None
    odds_h2h = {k: v for k, v in odds['h2h'].items() if k != 'Draw'}
    if not odds_h2h: return None
    nome_favorito, odd_favorito = min(odds_h2h, key=odds_h2h.get), min(odds_h2h.values())
    odd_over_1_5 = odds.get('totals_1_5', {}).get('Over')
    if not (odd_favorito <= FAVORITO_CONSERVADOR_MAX_ODD and odd_over_1_5 and odd_over_1_5 > FAVORITO_CONSERVADOR_OVER_1_5_MIN_ODD): return None
    print(f"  -> Jogo pré-qualificado para 'Favorito Conservador': {nome_favorito}")
    relatorio = consultar_forma_sofascore(nome_favorito, cache_execucao); time.sleep(2)
    if relatorio and relatorio['forma'].count('V') >= 3:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Forma: {relatorio['forma']}")
        motivo = f"O time favorito ({nome_favorito}) está em boa forma recente, com {relatorio['forma'].count('V')} vitórias nos últimos {len(relatorio['forma'])} jogos."
        return {"mercado": "Mais de 1.5", "odd": odd_over_1_5, "emoji": '💪', "nome_estrategia": "FAVORITO CONSERVADOR (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA. Forma: {relatorio['forma'] if relatorio else 'N/A'}")
    return None

def analisar_pressao_mercado(jogo, cache_execucao, stats_individuais, stats_h2h):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['totals_2_5']: return None
    odd_over_2_5 = odds['totals_2_5'].get('Over')
    if not (odd_over_2_5 and PRESSAO_MERCADO_OVER_2_5_MIN_ODD <= odd_over_2_5 <= PRESSAO_MERCADO_OVER_2_5_MAX_ODD): return None
    print(f"  -> Jogo pré-qualificado para 'Pressão do Mercado': {jogo['home_team']} vs {jogo['away_team']}")
    relatorio_casa, relatorio_fora = consultar_forma_sofascore(jogo['home_team'], cache_execucao), consultar_forma_sofascore(jogo['away_team'], cache_execucao); time.sleep(2)
    if relatorio_casa and relatorio_fora and (relatorio_casa['media_gols_partida'] + relatorio_fora['media_gols_partida']) / 2 > 2.6:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Média de gols combinada: {(relatorio_casa['media_gols_partida'] + relatorio_fora['media_gols_partida']) / 2:.2f}")
        motivo = f"As odds estão em uma faixa de valor para Over e a média de gols combinada das equipes nos jogos recentes é alta ({(relatorio_casa['media_gols_partida'] + relatorio_fora['media_gols_partida']) / 2:.2f})."
        return {"mercado": "Mais de 2.5", "odd": odd_over_2_5, "emoji": '🌡️', "nome_estrategia": "PRESSÃO DO MERCADO (VALIDADA)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA.")
    return None

# --- 3. FUNÇÕES DE SUPORTE ---
def carregar_json(caminho_arquivo):
    try:
        with open(caminho_arquivo, 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return [] if caminho_arquivo in [ARQUIVO_PENDENTES, ARQUIVO_RESULTADOS_DIA, ARQUIVO_HISTORICO_APOSTAS] else {}

def salvar_json(dados, caminho_arquivo):
    with open(caminho_arquivo, 'w', encoding='utf-8') as f: json.dump(dados, f, indent=4, ensure_ascii=False)

def enviar_alerta_telegram(mensagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    caracteres_especiais = ['_', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in caracteres_especiais: mensagem = mensagem.replace(char, f'\\{char}')
    url, payload = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", {'chat_id': TELEGRAM_CHAT_ID, 'text': mensagem, 'parse_mode': 'MarkdownV2'}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200: print("  > Mensagem enviada com sucesso para o Telegram!")
        else: print(f"  > ERRO ao enviar para o Telegram: {response.status_code} - {response.text}")
    except Exception as e: print(f"  > ERRO de conexão com o Telegram: {e}")

def calcular_estatisticas_historicas(df):
    if df.empty: return {}, {}
    print("  -> 📊 Pré-calculando estatísticas do banco de dados histórico...")
    df.dropna(subset=['HomeTeam', 'AwayTeam', 'Date'], inplace=True)
    try:
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
        df.dropna(subset=['Date'], inplace=True)
    except Exception:
        print("  -> ERRO: Falha ao converter a coluna de datas. Verifique o formato no CSV.")
        return {}, {}
    df['Resultado'] = df.apply(lambda r: 'V' if r['FTHG'] > r['FTAG'] else ('E' if r['FTHG'] == r['FTAG'] else 'D'), axis=1)
    stats_casa = df.groupby('HomeTeam').agg(avg_gols_marcados_casa=('FTHG', 'mean'), avg_gols_sofridos_casa=('FTAG', 'mean'), total_jogos_casa=('HomeTeam', 'count'))
    stats_fora = df.groupby('AwayTeam').agg(avg_gols_marcados_fora=('FTAG', 'mean'), total_jogos_fora=('AwayTeam', 'count'))
    vitorias_casa = df[df['Resultado'] == 'V'].groupby('HomeTeam').size().rename('vitorias_casa')
    vitorias_fora = df[df['Resultado'] == 'D'].groupby('AwayTeam').size().rename('vitorias_fora')
    derrotas_fora = df[df['Resultado'] == 'V'].groupby('AwayTeam').size().rename('derrotas_fora')
    stats_individuais = pd.concat([stats_casa, stats_fora, vitorias_casa, vitorias_fora, derrotas_fora], axis=1).fillna(0).to_dict('index')
    for time, stats in stats_individuais.items():
        total_jogos = stats.get('total_jogos_casa', 0) + stats.get('total_jogos_fora', 0)
        total_vitorias = stats.get('vitorias_casa', 0) + stats.get('vitorias_fora', 0)
        if total_jogos > 0: stats['perc_vitorias_geral'] = (total_vitorias / total_jogos) * 100
        if stats.get('total_jogos_fora', 0) > 0: stats['perc_derrotas_fora'] = (stats.get('derrotas_fora', 0) / stats['total_jogos_fora']) * 100
    df_sorted = df.sort_values(by='Date', ascending=False)
    ultimos_jogos = {}
    for index, row in df_sorted.iterrows():
        time_c, time_f = row['HomeTeam'], row['AwayTeam']
        if time_c not in ultimos_jogos: ultimos_jogos[time_c] = row['Resultado']
        if time_f not in ultimos_jogos: ultimos_jogos[time_f] = 'V' if row['Resultado'] == 'D' else ('D' if row['Resultado'] == 'V' else 'E')
    for time, resultado in ultimos_jogos.items():
        if time in stats_individuais: stats_individuais[time]['resultado_ultimo_jogo'] = resultado
    df['TotalGols'] = df['FTHG'] + df['FTAG']
    df['H2H_Key'] = df.apply(lambda row: '|'.join(sorted([str(row['HomeTeam']), str(row['AwayTeam'])])), axis=1)
    stats_h2h = df.groupby('H2H_Key').agg(avg_gols_h2h=('TotalGols', 'mean'), total_jogos_h2h=('H2H_Key', 'count')).to_dict('index')
    print(f"  -> Estatísticas individuais para {len(stats_individuais)} times e {len(stats_h2h)} confrontos diretos calculadas.")
    return stats_individuais, stats_h2h

def consultar_forma_sofascore(nome_time, cache_execucao, num_jogos=6):
    if nome_time in cache_execucao: return cache_execucao[nome_time]
    print(f"  -> 🔎 [Sofascore] Consultando forma para: {nome_time}")
    cache_ids = carregar_json(ARQUIVO_CACHE_IDS)
    time_id = cache_ids.get(nome_time)
    if not time_id:
        try:
            search_url = f"https://api.sofascore.com/api/v1/search/all?q={nome_time}"
            res = requests.get(search_url, headers=HEADERS, timeout=10)
            search_data = res.json()
            resultados_times = [r['entity'] for r in search_data.get('results', []) if r.get('type') == 'team' and r['entity'].get('sport', {}).get('name') == 'Football']
            if not resultados_times: return None
            nomes_encontrados = {time['name']: time['id'] for time in resultados_times}
            melhor_match = process.extractOne(nome_time, nomes_encontrados.keys())
            if not melhor_match or melhor_match[1] < 70: return None
            time_id = nomes_encontrados[melhor_match[0]]
            cache_ids[nome_time] = time_id
            salvar_json(cache_ids, ARQUIVO_CACHE_IDS)
            time.sleep(1)
        except Exception: return None
    if not time_id: return None
    try:
        events_url = f"https://api.sofascore.com/api/v1/team/{time_id}/events/last/0"
        res = requests.get(events_url, headers=HEADERS, timeout=10)
        events_data = res.json().get('events', [])
        forma, total_gols_lista = [], []
        for jogo in events_data[:num_jogos]:
            if jogo['status']['code'] != 100: continue
            placar_casa, placar_fora = jogo['homeScore']['current'], jogo['awayScore']['current']
            total_gols_lista.append(placar_casa + placar_fora)
            resultado = 'E' if placar_casa == placar_fora else ('V' if (jogo['homeTeam']['id'] == time_id and placar_casa > placar_fora) or (jogo['awayTeam']['id'] == time_id and placar_fora > placar_casa) else 'D')
            forma.append(resultado)
        if not forma: return None
        relatorio_time = {"forma": forma[::-1], "media_gols_partida": sum(total_gols_lista) / len(total_gols_lista)}
        cache_execucao[nome_time] = relatorio_time
        return relatorio_time
    except Exception: return None

def buscar_resultado_sofascore(time_casa, time_fora, timestamp_partida):
    print(f"  -> Buscando resultado para {time_casa} vs {time_fora}")
    cache_temp = {}
    consultar_forma_sofascore(time_casa, cache_temp)
    time.sleep(2)
    time_id = carregar_json(ARQUIVO_CACHE_IDS).get(time_casa)
    if not time_id: return None
    try:
        events_url = f"https://api.sofascore.com/api/v1/team/{time_id}/events/last/0"
        res = requests.get(events_url, headers=HEADERS, timeout=10)
        events_data = res.json().get('events', [])
        for jogo in events_data:
            oponente_no_jogo = jogo['awayTeam']['name'] if jogo['homeTeam']['id'] == time_id else jogo['homeTeam']['name']
            if time_fora in oponente_no_jogo and abs(jogo['startTimestamp'] - timestamp_partida) < 7200:
                if jogo['status']['code'] == 100:
                    return {'placar_casa': jogo['homeScore']['current'], 'placar_fora': jogo['awayScore']['current']}
                else:
                    return "EM_ANDAMENTO"
        return None
    except Exception: return None

def verificar_apostas_pendentes_sofascore():
    print("\n--- 🔍 Verificando resultados de apostas pendentes (via Sofascore)... ---")
    apostas_pendentes = carregar_json(ARQUIVO_PENDENTES)
    if not apostas_pendentes:
        print("Nenhuma aposta pendente na lista.")
        return
    apostas_restantes, apostas_concluidas = [], []
    agora_timestamp = int(datetime.now().timestamp())
    for aposta in apostas_pendentes:
        if 'timestamp' in aposta and agora_timestamp > aposta['timestamp'] + (110 * 60):
            resultado_api = buscar_resultado_sofascore(aposta['time_casa'], aposta['time_fora'], aposta['timestamp'])
            if resultado_api and resultado_api != "EM_ANDAMENTO":
                placar_casa, placar_fora = resultado_api['placar_casa'], resultado_api['placar_fora']
                total_gols = placar_casa + placar_fora
                resultado_final, mercado = "", aposta['mercado']
                if "Mais de 1.5" in mercado: resultado_final = "GREEN" if total_gols > 1.5 else "RED"
                elif "Mais de 2.5" in mercado: resultado_final = "GREEN" if total_gols > 2.5 else "RED"
                elif "Menos de 2.5" in mercado: resultado_final = "GREEN" if total_gols < 2.5 else "RED"
                elif "Menos de 3.5" in mercado: resultado_final = "GREEN" if total_gols < 3.5 else "RED"
                elif "Empate" in mercado: resultado_final = "GREEN" if placar_casa == placar_fora else "RED"
                elif f"Resultado Final - {aposta['time_casa']}" in mercado: resultado_final = "GREEN" if placar_casa > placar_fora else "RED"
                elif f"Resultado Final - {aposta['time_fora']}" in mercado: resultado_final = "GREEN" if placar_fora > placar_casa else "RED"
                if resultado_final:
                    print(f"  -> Resultado encontrado para {aposta['nome_jogo']}: {resultado_final}")
                    aposta['resultado'] = resultado_final
                    apostas_concluidas.append(aposta)
                else: apostas_restantes.append(aposta)
            else: apostas_restantes.append(aposta)
        else:
            apostas_restantes.append(aposta)
    salvar_json(apostas_restantes, ARQUIVO_PENDENTES)
    if apostas_concluidas:
        resultados_dia = carregar_json(ARQUIVO_RESULTADOS_DIA)
        resultados_dia.extend(apostas_concluidas)
        salvar_json(resultados_dia, ARQUIVO_RESULTADOS_DIA)
        print(f"✅ {len(apostas_concluidas)} apostas concluídas foram adicionadas ao diário de bordo.")

def gerar_e_enviar_resumo_diario():
    print("\n--- 📊 Verificando se há resumo diário para enviar... ---")
    resultados_ontem = carregar_json(ARQUIVO_RESULTADOS_DIA)
    if not resultados_ontem:
        print("Nenhum resultado de ontem para resumir.")
        return
    data_primeiro_resultado, data_hoje = datetime.fromtimestamp(resultados_ontem[0]['timestamp']).date(), datetime.now().date()
    if data_primeiro_resultado < data_hoje:
        greens, reds = len([r for r in resultados_ontem if r['resultado'] == 'GREEN']), len([r for r in resultados_ontem if r['resultado'] == 'RED'])
        total = len(resultados_ontem)
        assertividade = (greens / total * 100) if total > 0 else 0
        resumo_msg = (f"📊 *Resumo de Desempenho - {data_primeiro_resultado.strftime('%d/%m/%Y')}* 📊\n\nResultados do dia anterior foram processados:\n\n✅ *GREENs:* {greens}\n🔴 *REDs:* {reds}\n--------------------------\n📈 *Assertividade:* {assertividade:.2f}%\n💰 *Total de Entradas:* {total}")
        enviar_alerta_telegram(resumo_msg)
        historico_completo = carregar_json(ARQUIVO_HISTORICO_APOSTAS)
        historico_completo.extend(resultados_ontem)
        salvar_json(historico_completo, ARQUIVO_HISTORICO_APOSTAS)
        salvar_json([], ARQUIVO_RESULTADOS_DIA)
        print("Resumo de ontem enviado e resultados arquivados.")
    else:
        print("Os resultados no diário de bordo são de hoje. O resumo será gerado amanhã.")

# --- 4. FUNÇÃO PRINCIPAL DE ORQUESTRAÇÃO ---
def rodar_analise_completa():
    gerar_e_enviar_resumo_diario()
    verificar_apostas_pendentes_sofascore()
    print(f"\n--- 🦅 Iniciando busca v13.2 (Falcão Analista)... ---")
    try:
        df_historico = pd.read_csv(ARQUIVO_HISTORICO_CORRIGIDO)
        stats_individuais, stats_h2h = calcular_estatisticas_historicas(df_historico)
    except FileNotFoundError:
        print(f"  -> AVISO: Arquivo '{ARQUIVO_HISTORICO_CORRIGIDO}' não encontrado. Estratégias históricas desativadas.")
        stats_individuais, stats_h2h = {}, {}
    url_jogos_e_odds = (f"https://api.the-odds-api.com/v4/sports/soccer/odds?apiKey={API_KEY_ODDS}&regions=eu,us,uk,au&markets=h2h,totals&bookmakers={CASA_ALVO}&oddsFormat=decimal")
    try:
        response_jogos = requests.get(url_jogos_e_odds, timeout=30)
        jogos_do_dia = response_jogos.json() if response_jogos.status_code == 200 else []
    except Exception as e:
        print(f"  > ERRO de conexão com The Odds API: {e}"); jogos_do_dia = []
    jogos_analisados, nomes_jogos_analisados, alerta_de_aposta_enviado_geral = 0, [], False
    cache_forma_execucao = {}
    if jogos_do_dia:
        fuso_brasilia, fuso_utc = timezone(timedelta(hours=-3)), timezone.utc
        for jogo in jogos_do_dia:
            time_casa, time_fora = jogo['home_team'], jogo['away_team']
            if not jogo.get('bookmakers'): continue
            jogos_analisados += 1
            nomes_jogos_analisados.append(f"⚽ {time_casa} vs {time_fora}")
            print(f"\n--------------------------------------------------\nAnalisando Jogo: {time_casa} vs {time_fora}")
            lista_de_funcoes = [
                analisar_reacao_gigante, analisar_classico_de_gols, analisar_goleador_casa, analisar_visitante_fraco, analisar_fortaleza_defensiva,
                analisar_favorito_conservador, analisar_favoritos_em_niveis,
                analisar_consenso_de_gols, analisar_pressao_mercado, analisar_mercado_otimista,
                analisar_consenso_de_defesa, analisar_duelo_tatico, analisar_linha_esticada, analisar_zebra_valorosa
            ]
            for func in lista_de_funcoes:
                oportunidade = func(jogo, cache_forma_execucao, stats_individuais, stats_h2h)
                if oportunidade:
                    alerta_de_aposta_enviado_geral = True
                    data_hora = datetime.fromisoformat(jogo['commence_time'].replace('Z', '+00:00')).astimezone(fuso_brasilia).strftime('%d/%m/%Y às %H:%M')
                    mercado_str = oportunidade['mercado']
                    if "Mais de" in mercado_str or "Menos de" in mercado_str: mercado_str += " Gols"

                    alerta = (f"*{oportunidade['emoji']} ENTRADA VALIDADA ({oportunidade['nome_estrategia']}) {oportunidade['emoji']}*\n\n"
                              f"*⚽ JOGO:* {time_casa} vs {time_fora}\n"
                              f"*🏆 LIGA:* {jogo.get('sport_title', 'N/A')}\n"
                              f"*🗓️ DATA:* {data_hora}\n\n"
                              f"*📈 MERCADO:* {mercado_str}\n"
                              f"*📊 ODD ENCONTRADA:* *{oportunidade['odd']}*")

                    if 'motivo' in oportunidade and oportunidade['motivo']:
                        alerta += f"\n\n*🔍 Análise do Falcão:*\n_{oportunidade['motivo']}_"

                    enviar_alerta_telegram(alerta)

                    timestamp_utc = datetime.fromisoformat(jogo['commence_time'].replace('Z', '+00:00')).replace(tzinfo=fuso_utc).timestamp()
                    nova_aposta = {
                        "id_api": jogo['id'], "nome_jogo": f"{time_casa} vs {time_fora}", "time_casa": time_casa,
                        "time_fora": time_fora, "mercado": oportunidade['mercado'], "timestamp": int(timestamp_utc)
                    }
                    apostas_pendentes = carregar_json(ARQUIVO_PENDENTES)
                    apostas_pendentes.append(nova_aposta)
                    salvar_json(apostas_pendentes, ARQUIVO_PENDENTES)
                    break
    print("\n--- Análise deste ciclo finalizada. ---")
    if not alerta_de_aposta_enviado_geral:
        data_hoje_str = datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y às %H:%M')
        jogos_texto = "\n".join(nomes_jogos_analisados[:15])
        if len(nomes_jogos_analisados) > 15: jogos_texto += f"\n...e mais {len(nomes_jogos_analisados) - 15} jogos."
        total_pendentes = len(carregar_json(ARQUIVO_PENDENTES))
        mensagem_status = (f"🦅 *Relatório do Falcão da ODDS (v13.2)*\n\n🗓️ *Data:* {data_hoje_str}\n-----------------------------------\n\n🔍 *Resumo:*\n- Verifiquei e processei resultados antigos.\n- Analisei *{jogos_analisados}* jogos com o arsenal completo de estratégias.\n- Atualmente, há *{total_pendentes}* apostas em aberto.\n\n🚫 *Resultado:*\nNenhuma oportunidade de alta qualidade encontrada neste ciclo.\n\n🗒️ *Jogos Verificados:*\n{jogos_texto if jogos_texto else 'Nenhum jogo encontrado.'}\n\nContinuo monitorando! 🕵️‍♂️")
        print("Nenhuma oportunidade encontrada. Enviando relatório de status...")
        enviar_alerta_telegram(mensagem_status)

# --- 5. PONTO DE ENTRADA ---
if __name__ == "__main__":
    print("--- Iniciando execução única do bot (v13.2 Falcão Analista) ---")
    if not all([API_KEY_ODDS, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
        print("❌ ERRO FATAL: Chaves de API/Telegram não configuradas.")
    else:
        rodar_analise_completa()
    print("--- Execução finalizada com sucesso. ---")
