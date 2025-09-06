import os
import requests
import json
from datetime import datetime, timezone, timedelta
import time
from thefuzz import fuzz, process
import pandas as pd

# --- IMPORTAÇÃO DOS MÓDULOS DO PROJETO ---
from gestao_banca import carregar_banca, calcular_stake, registrar_resultado
from sofascore_utils import (
    consultar_classificacao_sofascore,
    consultar_estatisticas_escanteios,
    consultar_forma_sofascore,
    buscar_resultado_sofascore
)
from utils import carregar_json, salvar_json
from config import *

# --- 1. CONFIGURAÇÕES GERAIS DO AMBIENTE ---
API_KEY_ODDS = os.environ.get('API_KEY_ODDS')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

ARQUIVO_PENDENTES = 'apostas_pendentes.json'
ARQUIVO_HISTORICO_APOSTAS = 'historico_de_apostas.json'
ARQUIVO_RESULTADOS_DIA = 'resultados_do_dia.json'
ARQUIVO_HISTORICO_CORRIGIDO = 'dados_historicos_corrigido.csv'
CASA_ALVO = 'pinnacle'
ARQUIVO_MAPA_LIGAS = 'mapa_ligas.json'
ARQUIVO_HISTORICO_ODDS = 'historico_odds.json'


# --- 2. FUNÇÕES DE SUPORTE ---

def enviar_alerta_telegram(mensagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
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

def calcular_estatisticas_historicas(df):
    if df.empty:
        return {}, {}

    cols_stats = ['FTHG', 'FTAG', 'HC', 'AC', 'HS', 'AS', 'HST', 'AST', 'HY', 'AY', 'HR', 'AR']
    for col in cols_stats:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        else:
            df[col] = 0

    try:
        mapa_nomes = carregar_json('mapa_de_nomes.json')
        if mapa_nomes:
            print("  -> 🗺️ Aplicando mapa de padronização de nomes...")
            df['HomeTeam'] = df['HomeTeam'].replace(mapa_nomes)
            df['AwayTeam'] = df['AwayTeam'].replace(mapa_nomes)
            print(f"  -> Nomes de times padronizados.")
    except FileNotFoundError:
        print("  -> ⚠️ AVISO: Ficheiro 'mapa_de_nomes.json' não encontrado. Os nomes não serão padronizados.")

    print("  -> 📊 Pré-calculando estatísticas do banco de dados histórico...")
    df.dropna(subset=['HomeTeam', 'AwayTeam', 'Date'], inplace=True)
    try:
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
        df.dropna(subset=['Date'], inplace=True)
    except Exception:
        print("  -> ERRO: Falha ao converter a coluna de datas. Verifique o formato no CSV.")
        return {}, {}
    df['Resultado'] = df.apply(lambda r: 'V' if r['FTHG'] > r['FTAG'] else ('E' if r['FTHG'] == r['FTAG'] else 'D'), axis=1)

    stats_casa = df.groupby('HomeTeam').agg(
        avg_gols_marcados_casa=('FTHG', 'mean'),
        avg_gols_sofridos_casa=('FTAG', 'mean'),
        avg_escanteios_pro_casa=('HC', 'mean'),
        avg_escanteios_contra_casa=('AC', 'mean'),
        avg_remates_pro_casa=('HS', 'mean'),
        avg_remates_contra_casa=('AS', 'mean'),
        avg_remates_alvo_pro_casa=('HST', 'mean'),
        avg_remates_alvo_contra_casa=('AST', 'mean'),
        avg_cartoes_amarelos_pro_casa=('HY', 'mean'),
        avg_cartoes_vermelhos_pro_casa=('HR', 'mean'),
        total_jogos_casa=('HomeTeam', 'count')
    )

    stats_fora = df.groupby('AwayTeam').agg(
        avg_gols_marcados_fora=('FTAG', 'mean'),
        avg_gols_sofridos_fora=('FTHG', 'mean'),
        avg_escanteios_pro_fora=('AC', 'mean'),
        avg_escanteios_contra_fora=('HC', 'mean'),
        avg_remates_pro_fora=('AS', 'mean'),
        avg_remates_contra_fora=('HS', 'mean'),
        avg_remates_alvo_pro_fora=('AST', 'mean'),
        avg_remates_alvo_contra_fora=('HST', 'mean'),
        avg_cartoes_amarelos_pro_fora=('AY', 'mean'),
        avg_cartoes_vermelhos_pro_fora=('AR', 'mean'),
        total_jogos_fora=('AwayTeam', 'count')
    )

    vitorias_casa = df[df['Resultado'] == 'V'].groupby('HomeTeam').size().rename('vitorias_casa')
    derrotas_casa = df[df['Resultado'] == 'D'].groupby('HomeTeam').size().rename('derrotas_casa')
    vitorias_fora = df[df['Resultado'] == 'D'].groupby('AwayTeam').size().rename('vitorias_fora')
    derrotas_fora = df[df['Resultado'] == 'V'].groupby('AwayTeam').size().rename('derrotas_fora')

    stats_individuais = pd.concat([stats_casa, stats_fora, vitorias_casa, vitorias_fora, derrotas_fora, derrotas_casa], axis=1).fillna(0).to_dict('index')

    for time_nome, stats in stats_individuais.items():
        total_jogos = stats.get('total_jogos_casa', 0) + stats.get('total_jogos_fora', 0)
        total_vitorias = stats.get('vitorias_casa', 0) + stats.get('vitorias_fora', 0)
        if total_jogos > 0:
            stats['perc_vitorias_geral'] = (total_vitorias / total_jogos) * 100
        if stats.get('total_jogos_fora', 0) > 0:
            stats['perc_derrotas_fora'] = (stats.get('derrotas_fora', 0) / stats['total_jogos_fora']) * 100
        if stats.get('total_jogos_casa', 0) > 0:
            stats['perc_derrotas_casa'] = (stats.get('derrotas_casa', 0) / stats['total_jogos_casa']) * 100

    df_sorted = df.sort_values(by='Date', ascending=False)
    ultimos_jogos = {}
    for index, row in df_sorted.iterrows():
        time_c, time_f = row['HomeTeam'], row['AwayTeam']
        if time_c not in ultimos_jogos:
            ultimos_jogos[time_c] = row['Resultado']
        if time_f not in ultimos_jogos:
            ultimos_jogos[time_f] = 'V' if row['Resultado'] == 'D' else ('D' if row['Resultado'] == 'V' else 'E')
    for time_nome, resultado in ultimos_jogos.items():
        if time_nome in stats_individuais:
            stats_individuais[time_nome]['resultado_ultimo_jogo'] = resultado

    df['TotalGols'] = df['FTHG'] + df['FTAG']
    df['H2H_Key'] = df.apply(lambda row: '|'.join(sorted([str(row['HomeTeam']), str(row['AwayTeam'])])), axis=1)
    stats_h2h = df.groupby('H2H_Key').agg(avg_gols_h2h=('TotalGols', 'mean'), total_jogos_h2h=('H2H_Key', 'count')).to_dict('index')
    print(f"  -> Estatísticas detalhadas para {len(stats_individuais)} times e {len(stats_h2h)} confrontos diretos calculadas.")
    return stats_individuais, stats_h2h

def extrair_odds_principais(jogo):
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

def pre_buscar_dados_sofascore(jogos_do_dia, cache_existente):
    print("\n--- 🧠 Pré-buscando dados do Sofascore para otimização ---")
    times_unicos = set()
    for jogo in jogos_do_dia:
        times_unicos.add(jogo['home_team'])
        times_unicos.add(jogo['away_team'])

    print(f"  -> Encontrados {len(times_unicos)} times únicos para buscar dados.")
    cache_preenchido = cache_existente.copy()

    for i, time_nome in enumerate(list(times_unicos)):
        if time_nome not in cache_preenchido:
            print(f"  -> Buscando dados para: {time_nome} ({i+1}/{len(times_unicos)})")
            consultar_forma_sofascore(time_nome, cache_preenchido)
            time.sleep(2)

    print("  -> ✅ Todos os dados de forma do Sofascore foram pré-buscados e estão em cache.")
    return cache_preenchido

def salvar_odds_futuras(jogos_do_dia):
    print("  -> 💾 Salvando odds de jogos futuros para análise de mercado...")
    historico_odds = carregar_json(ARQUIVO_HISTORICO_ODDS)
    agora = datetime.now(timezone.utc)
    novas_odds_salvas = 0

    for jogo in jogos_do_dia:
        jogo_id = jogo['id']
        if jogo_id in historico_odds:
            continue

        inicio_jogo_dt = datetime.fromisoformat(jogo['commence_time'].replace('Z', '+00:00'))

        if (inicio_jogo_dt - agora) > timedelta(hours=22):
            odds = extrair_odds_principais(jogo)
            if odds and odds.get('h2h'):
                historico_odds[jogo_id] = {
                    "home_team": jogo['home_team'],
                    "away_team": jogo['away_team'],
                    "commence_time": jogo['commence_time'],
                    "opening_odds": odds['h2h']
                }
                novas_odds_salvas += 1

    if novas_odds_salvas > 0:
        salvar_json(historico_odds, ARQUIVO_HISTORICO_ODDS)
        print(f"  -> {novas_odds_salvas} novas odds de jogos futuros foram salvas.")

# --- 3. FUNÇÕES DAS ESTRATÉGIAS ---

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
    if relatorio_casa and relatorio_fora and relatorio_casa.get('media_gols_partida', 0) >= BTTS_MIN_AVG_GOLS_PARTIDA and relatorio_fora.get('media_gols_partida', 0) >= BTTS_MIN_AVG_GOLS_PARTIDA:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Média de gols (C|F): {relatorio_casa['media_gols_partida']:.2f} | {relatorio_fora['media_gols_partida']:.2f}")
        motivo = f"Ambas as equipas têm um histórico recente de jogos com muitos golos. A média de golos nos últimos jogos do mandante é {relatorio_casa['media_gols_partida']:.2f} e do visitante é {relatorio_fora['media_gols_partida']:.2f}."
        return {"type": "aposta", "mercado": "Ambas as Equipas Marcam - Sim", "odd": odd_btts_sim, "emoji": '⚽', "nome_estrategia": "AMBAS MARCAM (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA. Médias de golos não atingiram o mínimo.")
    return None

def analisar_lider_vs_lanterna(jogo, contexto):
    liga = jogo.get('sport_title')
    mapa_ligas = contexto.get('mapa_ligas', {})
    if not liga or liga not in mapa_ligas:
        return None
    ano_atual_str = str(datetime.now(timezone(timedelta(hours=-3))).year)
    temporada_key = ano_atual_str
    for key in mapa_ligas[liga].get('temporadas', {}):
        if ano_atual_str in key:
            temporada_key = key
            break
    if temporada_key not in mapa_ligas[liga].get('temporadas', {}):
        return None
    id_liga = mapa_ligas[liga]['id_liga']
    id_temporada = mapa_ligas[liga]['temporadas'][temporada_key]
    classificacao = consultar_classificacao_sofascore(id_liga, id_temporada, contexto['cache_classificacao'])
    if not classificacao or len(classificacao) < 10:
        return None
    time_casa, time_fora = jogo['home_team'], jogo['away_team']
    pos_casa, pos_fora = None, None
    for time_info in classificacao:
        if time_info['nome'] == time_casa:
            pos_casa = time_info['posicao']
        if time_info['nome'] == time_fora:
            pos_fora = time_info['posicao']
    if not (pos_casa and pos_fora):
        return None
    lider, lanterna, mercado, lider_pos, lanterna_pos = None, None, None, None, None
    total_times = len(classificacao)
    posicao_corte_lanterna = total_times - LIDER_VS_LANTERNA_POSICAO_MIN_LANTERNA + 1
    if pos_casa <= LIDER_VS_LANTERNA_POSICAO_MAX_LIDER and pos_fora >= posicao_corte_lanterna:
        lider, lanterna, mercado, lider_pos, lanterna_pos = time_casa, time_fora, f"Resultado Final - {time_casa}", pos_casa, pos_fora
    elif pos_fora <= LIDER_VS_LANTERNA_POSICAO_MAX_LIDER and pos_casa >= posicao_corte_lanterna:
        lider, lanterna, mercado, lider_pos, lanterna_pos = time_fora, time_casa, f"Resultado Final - {time_fora}", pos_fora, pos_casa
    if not lider:
        return None
    print(f"  -> Jogo pré-qualificado para 'Líder vs. Lanterna': {lider} ({lider_pos}º) vs {lanterna} ({lanterna_pos}º)")
    odds = extrair_odds_principais(jogo)
    if not odds or not odds.get('h2h'):
        return None
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
            if not odds or not odds.get('h2h'):
                continue
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
    if not stats_time or stats_time.get('total_jogos_casa', 0) < MIN_JOGOS_HISTORICO:
        return None
    avg_gols_sofridos = stats_time.get('avg_gols_sofridos_casa', 99)
    if avg_gols_sofridos <= FORTALEZA_DEFENSIVA_MAX_AVG_GOLS_SOFRIDOS:
        print(f"  -> Jogo pré-qualificado para 'Fortaleza Defensiva': {time_casa} (Média Sofrida: {avg_gols_sofridos:.2f} gols/jogo)")
        odds = extrair_odds_principais(jogo)
        if not odds:
            return None
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
    avg_gols = stats_confronto.get('avg_gols_h2h', 0)
    if avg_gols >= CLASSICO_GOLS_MIN_AVG:
        print(f"  -> Jogo pré-qualificado para 'Clássico de Gols': {time_casa} vs {time_fora} (Média H2H: {avg_gols:.2f} gols)")
        odds = extrair_odds_principais(jogo)
        if not odds:
            return None
        odd_over_2_5 = odds.get('totals_2_5', {}).get('Over')
        if odd_over_2_5 and odd_over_2_5 >= CLASSICO_GOLS_MIN_ODD_OVER_2_5:
            print(f"  -> ✅ Validação de Odd APROVADA! Odd Over 2.5: {odd_over_2_5}")
            motivo = f"O confronto direto entre essas equipes tem um histórico de muitos gols, com uma média de {avg_gols:.2f} gols por partida."
            return {"type": "aposta", "mercado": "Mais de 2.5", "odd": odd_over_2_5, "emoji": '💥', "nome_estrategia": "CLÁSSICO DE GOLS (HISTÓRICO)", "motivo": motivo}
        else:
            print(f"  -> ❌ Validação de Odd REPROVADA. Odd Over 2.5: {odd_over_2_5 if odd_over_2_5 else 'N/A'}")
    return None

def analisar_goleador_casa(jogo, contexto):
    time_casa = jogo['home_team']
    stats_individuais = contexto['stats_individuais']
    stats_time = stats_individuais.get(time_casa)
    if not stats_time or stats_time.get('total_jogos_casa', 0) < MIN_JOGOS_HISTORICO:
        return None
    avg_gols_marcados = stats_time.get('avg_gols_marcados_casa', 0)
    if avg_gols_marcados >= GOLEADOR_CASA_MIN_AVG_GOLS:
        print(f"  -> Jogo pré-qualificado para 'Goleador da Casa': {time_casa} (Média: {avg_gols_marcados:.2f} gols/jogo)")
        odds = extrair_odds_principais(jogo)
        if not odds:
            return None
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
    if not stats_time_fora or stats_time_fora.get('total_jogos_fora', 0) < MIN_JOGOS_HISTORICO:
        return None
    perc_derrotas = stats_time_fora.get('perc_derrotas_fora', 0)
    if perc_derrotas >= VISITANTE_FRACO_MIN_PERC_DERROTAS:
        print(f"  -> Jogo pré-qualificado para 'Visitante Fraco': {time_fora} ({perc_derrotas:.2f}% de derrotas fora)")
        odds = extrair_odds_principais(jogo)
        if not odds or not odds.get('h2h'):
            return None
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
    if not odds or not odds['h2h']:
        return None
    odds_h2h = {k: v for k, v in odds['h2h'].items() if k != 'Draw'}
    if not odds_h2h:
        return None
    nome_favorito, odd_favorito = min(odds_h2h, key=odds_h2h.get), min(odds_h2h.values())
    nivel = "SUPER FAVORITO" if odd_favorito <= SUPER_FAVORITO_MAX_ODD else ("FAVORITO" if odd_favorito <= FAVORITO_MAX_ODD else None)
    odd_over_1_5 = odds.get('totals_1_5', {}).get('Over')
    if not (nivel and odd_over_1_5 and odd_over_1_5 > ODD_MINIMA_FAVORITO):
        return None
    print(f"  -> Jogo pré-qualificado para 'Ataque do {nivel}': {nome_favorito}")
    relatorio = consultar_forma_sofascore(nome_favorito, contexto['cache_execucao'])
    condicao_forma_geral = relatorio and relatorio['forma'].count('V') >= 3
    condicao_momento_atual = relatorio and relatorio['forma'][-3:].count('V') >= 2
    if condicao_forma_geral and condicao_momento_atual:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Forma: {relatorio['forma']} (Momento Forte)")
        motivo = f"O time favorito ({nome_favorito}) está em boa forma geral ({relatorio['forma'].count('V')} vitórias recentes) e em bom momento atual (ganhou {relatorio['forma'][-3:].count('V')} dos últimos 3 jogos)."
        return {"type": "aposta", "mercado": "Mais de 1.5", "odd": odd_over_1_5, "emoji": '👑', "nome_estrategia": f"ATAQUE DO {nivel} (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA. Forma: {relatorio['forma'] if relatorio else 'N/A'}")
    return None

def analisar_duelo_tatico(jogo, contexto):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['h2h'] or not odds['totals_2_5']:
        return None
    odd_casa, odd_fora, odd_under_2_5 = odds['h2h'].get(jogo['home_team']), odds['h2h'].get(jogo['away_team']), odds['totals_2_5'].get('Under')
    if not (odd_casa and odd_fora and odd_under_2_5 and odd_casa > JOGO_EQUILIBRADO_MIN_ODD and odd_fora > JOGO_EQUILIBRADO_MIN_ODD and odd_under_2_5 > ODD_MINIMA_UNDER_Tatico):
        return None
    print(f"  -> Jogo pré-qualificado para 'Duelo Tático': {jogo['home_team']} vs {jogo['away_team']}")
    cache_execucao = contexto['cache_execucao']
    relatorio_casa = consultar_forma_sofascore(jogo['home_team'], cache_execucao)
    relatorio_fora = consultar_forma_sofascore(jogo['away_team'], cache_execucao)
    if relatorio_casa and relatorio_fora and relatorio_casa['media_gols_partida'] < 2.6 and relatorio_fora['media_gols_partida'] < 2.6:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Média de gols (C|F): {relatorio_casa['media_gols_partida']:.2f} | {relatorio_fora['media_gols_partida']:.2f}")
        motivo = f"Ambas as equipes vêm de jogos com poucos gols. A média de gols recente do time da casa é {relatorio_casa['media_gols_partida']:.2f} e do visitante é {relatorio_fora['media_gols_partida']:.2f}."
        return {"type": "aposta", "mercado": "Menos de 2.5", "odd": odd_under_2_5, "emoji": '♟️', "nome_estrategia": "DUELO TÁTICO (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA.")
    return None

def analisar_mercado_otimista(jogo, contexto):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['totals_1_5'] or not odds['totals_2_5']:
        return None
    odd_over_2_5, odd_over_1_5 = odds['totals_2_5'].get('Over'), odds.get('totals_1_5', {}).get('Over')
    if not (odd_over_2_5 and odd_over_1_5 and odd_over_2_5 <= MERCADO_OTIMISTA_MAX_ODD and odd_over_1_5 > ODD_MINIMA_OVER_Otimista):
        return None
    print(f"  -> Jogo pré-qualificado para 'Mercado Otimista': {jogo['home_team']} vs {jogo['away_team']}")
    cache_execucao = contexto['cache_execucao']
    relatorio_casa = consultar_forma_sofascore(jogo['home_team'], cache_execucao)
    relatorio_fora = consultar_forma_sofascore(jogo['away_team'], cache_execucao)
    if relatorio_casa and relatorio_fora and relatorio_casa['media_gols_partida'] > 2.7 and relatorio_fora['media_gols_partida'] > 2.7:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Média de gols (C|F): {relatorio_casa['media_gols_partida']:.2f} | {relatorio_fora['media_gols_partida']:.2f}")
        motivo = f"Ambas as equipes vêm de jogos com muitos gols. A média de gols recente do time da casa é {relatorio_casa['media_gols_partida']:.2f} e do visitante é {relatorio_fora['media_gols_partida']:.2f}."
        return {"type": "aposta", "mercado": "Mais de 1.5", "odd": odd_over_1_5, "emoji": '📈', "nome_estrategia": "MERCADO OTIMISTA (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA.")
    return None

def analisar_consenso_de_gols(jogo, contexto):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['h2h'] or not odds['totals_2_5']:
        return None
    odds_h2h = {k: v for k, v in odds['h2h'].items() if k != 'Draw'}
    if not odds_h2h:
        return None
    nome_favorito, odd_favorito = min(odds_h2h, key=odds_h2h.get), min(odds_h2h.values())
    odd_over_2_5 = odds['totals_2_5'].get('Over')
    if not (odd_favorito <= CONSENSO_FAVORITO_MAX_ODD and odd_over_2_5 and odd_over_2_5 <= CONSENSO_MERCADO_OVER_MAX_ODD and odd_over_2_5 > CONSENSO_OVER_MIN_ODD_VALOR):
        return None
    print(f"  -> Jogo pré-qualificado para 'Consenso de Gols': {jogo['home_team']} vs {jogo['away_team']}")
    cache_execucao = contexto['cache_execucao']
    relatorio_fav = consultar_forma_sofascore(nome_favorito, cache_execucao)
    relatorio_outro = consultar_forma_sofascore(next(iter(k for k in odds_h2h if k != nome_favorito)), cache_execucao)
    if relatorio_fav and relatorio_outro and relatorio_fav['forma'].count('V') >= 3 and (relatorio_fav['media_gols_partida'] + relatorio_outro['media_gols_partida']) / 2 > 2.8:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Forma do Fav: {relatorio_fav['forma']}, Média Gols: {(relatorio_fav['media_gols_partida'] + relatorio_outro['media_gols_partida']) / 2:.2f}")
        motivo = f"O favorito ({nome_favorito}) está em boa forma ({relatorio_fav['forma'].count('V')} vitórias recentes) e a média de gols combinada das equipes é alta ({(relatorio_fav['media_gols_partida'] + relatorio_outro['media_gols_partida']) / 2:.2f})."
        return {"type": "aposta", "mercado": "Mais de 2.5", "odd": odd_over_2_5, "emoji": '🎯', "nome_estrategia": "CONSENSO DE GOLS (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA.")
    return None

def analisar_consenso_de_defesa(jogo, contexto):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['h2h'] or not odds['totals_2_5']:
        return None
    odd_empate, odd_under_2_5 = odds['h2h'].get('Draw'), odds['totals_2_5'].get('Under')
    if not (odd_empate and odd_under_2_5 and odd_empate <= CONSENSO_EMPATE_MAX_ODD and odd_under_2_5 <= CONSENSO_MERCADO_UNDER_MAX_ODD and odd_under_2_5 > CONSENSO_UNDER_MIN_ODD_VALOR):
        return None
    print(f"  -> Jogo pré-qualificado para 'Consenso de Defesa': {jogo['home_team']} vs {jogo['away_team']}")
    cache_execucao = contexto['cache_execucao']
    relatorio_casa = consultar_forma_sofascore(jogo['home_team'], cache_execucao)
    relatorio_fora = consultar_forma_sofascore(jogo['away_team'], cache_execucao)
    if relatorio_casa and relatorio_fora and relatorio_casa['media_gols_partida'] < 2.5 and relatorio_fora['media_gols_partida'] < 2.5:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Média de gols (C|F): {relatorio_casa['media_gols_partida']:.2f} | {relatorio_fora['media_gols_partida']:.2f}")
        motivo = f"O mercado aponta para um jogo equilibrado (odd do empate baixa) e as equipes têm uma média de gols recente baixa ({relatorio_casa['media_gols_partida']:.2f} e {relatorio_fora['media_gols_partida']:.2f})."
        return {"type": "aposta", "mercado": "Menos de 2.5", "odd": odd_under_2_5, "emoji": '🛡️', "nome_estrategia": "CONSENSO DE DEFESA (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA.")
    return None

def analisar_linha_esticada(jogo, contexto):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['totals_2_5'] or not odds['totals_3_5']:
        return None
    odd_over_2_5, odd_under_3_5 = odds['totals_2_5'].get('Over'), odds['totals_3_5'].get('Under')
    if not (odd_over_2_5 and odd_under_3_5 and odd_over_2_5 < LINHA_ESTICADA_OVER_2_5_MAX_ODD and odd_under_3_5 > LINHA_ESTICADA_UNDER_3_5_MIN_ODD):
        return None
    print(f"  -> Jogo pré-qualificado para 'Linha Esticada': {jogo['home_team']} vs {jogo['away_team']}")
    cache_execucao = contexto['cache_execucao']
    relatorio_casa = consultar_forma_sofascore(jogo['home_team'], cache_execucao)
    relatorio_fora = consultar_forma_sofascore(jogo['away_team'], cache_execucao)
    if relatorio_casa and relatorio_fora and relatorio_casa['media_gols_partida'] < 3.5 and relatorio_fora['media_gols_partida'] < 3.5:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Média de gols (C|F): {relatorio_casa['media_gols_partida']:.2f} | {relatorio_fora['media_gols_partida']:.2f}")
        motivo = f"O mercado espera muitos gols (odd Over 2.5 baixa), mas a média de gols recente das equipes ({relatorio_casa['media_gols_partida']:.2f} e {relatorio_fora['media_gols_partida']:.2f}) sugere que a linha de 3.5 gols está exagerada."
        return {"type": "aposta", "mercado": "Menos de 3.5", "odd": odd_under_3_5, "emoji": '📏', "nome_estrategia": "LINHA ESTICADA (VALIDADA)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA.")
    return None

def analisar_zebra_valorosa(jogo, contexto):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['h2h']:
        return None
    odds_h2h = {k: v for k, v in odds['h2h'].items() if k != 'Draw'}
    if not odds_h2h:
        return None
    nome_favorito, odd_favorito = min(odds_h2h, key=odds_h2h.get), min(odds_h2h.values())
    odd_empate = odds['h2h'].get('Draw')
    if not (odd_favorito < ZEBRA_VALOROSA_FAVORITO_MAX_ODD and odd_empate and ZEBRA_VALOROSA_EMPATE_MIN_ODD <= odd_empate <= ZEBRA_VALOROSA_EMPATE_MAX_ODD):
        return None
    print(f"  -> Jogo pré-qualificado para 'Zebra Valorosa', favorito: {nome_favorito}")
    relatorio_fav = consultar_forma_sofascore(nome_favorito, contexto['cache_execucao'])
    if relatorio_fav and ('D' in relatorio_fav['forma'] or 'E' in relatorio_fav['forma']):
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Forma do favorito tem brechas: {relatorio_fav['forma']}")
        motivo = f"Apesar do favoritismo esmagador, o time favorito ({nome_favorito}) mostrou instabilidade recente ({relatorio_fav['forma']}), o que aumenta o valor da aposta no empate."
        return {"type": "aposta", "mercado": "Empate", "odd": odd_empate, "emoji": '🦓', "nome_estrategia": "ZEBRA VALOROSA (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA. Favorito está 100% vitorioso recentemente.")
    return None

def analisar_mercado_congelado(jogo, contexto):
    return None

def analisar_favorito_conservador(jogo, contexto):
    odds = extrair_odds_principais(jogo)
    if not odds or not odds['h2h'] or not odds['totals_1_5']:
        return None
    odds_h2h = {k: v for k, v in odds['h2h'].items() if k != 'Draw'}
    if not odds_h2h:
        return None
    nome_favorito, odd_favorito = min(odds_h2h, key=odds_h2h.get), min(odds_h2h.values())
    odd_over_1_5 = odds.get('totals_1_5', {}).get('Over')
    if not (odd_favorito <= FAVORITO_CONSERVADOR_MAX_ODD and odd_over_1_5 and odd_over_1_5 > FAVORITO_CONSERVADOR_OVER_1_5_MIN_ODD):
        return None
    print(f"  -> Jogo pré-qualificado para 'Favorito Conservador': {nome_favorito}")
    relatorio = consultar_forma_sofascore(nome_favorito, contexto['cache_execucao'])
    if relatorio and relatorio['forma'].count('V') >= 3:
        print(f"  -> ✅ [Sofascore] Validação APROVADA! Forma: {relatorio['forma']}")
        motivo = f"O time favorito ({nome_favorito}) está em boa forma recente, com {relatorio['forma'].count('V')} vitórias nos últimos {len(relatorio['forma'])} jogos."
        return {"type": "aposta", "mercado": "Mais de 1.5", "odd": odd_over_1_5, "emoji": '💪', "nome_estrategia": "FAVORITO CONSERVADOR (VALIDADO)", "motivo": motivo}
    print(f"  -> ❌ [Sofascore] Validação REPROVADA. Forma: {relatorio['forma'] if relatorio else 'N/A'}")
    return None

def analisar_pressao_mercado(jogo, contexto):
    historico_odds = contexto.get("historico_odds", {})
    jogo_id = jogo.get("id")

    if not jogo_id or jogo_id not in historico_odds:
        return None

    print(f"  -> Analisando 'Pressão do Mercado' para: {jogo['home_team']} vs {jogo['away_team']}")

    dados_antigos = historico_odds[jogo_id]
    odds_antigas = dados_antigos.get("opening_odds", {})
    odds_atuais_data = extrair_odds_principais(jogo)
    if not odds_atuais_data:
        return None
    odds_atuais = odds_atuais_data.get('h2h', {})

    if not odds_antigas or not odds_atuais:
        return None

    odds_antigas_sem_empate = {k: v for k, v in odds_antigas.items() if k != 'Draw'}
    odds_atuais_sem_empate = {k: v for k, v in odds_atuais.items() if k != 'Draw'}

    if not odds_antigas_sem_empate or not odds_atuais_sem_empate:
        return None

    fav_antigo = min(odds_antigas_sem_empate, key=odds_antigas_sem_empate.get)
    fav_atual = min(odds_atuais_sem_empate, key=odds_atuais_sem_empate.get)

    if fav_antigo != fav_atual:
        return None

    odd_antiga = odds_antigas[fav_antigo]
    odd_atual = odds_atuais[fav_atual]

    if not (PRESSAO_MERCADO_OPENING_ODD_MIN <= odd_antiga <= PRESSAO_MERCADO_OPENING_ODD_MAX):
        return None
    if odd_atual > PRESSAO_MERCADO_CURRENT_ODD_MAX:
        return None

    percent_drop = ((odd_antiga - odd_atual) / odd_antiga) * 100

    if percent_drop >= PRESSAO_MERCADO_MIN_ODD_DROP_PERCENT:
        print(f"  -> ✅ PRESSÃO DO MERCADO DETETADA! Odd do {fav_atual} caiu {percent_drop:.2f}% (de {odd_antiga} para {odd_atual})")
        motivo = f"A odd para a vitória do(a) {fav_atual} caiu significativamente em {percent_drop:.2f}%, de {odd_antiga} para {odd_atual}, indicando forte pressão do mercado a seu favor."
        return {"type": "aposta", "mercado": f"Resultado Final - {fav_atual}", "odd": odd_atual, "emoji": '💰', "nome_estrategia": "PRESSÃO DO MERCADO (QUEDA DE ODD)", "motivo": motivo}

    return None

def analisar_dominio_em_cantos(jogo, contexto):
    stats_individuais = contexto['stats_individuais']
    time_casa, time_fora = jogo['home_team'], jogo['away_team']

    stats_casa = stats_individuais.get(time_casa)
    stats_fora = stats_individuais.get(time_fora)

    if not stats_casa or not stats_fora or stats_casa.get('total_jogos_casa', 0) < MIN_JOGOS_HISTORICO or stats_fora.get('total_jogos_fora', 0) < MIN_JOGOS_HISTORICO:
        return None

    condicao_casa_pro = stats_casa.get('avg_escanteios_pro_casa', 0) >= CANTOS_HISTORICO_MIN_AVG_PRO
    condicao_fora_sofre = stats_fora.get('avg_escanteios_contra_fora', 0) >= CANTOS_HISTORICO_MIN_AVG_CONTRA
    soma_pro = stats_casa.get('avg_escanteios_pro_casa', 0) + stats_fora.get('avg_escanteios_pro_fora', 0)
    condicao_soma = soma_pro >= CANTOS_HISTORICO_MIN_SUM_GERAL

    if condicao_casa_pro and condicao_fora_sofre and condicao_soma:
        print(f"  -> ✅ ALERTA DE CANTOS! {time_casa} (média {stats_casa.get('avg_escanteios_pro_casa', 0):.2f}) vs {time_fora} (sofre média {stats_fora.get('avg_escanteios_contra_fora', 0):.2f})")
        motivo = f"O time da casa ({time_casa}) tem uma forte média de escanteios a favor ({stats_casa.get('avg_escanteios_pro_casa', 0):.2f}) e o visitante ({time_fora}) costuma sofrer muitos escanteios ({stats_fora.get('avg_escanteios_contra_fora', 0):.2f}). A soma das médias de escanteios a favor de ambas as equipes é de {soma_pro:.2f}."
        return {"type": "alerta", "emoji": '🚩', "nome_estrategia": "ALERTA DE DOMÍNIO EM CANTOS (HISTÓRICO)", "motivo": motivo}

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
    stats_fora = stats_individuais.get(time_fora)

    if not stats_casa or not stats_fora or stats_casa.get('total_jogos_casa', 0) < MIN_JOGOS_HISTORICO:
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

# --- 4. FUNÇÕES DE ORQUESTRAÇÃO ---

def verificar_apostas_pendentes_sofascore():
    print("\n--- 🔍 Verificando resultados de apostas pendentes (via Sofascore)... ---")
    apostas_pendentes = carregar_json(ARQUIVO_PENDENTES)
    if not apostas_pendentes:
        print("Nenhuma aposta pendente na lista.")
        return

    apostas_restantes = []
    apostas_concluidas = []
    agora_timestamp = int(datetime.now().timestamp())

    for aposta in apostas_pendentes:
        if 'timestamp' in aposta and agora_timestamp > aposta['timestamp'] + (110 * 60):
            resultado_api = buscar_resultado_sofascore(aposta['time_casa'], aposta['time_fora'], aposta['timestamp'])
            if resultado_api and resultado_api != "EM_ANDAMENTO":
                placar_casa, placar_fora = resultado_api['placar_casa'], resultado_api['placar_fora']
                total_gols = placar_casa + placar_fora
                resultado_final = ""
                mercado = aposta['mercado']

                if "Mais de 1.5" in mercado:
                    resultado_final = "GREEN" if total_gols > 1.5 else "RED"
                elif "Mais de 2.5" in mercado:
                    resultado_final = "GREEN" if total_gols > 2.5 else "RED"
                elif "Menos de 2.5" in mercado:
                    resultado_final = "GREEN" if total_gols < 2.5 else "RED"
                elif "Menos de 3.5" in mercado:
                    resultado_final = "GREEN" if total_gols < 3.5 else "RED"
                elif "Empate" in mercado:
                    resultado_final = "GREEN" if placar_casa == placar_fora else "RED"
                elif f"Resultado Final - {aposta['time_casa']}" in mercado:
                    resultado_final = "GREEN" if placar_casa > placar_fora else "RED"
                elif f"Resultado Final - {aposta['time_fora']}" in mercado:
                    resultado_final = "GREEN" if placar_fora > placar_casa else "RED"
                elif "Ambas as Equipas Marcam - Sim" in mercado:
                    resultado_final = "GREEN" if placar_casa > 0 and placar_fora > 0 else "RED"

                if resultado_final:
                    print(f"  -> Resultado encontrado para {aposta['nome_jogo']}: {resultado_final}")
                    aposta['resultado'] = resultado_final

                    mensagem_resultado = registrar_resultado(aposta, resultado_final, placar_casa, placar_fora)
                    enviar_alerta_telegram(mensagem_resultado)
                    apostas_concluidas.append(aposta)
                else:
                    apostas_restantes.append(aposta)
            else:
                apostas_restantes.append(aposta)
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
    data_primeiro_resultado = datetime.fromtimestamp(resultados_ontem[0]['timestamp']).date()
    data_hoje = datetime.now(timezone(timedelta(hours=-3))).date()
    if data_primeiro_resultado < data_hoje:
        greens = len([r for r in resultados_ontem if r['resultado'] == 'GREEN'])
        reds = len([r for r in resultados_ontem if r['resultado'] == 'RED'])
        total = len(resultados_ontem)
        assertividade = (greens / total * 100) if total > 0 else 0
        placar_estrategias = {}
        for res in resultados_ontem:
            estrategia = res.get('estrategia', 'Desconhecida')
            placar_estrategias.setdefault(estrategia, {'GREEN': 0, 'RED': 0})
            if res['resultado'] == 'GREEN':
                placar_estrategias[estrategia]['GREEN'] += 1
            elif res['resultado'] == 'RED':
                placar_estrategias[estrategia]['RED'] += 1
        texto_detalhado_lista = []
        for estrategia, placar in sorted(placar_estrategias.items()):
            g, r = placar['GREEN'], placar['RED']
            texto_detalhado_lista.append(f"*{estrategia}:* {g} ✅ / {r} 🔴")
        texto_detalhado = "\n".join(texto_detalhado_lista)

        linhas_mensagem = [
            f"📊 *Resumo de Desempenho - {data_primeiro_resultado.strftime('%d/%m/%Y')}* 📊", "",
            "*Placar Geral:*", f"✅ *GREENs:* {greens}", f"🔴 *REDs:* {reds}",
            f"📈 *Assertividade:* {assertividade:.2f}%", f"💰 *Total de Entradas:* {total}", "",
            "--------------------------", "*Desempenho por Estratégia:*", texto_detalhado
        ]
        resumo_msg = "\n".join(linhas_mensagem)
        enviar_alerta_telegram(resumo_msg)
        historico_completo = carregar_json(ARQUIVO_HISTORICO_APOSTAS)
        historico_completo.extend(resultados_ontem)
        salvar_json(historico_completo, ARQUIVO_HISTORICO_APOSTAS)
        salvar_json([], ARQUIVO_RESULTADOS_DIA)
        print("Resumo de ontem enviado e resultados arquivados.")
    else:
        print("Os resultados no diário de bordo são de hoje. O resumo será gerado amanhã.")

def gerar_e_enviar_resumo_semanal():
    print("\n--- 🗓️ Verificando se é dia de enviar o resumo semanal... ---")
    fuso_horario = timezone(timedelta(hours=-3))
    hoje = datetime.now(fuso_horario)
    if hoje.weekday() != DIA_DO_RELATORIO_SEMANAL:
        print(f"Hoje não é o dia do relatório semanal. O relatório não será enviado.")
        return
    nome_arquivo_flag = f"relatorio_semanal_{hoje.strftime('%Y-%m-%d')}.flag"
    if os.path.exists(nome_arquivo_flag):
        print("O relatório semanal para hoje já foi enviado.")
        return
    print("-> ✅ Hoje é dia de relatório! Compilando os dados da semana...")
    apostas_totais = carregar_json(ARQUIVO_HISTORICO_APOSTAS) + carregar_json(ARQUIVO_RESULTADOS_DIA)
    if not apostas_totais:
        print("Nenhum dado histórico para gerar o resumo semanal.")
        return
    sete_dias_atras = hoje - timedelta(days=7)
    apostas_da_semana = [aposta for aposta in apostas_totais if datetime.fromtimestamp(aposta.get('timestamp', 0), tz=fuso_horario) >= sete_dias_atras]
    if not apostas_da_semana:
        print("Nenhuma aposta encontrada na última semana.")
        with open(nome_arquivo_flag, 'w') as f:
            f.write(str(hoje))
        return
    greens = len([r for r in apostas_da_semana if r.get('resultado') == 'GREEN'])
    reds = len([r for r in apostas_da_semana if r.get('resultado') == 'RED'])
    total = len(apostas_da_semana)
    assertividade = (greens / total * 100) if total > 0 else 0
    placar_estrategias = {}
    for res in apostas_da_semana:
        estrategia = res.get('estrategia', 'Desconhecida')
        placar_estrategias.setdefault(estrategia, {'GREEN': 0, 'RED': 0})
        if res.get('resultado') == 'GREEN':
            placar_estrategias[estrategia]['GREEN'] += 1
        elif res.get('resultado') == 'RED':
            placar_estrategias[estrategia]['RED'] += 1
    texto_detalhado_lista = []
    estrategias_ordenadas = sorted(placar_estrategias.items(), key=lambda item: item[1]['GREEN'], reverse=True)
    for estrategia, placar in estrategias_ordenadas:
        g, r = placar['GREEN'], placar['RED']
        texto_detalhado_lista.append(f"*{estrategia}:* {g} ✅ / {r} 🔴")
    texto_detalhado = "\n".join(texto_detalhado_lista)
    data_inicio_str = sete_dias_atras.strftime('%d/%m/%Y')
    data_fim_str = hoje.strftime('%d/%m/%Y')

    linhas_mensagem = [
        f"📊 *Resumo Semanal de Desempenho* 📊", "",
        f"*🗓️ Período:* {data_inicio_str} a {data_fim_str}", "",
        "*Placar Geral da Semana:*", f"✅ *GREENs:* {greens}", f"🔴 *REDs:* {reds}",
        f"📈 *Assertividade:* {assertividade:.2f}%", f"💰 *Total de Entradas:* {total}", "",
        "--------------------------", "*Desempenho por Estratégia na Semana:*", texto_detalhado
    ]
    resumo_msg = "\n".join(linhas_mensagem)
    enviar_alerta_telegram(resumo_msg)
    with open(nome_arquivo_flag, 'w') as f:
        f.write(str(hoje))
    print(f"✅ Relatório semanal enviado com sucesso! Ficheiro de controlo '{nome_arquivo_flag}' criado.")


# --- 5. FUNÇÃO PRINCIPAL ---

def rodar_analise_completa():
    gerar_e_enviar_resumo_diario()
    gerar_e_enviar_resumo_semanal()
    verificar_apostas_pendentes_sofascore()

    print(f"\n--- 🦅 Iniciando busca... ---")

    url_base = f"https://api.the-odds-api.com/v4/sports/soccer/odds?apiKey={API_KEY_ODDS}&regions=eu,us,uk,au&bookmakers={CASA_ALVO}&oddsFormat=decimal"
    url_jogos_principais = f"{url_base}&markets=h2h,totals"
    jogos_do_dia = []
    try:
        response_jogos = requests.get(url_jogos_principais, timeout=30)
        response_jogos.raise_for_status()
        jogos_do_dia = response_jogos.json()
    except requests.exceptions.RequestException as e:
        print(f"  > ERRO na busca principal de jogos: {e}")
        return

    url_jogos_btts = f"{url_base}&markets=both_teams_to_score"
    dados_btts = {}
    try:
        response_btts = requests.get(url_jogos_btts, timeout=30)
        response_btts.raise_for_status()
        jogos_com_btts = response_btts.json()
        dados_btts = {jogo['id']: jogo for jogo in jogos_com_btts}
        print(f"  -> Encontradas odds de BTTS para {len(dados_btts)} jogos.")
    except requests.exceptions.RequestException as e:
        print(f"  > ERRO na busca de odds BTTS: {e}")

    salvar_odds_futuras(jogos_do_dia)

    contexto = {
        "cache_execucao": {}, "cache_classificacao": {},
        "mapa_ligas": carregar_json(ARQUIVO_MAPA_LIGAS),
        "stats_individuais": {}, "stats_h2h": {},
        "dados_btts": dados_btts,
        "historico_odds": carregar_json(ARQUIVO_HISTORICO_ODDS)
    }

    if jogos_do_dia:
        contexto['cache_execucao'] = pre_buscar_dados_sofascore(jogos_do_dia, contexto['cache_execucao'])

    try:
        df_historico = pd.read_csv(ARQUIVO_HISTORICO_CORRIGIDO, low_memory=False)
        contexto["stats_individuais"], contexto["stats_h2h"] = calcular_estatisticas_historicas(df_historico)
    except FileNotFoundError:
        print(f"  -> ⚠️ AVISO: Arquivo '{ARQUIVO_HISTORICO_CORRIGIDO}' não encontrado. Estratégias históricas desativadas.")

    jogos_analisados, nomes_jogos_analisados, alerta_de_aposta_enviado_geral = 0, [], False
    if jogos_do_dia:
        fuso_brasilia, fuso_utc = timezone(timedelta(hours=-3)), timezone.utc
        agora_utc = datetime.now(timezone.utc)

        lista_de_funcoes = [
            analisar_tendencia_escanteios, analisar_ambas_marcam, analisar_lider_vs_lanterna,
            analisar_reacao_gigante, analisar_fortaleza_defensiva, analisar_classico_de_gols,
            analisar_goleador_casa, analisar_visitante_fraco, analisar_mandante_fraco, analisar_favoritos_em_niveis,
            analisar_duelo_tatico, analisar_mercado_otimista, analisar_consenso_de_gols,
            analisar_consenso_de_defesa, analisar_linha_esticada, analisar_zebra_valorosa,
            analisar_favorito_conservador, analisar_pressao_mercado,
            analisar_dominio_em_cantos, analisar_pressao_ofensiva, analisar_jogo_agressivo,
            analisar_pressao_ofensiva_extrema
        ]

        for jogo in jogos_do_dia:
            time_casa, time_fora = jogo['home_team'], jogo['away_team']
            if not jogo.get('bookmakers'):
                continue

            inicio_jogo_dt = datetime.fromisoformat(jogo['commence_time'].replace('Z', '+00:00'))
            is_live = inicio_jogo_dt < agora_utc

            jogos_analisados += 1
            nomes_jogos_analisados.append(f"⚽ {time_casa} vs {time_fora}")
            print(f"\n--------------------------------------------------\nAnalisando Jogo: {time_casa} vs {time_fora}{' (AO VIVO)' if is_live else ''}")

            for func in lista_de_funcoes:
                oportunidade = func(jogo, contexto)
                if not oportunidade:
                    continue

                if oportunidade.get('type') == 'alerta':
                    print(f"  -> ✅ ALERTA ENCONTRADO: {oportunidade['nome_estrategia']}")
                    alerta_de_aposta_enviado_geral = True
                    data_hora = inicio_jogo_dt.astimezone(fuso_brasilia).strftime('%d/%m/%Y às %H:%M')

                    linhas_alerta = [
                        f"*{oportunidade['emoji']} {oportunidade['nome_estrategia']} {oportunidade['emoji']}*", "",
                        f"*⚽ JOGO:* {time_casa} vs {time_fora}", f"*🏆 LIGA:* {jogo.get('sport_title', 'N/A')}", f"*🗓️ DATA:* {data_hora}", "",
                        "*🔍 Análise do Falcão:*", f"_{oportunidade['motivo']}_",
                    ]

                    if "OBSERVAÇÃO AO VIVO" in oportunidade.get('nome_estrategia', ''):
                         linhas_alerta.extend(["", "_*NOTA: Isto é apenas um alerta de observação. Nenhuma aposta foi feita._"])

                    alerta = "\n".join(linhas_alerta)
                    enviar_alerta_telegram(alerta)

                elif oportunidade.get('type') == 'aposta':
                    if is_live:
                        print(f"  -> ⚠️ Oportunidade de APOSTA encontrada em jogo AO VIVO. Convertendo para ALERTA (Modo Observação).")
                        alerta_de_aposta_enviado_geral = True
                        data_hora = inicio_jogo_dt.astimezone(fuso_brasilia).strftime('%d/%m/%Y às %H:%M')
                        mercado_str = oportunidade['mercado']
                        if "Mais de" in mercado_str or "Menos de" in mercado_str:
                            mercado_str += " Gols"

                        linhas_alerta = [
                            f"*{oportunidade['emoji']} OPORTUNIDADE AO VIVO (OBSERVAÇÃO) {oportunidade['emoji']}*", "",
                            f"*Estratégia:* {oportunidade['nome_estrategia']}", "",
                            f"*⚽ JOGO:* {time_casa} vs {time_fora}",
                            f"*📈 MERCADO SUGERIDO:* {mercado_str}",
                            f"*📊 ODD NO MOMENTO:* *{oportunidade['odd']}*", "",
                            "*🔍 Análise do Falcão:*", f"_{oportunidade.get('motivo', 'N/A')}_", "",
                            "_*NOTA: Isto é apenas um alerta de observação. Nenhuma aposta foi feita._"
                        ]
                        alerta = "\n".join(linhas_alerta)
                        enviar_alerta_telegram(alerta)
                    else:
                        if oportunidade.get('odd', 0) >= ODD_MINIMA_GLOBAL:
                            print(f"  -> ✅ OPORTUNIDADE PRÉ-JOGO APROVADA ({oportunidade['odd']} >= {ODD_MINIMA_GLOBAL})")
                            alerta_de_aposta_enviado_geral = True

                            banca = carregar_banca()
                            stake = calcular_stake(oportunidade['odd'], banca)
                            saldo_atual = banca.get('banca_atual')

                            data_hora = inicio_jogo_dt.astimezone(fuso_brasilia).strftime('%d/%m/%Y às %H:%M')
                            mercado_str = oportunidade['mercado']
                            if "Mais de" in mercado_str or "Menos de" in mercado_str:
                                mercado_str += " Gols"

                            linhas_alerta = [
                                f"*{oportunidade['emoji']} ENTRADA VALIDADA ({oportunidade['nome_estrategia']}) {oportunidade['emoji']}*", "",
                                f"*⚽ JOGO:* {time_casa} vs {time_fora}",
                                f"*📈 MERCADO:* {mercado_str}",
                                f"*📊 ODD ENCONTRADA:* *{oportunidade['odd']}*",
                                f"*💰 STAKE SUGERIDA:* *R$ {stake:.2f}*", "",
                                f"*🏦 Saldo Pré-Aposta:* R$ {saldo_atual:.2f}"
                            ]
                            if 'motivo' in oportunidade and oportunidade['motivo']:
                                linhas_alerta.extend(["", "*🔍 Análise do Falcão:*", f"_{oportunidade['motivo']}_"])

                            alerta = "\n".join(linhas_alerta)
                            enviar_alerta_telegram(alerta)

                            timestamp_utc = inicio_jogo_dt.replace(tzinfo=timezone.utc).timestamp()
                            nova_aposta = {
                                "id_api": jogo['id'], "nome_jogo": f"{time_casa} vs {time_fora}", "time_casa": time_casa,
                                "time_fora": time_fora, "mercado": oportunidade['mercado'], "timestamp": int(timestamp_utc),
                                "estrategia": oportunidade['nome_estrategia'], "odd": oportunidade['odd'], "stake": stake
                            }
                            apostas_pendentes = carregar_json(ARQUIVO_PENDENTES)
                            apostas_pendentes.append(nova_aposta)
                            salvar_json(apostas_pendentes, ARQUIVO_PENDENTES)
                        else:
                            print(f"  -> ❌ OPORTUNIDADE PRÉ-JOGO REPROVADA PELA ODD MÍNIMA ({oportunidade.get('odd', 0)} < {ODD_MINIMA_GLOBAL})")

    print("\n--- Análise deste ciclo finalizada. ---")
    if not alerta_de_aposta_enviado_geral:
        data_hoje_str = datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y às %H:%M')
        jogos_texto = "\n".join(nomes_jogos_analisados[:15])
        if len(nomes_jogos_analisados) > 15:
            jogos_texto += f"\n...e mais {len(nomes_jogos_analisados) - 15} jogos."
        total_pendentes = len(carregar_json(ARQUIVO_PENDENTES))

        linhas_mensagem = [
            f"🦅 *Relatório do Falcão da ODDS*", "", f"🗓️ *Data:* {data_hoje_str}", "-----------------------------------", "", "🔍 *Resumo:*",
            "- Verifiquei e processei resultados antigos.", f"- Analisei *{jogos_analisados}* jogos com o arsenal completo de estratégias.",
            f"- Atualmente, há *{total_pendentes}* apostas em aberto.", "", "🚫 *Resultado:*", "Nenhuma oportunidade de alta qualidade encontrada neste ciclo.",
            "", "🗒️ *Jogos Verificados:*", f"{jogos_texto if jogos_texto else 'Nenhum jogo encontrado.'}", "", "Continuo monitorando! 🕵️‍♂️"
        ]
        mensagem_status = "\n".join(linhas_mensagem)
        print("Nenhuma oportunidade encontrada. Enviando relatório de status...")
        enviar_alerta_telegram(mensagem_status)


# --- 6. PONTO DE ENTRADA ---
if __name__ == "__main__":
    print("--- Iniciando execução única do bot ---")
    if not all([API_KEY_ODDS, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
        print("❌ ERRO FATAL: Chaves de API/Telegram não configuradas.")
    else:
        rodar_analise_completa()
    print("--- Execução finalizada com sucesso. ---")