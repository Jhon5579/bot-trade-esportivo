import os
import requests
import json
from datetime import datetime, timezone, timedelta
import time

# --- 1. CONFIGURAÇÕES GERAIS ---
API_KEY_ODDS = os.environ.get('API_KEY')
API_KEY_FOOTBALL = os.environ.get('API_FOOTBALL_KEY')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

ARQUIVO_PENDENTES = 'apostas_pendentes.json'
ARQUIVO_CATALOGO = 'catalogo_times.json'
CASA_ALVO = 'bet365'

ODD_MINIMA_UNDER = 1.80
ODD_MINIMA_OVER = 1.80
JOGOS_PARA_ANALISE = 4
JOGOS_H2H = 3

try:
    with open(ARQUIVO_CATALOGO, 'r', encoding='utf-8') as f:
        CATALOGO_TIMES = json.load(f)
    print(f"✅ Catálogo com {len(CATALOGO_TIMES)} chaves de times carregado com sucesso.")
except FileNotFoundError:
    print(f"❌ ERRO: Arquivo '{ARQUIVO_CATALOGO}' não foi encontrado.")
    CATALOGO_TIMES = {}

# --- 2. FUNÇÕES AUXILIARES ---

def enviar_alerta_telegram(mensagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    caracteres_especiais = ['_', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in caracteres_especiais: mensagem = mensagem.replace(char, f'\\{char}')
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

def buscar_estatisticas_time(id_time, n_jogos):
    headers = {'x-apisports-key': API_KEY_FOOTBALL}
    url = "https://v3.football.api-sports.io/fixtures"
    params = {'team': id_time, 'last': n_jogos, 'status': 'FT'}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
        if response.status_code != 200: return None
        dados = response.json().get('response', [])
        if len(dados) < n_jogos: return None
        gols_marcados = sum(jogo['goals']['home'] if jogo['teams']['home']['id'] == id_time else jogo['goals']['away'] for jogo in dados)
        gols_sofridos = sum(jogo['goals']['away'] if jogo['teams']['home']['id'] == id_time else jogo['goals']['home'] for jogo in dados)
        return {'gols_marcados_media': gols_marcados / len(dados), 'gols_sofridos_media': gols_sofridos / len(dados)}
    except Exception: return None

def buscar_h2h(id_time_casa, id_time_fora, n_jogos):
    headers = {'x-apisports-key': API_KEY_FOOTBALL}
    url = "https://v3.football.api-sports.io/fixtures"
    params = {'h2h': f'{id_time_casa}-{id_time_fora}', 'last': n_jogos, 'status': 'FT'}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
        if response.status_code != 200: return None
        return response.json().get('response', [])
    except Exception: return None

def encontrar_id_correto(nome_time, pista_liga, catalogo):
    candidatos = catalogo.get(nome_time, [])
    if not candidatos: return None
    if len(candidatos) == 1: return candidatos[0]['id']
    for candidato in candidatos:
        if candidato['country'] in pista_liga:
            return candidato['id']
    return None

# --- 3. FUNÇÕES DAS ESTRATÉGIAS ---

def analisar_fortaleza_defensiva(stats_casa, stats_fora, h2h):
    if stats_casa['gols_sofridos_media'] >= 0.8: return False
    if stats_casa['gols_marcados_media'] >= 1.5: return False
    if stats_fora['gols_sofridos_media'] >= 1.2: return False
    if stats_fora['gols_marcados_media'] >= 1.5: return False
    if h2h and len(h2h) >= 2:
        jogos_under = sum(1 for jogo in h2h if (jogo['goals']['home'] + jogo['goals']['away']) < 2.5)
        if (jogos_under / len(h2h)) < 0.5: return False
    return True

def analisar_tempestade_ofensiva(stats_casa, stats_fora, h2h):
    if stats_casa['gols_marcados_media'] < 1.9: return False
    if stats_fora['gols_marcados_media'] < 1.7: return False
    if stats_casa['gols_sofridos_media'] < 0.9: return False
    if stats_fora['gols_sofridos_media'] < 1.0: return False
    if h2h and len(h2h) >= 2:
        jogos_over = sum(1 for jogo in h2h if (jogo['goals']['home'] + jogo['goals']['away']) > 2.5)
        if (jogos_over / len(h2h)) < 0.5: return False
    return True

# --- 4. FUNÇÃO DE VERIFICAÇÃO (CORRIGIDA PARA SEMPRE CRIAR O ARQUIVO) ---

def verificar_apostas_pendentes():
    print("\n--- 🔍 Verificando resultados de apostas pendentes... ---")
    try:
        with open(ARQUIVO_PENDENTES, 'r', encoding='utf-8') as f:
            apostas = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("Nenhuma aposta pendente encontrada. Criando arquivo pela primeira vez.")
        # Se o arquivo não existe, nós o criamos aqui com uma lista vazia
        with open(ARQUIVO_PENDENTES, 'w', encoding='utf-8') as f:
            json.dump([], f)
        apostas = [] # Começamos com uma lista vazia
    
    if not apostas:
        print("Nenhuma aposta pendente na lista.")
        # Retornamos 0 pendentes, mas agora o arquivo sempre existe
        return 0
    
    apostas_finalizadas_ids = []
    url_scores = f"https://api.the-odds-api.com/v4/sports/soccer/scores/?apiKey={API_KEY_ODDS}&daysFrom=3"
    try:
        response_scores = requests.get(url_scores, timeout=15)
        if response_scores.status_code != 200: return len(apostas)
        jogos_finalizados = response_scores.json()
    except Exception: return len(apostas)

    for aposta in apostas:
        for jogo in jogos_finalizados:
            if jogo['id'] == aposta['id_api'] and jogo['completed']:
                placar_casa = int(next((item['score'] for item in jogo['scores'] if item['name'] == jogo['home_team']), 0))
                placar_fora = int(next((item['score'] for item in jogo['scores'] if item['name'] == jogo['away_team']), 0))
                total_gols = placar_casa + placar_fora
                resultado = ""
                if aposta['mercado'] == 'Menos de 2.5': resultado = "GREEN" if total_gols < 2.5 else "RED"
                elif aposta['mercado'] == 'Mais de 2.5': resultado = "GREEN" if total_gols > 2.5 else "RED"
                if resultado:
                    simbolo = "✅" if resultado == "GREEN" else "🔴"
                    mensagem = (f"*{simbolo} RESULTADO: {resultado} {simbolo}*\n"
                                f"====================\n"
                                f"*JOGO:* {aposta['nome_jogo']}\n"
                                f"*PLACAR FINAL:* {placar_casa} x {placar_fora}\n"
                                f"*SUA APOSTA:* {aposta['mercado']}")
                    enviar_alerta_telegram(mensagem)
                    apostas_finalizadas_ids.append(aposta['id_api'])
                break
    
    apostas_restantes = [ap for ap in apostas if ap['id_api'] not in apostas_finalizadas_ids]
    with open(ARQUIVO_PENDENTES, 'w', encoding='utf-8') as f: json.dump(apostas_restantes, f, indent=4)
    print("--- Verificação de pendentes finalizada. ---")
    return len(apostas_restantes)

# --- 5. FUNÇÃO PRINCIPAL DE ORQUESTRAÇÃO ---

def rodar_analise_completa():
    if not CATALOGO_TIMES:
        print("Catálogo de times está vazio. Encerrando ciclo.")
        return

    num_pendentes = verificar_apostas_pendentes()
    alerta_de_aposta_enviado = False
    
    print("\n--- 🤖 Iniciando busca por novas oportunidades ---")
    fuso_horario_brasilia = timezone(timedelta(hours=-3))
    
    url_jogos_dia = f"https://api.the-odds-api.com/v4/sports/soccer/odds?apiKey={API_KEY_ODDS}&regions=eu,us,uk,au&markets=h2h"
    try:
        response_jogos = requests.get(url_jogos_dia, timeout=20)
        jogos_do_dia = response_jogos.json() if response_jogos.status_code == 200 else []
    except Exception as e:
        print(f"  > ERRO de conexão ao buscar jogos do dia: {e}")
        jogos_do_dia = []
    
    jogos_analisados = 0
    if jogos_do_dia:
        for jogo in jogos_do_dia:
            time_casa_nome = jogo['home_team']
            time_fora_nome = jogo['away_team']
            pista_liga = jogo.get('sport_title', '')
            
            id_time_casa = encontrar_id_correto(time_casa_nome, pista_liga, CATALOGO_TIMES)
            id_time_fora = encontrar_id_correto(time_fora_nome, pista_liga, CATALOGO_TIMES)

            if not id_time_casa or not id_time_fora:
                continue
            
            jogos_analisados += 1
            print(f"\nAnalisando {time_casa_nome} vs {time_fora_nome} (Liga: {pista_liga})...")
            stats_casa = buscar_estatisticas_time(id_time_casa, JOGOS_PARA_ANALISE)
            stats_fora = buscar_estatisticas_time(id_time_fora, JOGOS_PARA_ANALISE)
            h2h = buscar_h2h(id_time_casa, id_time_fora, JOGOS_H2H)
            time.sleep(7)

            if not stats_casa or not stats_fora or h2h is None:
                print("  > Não foi possível obter o histórico completo para este jogo. Pulando.")
                continue

            mercado, odd_minima, emoji, nome_estrategia, outcome_name = (None,) * 5
            
            if analisar_fortaleza_defensiva(stats_casa, stats_fora, h2h):
                mercado, odd_minima, emoji, nome_estrategia, outcome_name = "Menos de 2.5", ODD_MINIMA_UNDER, "🎯", "FORTALEZA DEFENSIVA", "Under"
            elif analisar_tempestade_ofensiva(stats_casa, stats_fora, h2h):
                mercado, odd_minima, emoji, nome_estrategia, outcome_name = "Mais de 2.5", ODD_MINIMA_OVER, "🔥", "TEMPESTADE OFENSIVA", "Over"
            else:
                continue

            url_odds = f"https://api.the-odds-api.com/v4/sports/soccer/events/{jogo['id']}/odds?apiKey={API_KEY_ODDS}&regions=eu&markets=totals&bookmakers={CASA_ALVO}"
            try:
                response_odds = requests.get(url_odds, timeout=15)
                if response_odds.status_code == 200:
                    dados_odds = response_odds.json()
                    odd_encontrada = next((o.get('price') for b in dados_odds.get('bookmakers', []) for m in b.get('markets', []) if m.get('key') == 'totals' for o in m.get('outcomes', []) if o.get('name') == outcome_name and o.get('point') == 2.5), None)

                    if odd_encontrada and odd_encontrada > odd_minima:
                        alerta_de_aposta_enviado = True
                        data_hora_local = datetime.fromisoformat(jogo['commence_time'].replace('Z', '+00:00')).astimezone(fuso_horario_brasilia).strftime('%d/%m/%Y às %H:%M')
                        alerta = (f"*{emoji} INSTRUÇÃO DE ENTRADA ({nome_estrategia}) {emoji}*\n\n"
                                  f"*⚽ JOGO:* {time_casa_nome} vs {time_fora_nome}\n"
                                  f"*🏆 LIGA:* {jogo.get('sport_title', 'Não informada')}\n"
                                  f"*🗓️ DATA:* {data_hora_local}\n\n"
                                  f"*📈 MERCADO:* {mercado} Gols\n"
                                  f"*📊 ODD ENCONTRADA:* *{odd_encontrada}*\n"
                                  f"*(Mínima: {odd_minima})*\n\n"
                                  f"*👉 INSTRUÇÃO:*\n"
                                  f"Faça sua entrada em *{mercado}* na {CASA_ALVO}.")
                        enviar_alerta_telegram(alerta)
                        nova_aposta = {"id_api": jogo['id'], "nome_jogo": f"{time_casa_nome} vs {time_fora_nome}", "mercado": mercado}
                        try:
                            with open(ARQUIVO_PENDENTES, 'r') as f: apostas_salvas = json.load(f)
                        except (FileNotFoundError, json.JSONDecodeError):
                            apostas_salvas = []
                        apostas_salvas.append(nova_aposta)
                        with open(ARQUIVO_PENDENTES, 'w') as f: json.dump(apostas_salvas, f, indent=4)
                else:
                    print(f"  > Não foi possível buscar as odds. Status: {response_odds.status_code} - {response_odds.text}")
            except Exception as e:
                print(f"  > ERRO ao buscar odds: {e}")

    print("\n--- Análise deste ciclo finalizada. ---")
    if not alerta_de_aposta_enviado:
        data_hoje_str = datetime.now(fuso_horario_brasilia).strftime('%d/%m/%Y às %H:%M')
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
    print("--- Iniciando execução única do bot ---")
    if not all([API_KEY_ODDS, API_KEY_FOOTBALL, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
        print("❌ ERRO FATAL: Uma ou mais chaves de API não estão configuradas.")
    elif not CATALOGO_TIMES:
         print("❌ ERRO FATAL: 'catalogo_times.json' está vazio ou não foi encontrado.")
    else:
        rodar_analise_completa()
    
    print("--- Execução finalizada com sucesso. ---")
