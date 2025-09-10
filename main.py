import os
import requests
import json
from datetime import datetime, timezone, timedelta
import time
from thefuzz import fuzz
import pandas as pd
from decouple import Config, RepositoryEnv

print("--- Iniciando ROBÔ FALCÃO (Versão Única e Completa) ---")

# --- PARTE 1: CONFIGURAÇÃO ---
try:
    DOTENV_PATH = os.path.join(os.path.dirname(__file__), '.env')
    env_config = Config(RepositoryEnv(DOTENV_PATH))
    TELEGRAM_TOKEN = env_config('TELEGRAM_TOKEN')
    TELEGRAM_CHAT_ID = env_config('TELEGRAM_CHAT_ID')
    API_KEY_ODDS = env_config('API_KEY_ODDS')
    API_KEY_FOOTBALL = env_config('API_KEY_FOOTBALL')
    print("✅ Chaves de API lidas com sucesso.")
except Exception as e:
    print(f"❌ ERRO FATAL ao ler o arquivo .env: {e}")
    exit()

CASA_ALVO = 'pinnacle'
ODD_MINIMA_GLOBAL = 1.50
MIN_JOGOS_HISTORICO = 6
MIN_JOGOS_H2H = 3
GIGANTE_MIN_PERC_VITORIAS = 60.0
GIGANTE_MIN_ODD_VITORIA = 1.40
CLASSICO_GOLS_MIN_AVG = 3.0
CLASSICO_GOLS_MIN_ODD_OVER_2_5 = 1.70
VISITANTE_FRACO_MIN_PERC_DERROTAS = 50.0
VISITANTE_FRACO_ODD_CASA_MIN = 1.40
VISITANTE_FRACO_ODD_CASA_MAX = 4.00
ARQUIVO_HISTORICO_CORRIGIDO = 'dados_historicos_corrigido.csv'


# --- PARTE 2: FUNÇÕES DE API EXTERNAS ---

def buscar_jogos_api_football(api_key):
    hoje_str = datetime.now().strftime('%Y-%m-%d')
    print(f"--- 📡 Buscando jogos do dia {hoje_str} na API-Football... ---")
    url = "https://v3.football.api-sports.io/fixtures"
    params = {"date": hoje_str}
    headers = {"x-apisports-key": api_key}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
        response.raise_for_status()
        dados = response.json()
        jogos_do_dia = []
        for jogo_data in dados.get('response', []):
            fixture = jogo_data.get('fixture', {})
            teams = jogo_data.get('teams', {})
            league = jogo_data.get('league', {})
            if fixture.get('status', {}).get('short') != 'NS': continue
            jogo = {
                "home_team": teams.get('home', {}).get('name', 'N/A'),
                "away_team": teams.get('away', {}).get('name', 'N/A'),
                "liga": league.get('name', 'N/A'),
            }
            jogos_do_dia.append(jogo)
        print(f"  -> ✅ Sucesso! Encontrados {len(jogos_do_dia)} jogos agendados.")
        return jogos_do_dia
    except requests.exceptions.RequestException as e:
        print(f"  -> ❌ ERRO ao buscar jogos na API-Football: {e}")
        return []

def buscar_odds_the_odds_api(api_key):
    print("\n--- 💰 Buscando odds na The Odds API... ---")
    url_odds = f"https://api.the-odds-api.com/v4/sports/soccer/odds?apiKey={api_key}&regions=eu,us,uk,au&bookmakers={CASA_ALVO}&oddsFormat=decimal&markets=h2h,totals"
    try:
        response_odds = requests.get(url_odds, timeout=30)
        response_odds.raise_for_status()
        jogos_com_odds = response_odds.json()
        print(f"  -> Encontradas odds para {len(jogos_com_odds)} jogos.")
        return jogos_com_odds
    except requests.exceptions.RequestException as e:
        print(f"  -> ⚠️ AVISO: Não foi possível buscar odds da The Odds API: {e}")
        return []


# --- PARTE 3: ESTRATÉGIAS ---

def extrair_odds_principais(jogo):
    try:
        bookmaker_data = jogo.get('bookmakers', [])
        if not bookmaker_data: return None
        markets = bookmaker_data[0].get('markets', [])
        odds = {'h2h': {}, 'totals_2_5': {}}
        for market in markets:
            if market['key'] == 'h2h':
                odds['h2h'] = {o['name']: o['price'] for o in market['outcomes']}
            elif market['key'] == 'totals':
                point = market.get('outcomes', [{}])[0].get('point')
                if point == 2.5: odds['totals_2_5'] = {o['name']: o['price'] for o in market['outcomes']}
        return odds if any(odds.values()) else None
    except (IndexError, KeyError):
        return None

def analisar_reacao_gigante(jogo, contexto):
    stats_individuais = contexto.get('stats_individuais')
    if not stats_individuais: return None
    
    times_no_jogo = [jogo['home_team'], jogo['away_team']]
    for time_analisado in times_no_jogo:
        stats_time = stats_individuais.get(time_analisado)
        if stats_time and stats_time.get('perc_vitorias_geral', 0) >= GIGANTE_MIN_PERC_VITORIAS:
            motivo = f"O time ({time_analisado}) é um 'gigante' histórico com {stats_time.get('perc_vitorias_geral', 0):.1f}% de vitórias."
            mercado = f"Resultado Final - {time_analisado}"
            odds = extrair_odds_principais(jogo)
            if not odds:
                return {"type": "aposta", "mercado": mercado, "emoji": '⚡', "nome_estrategia": "GIGANTE EM CAMPO (SEM ODD)", "motivo": motivo}
            odd_vitoria = odds.get('h2h', {}).get(time_analisado)
            if odd_vitoria and odd_vitoria >= GIGANTE_MIN_ODD_VITORIA:
                return {"type": "aposta", "mercado": mercado, "odd": odd_vitoria, "emoji": '⚡', "nome_estrategia": "GIGANTE EM CAMPO (VALIDADO)", "motivo": motivo}
    return None

def analisar_classico_de_gols(jogo, contexto):
    stats_h2h = contexto.get('stats_h2h')
    if not stats_h2h: return None

    time_casa, time_fora = jogo['home_team'], jogo['away_team']
    h2h_key = '|'.join(sorted([time_casa, time_fora]))
    stats_confronto = stats_h2h.get(h2h_key)
    if not stats_confronto or stats_confronto.get('total_jogos_h2h', 0) < MIN_JOGOS_H2H: return None
    
    avg_gols = stats_confronto.get('avg_gols_h2h', 0)
    if avg_gols >= CLASSICO_GOLS_MIN_AVG:
        motivo = f"O confronto direto entre essas equipes tem um histórico de muitos gols, com uma média de {avg_gols:.2f} gols por partida."
        mercado = "Mais de 2.5"
        odds = extrair_odds_principais(jogo)
        if not odds or not odds.get('totals_2_5'):
            return {"type": "aposta", "mercado": mercado, "emoji": '💥', "nome_estrategia": "CLÁSSICO DE GOLS (SEM ODD)", "motivo": motivo}
        odd_over_2_5 = odds.get('totals_2_5', {}).get('Over')
        if odd_over_2_5 and odd_over_2_5 >= CLASSICO_GOLS_MIN_ODD_OVER_2_5:
            return {"type": "aposta", "mercado": mercado, "odd": odd_over_2_5, "emoji": '💥', "nome_estrategia": "CLÁSSICO DE GOLS (VALIDADO)", "motivo": motivo}
    return None

def analisar_visitante_fraco(jogo, contexto):
    stats_individuais = contexto.get('stats_individuais')
    if not stats_individuais: return None
    
    time_casa, time_fora = jogo['home_team'], jogo['away_team']
    stats_time_fora = stats_individuais.get(time_fora)
    if not stats_time_fora or stats_time_fora.get('total_jogos_fora', 0) < MIN_JOGOS_HISTORICO: return None
    
    perc_derrotas = stats_time_fora.get('perc_derrotas_fora', 0)
    if perc_derrotas >= VISITANTE_FRACO_MIN_PERC_DERROTAS:
        motivo = f"O time visitante ({time_fora}) tem um histórico ruim fora de casa, perdendo {perc_derrotas:.1f}% de suas partidas nesta condição."
        mercado = f"Resultado Final - {time_casa}"
        odds = extrair_odds_principais(jogo)
        if not odds or not odds.get('h2h'):
            return {"type": "aposta", "mercado": mercado, "emoji": '📉', "nome_estrategia": "VISITANTE FRACO (SEM ODD)", "motivo": motivo}
        odd_casa = odds.get('h2h', {}).get(time_casa)
        if odd_casa and VISITANTE_FRACO_ODD_CASA_MIN <= odd_casa <= VISITANTE_FRACO_ODD_CASA_MAX:
            return {"type": "aposta", "mercado": mercado, "odd": odd_casa, "emoji": '📉', "nome_estrategia": "VISITANTE FRACO (VALIDADO)", "motivo": motivo}
    return None

# --- PARTE 4: LÓGICA PRINCIPAL ---

def enviar_alerta_telegram(mensagem):
    caracteres_especiais = ['_', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in caracteres_especiais:
        mensagem = mensagem.replace(char, f'\\{char}')
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': mensagem, 'parse_mode': 'MarkdownV2'}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("  > ✅ Mensagem enviada com sucesso para o Telegram!")
        else:
            print(f"  > ❌ ERRO ao enviar para o Telegram: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"  > ❌ ERRO de conexão com o Telegram: {e}")

def calcular_estatisticas_historicas(df):
    if df.empty: return {}, {}
    print("  -> 📊 Pré-calculando estatísticas do CSV...")
    cols_stats = ['FTHG', 'FTAG']
    for col in cols_stats:
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        else: df[col] = 0
    df.dropna(subset=['HomeTeam', 'AwayTeam', 'Date'], inplace=True)
    try:
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
        df.dropna(subset=['Date'], inplace=True)
    except Exception: return {}, {}
    df['Resultado'] = df.apply(lambda r: 'V' if r['FTHG'] > r['FTAG'] else ('E' if r['FTHG'] == r['FTAG'] else 'D'), axis=1)
    stats_casa = df.groupby('HomeTeam').agg(total_jogos_casa=('HomeTeam', 'count'))
    stats_fora = df.groupby('AwayTeam').agg(total_jogos_fora=('AwayTeam', 'count'))
    vitorias_casa = df[df['Resultado'] == 'V'].groupby('HomeTeam').size().rename('vitorias_casa')
    derrotas_fora = df[df['Resultado'] == 'V'].groupby('AwayTeam').size().rename('derrotas_fora')
    vitorias_fora = df[df['Resultado'] == 'D'].groupby('AwayTeam').size().rename('vitorias_fora')
    stats_individuais = pd.concat([stats_casa, stats_fora, vitorias_casa, vitorias_fora, derrotas_fora], axis=1).fillna(0).to_dict('index')
    for time_nome, stats in stats_individuais.items():
        total_jogos = stats.get('total_jogos_casa', 0) + stats.get('total_jogos_fora', 0)
        total_vitorias = stats.get('vitorias_casa', 0) + stats.get('vitorias_fora', 0)
        if total_jogos > 0: stats['perc_vitorias_geral'] = (total_vitorias / total_jogos) * 100
        if stats.get('total_jogos_fora', 0) > 0: stats['perc_derrotas_fora'] = (stats.get('derrotas_fora', 0) / stats['total_jogos_fora']) * 100
    df['TotalGols'] = df['FTHG'] + df['FTAG']
    df['H2H_Key'] = df.apply(lambda row: '|'.join(sorted([str(row['HomeTeam']), str(row['AwayTeam'])])), axis=1)
    stats_h2h = df.groupby('H2H_Key').agg(avg_gols_h2h=('TotalGols', 'mean'), total_jogos_h2h=('H2H_Key', 'count')).to_dict('index')
    print(f"  -> Estatísticas para {len(stats_individuais)} times e {len(stats_h2h)} confrontos calculadas.")
    return stats_individuais, stats_h2h

if __name__ == "__main__":
    
    jogos_principais = buscar_jogos_api_football(API_KEY_FOOTBALL)
    if not jogos_principais:
        print("Encerrando o ciclo.")
        exit()
    jogos_com_odds = buscar_odds_the_odds_api(API_KEY_ODDS)
    
    contexto = {}
    try:
        df_historico = pd.read_csv(ARQUIVO_HISTORICO_CORRIGIDO, low_memory=False)
        contexto["stats_individuais"], contexto["stats_h2h"] = calcular_estatisticas_historicas(df_historico)
    except FileNotFoundError:
        print(f"  -> ⚠️ AVISO: Arquivo histórico '{ARQUIVO_HISTORICO_CORRIGIDO}' não encontrado.")
    
    print(f"\n--- 🔬 Analisando os {len(jogos_principais)} jogos encontrados... ---")
    lista_de_funcoes = [analisar_reacao_gigante, analisar_classico_de_gols, analisar_visitante_fraco]

    for jogo in jogos_principais:
        time_casa = jogo['home_team']
        time_fora = jogo['away_team']
        print(f"\n--- Analisando: {time_casa} vs {time_fora} ---")

        jogo['bookmakers'] = []
        if jogos_com_odds:
            melhor_match = max(jogos_com_odds, key=lambda jogo_odd: fuzz.token_set_ratio(f"{time_casa} {time_fora}", f"{jogo_odd['home_team']} {jogo_odd['away_team']}"))
            pontuacao = fuzz.token_set_ratio(f"{time_casa} {time_fora}", f"{melhor_match['home_team']} {melhor_match['away_team']}")
            if pontuacao > 75:
                print(f"  -> Odds encontradas com {pontuacao}% de confiança.")
                jogo['bookmakers'] = melhor_match.get('bookmakers', [])
        
        for func in lista_de_funcoes:
            oportunidade = func(jogo, contexto)
            if oportunidade:
                print(f"  -> OPORTUNIDADE ENCONTRADA! Estratégia: {oportunidade['nome_estrategia']}")
                if oportunidade.get('odd'):
                    if oportunidade.get('odd', 0) >= ODD_MINIMA_GLOBAL:
                        mensagem = f"*{oportunidade.get('emoji', '⚠️')} ENTRADA VALIDADA {oportunidade.get('emoji', '⚠️')}*\n\n"
                        mensagem += f"*Estratégia:* {oportunidade.get('nome_estrategia', 'N/A')}\n"
                        mensagem += f"*⚽ JOGO:* {time_casa} vs {time_fora}\n"
                        mensagem += f"*📈 MERCADO:* {oportunidade.get('mercado', 'N/A')}\n"
                        mensagem += f"*📊 ODD ENCONTRADA:* *{oportunidade.get('odd')}*\n\n"
                        mensagem += f"*🔍 Análise do Falcão:* _{oportunidade.get('motivo', 'N/A')}_"
                        enviar_alerta_telegram(mensagem)
                    else:
                        print(f"  -> ❌ OPORTUNIDADE REPROVADA PELA ODD MÍNIMA ({oportunidade.get('odd', 0)} < {ODD_MINIMA_GLOBAL})")
                else:
                    mensagem = f"*{oportunidade.get('emoji', '⚠️')} ENTRADA VALIDADA (SEM ODD) {oportunidade.get('emoji', '⚠️')}*\n\n"
                    mensagem += f"*Estratégia:* {oportunidade.get('nome_estrategia', 'N/A')}\n"
                    mensagem += f"*⚽ JOGO:* {time_casa} vs {time_fora}\n"
                    mensagem += f"*📈 MERCADO SUGERIDO:* {oportunidade.get('mercado', 'N/A')}\n\n"
                    mensagem += f"*🔍 Análise do Falcão:* _{oportunidade.get('motivo', 'N/A')}_\n\n"
                    mensagem += "_NOTA: Verifique a odd na sua casa de apostas e decida se a entrada tem valor._"
                    enviar_alerta_telegram(mensagem)
                break
    
    print("\n--- Ciclo de análise concluído com sucesso. ---")