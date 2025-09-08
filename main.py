# Arquivo: main.py
# Descrição: Orquestrador principal do bot Falcão das Odds.

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
    buscar_resultado_sofascore,
    buscar_jogos_ao_vivo,
    buscar_estatisticas_ao_vivo
)
from utils import carregar_json, salvar_json
from config import *
from estrategias import *

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
ARQUIVO_CACHE_SOFASCORE = 'sofascore_cache.json' # Novo arquivo de cache

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

def calcular_estatisticas_por_liga(df):
    print("  -> 📊 Calculando estatísticas médias por liga...")
    NOME_COLUNA_LIGA = 'League'

    if df.empty or NOME_COLUNA_LIGA not in df.columns:
        print(f"  -> ⚠️ AVISO: Coluna da liga ('{NOME_COLUNA_LIGA}') não encontrada. As estatísticas de liga não serão usadas.")
        return {}

    cols_stats = ['FTHG', 'FTAG', 'HC', 'AC', 'HY', 'AY']
    for col in cols_stats:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    df['TotalGols'] = df['FTHG'] + df['FTAG']
    df['TotalCantos'] = df['HC'] + df['AC']
    df['TotalCartoesAmarelos'] = df['HY'] + df['AY']

    stats_ligas = df.groupby(NOME_COLUNA_LIGA).agg(
        avg_gols_por_jogo=('TotalGols', 'mean'),
        avg_cantos_por_jogo=('TotalCantos', 'mean'),
        avg_cartoes_por_jogo=('TotalCartoesAmarelos', 'mean')
    ).to_dict('index')

    print(f"  -> Médias calculadas para {len(stats_ligas)} ligas.")
    return stats_ligas

def pre_buscar_dados_sofascore(jogos_do_dia):
    print("\n--- 🧠 Pré-buscando dados do Sofascore com cache persistente ---")

    cache_persistente = carregar_json(ARQUIVO_CACHE_SOFASCORE)
    cache_alterado = False

    times_unicos = set()
    for jogo in jogos_do_dia:
        times_unicos.add(jogo['home_team'])
        times_unicos.add(jogo['away_team'])

    print(f"  -> Encontrados {len(times_unicos)} times únicos para buscar dados.")

    agora = datetime.now(timezone.utc)

    for i, time_nome in enumerate(list(times_unicos)):
        dados_time = cache_persistente.get(time_nome)

        if dados_time:
            timestamp_cache = datetime.fromisoformat(dados_time['timestamp'])
            idade_cache = agora - timestamp_cache
            if idade_cache < timedelta(hours=CACHE_EXPIRATION_HOURS):
                print(f"  -> [CACHE HIT] Usando dados em cache para: {time_nome}")
                continue

        print(f"  -> [CACHE MISS] Buscando novos dados para: {time_nome} ({i+1}/{len(times_unicos)})")
        cache_temporario_para_funcao = {}
        novo_dado = consultar_forma_sofascore(time_nome, cache_temporario_para_funcao)

        if novo_dado:
            cache_persistente[time_nome] = {
                'data': novo_dado,
                'timestamp': agora.isoformat()
            }
            cache_alterado = True

        time.sleep(2)

    if cache_alterado:
        print("  -> Salvando cache atualizado no arquivo...")
        salvar_json(cache_persistente, ARQUIVO_CACHE_SOFASCORE)

    cache_execucao_final = {time: dados['data'] for time, dados in cache_persistente.items() if 'data' in dados}

    print("  -> ✅ Pré-busca de dados do Sofascore concluída.")
    return cache_execucao_final

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
        "cache_execucao": {},
        "cache_classificacao": {},
        "mapa_ligas": carregar_json(ARQUIVO_MAPA_LIGAS),
        "stats_individuais": {},
        "stats_h2h": {},
        "dados_btts": dados_btts,
        "historico_odds": carregar_json(ARQUIVO_HISTORICO_ODDS),
        "stats_ligas": {}
    }

    if jogos_do_dia:
        contexto['cache_execucao'] = pre_buscar_dados_sofascore(jogos_do_dia)

    try:
        df_historico = pd.read_csv(ARQUIVO_HISTORICO_CORRIGIDO, low_memory=False)
        contexto["stats_individuais"], contexto["stats_h2h"] = calcular_estatisticas_historicas(df_historico)
        contexto["stats_ligas"] = calcular_estatisticas_por_liga(df_historico.copy())
    except FileNotFoundError:
        print(f"  -> ⚠️ AVISO: Arquivo '{ARQUIVO_HISTORICO_CORRIGIDO}' não encontrado. Estratégias históricas desativadas.")

    jogos_analisados = 0
    apostas_feitas_neste_ciclo = []
    alertas_enviados_neste_ciclo = 0

    apostas_pendentes_atuais = carregar_json(ARQUIVO_PENDENTES)
    ids_apostas_pendentes = {aposta['id_api'] for aposta in apostas_pendentes_atuais}

    if jogos_do_dia:
        fuso_brasilia, fuso_utc = timezone(timedelta(hours=-3)), timezone.utc
        agora_utc = datetime.now(timezone.utc)

        lista_de_funcoes = [
            analisar_tendencia_escanteios, analisar_ambas_marcam, analisar_lider_vs_lanterna,
            analisar_reacao_gigante, analisar_fortaleza_defensiva, analisar_classico_de_gols,
            analisar_goleador_casa, analisar_visitante_fraco, analisar_mandante_fraco, analisar_favoritos_em_niveis,
            # analisar_duelo_tatico, # DESATIVADA
            analisar_mercado_otimista, analisar_consenso_de_gols,
            analisar_consenso_de_defesa, analisar_linha_esticada, analisar_zebra_valorosa,
            analisar_favorito_conservador, analisar_pressao_mercado,
            analisar_dominio_em_cantos, analisar_pressao_ofensiva, analisar_jogo_agressivo,
            analisar_pressao_ofensiva_extrema
        ]

        for jogo in jogos_do_dia:
            if jogo['id'] in ids_apostas_pendentes:
                print(f"\n-> Jogo '{jogo['home_team']} vs {jogo['away_team']}' já possui uma aposta pendente. Pulando análise.")
                continue

            time_casa, time_fora = jogo['home_team'], jogo['away_team']
            if not jogo.get('bookmakers'):
                continue

            inicio_jogo_dt = datetime.fromisoformat(jogo['commence_time'].replace('Z', '+00:00'))
            is_live = inicio_jogo_dt < agora_utc

            jogos_analisados += 1
            print(f"\n--------------------------------------------------\nAnalisando Jogo: {time_casa} vs {time_fora}{' (AO VIVO)' if is_live else ''}")

            for func in lista_de_funcoes:
                try:
                    oportunidade = func(jogo, contexto)
                except NameError:
                    continue

                if not oportunidade:
                    continue

                if oportunidade.get('type') == 'alerta':
                    print(f"   -> ✅ ALERTA ENCONTRADO: {oportunidade['nome_estrategia']}")
                    alertas_enviados_neste_ciclo += 1
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
                        alertas_enviados_neste_ciclo += 1
                        data_hora = inicio_jogo_dt.astimezone(fuso_brasilia).strftime('%d/%m/%Y às %H:%M')
                        mercado_str = oportunidade['mercado']
                        if "Mais de" in mercado_str or "Menos de" in mercado_str:
                            mercado_str += " Gols"

                        odd_da_aposta = oportunidade.get('odd', 'N/A')
                        # risco_calculado = classificar_odd(odd_da_aposta) # A função classificar_odd não foi fornecida no código original

                        linhas_alerta = [
                            f"*{oportunidade['emoji']} OPORTUNIDADE AO VIVO (OBSERVAÇÃO) {oportunidade['emoji']}*", "",
                            f"*Estratégia:* {oportunidade['nome_estrategia']}", "",
                            f"*⚽ JOGO:* {time_casa} vs {time_fora}",
                            f"*📈 MERCADO SUGERIDO:* {mercado_str}",
                            f"*📊 ODD NO MOMENTO:* *{odd_da_aposta}*",
                            # f"⚖️ *Risco Percebido:* {risco_calculado}",
                            "",
                            "*🔍 Análise do Falcão:*", f"_{oportunidade.get('motivo', 'N/A')}_", "",
                            "_*NOTA: Isto é apenas um alerta de observação. Nenhuma aposta foi feita._"
                        ]
                        alerta = "\n".join(linhas_alerta)
                        enviar_alerta_telegram(alerta)
                    else:
                        if oportunidade.get('odd', 0) >= ODD_MINIMA_GLOBAL:
                            print(f"  -> ✅ OPORTUNIDADE PRÉ-JOGO APROVADA ({oportunidade['odd']} >= {ODD_MINIMA_GLOBAL})")
                            apostas_feitas_neste_ciclo.append(oportunidade)

                            banca = carregar_banca()
                            stake = calcular_stake(oportunidade['odd'], banca)
                            saldo_atual = banca.get('banca_atual')

                            data_hora = inicio_jogo_dt.astimezone(fuso_brasilia).strftime('%d/%m/%Y às %H:%M')
                            mercado_str = oportunidade['mercado']
                            if "Mais de" in mercado_str or "Menos de" in mercado_str:
                                mercado_str += " Gols"

                            odd_da_aposta = oportunidade.get('odd')
                            # risco_calculado = classificar_odd(odd_da_aposta) # A função classificar_odd não foi fornecida no código original

                            linhas_alerta = [
                                f"*{oportunidade['emoji']} ENTRADA VALIDADA ({oportunidade['nome_estrategia']}) {oportunidade['emoji']}*", "",
                                f"*⚽ JOGO:* {time_casa} vs {time_fora}",
                                f"*📈 MERCADO:* {mercado_str}",
                                f"*📊 ODD ENCONTRADA:* *{odd_da_aposta}*",
                                # f"⚖️ *Risco Percebido:* {risco_calculado}",
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

    print("\n--- Análise deste ciclo finalizada. Gerando relatório de status... ---")

    apostas_pendentes_final = carregar_json(ARQUIVO_PENDENTES)
    total_pendentes = len(apostas_pendentes_final)

    texto_pendentes_lista = []
    if total_pendentes > 0:
        texto_pendentes_lista.append("\n\n*🔔 Apostas Pendentes:*")
        for aposta in apostas_pendentes_final:
            texto_pendentes_lista.append(f"- {aposta['nome_jogo']} ({aposta['mercado']})")
    texto_pendentes = "\n".join(texto_pendentes_lista)

    data_hoje_str = datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y às %H:%M')

    linhas_mensagem = [
        f"🦅 *Relatório do Falcão da ODDS*", "", f"🗓️ *Data:* {data_hoje_str}", "-----------------------------------", "",
        "🔍 *Resumo da Execução:*",
        f"- *{jogos_analisados}* jogos analisados.",
        f"- *{total_pendentes}* apostas estão em aberto no momento.", ""
    ]

    novas_entradas_count = len(apostas_feitas_neste_ciclo)
    if novas_entradas_count > 0:
        linhas_mensagem.append(f"✅ *{novas_entradas_count}* nova(s) oportunidade(s) de aposta encontradas e enviadas!")
    elif alertas_enviados_neste_ciclo > 0:
        linhas_mensagem.append(f"⚠️ *{alertas_enviados_neste_ciclo}* novo(s) alerta(s) estatístico(s) enviados.")
    else:
        linhas_mensagem.append("🚫 *Nenhuma nova oportunidade ou alerta de alta qualidade encontrados neste ciclo.*")

    if texto_pendentes:
        linhas_mensagem.append(texto_pendentes)

    mensagem_status = "\n".join(linhas_mensagem)
    enviar_alerta_telegram(mensagem_status)

# --- NOVA FUNÇÃO DE ORQUESTRAÇÃO PARA JOGOS AO VIVO (ADICIONADA) ---

def rodar_analise_ao_vivo():
    """
    Orquestra a busca e análise de jogos que estão acontecendo em tempo real.
    """
    print("\n\n--- 🚀 Iniciando análise de jogos AO VIVO (In-Play)... ---")

    jogos_ao_vivo = buscar_jogos_ao_vivo()
    if not jogos_ao_vivo:
        print("  -> Nenhum jogo ao vivo encontrado no momento.")
        return

    estrategias_in_play = [
        # analisar_pressao_fim_de_jogo # Exemplo, a função precisa ser criada
    ]

    jogos_filtrados = [j for j in jogos_ao_vivo if 'half' in j.get('tempo_jogo', '').lower()]
    print(f"  -> {len(jogos_filtrados)} jogos filtrados para análise aprofundada.")

    for jogo in jogos_filtrados:
        estatisticas = buscar_estatisticas_ao_vivo(jogo['id_sofascore'])
        time.sleep(1.5)

        if estatisticas:
            for estrategia_func in estrategias_in_play:
                oportunidade = estrategia_func(jogo, estatisticas)
                if oportunidade:
                    data_hora = datetime.now(timezone(timedelta(hours=-3))).strftime('%H:%M')

                    linhas_alerta = [
                        f"*{oportunidade['emoji']} {oportunidade['nome_estrategia']} {oportunidade['emoji']}*", "",
                        f"*⚽ JOGO:* {jogo['time_casa']} vs {jogo['time_fora']}",
                        f"*🏆 LIGA:* {jogo.get('liga', 'N/A')}",
                        f"*⏰ PLACAR ATUAL:* {jogo['placar_casa']} - {jogo['placar_fora']} ({jogo['tempo_jogo']})", "",
                        "*🔍 Análise do Falcão:*", f"_{oportunidade['motivo']}_",
                    ]
                    alerta = "\n".join(linhas_alerta)
                    enviar_alerta_telegram(alerta)

    print("--- 🏁 Análise de jogos ao vivo concluída. ---")


# --- 6. PONTO DE ENTRADA ---
if __name__ == "__main__":
    print("--- Iniciando execução única do bot ---")

    if not all([API_KEY_ODDS, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
        print("❌ ERRO FATAL: Chaves de API/Telegram não configuradas nos Secrets.")
    else:
        try:
            # Nota: A função classificar_odd() é chamada no código mas não foi definida.
            # Você precisará adicioná-la ou remover as chamadas a ela.
            rodar_analise_completa()
            rodar_analise_ao_vivo()
            print("\n--- Ciclo único de análise (Pré-jogo + Ao Vivo) concluído com sucesso. ---")
        except Exception as e:
            print(f"❌ Ocorreu um erro inesperado durante a execução: {e}")