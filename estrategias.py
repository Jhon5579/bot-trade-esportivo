# Arquivo: estrategias.py
# Descrição: Módulo dedicado a todas as estratégias de análise de jogos de futebol.

# --- IMPORTAÇÕES NECESSÁRIAS PARA AS ESTRATÉGIAS ---
from datetime import datetime, timezone, timedelta
from sofascore_utils import (
    consultar_classificacao_sofascore,
    consultar_estatisticas_escanteios,
    consultar_forma_sofascore
)
from config import *

# --- FUNÇÃO DE SUPORTE ---

def extrair_odds_principais(jogo):
    """
    Extrai as odds dos mercados principais (H2H, Over/Under) de um jogo.
    """
    try:
        bookmaker_data = jogo.get('bookmakers', [{}])[0].get('markets', [])
        odds = {'h2h': {}, 'totals_1_5': {}, 'totals_2_5': {}, 'totals_3_5': {}}
        for market in bookmaker_data:
            if market['key'] == 'h2h':
                odds['h2h'] = {o['name']: o['price'] for o in market['outcomes']}
            elif market['key'] == 'totals':
                point = market.get('outcomes', [{}])[0].get('point')
                if point == 1.5:
                    odds['totals_1_5'] = {o['name']: o['price'] for o in market['outcomes']}
                elif point == 2.5:
                    odds['totals_2_5'] = {o['name']: o['price'] for o in market['outcomes']}
                elif point == 3.5:
                    odds['totals_3_5'] = {o['name']: o['price'] for o in market['outcomes']}
        return odds
    except (IndexError, KeyError):
        return None

# --- FUNÇÕES DAS ESTRATÉGIAS ---

def analisar_tendencia_escanteios(jogo, contexto):
    print(f"  -> Analisando tendência de escanteios para: {jogo['home_team']} vs {jogo['away_team']}")
    media_cantos_casa = consultar_estatisticas_escanteios(jogo['home_team'], contexto['cache_execucao'], CANTOS_NUM_JOGOS_ANALISE)
    media_cantos_fora = consultar_estatisticas_escanteios(jogo['away_team'], contexto['cache_execucao'], CANTOS_NUM_JOGOS_ANALISE)
    if not media_cantos_casa or not media_cantos_fora:
        print("       -> Não foi possível calcular a média de escanteios. Estratégia cancelada.")
        return None
    media_esperada_jogo = (media_cantos_casa + media_cantos_fora) / 2
    if media_esperada_jogo >= CANTOS_MEDIA_MINIMA_TOTAL:
        print(f"  -> ✅ ALERTA DE ESCANTEIOS! Média esperada: {media_esperada_jogo:.2f}")
        motivo = f"Análise estatística indica alta probabilidade de escanteios. A média de cantos nos jogos recentes do mandante é {media_cantos_casa:.2f} e do visitante é {media_cantos_fora:.2f}, resultando numa expectativa de {media_esperada_jogo:.2f} para esta partida."
        return {"type": "alerta", "emoji": '🚩', "nome_estrategia": "ALERTA DE ESCANTEIOS (ESTATÍSTICO)", "motivo": motivo}
    return None

def analisar_ambas_marcam(jogo, contexto):
    dados_btts = contexto.get('dados_btts', {}).get(jogo['id'])
    if not dados_btts:
        return None
    odd_btts_sim = None
    try:
        for market in dados_btts.get('bookmakers', [{}])[0].get('markets', []):
            if market['key'] == 'both_teams_to_score':
                for outcome in market['outcomes']:
                    if outcome['name'] == 'Yes':
                        odd_btts_sim = outcome['price']
                        break
    except (IndexError, KeyError):
        return None
    if not odd_btts_sim:
        return None
    print(f"  -> Jogo pré-qualificado para 'Ambas Marcam': {jogo['home_team']} vs {jogo['away_team']} (Odd: {odd_btts_sim})")
    cache_execucao = contexto['cache_execucao']
    relatorio_casa = consultar_forma_sofascore(jogo['home_team'], cache_execucao)
    relatorio_fora = consultar_forma_sofascore(jogo['away_team'], cache_execucao)
    if not relatorio_casa or not relatorio_fora:
        print(f"  -> ❌ [Sofascore] Validação REPROVADA. Não foi possível obter o relatório de forma de um dos times.")
        return None
    if relatorio_casa.get('media_gols_partida', 0) >= BTTS_MIN_AVG_GOLS_PARTIDA and relatorio_fora.get('media_gols_partida', 0) >= BTTS_MIN_AVG_GOLS_PARTIDA:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Média de gols (C|F): {relatorio_casa['media_gols_partida']:.2f} | {relatorio_fora['media_gols_partida']:.2f}")
        motivo = f"Ambas as equipas têm um histórico recente de jogos com muitos golos. A média de golos nos últimos jogos do mandante é {relatorio_casa['media_gols_partida']:.2f} e do visitante é {relatorio_fora['media_gols_partida']:.2f}."
        return {"type": "aposta", "mercado": "Ambas as Equipas Marcam - Sim", "odd": odd_btts_sim, "emoji": '⚽', "nome_estrategia": "AMBAS MARCAM (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA. Médias de golos não atingiram o mínimo.")
    return None

def analisar_lider_vs_lanterna(jogo, contexto):
    liga = jogo.get('sport_title')
    mapa_ligas = contexto.get('mapa_ligas', {})
    if not liga or liga not in mapa_ligas: return None
    ano_atual_str = str(datetime.now(timezone(timedelta(hours=-3))).year)
    temporada_key = ano_atual_str
    for key in mapa_ligas[liga].get('temporadas', {}):
        if ano_atual_str in key:
            temporada_key = key
            break
    if temporada_key not in mapa_ligas[liga].get('temporadas', {}): return None
    id_liga = mapa_ligas[liga]['id_liga']
    id_temporada = mapa_ligas[liga]['temporadas'][temporada_key]
    classificacao = consultar_classificacao_sofascore(id_liga, id_temporada, contexto['cache_classificacao'])
    if not classificacao or len(classificacao) < 10: return None
    time_casa, time_fora = jogo['home_team'], jogo['away_team']
    pos_casa, pos_fora = None, None
    for time_info in classificacao:
        if time_info['nome'] == time_casa: pos_casa = time_info['posicao']
        if time_info['nome'] == time_fora: pos_fora = time_info['posicao']
    if not (pos_casa and pos_fora): return None
    lider, lanterna, mercado, lider_pos, lanterna_pos = None, None, None, None, None
    total_times = len(classificacao)
    posicao_corte_lanterna = total_times - LIDER_VS_LANTERNA_POSICAO_MIN_LANTERNA + 1
    if pos_casa <= LIDER_VS_LANTERNA_POSICAO_MAX_LIDER and pos_fora >= posicao_corte_lanterna:
        lider, lanterna, mercado, lider_pos, lanterna_pos = time_casa, time_fora, f"Resultado Final - {time_casa}", pos_casa, pos_fora
    elif pos_fora <= LIDER_VS_LANTERNA_POSICAO_MAX_LIDER and pos_casa >= posicao_corte_lanterna:
        lider, lanterna, mercado, lider_pos, lanterna_pos = time_fora, time_casa, f"Resultado Final - {time_fora}", pos_fora, pos_casa
    if not lider: return None
    print(f"  -> Jogo pré-qualificado para 'Líder vs. Lanterna': {lider} ({lider_pos}º) vs {lanterna} ({lanterna_pos}º)")
    odds = extrair_odds_principais(jogo)
    if not odds or not odds.get('h2h'): return None
    odd_vitoria_lider = odds['h2h'].get(lider)
    if odd_vitoria_lider and odd_vitoria_lider >= LIDER_VS_LANTERNA_ODD_MIN:
        print(f"  -> ✅ Validação de Odd APROVADA! Odd para {lider} vencer: {odd_vitoria_lider}")
        motivo = f"O time ({lider}) está no topo da tabela ({lider_pos}º lugar), enquanto o adversário ({lanterna}) está na parte de baixo ({lanterna_pos}º lugar)."
        return {"type": "aposta", "mercado": mercado, "odd": odd_vitoria_lider, "emoji": '⚔️', "nome_estrategia": "LÍDER VS. LANTERNA (CONTEXTO)", "motivo": motivo}
    return None

def analisar_reacao_gigante(jogo, contexto):
    stats_individuais = contexto['stats_individuais']
    times_no_jogo = [jogo['home_team'], jogo['away_team']]
    for time_analisado in times_no_jogo:
        stats_time = stats_individuais.get(time_analisado)
        if stats_time and stats_time.get('perc_vitorias_geral', 0) >= GIGANTE_MIN_PERC_VITORIAS and stats_time.get('resultado_ultimo_jogo') == 'D':
            print(f"  -> Jogo pré-qualificado para 'Reação do Gigante': {time_analisado} (Vem de derrota)")
            odds = extrair_odds_principais(jogo)
            if not odds or not odds.get('h2h'): continue
            odd_vitoria = odds.get('h2h', {}).get(time_analisado)
            if odd_vitoria and odd_vitoria >= GIGANTE_MIN_ODD_VITORIA:
                print(f"  -> ✅ Validação de Odd APROVADA! Odd para {time_analisado} vencer: {odd_vitoria}")
                motivo = f"O time ({time_analisado}) é um 'gigante' histórico ({stats_time.get('perc_vitorias_geral', 0):.1f}% de vitórias) e vem de uma derrota, indicando uma forte tendência de recuperação."
                return {"type": "aposta", "mercado": f"Resultado Final - {time_analisado}", "odd": odd_vitoria, "emoji": '⚡', "nome_estrategia": "REAÇÃO DO GIGANTE (HISTÓRICO)", "motivo": motivo}
            else:
                print(f"  -> ❌ Validação de Odd REPROVADA. Odd da vitória: {odd_vitoria if odd_vitoria else 'N/A'}")
    return None

def analisar_fortaleza_defensiva(jogo, contexto):
    time_casa = jogo['home_team']
    stats_individuais = contexto['stats_individuais']
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
            return {"type": "aposta", "mercado": "Menos de 2.5", "odd": odd_under_2_5, "emoji": '🛡️', "nome_estrategia": "FORTALEZA DEFENSIVA (HISTÓRICO)", "motivo": motivo}
        else:
            print(f"  -> ❌ Validação de Odd REPROVADA. Odd Under 2.5: {odd_under_2_5 if odd_under_2_5 else 'N/A'}")
    return None

def analisar_classico_de_gols(jogo, contexto):
    time_casa, time_fora = jogo['home_team'], jogo['away_team']
    stats_h2h = contexto['stats_h2h']
    h2h_key = '|'.join(sorted([time_casa, time_fora]))
    stats_confronto = stats_h2h.get(h2h_key)

    if not stats_confronto or stats_confronto.get('total_jogos_h2h', 0) < MIN_JOGOS_H2H:
        return None

    avg_gols_h2h = stats_confronto.get('avg_gols_h2h', 0)
    liga_api = jogo.get('sport_title')
    mapa_ligas_para_div = {"Premier League": "E0", "La Liga": "SP1", "Serie A": "I1", "Bundesliga": "D1"}
    div_liga = mapa_ligas_para_div.get(liga_api)

    stats_ligas = contexto.get('stats_ligas', {})
    media_gols_da_liga = 0
    if div_liga and div_liga in stats_ligas:
        media_gols_da_liga = stats_ligas[div_liga].get('avg_gols_por_jogo', 0)

    condicao_h2h = avg_gols_h2h >= CLASSICO_GOLS_MIN_AVG
    condicao_contexto_liga = False
    if media_gols_da_liga > 0:
        condicao_contexto_liga = avg_gols_h2h > (media_gols_da_liga * 1.15)
    else:
        condicao_contexto_liga = True

    if condicao_h2h and condicao_contexto_liga:
        print(f"  -> Jogo pré-qualificado para 'Clássico de Gols': {time_casa} vs {time_fora} (Média H2H: {avg_gols_h2h:.2f} | Média Liga: {media_gols_da_liga:.2f})")

        odds = extrair_odds_principais(jogo)
        if not odds: return None
        odd_over_2_5 = odds.get('totals_2_5', {}).get('Over')
        if odd_over_2_5 and odd_over_2_5 >= CLASSICO_GOLS_MIN_ODD_OVER_2_5:
            print(f"  -> ✅ Validação de Odd APROVADA! Odd Over 2.5: {odd_over_2_5}")
            motivo_extra = f"A média de gols do confronto ({avg_gols_h2h:.2f}) é superior à média da liga ({media_gols_da_liga:.2f})." if media_gols_da_liga > 0 else ""
            motivo_base = f"O confronto direto entre essas equipes tem um histórico de muitos gols, com uma média de {avg_gols_h2h:.2f} gols por partida. {motivo_extra}"
            return {"type": "aposta", "mercado": "Mais de 2.5", "odd": odd_over_2_5, "emoji": '💥', "nome_estrategia": "CLÁSSICO DE GOLS (VALIDADO)", "motivo": motivo_base}
        else:
            print(f"  -> ❌ Validação de Odd REPROVADA. Odd Over 2.5: {odd_over_2_5 if odd_over_2_5 else 'N/A'}")
    return None

def analisar_goleador_casa(jogo, contexto):
    time_casa = jogo['home_team']
    stats_individuais = contexto['stats_individuais']
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
            return {"type": "aposta", "mercado": "Mais de 1.5", "odd": odd_over_1_5, "emoji": '🏠', "nome_estrategia": "GOLEADOR DA CASA (HISTÓRICO)", "motivo": motivo}
        else:
            print(f"  -> ❌ Validação de Odd REPROVADA. Odd Over 1.5: {odd_over_1_5 if odd_over_1_5 else 'N/A'}")
    return None

def analisar_visitante_fraco(jogo, contexto):
    time_casa, time_fora = jogo['home_team'], jogo['away_team']
    stats_individuais = contexto['stats_individuais']
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
            return {"type": "aposta", "mercado": f"Resultado Final - {time_casa}", "odd": odd_casa, "emoji": '📉', "nome_estrategia": "VISITANTE FRACO (HISTÓRICO)", "motivo": motivo}
        else:
            print(f"  -> ❌ Validação de Odd REPROVADA. Odd da casa: {odd_casa if odd_casa else 'N/A'}")
    return None

def analisar_mandante_fraco(jogo, contexto):
    stats_individuais = contexto['stats_individuais']
    time_casa, time_fora = jogo['home_team'], jogo['away_team']
    stats_casa = stats_individuais.get(time_casa)
    if not stats_casa or stats_casa.get('total_jogos_casa', 0) < MIN_JOGOS_HISTORICO:
        return None
    perc_derrotas_casa = stats_casa.get('perc_derrotas_casa', 0)
    if perc_derrotas_casa >= MANDANTE_FRACO_MIN_PERC_DERROTAS_CASA:
        print(f"  -> Jogo pré-qualificado para 'Mandante Fraco': {time_casa} ({perc_derrotas_casa:.2f}% de derrotas em casa)")
        odds = extrair_odds_principais(jogo)
        if not odds or not odds.get('h2h'):
            return None
        odd_fora = odds.get('h2h', {}).get(time_fora)
        if odd_fora and (MANDANTE_FRACO_ODD_FORA_MIN <= odd_fora <= MANDANTE_FRACO_ODD_FORA_MAX):
            print(f"  -> ✅ Validação de Odd APROVADA! Odd para {time_fora} vencer: {odd_fora}")
            motivo = f"O time da casa ({time_casa}) tem um histórico ruim em casa, perdendo {perc_derrotas_casa:.1f}% de suas partidas nesta condição."
            return {"type": "aposta", "mercado": f"Resultado Final - {time_fora}", "odd": odd_fora, "emoji": '✈️', "nome_estrategia": "MANDANTE FRACO (HISTÓRICO)", "motivo": motivo}
        else:
            print(f"  -> ❌ Validação de Odd REPROVADA. Odd do visitante: {odd_fora if odd_fora else 'N/A'}")
    return None

def analisar_favoritos_em_niveis(jogo, contexto):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['h2h']: return None
    odds_h2h = {k: v for k, v in odds['h2h'].items() if k != 'Draw'}
    if not odds_h2h: return None
    nome_favorito, odd_favorito = min(odds_h2h, key=odds_h2h.get), min(odds_h2h.values())
    nivel = "SUPER FAVORITO" if odd_favorito <= SUPER_FAVORITO_MAX_ODD else ("FAVORITO" if odd_favorito <= FAVORITO_MAX_ODD else None)
    odd_over_1_5 = odds.get('totals_1_5', {}).get('Over')
    if not (nivel and odd_over_1_5 and odd_over_1_5 > ODD_MINIMA_FAVORITO): return None
    print(f"  -> Jogo pré-qualificado para 'Ataque do {nivel}': {nome_favorito}")
    relatorio = consultar_forma_sofascore(nome_favorito, contexto['cache_execucao'])
    if not relatorio:
        print(f"  -> ❌ [Sofascore] Validação REPROVADA. Não foi possível obter o relatório de forma para '{nome_favorito}'.")
        return None
    condicao_forma_geral = relatorio['forma'].count('V') >= 3
    condicao_momento_atual = relatorio['forma'][-3:].count('V') >= 2
    if condicao_forma_geral and condicao_momento_atual:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Forma: {relatorio['forma']} (Momento Forte)")
        motivo = f"O time favorito ({nome_favorito}) está em boa forma geral ({relatorio['forma'].count('V')} vitórias recentes) e em bom momento atual (ganhou {relatorio['forma'][-3:].count('V')} dos últimos 3 jogos)."
        return {"type": "aposta", "mercado": "Mais de 1.5", "odd": odd_over_1_5, "emoji": '👑', "nome_estrategia": f"ATAQUE DO {nivel} (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA. Forma: {relatorio['forma']}")
    return None

def analisar_duelo_tatico(jogo, contexto):
    try:
        if JOGO_EQUILIBRADO_MIN_ODD is None: return None
    except NameError:
        return None
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['h2h'] or not odds['totals_2_5']: return None
    odd_casa, odd_fora, odd_under_2_5 = odds['h2h'].get(jogo['home_team']), odds['h2h'].get(jogo['away_team']), odds['totals_2_5'].get('Under')
    if not (odd_casa and odd_fora and odd_under_2_5 and odd_casa > JOGO_EQUILIBRADO_MIN_ODD and odd_fora > JOGO_EQUILIBRADO_MIN_ODD and odd_under_2_5 > ODD_MINIMA_UNDER_Tatico): return None
    print(f"  -> Jogo pré-qualificado para 'Duelo Tático': {jogo['home_team']} vs {jogo['away_team']}")
    cache_execucao = contexto['cache_execucao']
    relatorio_casa, relatorio_fora = consultar_forma_sofascore(jogo['home_team'], cache_execucao), consultar_forma_sofascore(jogo['away_team'], cache_execucao)
    if not relatorio_casa or not relatorio_fora:
        print(f"  -> ❌ [Sofascore] Validação REPROVADA. Não foi possível obter o relatório de forma de um dos times.")
        return None
    if relatorio_casa['media_gols_partida'] < 2.6 and relatorio_fora['media_gols_partida'] < 2.6:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Média de gols (C|F): {relatorio_casa['media_gols_partida']:.2f} | {relatorio_fora['media_gols_partida']:.2f}")
        motivo = f"Ambas as equipes vêm de jogos com poucos gols. A média de gols recente do time da casa é {relatorio_casa['media_gols_partida']:.2f} e do visitante é {relatorio_fora['media_gols_partida']:.2f}."
        return {"type": "aposta", "mercado": "Menos de 2.5", "odd": odd_under_2_5, "emoji": '♟️', "nome_estrategia": "DUELO TÁTICO (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA.")
    return None

def analisar_mercado_otimista(jogo, contexto):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['totals_1_5'] or not odds['totals_2_5']: return None
    odd_over_2_5, odd_over_1_5 = odds['totals_2_5'].get('Over'), odds.get('totals_1_5', {}).get('Over')
    if not (odd_over_2_5 and odd_over_1_5 and odd_over_2_5 <= MERCADO_OTIMISTA_MAX_ODD and odd_over_1_5 > ODD_MINIMA_OVER_Otimista): return None
    print(f"  -> Jogo pré-qualificado para 'Mercado Otimista': {jogo['home_team']} vs {jogo['away_team']}")
    cache_execucao = contexto['cache_execucao']
    relatorio_casa, relatorio_fora = consultar_forma_sofascore(jogo['home_team'], cache_execucao), consultar_forma_sofascore(jogo['away_team'], cache_execucao)
    if not relatorio_casa or not relatorio_fora:
        print(f"  -> ❌ [Sofascore] Validação REPROVADA. Não foi possível obter o relatório de forma de um dos times.")
        return None
    if relatorio_casa['media_gols_partida'] > 2.7 and relatorio_fora['media_gols_partida'] > 2.7:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Média de gols (C|F): {relatorio_casa['media_gols_partida']:.2f} | {relatorio_fora['media_gols_partida']:.2f}")
        motivo = f"Ambas as equipes vêm de jogos com muitos gols. A média de gols recente do time da casa é {relatorio_casa['media_gols_partida']:.2f} e do visitante é {relatorio_fora['media_gols_partida']:.2f}."
        return {"type": "aposta", "mercado": "Mais de 1.5", "odd": odd_over_1_5, "emoji": '📈', "nome_estrategia": "MERCADO OTIMISTA (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA.")
    return None

def analisar_consenso_de_gols(jogo, contexto):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['h2h'] or not odds['totals_2_5']: return None
    odds_h2h = {k: v for k, v in odds['h2h'].items() if k != 'Draw'}
    if not odds_h2h: return None
    nome_favorito, odd_favorito = min(odds_h2h, key=odds_h2h.get), min(odds_h2h.values())
    odd_over_2_5 = odds['totals_2_5'].get('Over')
    if not (odd_favorito <= CONSENSO_FAVORITO_MAX_ODD and odd_over_2_5 and odd_over_2_5 <= CONSENSO_MERCADO_OVER_MAX_ODD and odd_over_2_5 > CONSENSO_OVER_MIN_ODD_VALOR): return None
    print(f"  -> Jogo pré-qualificado para 'Consenso de Gols': {jogo['home_team']} vs {jogo['away_team']}")
    cache_execucao = contexto['cache_execucao']
    relatorio_fav, relatorio_outro = consultar_forma_sofascore(nome_favorito, cache_execucao), consultar_forma_sofascore(next(iter(k for k in odds_h2h if k != nome_favorito)), cache_execucao)
    if not relatorio_fav or not relatorio_outro:
        print(f"  -> ❌ [Sofascore] Validação REPROVADA. Não foi possível obter o relatório de forma de um dos times.")
        return None
    if relatorio_fav['forma'].count('V') >= 3 and (relatorio_fav['media_gols_partida'] + relatorio_outro['media_gols_partida']) / 2 > 2.8:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Forma do Fav: {relatorio_fav['forma']}, Média Gols: {(relatorio_fav['media_gols_partida'] + relatorio_outro['media_gols_partida']) / 2:.2f}")
        motivo = f"O favorito ({nome_favorito}) está em boa forma ({relatorio_fav['forma'].count('V')} vitórias recentes) e a média de gols combinada das equipes é alta ({(relatorio_fav['media_gols_partida'] + relatorio_outro['media_gols_partida']) / 2:.2f})."
        return {"type": "aposta", "mercado": "Mais de 2.5", "odd": odd_over_2_5, "emoji": '🎯', "nome_estrategia": "CONSENSO DE GOLS (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA.")
    return None

def analisar_consenso_de_defesa(jogo, contexto):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['h2h'] or not odds['totals_2_5']: return None
    odd_empate, odd_under_2_5 = odds['h2h'].get('Draw'), odds['totals_2_5'].get('Under')
    if not (odd_empate and odd_under_2_5 and odd_empate <= CONSENSO_EMPATE_MAX_ODD and odd_under_2_5 <= CONSENSO_MERCADO_UNDER_MAX_ODD and odd_under_2_5 > CONSENSO_UNDER_MIN_ODD_VALOR): return None
    print(f"  -> Jogo pré-qualificado para 'Consenso de Defesa': {jogo['home_team']} vs {jogo['away_team']}")
    cache_execucao = contexto['cache_execucao']
    relatorio_casa, relatorio_fora = consultar_forma_sofascore(jogo['home_team'], cache_execucao), consultar_forma_sofascore(jogo['away_team'], cache_execucao)
    if not relatorio_casa or not relatorio_fora:
        print(f"  -> ❌ [Sofascore] Validação REPROVADA. Não foi possível obter o relatório de forma de um dos times.")
        return None
    if relatorio_casa['media_gols_partida'] < 2.5 and relatorio_fora['media_gols_partida'] < 2.5:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Média de gols (C|F): {relatorio_casa['media_gols_partida']:.2f} | {relatorio_fora['media_gols_partida']:.2f}")
        motivo = f"O mercado aponta para um jogo equilibrado (odd do empate baixa) e as equipes têm uma média de gols recente baixa ({relatorio_casa['media_gols_partida']:.2f} e {relatorio_fora['media_gols_partida']:.2f})."
        return {"type": "aposta", "mercado": "Menos de 2.5", "odd": odd_under_2_5, "emoji": '🛡️', "nome_estrategia": "CONSENSO DE DEFESA (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA.")
    return None

def analisar_linha_esticada(jogo, contexto):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['totals_2_5'] or not odds['totals_3_5']: return None
    odd_over_2_5, odd_under_3_5 = odds['totals_2_5'].get('Over'), odds['totals_3_5'].get('Under')
    if not (odd_over_2_5 and odd_under_3_5 and odd_over_2_5 < LINHA_ESTICADA_OVER_2_5_MAX_ODD and odd_under_3_5 > LINHA_ESTICADA_UNDER_3_5_MIN_ODD): return None
    print(f"  -> Jogo pré-qualificado para 'Linha Esticada': {jogo['home_team']} vs {jogo['away_team']}")
    cache_execucao = contexto['cache_execucao']
    relatorio_casa, relatorio_fora = consultar_forma_sofascore(jogo['home_team'], cache_execucao), consultar_forma_sofascore(jogo['away_team'], cache_execucao)
    if not relatorio_casa or not relatorio_fora:
        print(f"  -> ❌ [Sofascore] Validação REPROVADA. Não foi possível obter o relatório de forma de um dos times.")
        return None
    if relatorio_casa['media_gols_partida'] < 3.5 and relatorio_fora['media_gols_partida'] < 3.5:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Média de gols (C|F): {relatorio_casa['media_gols_partida']:.2f} | {relatorio_fora['media_gols_partida']:.2f}")
        motivo = f"O mercado espera muitos gols (odd Over 2.5 baixa), mas a média de gols recente das equipes ({relatorio_casa['media_gols_partida']:.2f} e {relatorio_fora['media_gols_partida']:.2f}) sugere que a linha de 3.5 gols está exagerada."
        return {"type": "aposta", "mercado": "Menos de 3.5", "odd": odd_under_3_5, "emoji": '📏', "nome_estrategia": "LINHA ESTICADA (VALIDADA)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA.")
    return None

def analisar_zebra_valorosa(jogo, contexto):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['h2h']: return None
    odds_h2h = {k: v for k, v in odds['h2h'].items() if k != 'Draw'}
    if not odds_h2h: return None
    nome_favorito, odd_favorito = min(odds_h2h, key=odds_h2h.get), min(odds_h2h.values())
    odd_empate = odds['h2h'].get('Draw')
    if not (odd_favorito < ZEBRA_VALOROSA_FAVORITO_MAX_ODD and odd_empate and ZEBRA_VALOROSA_EMPATE_MIN_ODD <= odd_empate <= ZEBRA_VALOROSA_EMPATE_MAX_ODD): return None
    print(f"  -> Jogo pré-qualificado para 'Zebra Valorosa', favorito: {nome_favorito}")
    relatorio_fav = consultar_forma_sofascore(nome_favorito, contexto['cache_execucao'])
    if not relatorio_fav:
        print(f"  -> ❌ [Sofascore] Validação REPROVADA. Não foi possível obter o relatório de forma para '{nome_favorito}'.")
        return None
    if ('D' in relatorio_fav['forma'] or 'E' in relatorio_fav['forma']):
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Forma do favorito tem brechas: {relatorio_fav['forma']}")
        motivo = f"Apesar do favoritismo esmagador, o time favorito ({nome_favorito}) mostrou instabilidade recente ({relatorio_fav['forma']}), o que aumenta o valor da aposta no empate."
        return {"type": "aposta", "mercado": "Empate", "odd": odd_empate, "emoji": '🦓', "nome_estrategia": "ZEBRA VALOROSA (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA. Favorito está 100% vitorioso recentemente.")
    return None

def analisar_mercado_congelado(jogo, contexto):
    return None

def analisar_favorito_conservador(jogo, contexto):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['h2h'] or not odds['totals_1_5']: return None
    odds_h2h = {k: v for k, v in odds['h2h'].items() if k != 'Draw'}
    if not odds_h2h: return None
    nome_favorito, odd_favorito = min(odds_h2h, key=odds_h2h.get), min(odds_h2h.values())
    odd_over_1_5 = odds.get('totals_1_5', {}).get('Over')
    if not (odd_favorito <= FAVORITO_CONSERVADOR_MAX_ODD and odd_over_1_5 and odd_over_1_5 > FAVORITO_CONSERVADOR_OVER_1_5_MIN_ODD): return None
    print(f"  -> Jogo pré-qualificado para 'Favorito Conservador': {nome_favorito}")
    relatorio = consultar_forma_sofascore(nome_favorito, contexto['cache_execucao'])
    if not relatorio:
        print(f"  -> ❌ [Sofascore] Validação REPROVADA. Não foi possível obter o relatório de forma para '{nome_favorito}'.")
        return None
    if relatorio['forma'].count('V') >= 3:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Forma: {relatorio['forma']}")
        motivo = f"O time favorito ({nome_favorito}) está em boa forma recente, com {relatorio['forma'].count('V')} vitórias nos últimos {len(relatorio['forma'])} jogos."
        return {"type": "aposta", "mercado": "Mais de 1.5", "odd": odd_over_1_5, "emoji": '💪', "nome_estrategia": "FAVORITO CONSERVADOR (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA. Forma: {relatorio['forma']}")
    return None

def analisar_pressao_mercado(jogo, contexto):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['totals_2_5']: return None
    odd_over_2_5 = odds['totals_2_5'].get('Over')
    if not (odd_over_2_5 and PRESSAO_MERCADO_OVER_2_5_MIN_ODD <= odd_over_2_5 <= PRESSAO_MERCADO_OVER_2_5_MAX_ODD): return None
    print(f"  -> Jogo pré-qualificado para 'Pressão do Mercado': {jogo['home_team']} vs {jogo['away_team']}")
    cache_execucao = contexto['cache_execucao']
    relatorio_casa, relatorio_fora = consultar_forma_sofascore(jogo['home_team'], cache_execucao), consultar_forma_sofascore(jogo['away_team'], cache_execucao)
    if not relatorio_casa or not relatorio_fora:
        print(f"  -> ❌ [Sofascore] Validação REPROVADA. Não foi possível obter o relatório de forma de um dos times.")
        return None
    if (relatorio_casa['media_gols_partida'] + relatorio_fora['media_gols_partida']) / 2 > 2.6:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Média de gols combinada: {(relatorio_casa['media_gols_partida'] + relatorio_fora['media_gols_partida']) / 2:.2f}")
        motivo = f"As odds estão em uma faixa de valor para Over e a média de gols combinada das equipes nos jogos recentes é alta ({(relatorio_casa['media_gols_partida'] + relatorio_fora['media_gols_partida']) / 2:.2f})."
        return {"type": "aposta", "mercado": "Mais de 2.5", "odd": odd_over_2_5, "emoji": '🌡️', "nome_estrategia": "PRESSÃO DO MERCADO (VALIDADA)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA.")
    return None

def analisar_dominio_em_cantos(jogo, contexto):
    stats_individuais = contexto['stats_individuais']
    time_casa, time_fora = jogo['home_team'], jogo['away_team']
    stats_casa = stats_individuais.get(time_casa)
    stats_fora = stats_individuais.get(time_fora)

    if not stats_casa or not stats_fora or stats_casa.get('total_jogos_casa', 0) < MIN_JOGOS_HISTORICO or stats_fora.get('total_jogos_fora', 0) < MIN_JOGOS_HISTORICO:
        return None

    liga_api = jogo.get('sport_title')
    mapa_ligas_para_div = {"Premier League": "E0", "La Liga": "SP1", "Serie A": "I1", "Bundesliga": "D1"}
    div_liga = mapa_ligas_para_div.get(liga_api)

    stats_ligas = contexto.get('stats_ligas', {})
    media_cantos_da_liga = 0
    if div_liga and div_liga in stats_ligas:
        media_cantos_da_liga = stats_ligas[div_liga].get('avg_cantos_por_jogo', 0)

    condicao_casa_pro = stats_casa.get('avg_escanteios_pro_casa', 0) >= CANTOS_HISTORICO_MIN_AVG_PRO
    condicao_fora_sofre = stats_fora.get('avg_escanteios_contra_fora', 0) >= CANTOS_HISTORICO_MIN_AVG_CONTRA

    soma_pro_times = stats_casa.get('avg_escanteios_pro_casa', 0) + stats_fora.get('avg_escanteios_pro_fora', 0)
    condicao_soma_fixa = soma_pro_times >= CANTOS_HISTORICO_MIN_SUM_GERAL

    condicao_contexto_liga = False
    if media_cantos_da_liga > 0:
        condicao_contexto_liga = soma_pro_times > (media_cantos_da_liga * 1.20)
    else:
        condicao_contexto_liga = True

    if condicao_casa_pro and condicao_fora_sofre and condicao_soma_fixa and condicao_contexto_liga:
        print(f"  -> ✅ ALERTA DE CANTOS! {time_casa} (média {stats_casa.get('avg_escanteios_pro_casa', 0):.2f}) vs {time_fora} (sofre média {stats_fora.get('avg_escanteios_contra_fora', 0):.2f})")
        print(f"       -> Soma de cantos dos times ({soma_pro_times:.2f}) vs Média da liga ({media_cantos_da_liga:.2f})")

        motivo_extra = f"A soma das médias de cantos a favor das equipes ({soma_pro_times:.2f}) é significativamente superior à média da liga ({media_cantos_da_liga:.2f})." if media_cantos_da_liga > 0 else ""
        motivo_base = f"O time da casa ({time_casa}) tem uma forte média de escanteios a favor ({stats_casa.get('avg_escanteios_pro_casa', 0):.2f}) e o visitante ({time_fora}) costuma sofrer muitos escanteios ({stats_fora.get('avg_escanteios_contra_fora', 0):.2f}). {motivo_extra}"

        return {"type": "alerta", "emoji": '🚩', "nome_estrategia": "ALERTA DE DOMÍNIO EM CANTOS (HISTÓRICO)", "motivo": motivo_base}
    return None

def analisar_pressao_ofensiva(jogo, contexto):
    stats_individuais = contexto['stats_individuais']
    time_casa, time_fora = jogo['home_team'], jogo['away_team']
    stats_casa = stats_individuais.get(time_casa)
    stats_fora = stats_individuais.get(time_fora)
    if not stats_casa or not stats_fora or stats_casa.get('total_jogos_casa', 0) < MIN_JOGOS_HISTORICO or stats_fora.get('total_jogos_fora', 0) < MIN_JOGOS_HISTORICO:
        return None
    condicao_remates_casa = stats_casa.get('avg_remates_pro_casa', 0) >= PRESSAO_OFENSIVA_MIN_REMATES_PRO
    condicao_remates_alvo_casa = stats_casa.get('avg_remates_alvo_pro_casa', 0) >= PRESSAO_OFENSIVA_MIN_REMATES_ALVO_PRO
    if condicao_remates_casa and condicao_remates_alvo_casa:
        odds = extrair_odds_principais(jogo)
        if not odds: return None
        odd_over_2_5 = odds.get('totals_2_5', {}).get('Over')
        if odd_over_2_5 and odd_over_2_5 >= PRESSAO_OFENSIVA_MIN_ODD_OVER_2_5:
            print(f"  -> ✅ PRESSÃO OFENSIVA DETETADA! {time_casa} tem média de {stats_casa.get('avg_remates_pro_casa', 0):.2f} remates. Odd Over 2.5: {odd_over_2_5}")
            motivo = f"O time da casa ({time_casa}) possui um forte histórico ofensivo, com média de {stats_casa.get('avg_remates_pro_casa', 0):.2f} remates e {stats_casa.get('avg_remates_alvo_pro_casa', 0):.2f} remates no alvo por jogo em casa. A odd para Mais de 2.5 Gols está com valor."
            return {"type": "aposta", "mercado": "Mais de 2.5", "odd": odd_over_2_5, "emoji": '💥', "nome_estrategia": "PRESSÃO OFENSIVA (OVER 2.5)", "motivo": motivo}
    return None

def analisar_jogo_agressivo(jogo, contexto):
    stats_individuais = contexto['stats_individuais']
    time_casa, time_fora = jogo['home_team'], jogo['away_team']
    stats_casa = stats_individuais.get(time_casa)
    stats_fora = stats_individuais.get(time_fora)
    if not stats_casa or not stats_fora or stats_casa.get('total_jogos_casa', 0) < MIN_JOGOS_HISTORICO or stats_fora.get('total_jogos_fora', 0) < MIN_JOGOS_HISTORICO:
        return None
    media_cartoes_casa = stats_casa.get('avg_cartoes_amarelos_pro_casa', 0)
    media_cartoes_fora = stats_fora.get('avg_cartoes_amarelos_pro_fora', 0)
    condicao_casa = media_cartoes_casa >= CARTOES_MIN_AVG_EQUIPA
    condicao_fora = media_cartoes_fora >= CARTOES_MIN_AVG_EQUIPA
    soma_cartoes = media_cartoes_casa + media_cartoes_fora
    condicao_soma = soma_cartoes >= CARTOES_MIN_AVG_JOGO_SUM
    if condicao_casa and condicao_fora and condicao_soma:
        print(f"  -> ✅ ALERTA DE JOGO AGRESSIVO! Média de cartões C|F: {media_cartoes_casa:.2f}|{media_cartoes_fora:.2f}")
        motivo = f"Este jogo tem um forte potencial para ser agressivo. A média de cartões amarelos do {time_casa} é de {media_cartoes_casa:.2f} e a do {time_fora} é de {media_cartoes_fora:.2f}. A soma das médias é de {soma_cartoes:.2f}."
        return {"type": "alerta", "emoji": '🟨', "nome_estrategia": "ALERTA DE JOGO AGRESSIVO (CARTÕES)", "motivo": motivo}
    return None

def analisar_pressao_ofensiva_extrema(jogo, contexto):
    stats_individuais = contexto['stats_individuais']
    time_casa, time_fora = jogo['home_team'], jogo['away_team']
    stats_casa = stats_individuais.get(time_casa)
    if not stats_casa or stats_casa.get('total_jogos_casa', 0) < MIN_JOGOS_HISTORICO:
        return None
    condicao_remates_casa = stats_casa.get('avg_remates_pro_casa', 0) >= PRESSAO_EXTREMA_MIN_REMATES_PRO
    condicao_remates_alvo_casa = stats_casa.get('avg_remates_alvo_pro_casa', 0) >= PRESSAO_EXTREMA_MIN_REMATES_ALVO_PRO
    if condicao_remates_casa and condicao_remates_alvo_casa:
        odds = extrair_odds_principais(jogo)
        if not odds: return None
        odd_over_2_5 = odds.get('totals_2_5', {}).get('Over')
        if odd_over_2_5 and (PRESSAO_EXTREMA_ODD_MIN <= odd_over_2_5 <= PRESSAO_EXTREMA_ODD_MAX):
            print(f"  -> ✅ PRESSÃO EXTREMA DETETADA! {time_casa} tem média de {stats_casa.get('avg_remates_pro_casa', 0):.2f} remates. Odd Over 2.5: {odd_over_2_5}")
            motivo = f"O time da casa ({time_casa}) possui um histórico de domínio ofensivo extremo, com média de {stats_casa.get('avg_remates_pro_casa', 0):.2f} remates e {stats_casa.get('avg_remates_alvo_pro_casa', 0):.2f} remates no alvo por jogo em casa. A odd para Mais de 2.5 Gols está dentro da faixa de valor definida."
            return {"type": "aposta", "mercado": "Mais de 2.5", "odd": odd_over_2_5, "emoji": '🎯', "nome_estrategia": "PRESSÃO EXTREMA (OVER 2.5)", "motivo": motivo}
    return None