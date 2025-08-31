import os
import requests
import json
from datetime import datetime, timezone, timedelta
import time
import pandas as pd
from csv import writer

# --- 1. CONFIGURAÇÕES GERAIS ---
API_KEY_ODDS = os.environ.get('API_KEY')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

ARQUIVO_PENDENTES = 'apostas_pendentes.json'
ARQUIVO_CATALOGO = 'catalogo_times.json'
ARQUIVO_CSV_HISTORICO = 'dados_historicos_corrigido.csv'
ARQUIVO_HISTORICO_APOSTAS = 'historico_de_apostas.json'
ARQUIVO_HISTORICO_ANALISES = 'historico_de_analises.csv' # Log de análises
CASA_ALVO = 'pinnacle'

# CONFIGURAÇÕES DAS ESTRATÉGIAS
ODD_MINIMA_UNDER = 1.50
ODD_MINIMA_OVER = 1.50
JOGOS_PARA_ANALISE = 4
JOGOS_H2H = 1

try:
    with open(ARQUIVO_CATALOGO, 'r', encoding='utf-8') as f:
        CATALOGO_TIMES = json.load(f)
    print(f"✅ Catálogo com {len(CATALOGO_TIMES)} chaves de times carregado com sucesso.")
except FileNotFoundError:
    print(f"❌ ERRO: Arquivo '{ARQUIVO_CATALOGO}' não foi encontrado."); CATALOGO_TIMES = {}

# CARREGAMENTO DO BANCO DE DADOS OFFLINE
print(f"--- 📊 Carregando banco de dados de '{ARQUIVO_CSV_HISTORICO}'... ---")
df_historico = None
try:
    df_historico = pd.read_csv(ARQUIVO_CSV_HISTORICO, encoding='utf-8')
    if 'Date' in df_historico.columns:
        df_historico['Date'] = pd.to_datetime(df_historico['Date'], dayfirst=True, errors='coerce')
    print(f"✅ Banco de dados com {len(df_historico)} jogos carregado com sucesso.")
except FileNotFoundError:
    print(f"❌ ERRO FATAL: O arquivo '{ARQUIVO_CSV_HISTORICO}' não foi encontrado."); df_historico = None

# --- 2. FUNÇÕES DE ANÁLISE OFFLINE (USANDO O CSV) ---
def buscar_estatisticas_do_csv(nome_time, df, n_jogos):
    try:
        jogos_do_time = df[(df['HomeTeam'] == nome_time) | (df['AwayTeam'] == nome_time)].copy()
        jogos_do_time = jogos_do_time.sort_values(by='Date', ascending=False)
        ultimos_jogos = jogos_do_time.head(n_jogos)
        if len(ultimos_jogos) < n_jogos: return None
        gols_marcados, gols_sofridos = 0, 0
        for index, jogo in ultimos_jogos.iterrows():
            if jogo['HomeTeam'] == nome_time: gols_marcados += jogo['FTHG']; gols_sofridos += jogo['FTAG']
            else: gols_marcados += jogo['FTAG']; gols_sofridos += jogo['FTHG']
        return {'gols_marcados_media': gols_marcados / n_jogos, 'gols_sofridos_media': gols_sofridos / n_jogos}
    except Exception: return None

def buscar_h2h_do_csv(time_casa, time_fora, df, n_jogos):
    try:
        h2h_jogos = df[((df['HomeTeam'] == time_casa) & (df['AwayTeam'] == time_fora)) | ((df['HomeTeam'] == time_fora) & (df['AwayTeam'] == time_casa))].copy()
        h2h_jogos = h2h_jogos.sort_values(by='Date', ascending=False)
        ultimos_h2h = h2h_jogos.head(n_jogos)
        return [{'goals': {'home': jogo['FTHG'], 'away': jogo['FTAG']}} for index, jogo in ultimos_h2h.iterrows()]
    except Exception: return None

# --- 3. FUNÇÕES DAS ESTRATÉGIAS (COM CRITÉRIOS CALIBRADOS) ---
def analisar_fortaleza_defensiva(stats_casa, stats_fora, h2h):
    if stats_casa['gols_sofridos_media'] >= 1.2: return False
    if stats_casa['gols_marcados_media'] >= 1.7: return False
    if stats_fora['gols_sofridos_media'] >= 1.5: return False
    if stats_fora['gols_marcados_media'] >= 1.7: return False
    if h2h and len(h2h) >= JOGOS_H2H:
        jogos_under = sum(1 for jogo in h2h if (jogo['goals']['home'] + jogo['goals']['away']) < 2.5)
        if (jogos_under / len(h2h)) < 0.5: return False
    return True

def analisar_tempestade_ofensiva(stats_casa, stats_fora, h2h):
    if stats_casa['gols_marcados_media'] < 1.6: return False
    if stats_fora['gols_marcados_media'] < 1.4: return False
    if stats_casa['gols_sofridos_media'] < 0.9: return False
    if stats_fora['gols_sofridos_media'] < 1.0: return False
    if h2h and len(h2h) >= JOGOS_H2H:
        jogos_over = sum(1 for jogo in h2h if (jogo['goals']['home'] + jogo['goals']['away']) > 2.5)
        if (jogos_over / len(h2h)) < 0.5: return False
    return True

# --- 4. FUNÇÕES DE SUPORTE E LOGGING ---
def enviar_alerta_telegram(mensagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    caracteres_especiais = ['_', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in caracteres_especiais: mensagem = mensagem.replace(char, f'\\{char}')
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': mensagem, 'parse_mode': 'MarkdownV2'}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200: print("  > Mensagem enviada com sucesso para o Telegram!")
        else: print(f"  > ERRO ao enviar para o Telegram: {response.status_code} - {response.text}")
    except Exception as e: print(f"  > ERRO de conexão com o Telegram: {e}")

def salvar_aposta_concluida(aposta, resultado, placar_str):
    try:
        with open(ARQUIVO_HISTORICO_APOSTAS, 'r', encoding='utf-8') as f:
            historico = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        historico = []
    aposta_concluida = aposta.copy()
    aposta_concluida['resultado'] = resultado
    aposta_concluida['placar_final'] = placar_str
    aposta_concluida['data_conclusao'] = datetime.now(timezone.utc).isoformat()
    historico.append(aposta_concluida)
    with open(ARQUIVO_HISTORICO_APOSTAS, 'w', encoding='utf-8') as f:
        json.dump(historico, f, indent=4)
    print(f"  > Aposta '{aposta['nome_jogo']}' salva no histórico com resultado {resultado}.")

def verificar_apostas_pendentes():
    print("\n--- 🔍 Verificando resultados de apostas pendentes... ---")
    try:
        with open(ARQUIVO_PENDENTES, 'r', encoding='utf-8') as f: apostas = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        with open(ARQUIVO_PENDENTES, 'w', encoding='utf-8') as f: json.dump([], f)
        apostas = []
    if not apostas:
        print("Nenhuma aposta pendente na lista."); return 0
    apostas_para_remover = []
    url_scores = f"https://api.the-odds-api.com/v4/sports/soccer/scores/?apiKey={API_KEY_ODDS}&daysFrom=3"
    try:
        response_scores = requests.get(url_scores, timeout=15)
        jogos_finalizados = response_scores.json() if response_scores.status_code == 200 else []
    except Exception: jogos_finalizados = []
    for aposta in apostas:
        for jogo in jogos_finalizados:
            if jogo['id'] == aposta['id_api'] and jogo['completed']:
                placar_casa = int(next((item['score'] for item in jogo['scores'] if item['name'] == jogo['home_team']), 0))
                placar_fora = int(next((item['score'] for item in jogo['scores'] if item['name'] == jogo['away_team']), 0))
                total_gols = placar_casa + placar_fora; placar_str = f"{placar_casa} x {placar_fora}"
                resultado = ""
                if aposta['mercado'] == 'Menos de 2.5': resultado = "GREEN" if total_gols < 2.5 else "RED"
                elif aposta['mercado'] == 'Mais de 2.5': resultado = "GREEN" if total_gols > 2.5 else "RED"
                if resultado:
                    simbolo = "✅" if resultado == "GREEN" else "🔴"
                    mensagem = (f"*{simbolo} RESULTADO: {resultado} {simbolo}*\n"
                                f"====================\n"
                                f"*JOGO:* {aposta['nome_jogo']}\n"
                                f"*PLACAR FINAL:* {placar_str}\n"
                                f"*SUA APOSTA:* {aposta['mercado']}")
                    enviar_alerta_telegram(mensagem)
                    salvar_aposta_concluida(aposta, resultado, placar_str)
                    apostas_para_remover.append(aposta)
                break
    if apostas_para_remover:
        apostas_restantes = [ap for ap in apostas if ap not in apostas_para_remover]
        with open(ARQUIVO_PENDENTES, 'w', encoding='utf-8') as f: json.dump(apostas_restantes, f, indent=4)
    print("--- Verificação de pendentes finalizada. ---")
    return len(apostas) - len(apostas_para_remover)

# --- 5. FUNÇÃO PRINCIPAL DE ORQUESTRAÇÃO (VERSÃO 3.3 OFFLINE CALIBRADA) ---
def rodar_analise_completa():
    num_pendentes = verificar_apostas_pendentes()
    alerta_de_aposta_enviado = False
    print(f"\n--- 🤖 Iniciando busca v3.3 Offline Calibrada (Casa Alvo: {CASA_ALVO.capitalize()})... ---")
    
    url_jogos_e_odds = (f"https://api.the-odds-api.com/v4/sports/soccer/odds?"
                        f"apiKey={API_KEY_ODDS}&regions=eu,us,uk,au"
                        f"&markets=h2h,totals&bookmakers={CASA_ALVO}")
    try:
        response_jogos = requests.get(url_jogos_e_odds, timeout=25)
        jogos_do_dia = response_jogos.json() if response_jogos.status_code == 200 else []
    except Exception as e:
        print(f"  > ERRO de conexão ao buscar jogos e odds: {e}"); jogos_do_dia = []
    
    jogos_analisados = 0
    if jogos_do_dia:
        fuso_brasilia = timezone(timedelta(hours=-3))
        for jogo in jogos_do_dia:
            time_casa_nome = jogo['home_team']; time_fora_nome = jogo['away_team']
            if time_casa_nome not in CATALOGO_TIMES or time_fora_nome not in CATALOGO_TIMES: continue
            if not jogo.get('bookmakers'): continue

            jogos_analisados += 1
            print(f"\nAnalisando {time_casa_nome} vs {time_fora_nome} (usando dados locais)...")
            stats_casa = buscar_estatisticas_do_csv(time_casa_nome, df_historico, JOGOS_PARA_ANALISE)
            stats_fora = buscar_estatisticas_do_csv(time_fora_nome, df_historico, JOGOS_PARA_ANALISE)
            h2h = buscar_h2h_do_csv(time_casa_nome, time_fora_nome, df_historico, JOGOS_H2H)
            
            if not stats_casa or not stats_fora:
                print(f"  > Histórico insuficiente para '{time_casa_nome}' ou '{time_fora_nome}' no CSV. Pulando."); continue
            
            mercado, odd_minima, emoji, nome_estrategia, outcome_name = (None,) * 5
            if analisar_fortaleza_defensiva(stats_casa, stats_fora, h2h):
                mercado, odd_minima, emoji, nome_estrategia, outcome_name = "Menos de 2.5", ODD_MINIMA_UNDER, "🎯", "FORTALEZA DEFENSIVA", "Under"
            elif analisar_tempestade_ofensiva(stats_casa, stats_fora, h2h):
                mercado, odd_minima, emoji, nome_estrategia, outcome_name = "Mais de 2.5", ODD_MINIMA_OVER, "🔥", "TEMPESTADE OFENSIVA", "Over"
            else: continue

            odd_encontrada = next((o.get('price') for b in jogo.get('bookmakers', []) for m in b.get('markets', []) if m.get('key') == 'totals' for o in m.get('outcomes', []) if o.get('name') == outcome_name and o.get('point') == 2.5), None)
            if odd_encontrada and odd_encontrada > odd_minima:
                alerta_de_aposta_enviado = True
                data_hora_local = datetime.fromisoformat(jogo['commence_time'].replace('Z', '+00:00')).astimezone(fuso_brasilia).strftime('%d/%m/%Y às %H:%M')
                alerta = (f"*{emoji} INSTRUÇÃO DE ENTRADA ({nome_estrategia}) {emoji}*\n\n"
                            f"*⚽ JOGO:* {time_casa_nome} vs {time_fora_nome}\n"
                            f"*🏆 LIGA:* {jogo.get('sport_title', 'Não informada')}\n"
                            f"*🗓️ DATA:* {data_hora_local}\n\n"
                            f"*📈 MERCADO:* {mercado} Gols\n"
                            f"*📊 ODD ENCONTRADA:* *{odd_encontrada}*\n"
                            f"*(Mínima: {odd_minima})*\n\n"
                            f"*👉 INSTRUÇÃO:*\n"
                            f"Faça sua entrada em *{mercado}* na {CASA_ALVO.capitalize()}.")
                enviar_alerta_telegram(alerta)
                nova_aposta = {"id_api": jogo['id'], "nome_jogo": f"{time_casa_nome} vs {time_fora_nome}", "mercado": mercado}
                try:
                    with open(ARQUIVO_PENDENTES, 'r') as f: apostas_salvas = json.load(f)
                except (FileNotFoundError, json.JSONDecodeError): apostas_salvas = []
                apostas_salvas.append(nova_aposta)
                with open(ARQUIVO_PENDENTES, 'w') as f: json.dump(apostas_salvas, f, indent=4)

    print("\n--- Análise deste ciclo finalizada. ---")
    if not alerta_de_aposta_enviado:
        fuso_brasilia = timezone(timedelta(hours=-3)); data_hoje_str = datetime.now(fuso_brasilia).strftime('%d/%m/%Y às %H:%M')
        mensagem_status = (f"🤖 *Relatório de Análise Automática*\n\n"
                           f"✅ Análise concluída em: {data_hoje_str}.\n\n"
                           f"🔍 *Resumo:*\n"
                           f"- Verifiquei {num_pendentes} apostas pendentes.\n"
                           f"- Analisei {jogos_analisados} jogos catalogados.\n\n"
                           f"🚫 *Resultado:*\n"
                           f"Nenhuma oportunidade encontrada que cumpra todos os critérios neste ciclo.")
        print("Nenhuma oportunidade encontrada. Enviando relatório de status...")
        enviar_alerta_telegram(mensagem_status)

# --- 6. PONTO DE ENTRADA (OTIMIZADO PARA GITHUB ACTIONS) ---
if __name__ == "__main__":
    print("--- Iniciando execução única do bot (v3.3 Offline Calibrado) ---")
    if df_historico is None:
        print("Encerrando o bot devido a erro no carregamento dos dados históricos.")
    elif not all([API_KEY_ODDS, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
        print("❌ ERRO FATAL: Chaves de API/Telegram não configuradas.")
    elif not CATALOGO_TIMES:
         print("❌ ERRO FATAL: 'catalogo_times.json' está vazio ou não foi encontrado.")
    else:
        rodar_analise_completa()
    print("--- Execução finalizada com sucesso. ---")
