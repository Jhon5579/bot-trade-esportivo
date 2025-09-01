import os
import requests
import json
from datetime import datetime, timezone, timedelta
import time

# --- 1. CONFIGURAÇÕES GERAIS ---
API_KEY_ODDS = os.environ.get('API_KEY')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

ARQUIVO_PENDENTES = 'apostas_pendentes.json'
ARQUIVO_HISTORICO_APOSTAS = 'historico_de_apostas.json'
CASA_ALVO = 'pinnacle'

# --- CONFIGURAÇÕES DAS ESTRATÉGIAS DE ODDS ---
SUPER_FAVORITO_MAX_ODD, FAVORITO_MAX_ODD, ODD_MINIMA_FAVORITO = 1.50, 1.60, 1.30
JOGO_EQUILIBRADO_MIN_ODD, ODD_MINIMA_UNDER_Tatico = 2.40, 1.80
MERCADO_OTIMISTA_MAX_ODD, ODD_MINIMA_OVER_Otimista = 1.70, 1.30
CONSENSO_FAVORITO_MAX_ODD, CONSENSO_MERCADO_OVER_MAX_ODD, CONSENSO_OVER_MIN_ODD_VALOR = 1.50, 1.75, 1.70
CONSENSO_EMPATE_MAX_ODD, CONSENSO_MERCADO_UNDER_MAX_ODD, CONSENSO_UNDER_MIN_ODD_VALOR = 3.20, 1.75, 1.70
LINHA_ESTICADA_OVER_2_5_MAX_ODD, LINHA_ESTICADA_UNDER_3_5_MIN_ODD = 1.50, 1.70
ZEBRA_VALOROSA_FAVORITO_MAX_ODD, ZEBRA_VALOROSA_EMPATE_MIN_ODD, ZEBRA_VALOROSA_EMPATE_MAX_ODD = 1.30, 3.50, 5.00
MERCADO_CONGELADO_RANGE_MIN, MERCADO_CONGELADO_RANGE_MAX, MERCADO_CONGELADO_BTTS_MIN_ODD = 1.85, 1.95, 1.70
FAVORITO_CONSERVADOR_MAX_ODD, FAVORITO_CONSERVADOR_OVER_1_5_MIN_ODD = 1.50, 1.30
PRESSAO_MERCADO_OVER_2_5_MIN_ODD, PRESSAO_MERCADO_OVER_2_5_MAX_ODD = 1.70, 1.85

# --- 2. FUNÇÕES DAS ESTRATÉGIAS DE ODDS ---
def analisar_favoritos_em_niveis(jogo):
    odd_casa, odd_fora = None, None
    try:
        bookmaker_data = jogo.get('bookmakers', [])[0]
        for market in bookmaker_data.get('markets', []):
            if market.get('key') == 'h2h':
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == jogo['home_team']: odd_casa = outcome.get('price')
                    elif outcome.get('name') == jogo['away_team']: odd_fora = outcome.get('price')
    except IndexError: return None
    nivel_favorito = None
    if (odd_casa and odd_casa <= SUPER_FAVORITO_MAX_ODD) or (odd_fora and odd_fora <= SUPER_FAVORITO_MAX_ODD): nivel_favorito = "SUPER FAVORITO"
    elif (odd_casa and odd_casa <= FAVORITO_MAX_ODD) or (odd_fora and odd_fora <= FAVORITO_MAX_ODD): nivel_favorito = "FAVORITO"
    if not nivel_favorito: return None
    odd_over_1_5 = None
    for market in bookmaker_data.get('markets', []):
        if market.get('key') == 'totals':
            for outcome in market.get('outcomes', []):
                if outcome.get('name') == 'Over' and outcome.get('point') == 1.5: odd_over_1_5 = outcome.get('price'); break
        if odd_over_1_5: break
    if odd_over_1_5 and odd_over_1_5 > ODD_MINIMA_FAVORITO: return {"mercado": "Mais de 1.5", "odd": odd_over_1_5, "emoji": '👑', "nome_estrategia": f"ATAQUE DO {nivel_favorito}"}
    return None

def analisar_duelo_tatico(jogo):
    odd_casa, odd_fora = None, None
    try:
        bookmaker_data = jogo.get('bookmakers', [])[0]
        for market in bookmaker_data.get('markets', []):
            if market.get('key') == 'h2h':
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == jogo['home_team']: odd_casa = outcome.get('price')
                    elif outcome.get('name') == jogo['away_team']: odd_fora = outcome.get('price')
    except IndexError: return None
    if not ((odd_casa and odd_casa > JOGO_EQUILIBRADO_MIN_ODD) and (odd_fora and odd_fora > JOGO_EQUILIBRADO_MIN_ODD)): return None
    for market in bookmaker_data.get('markets', []):
        if market.get('key') == 'totals':
            for outcome in market.get('outcomes', []):
                if outcome.get('name') == 'Under' and outcome.get('point') == 2.5 and outcome.get('price') > ODD_MINIMA_UNDER_Tatico: return {"mercado": "Menos de 2.5", "odd": outcome.get('price'), "emoji": '♟️', "nome_estrategia": "DUELO TÁTICO"}
    return None

def analisar_mercado_otimista(jogo):
    odd_over_2_5 = None
    try:
        bookmaker_data = jogo.get('bookmakers', [])[0]
        for market in bookmaker_data.get('markets', []):
            if market.get('key') == 'totals':
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == 'Over' and outcome.get('point') == 2.5: odd_over_2_5 = outcome.get('price'); break
        if odd_over_2_5 is None or odd_over_2_5 > MERCADO_OTIMISTA_MAX_ODD: return None
        for market in bookmaker_data.get('markets', []):
            if market.get('key') == 'totals':
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == 'Over' and outcome.get('point') == 1.5 and outcome.get('price') > ODD_MINIMA_OVER_Otimista: return {"mercado": "Mais de 1.5", "odd": outcome.get('price'), "emoji": '📈', "nome_estrategia": "MERCADO OTIMISTA"}
    except IndexError: return None
    return None

def analisar_consenso_de_gols(jogo):
    odd_favorito, odd_over_2_5 = None, None
    try:
        bookmaker_data = jogo.get('bookmakers', [])[0]
        for market in bookmaker_data.get('markets', []):
            if market.get('key') == 'h2h':
                odds_h2h = [o.get('price') for o in market.get('outcomes', []) if o.get('name') != 'Draw']
                if odds_h2h: odd_favorito = min(odds_h2h)
        for market in bookmaker_data.get('markets', []):
            if market.get('key') == 'totals':
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == 'Over' and outcome.get('point') == 2.5: odd_over_2_5 = outcome.get('price'); break
    except IndexError: return None
    if (odd_favorito and odd_favorito <= CONSENSO_FAVORITO_MAX_ODD) and (odd_over_2_5 and odd_over_2_5 <= CONSENSO_MERCADO_OVER_MAX_ODD) and (odd_over_2_5 > CONSENSO_OVER_MIN_ODD_VALOR): return {"mercado": "Mais de 2.5", "odd": odd_over_2_5, "emoji": '🎯', "nome_estrategia": "CONSENSO DE GOLS"}
    return None

def analisar_consenso_de_defesa(jogo):
    odd_empate, odd_under_2_5 = None, None
    try:
        bookmaker_data = jogo.get('bookmakers', [])[0]
        for market in bookmaker_data.get('markets', []):
            if market.get('key') == 'h2h':
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == 'Draw': odd_empate = outcome.get('price'); break
        for market in bookmaker_data.get('markets', []):
            if market.get('key') == 'totals':
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == 'Under' and outcome.get('point') == 2.5: odd_under_2_5 = outcome.get('price'); break
    except IndexError: return None
    if (odd_empate and odd_empate <= CONSENSO_EMPATE_MAX_ODD) and (odd_under_2_5 and odd_under_2_5 <= CONSENSO_MERCADO_UNDER_MAX_ODD) and (odd_under_2_5 > CONSENSO_UNDER_MIN_ODD_VALOR): return {"mercado": "Menos de 2.5", "odd": odd_under_2_5, "emoji": '🛡️', "nome_estrategia": "CONSENSO DE DEFESA"}
    return None

def analisar_linha_esticada(jogo):
    odd_over_2_5, odd_under_3_5 = None, None
    try:
        bookmaker_data = jogo.get('bookmakers', [])[0]
        for market in bookmaker_data.get('markets', []):
            if market.get('key') == 'totals':
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == 'Over' and outcome.get('point') == 2.5: odd_over_2_5 = outcome.get('price')
                    elif outcome.get('name') == 'Under' and outcome.get('point') == 3.5: odd_under_3_5 = outcome.get('price')
    except IndexError: return None
    if (odd_over_2_5 and odd_over_2_5 < LINHA_ESTICADA_OVER_2_5_MAX_ODD) and (odd_under_3_5 and odd_under_3_5 > LINHA_ESTICADA_UNDER_3_5_MIN_ODD): return {"mercado": "Menos de 3.5", "odd": odd_under_3_5, "emoji": '📏', "nome_estrategia": "LINHA ESTICADA"}
    return None

def analisar_zebra_valorosa(jogo):
    odd_favorito, odd_empate = None, None
    try:
        bookmaker_data = jogo.get('bookmakers', [])[0]
        for market in bookmaker_data.get('markets', []):
            if market.get('key') == 'h2h':
                odds_h2h = []
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == 'Draw': odd_empate = outcome.get('price')
                    else: odds_h2h.append(outcome.get('price'))
                if odds_h2h: odd_favorito = min(odds_h2h)
    except IndexError: return None
    if (odd_favorito and odd_favorito < ZEBRA_VALOROSA_FAVORITO_MAX_ODD) and (odd_empate and ZEBRA_VALOROSA_EMPATE_MIN_ODD <= odd_empate <= ZEBRA_VALOROSA_EMPATE_MAX_ODD): return {"mercado": "Empate", "odd": odd_empate, "emoji": '🦓', "nome_estrategia": "ZEBRA VALOROSA"}
    return None

def analisar_mercado_congelado(jogo):
    odd_over_2_5, odd_under_2_5, odd_btts_sim = None, None, None
    try:
        bookmaker_data = jogo.get('bookmakers', [])[0]
        for market in bookmaker_data.get('markets', []):
            if market.get('key') == 'totals' and market.get('outcomes', [])[0].get('point') == 2.5:
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == 'Over': odd_over_2_5 = outcome.get('price')
                    elif outcome.get('name') == 'Under': odd_under_2_5 = outcome.get('price')
            elif market.get('key') == 'both_teams_to_score':
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == 'Yes': odd_btts_sim = outcome.get('price')
    except IndexError: return None
    if (odd_over_2_5 and MERCADO_CONGELADO_RANGE_MIN <= odd_over_2_5 <= MERCADO_CONGELADO_RANGE_MAX) and (odd_under_2_5 and MERCADO_CONGELADO_RANGE_MIN <= odd_under_2_5 <= MERCADO_CONGELADO_RANGE_MAX) and (odd_btts_sim and odd_btts_sim > MERCADO_CONGELADO_BTTS_MIN_ODD): return {"mercado": "Ambas Marcam - Sim", "odd": odd_btts_sim, "emoji": '⚖️', "nome_estrategia": "MERCADO CONGELADO"}
    return None

def analisar_favorito_conservador(jogo):
    odd_favorito, odd_over_1_5 = None, None
    try:
        bookmaker_data = jogo.get('bookmakers', [])[0]
        for market in bookmaker_data.get('markets', []):
            if market.get('key') == 'h2h':
                odds_h2h = [o.get('price') for o in market.get('outcomes', []) if o.get('name') != 'Draw']
                if odds_h2h: odd_favorito = min(odds_h2h)
        for market in bookmaker_data.get('markets', []):
            if market.get('key') == 'totals':
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == 'Over' and outcome.get('point') == 1.5: odd_over_1_5 = outcome.get('price'); break
    except IndexError: return None
    if (odd_favorito and odd_favorito <= FAVORITO_CONSERVADOR_MAX_ODD) and (odd_over_1_5 and odd_over_1_5 > FAVORITO_CONSERVADOR_OVER_1_5_MIN_ODD): return {"mercado": "Mais de 1.5", "odd": odd_over_1_5, "emoji": '💪', "nome_estrategia": "FAVORITO CONSERVADOR"}
    return None

def analisar_pressao_mercado(jogo):
    odd_over_2_5 = None
    try:
        bookmaker_data = jogo.get('bookmakers', [])[0]
        for market in bookmaker_data.get('markets', []):
            if market.get('key') == 'totals':
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == 'Over' and outcome.get('point') == 2.5: odd_over_2_5 = outcome.get('price'); break
    except IndexError: return None
    if odd_over_2_5 and PRESSAO_MERCADO_OVER_2_5_MIN_ODD <= odd_over_2_5 <= PRESSAO_MERCADO_OVER_2_5_MAX_ODD: return {"mercado": "Mais de 2.5", "odd": odd_over_2_5, "emoji": '🌡️', "nome_estrategia": "PRESSÃO DO MERCADO"}
    return None

# --- 3. FUNÇÕES DE SUPORTE ---
def escolher_melhor_estrategia(oportunidades):
    ranking_confianca = [
        "FAVORITO CONSERVADOR", "ATAQUE DO SUPER FAVORITO", "ATAQUE DO FAVORITO",
        "CONSENSO DE GOLS", "PRESSÃO DO MERCADO", "MERCADO OTIMISTA",
        "LINHA ESTICADA", "CONSENSO DE DEFESA", "DUELO TÁTICO",
        "MERCADO CONGELADO", "ZEBRA VALOROSA"
    ]
    if len(oportunidades) == 1: return oportunidades[0]
    melhor_oportunidade, melhor_posicao_ranking = None, float('inf')
    for op in oportunidades:
        nome_estrategia = op['nome_estrategia']
        nome_base = nome_estrategia.replace("ATAQUE DO ", "") if "ATAQUE DO" in nome_estrategia else nome_estrategia
        if nome_base in ranking_confianca:
            posicao_atual = ranking_confianca.index(nome_base)
            if posicao_atual < melhor_posicao_ranking:
                melhor_posicao_ranking, melhor_oportunidade = posicao_atual, op
    return melhor_oportunidade

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

def salvar_aposta_concluida(aposta, resultado, placar_str):
    try:
        with open(ARQUIVO_HISTORICO_APOSTAS, 'r', encoding='utf-8') as f: historico = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): historico = []
    aposta_concluida = aposta.copy()
    aposta_concluida.update({'resultado': resultado, 'placar_final': placar_str, 'data_conclusao': datetime.now(timezone.utc).isoformat()})
    historico.append(aposta_concluida)
    with open(ARQUIVO_HISTORICO_APOSTAS, 'w', encoding='utf-8') as f: json.dump(historico, f, indent=4)
    print(f"  > Aposta '{aposta['nome_jogo']}' salva no histórico com resultado {resultado}.")

def verificar_apostas_pendentes():
    print("\n--- 🔍 Verificando resultados de apostas pendentes... ---")
    try:
        with open(ARQUIVO_PENDENTES, 'r', encoding='utf-8') as f: apostas = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): apostas = []
    total_pendentes_inicio = len(apostas)
    if total_pendentes_inicio == 0:
        print("Nenhuma aposta pendente na lista.")
        return {'total_pendentes_inicio': 0, 'resultados_encontrados': 0}
    apostas_para_remover, resultados_encontrados = [], 0
    url_scores = f"https://api.the-odds-api.com/v4/sports/soccer/scores/?apiKey={API_KEY_ODDS}&daysFrom=3"
    try:
        response_scores = requests.get(url_scores, timeout=15)
        jogos_finalizados = response_scores.json() if response_scores.status_code == 200 else []
    except Exception: jogos_finalizados = []
    for aposta in apostas:
        for jogo in jogos_finalizados:
            if jogo['id'] == aposta['id_api'] and jogo['completed']:
                resultados_encontrados += 1
                placar_casa = int(next((item['score'] for item in jogo['scores'] if item['name'] == jogo['home_team']), 0))
                placar_fora = int(next((item['score'] for item in jogo['scores'] if item['name'] == jogo['away_team']), 0))
                total_gols, placar_str = placar_casa + placar_fora, f"{placar_casa} x {placar_fora}"
                resultado, mercado = "", aposta['mercado']
                if "Mais de 1.5" in mercado: resultado = "GREEN" if total_gols > 1.5 else "RED"
                elif "Mais de 2.5" in mercado: resultado = "GREEN" if total_gols > 2.5 else "RED"
                elif "Menos de 2.5" in mercado: resultado = "GREEN" if total_gols < 2.5 else "RED"
                elif "Menos de 3.5" in mercado: resultado = "GREEN" if total_gols < 3.5 else "RED"
                elif "Ambas Marcam - Sim" in mercado: resultado = "GREEN" if placar_casa > 0 and placar_fora > 0 else "RED"
                elif "Empate" in mercado: resultado = "GREEN" if placar_casa == placar_fora else "RED"
                if resultado:
                    simbolo = "✅" if resultado == "GREEN" else "🔴"
                    msg_resultado = (f"*{simbolo} RESULTADO: {resultado} {simbolo}*\n====================\n*JOGO:* {aposta['nome_jogo']}\n*PLACAR FINAL:* {placar_str}\n*SUA APOSTA:* {aposta['mercado']}")
                    enviar_alerta_telegram(msg_resultado)
                    salvar_aposta_concluida(aposta, resultado, placar_str)
                    apostas_para_remover.append(aposta)
                break
    if apostas_para_remover:
        with open(ARQUIVO_PENDENTES, 'w', encoding='utf-8') as f: json.dump([ap for ap in apostas if ap not in apostas_para_remover], f, indent=4)
    if resultados_encontrados > 0:
        pendentes_agora = total_pendentes_inicio - resultados_encontrados
        msg_relatorio_pendentes = (f"📝 *Relatório de Apostas Pendentes*\n\n🏁 Encontrei e processei o resultado de *{resultados_encontrados}* apostas.\n⏳ Ainda restam *{pendentes_agora}* apostas em aberto.")
        enviar_alerta_telegram(msg_relatorio_pendentes)
    print("--- Verificação de pendentes finalizada. ---")
    return {'total_pendentes_inicio': total_pendentes_inicio, 'resultados_encontrados': resultados_encontrados}

# --- 4. FUNÇÃO PRINCIPAL DE ORQUESTRAÇÃO (v8.1 - BOT COMUNICADOR) ---
def rodar_analise_completa():
    stats_pendentes = verificar_apostas_pendentes()
    alerta_de_aposta_enviado_geral = False
    print(f"\n--- 🤖 Iniciando busca v8.1 (Bot Comunicador)... ---")
    url_jogos_e_odds = (f"https://api.the-odds-api.com/v4/sports/soccer/odds?apiKey={API_KEY_ODDS}&regions=eu,us,uk,au&markets=h2h,totals,both_teams_to_score&bookmakers={CASA_ALVO}&oddsFormat=decimal")
    try:
        response_jogos = requests.get(url_jogos_e_odds, timeout=25)
        jogos_do_dia = response_jogos.json() if response_jogos.status_code == 200 else []
    except Exception as e:
        print(f"  > ERRO de conexão: {e}"); jogos_do_dia = []
    jogos_analisados, nomes_jogos_analisados = 0, []
    if jogos_do_dia:
        fuso_brasilia = timezone(timedelta(hours=-3))
        for jogo in jogos_do_dia:
            time_casa, time_fora = jogo['home_team'], jogo['away_team']
            if not jogo.get('bookmakers'): continue
            jogos_analisados += 1
            nomes_jogos_analisados.append(f"⚽ {time_casa} vs {time_fora}")
            print(f"\n--------------------------------------------------\nAnalisando Jogo: {time_casa} vs {time_fora}")
            oportunidades_neste_jogo = []
            for func in [analisar_favoritos_em_niveis, analisar_duelo_tatico, analisar_mercado_otimista, analisar_consenso_de_gols, analisar_consenso_de_defesa, analisar_linha_esticada, analisar_zebra_valorosa, analisar_mercado_congelado, analisar_favorito_conservador, analisar_pressao_mercado]:
                if res := func(jogo): oportunidades_neste_jogo.append(res)
            if oportunidades_neste_jogo:
                if melhor_op := escolher_melhor_estrategia(oportunidades_neste_jogo):
                    alerta_de_aposta_enviado_geral = True
                    print(f"  -> ✅ MELHOR OPORTUNIDADE ESCOLHIDA! Estratégia: {melhor_op['nome_estrategia']}")
                    data_hora, mercado_str = datetime.fromisoformat(jogo['commence_time'].replace('Z', '+00:00')).astimezone(fuso_brasilia).strftime('%d/%m/%Y às %H:%M'), melhor_op['mercado']
                    if "Mais de" in mercado_str or "Menos de" in mercado_str: mercado_str += " Gols"
                    alerta = (f"*{melhor_op['emoji']} INSTRUÇÃO DE ENTRADA ({melhor_op['nome_estrategia']}) {melhor_op['emoji']}*\n\n*⚽ JOGO:* {time_casa} vs {time_fora}\n*🏆 LIGA:* {jogo.get('sport_title', 'N/A')}\n*🗓️ DATA:* {data_hora}\n\n*📈 MERCADO:* {mercado_str}\n*📊 ODD ENCONTRADA:* *{melhor_op['odd']}*")
                    enviar_alerta_telegram(alerta)
                    nova_aposta = {"id_api": jogo['id'], "nome_jogo": f"{time_casa} vs {time_fora}", "mercado": melhor_op['mercado']}
                    try:
                        with open(ARQUIVO_PENDENTES, 'r', encoding='utf-8') as f: apostas_salvas = json.load(f)
                    except (FileNotFoundError, json.JSONDecodeError): apostas_salvas = []
                    apostas_salvas.append(nova_aposta)
                    with open(ARQUIVO_PENDENTES, 'w', encoding='utf-8') as f: json.dump(apostas_salvas, f, indent=4)
    print("\n--- Análise deste ciclo finalizada. ---")
    if not alerta_de_aposta_enviado_geral:
        data_hoje_str = datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y às %H:%M')
        jogos_texto = "\n".join(nomes_jogos_analisados[:15])
        if len(nomes_jogos_analisados) > 15: jogos_texto += f"\n...e mais {len(nomes_jogos_analisados) - 15} jogos."
        mensagem_status = (f"🤖 *Relatório de Análise Automática (v8.1)* 🤖\n\n🗓️ *Data:* {data_hoje_str}\n-----------------------------------\n\n🔍 *Resumo da Varredura:*\n- Verifiquei *{stats_pendentes['total_pendentes_inicio']}* apostas que estavam pendentes.\n- Analisei um total de *{jogos_analisados}* jogos neste ciclo.\n\n🚫 *Resultado:*\nNenhuma oportunidade de alto valor encontrada nos jogos abaixo.\n\n-----------------------------------\n🗒️ *Jogos Verificados Hoje:*\n{jogos_texto if jogos_texto else 'Nenhum jogo encontrado para análise.'}\n\nContinuo monitorando! 🕵️‍♂️")
        print("Nenhuma oportunidade encontrada. Enviando relatório de status...")
        enviar_alerta_telegram(mensagem_status)

# --- 5. PONTO DE ENTRADA ---
if __name__ == "__main__":
    print("--- Iniciando execução única do bot (v8.1 Bot Comunicador) ---")
    if not all([API_KEY_ODDS, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
        print("❌ ERRO FATAL: Chaves de API/Telegram não configuradas.")
    else:
        rodar_analise_completa()
    print("--- Execução finalizada com sucesso. ---")
