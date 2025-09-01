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
# Estratégia "Ataque do Favorito" em Níveis
SUPER_FAVORITO_MAX_ODD = 1.50
FAVORITO_MAX_ODD = 1.60
ODD_MINIMA_FAVORITO = 1.30
# Estratégia "Duelo Tático"
JOGO_EQUILIBRADO_MIN_ODD = 2.40
ODD_MINIMA_UNDER_Tatico = 1.80
# Estratégia "Mercado Otimista"
MERCADO_OTIMISTA_MAX_ODD = 1.70
ODD_MINIMA_OVER_Otimista = 1.30
# Estratégias "Consenso"
CONSENSO_FAVORITO_MAX_ODD = 1.50
CONSENSO_MERCADO_OVER_MAX_ODD = 1.75
CONSENSO_OVER_MIN_ODD_VALOR = 1.70
CONSENSO_EMPATE_MAX_ODD = 3.20
CONSENSO_MERCADO_UNDER_MAX_ODD = 1.75
CONSENSO_UNDER_MIN_ODD_VALOR = 1.70

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
    if (odd_casa and odd_casa <= SUPER_FAVORITO_MAX_ODD) or (odd_fora and odd_fora <= SUPER_FAVORITO_MAX_ODD):
        nivel_favorito = "SUPER FAVORITO"
    elif (odd_casa and odd_casa <= FAVORITO_MAX_ODD) or (odd_fora and odd_fora <= FAVORITO_MAX_ODD):
        nivel_favorito = "FAVORITO"

    if not nivel_favorito: return None

    odd_over_1_5 = None
    for market in bookmaker_data.get('markets', []):
        if market.get('key') == 'totals':
            for outcome in market.get('outcomes', []):
                if outcome.get('name') == 'Over' and outcome.get('point') == 1.5:
                    odd_over_1_5 = outcome.get('price'); break
        if odd_over_1_5: break
            
    if odd_over_1_5 and odd_over_1_5 > ODD_MINIMA_FAVORITO:
        return {"mercado": "Mais de 1.5", "odd": odd_over_1_5, "emoji": '👑', "nome_estrategia": f"ATAQUE DO {nivel_favorito}"}
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
    jogo_equilibrado = (odd_casa and odd_casa > JOGO_EQUILIBRADO_MIN_ODD) and (odd_fora and odd_fora > JOGO_EQUILIBRADO_MIN_ODD)
    if not jogo_equilibrado: return None
    for market in bookmaker_data.get('markets', []):
        if market.get('key') == 'totals':
            for outcome in market.get('outcomes', []):
                if outcome.get('name') == 'Under' and outcome.get('point') == 2.5:
                    if outcome.get('price') > ODD_MINIMA_UNDER_Tatico:
                        return {"mercado": "Menos de 2.5", "odd": outcome.get('price'), "emoji": '♟️', "nome_estrategia": "DUELO TÁTICO"}
    return None

def analisar_mercado_otimista(jogo):
    odd_over_2_5 = None
    try:
        bookmaker_data = jogo.get('bookmakers', [])[0]
        for market in bookmaker_data.get('markets', []):
            if market.get('key') == 'totals':
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == 'Over' and outcome.get('point') == 2.5:
                        odd_over_2_5 = outcome.get('price'); break
        if odd_over_2_5 is None or odd_over_2_5 > MERCADO_OTIMISTA_MAX_ODD: return None
        for market in bookmaker_data.get('markets', []):
            if market.get('key') == 'totals':
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == 'Over' and outcome.get('point') == 1.5:
                        if outcome.get('price') > ODD_MINIMA_OVER_Otimista:
                            return {"mercado": "Mais de 1.5", "odd": outcome.get('price'), "emoji": '📈', "nome_estrategia": "MERCADO OTIMISTA"}
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
                    if outcome.get('name') == 'Over' and outcome.get('point') == 2.5:
                        odd_over_2_5 = outcome.get('price'); break
    except IndexError: return None
    if (odd_favorito and odd_favorito <= CONSENSO_FAVORITO_MAX_ODD) and (odd_over_2_5 and odd_over_2_5 <= CONSENSO_MERCADO_OVER_MAX_ODD):
        if odd_over_2_5 > CONSENSO_OVER_MIN_ODD_VALOR:
            return {"mercado": "Mais de 2.5", "odd": odd_over_2_5, "emoji": '🎯', "nome_estrategia": "CONSENSO DE GOLS"}
    return None

def analisar_consenso_de_defesa(jogo):
    odd_empate, odd_under_2_5 = None, None
    try:
        bookmaker_data = jogo.get('bookmakers', [])[0]
        for market in bookmaker_data.get('markets', []):
            if market.get('key') == 'h2h':
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == 'Draw':
                        odd_empate = outcome.get('price'); break
        for market in bookmaker_data.get('markets', []):
            if market.get('key') == 'totals':
                for outcome in market.get('outcomes', []):
                    if outcome.get('name') == 'Under' and outcome.get('point') == 2.5:
                        odd_under_2_5 = outcome.get('price'); break
    except IndexError: return None
    if (odd_empate and odd_empate <= CONSENSO_EMPATE_MAX_ODD) and (odd_under_2_5 and odd_under_2_5 <= CONSENSO_MERCADO_UNDER_MAX_ODD):
        if odd_under_2_5 > CONSENSO_UNDER_MIN_ODD_VALOR:
            return {"mercado": "Menos de 2.5", "odd": odd_under_2_5, "emoji": '🛡️', "nome_estrategia": "CONSENSO DE DEFESA"}
    return None

# --- 3. FUNÇÕES DE SUPORTE ---
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
                if "Mais de 1.5" in aposta['mercado']: resultado = "GREEN" if total_gols > 1.5 else "RED"
                elif "Mais de 2.5" in aposta['mercado']: resultado = "GREEN" if total_gols > 2.5 else "RED"
                elif "Menos de 2.5" in aposta['mercado']: resultado = "GREEN" if total_gols < 2.5 else "RED"
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

# --- 4. FUNÇÃO PRINCIPAL DE ORQUESTRAÇÃO (v5.2 - ARSENAL COMPLETO) ---
def rodar_analise_completa():
    num_pendentes = verificar_apostas_pendentes()
    alerta_de_aposta_enviado_geral = False
    print(f"\n--- 🤖 Iniciando busca v5.2 (Estrategista de Odds Aprimorado)... ---")
    
    url_jogos_e_odds = (f"https://api.the-odds-api.com/v4/sports/soccer/odds?"
                        f"apiKey={API_KEY_ODDS}&regions=eu,us,uk,au"
                        f"&markets=h2h,totals&bookmakers={CASA_ALVO}&oddsFormat=decimal")
    try:
        response_jogos = requests.get(url_jogos_e_odds, timeout=25)
        jogos_do_dia = response_jogos.json() if response_jogos.status_code == 200 else []
    except Exception as e:
        print(f"  > ERRO de conexão: {e}"); jogos_do_dia = []
    
    jogos_analisados = 0
    if jogos_do_dia:
        fuso_brasilia = timezone(timedelta(hours=-3))
        for jogo in jogos_do_dia:
            time_casa_nome = jogo['home_team']; time_fora_nome = jogo['away_team']
            if not jogo.get('bookmakers'): continue
            
            jogos_analisados += 1
            print(f"\n--------------------------------------------------")
            print(f"Analisando Jogo: {time_casa_nome} vs {time_fora_nome}")
            oportunidades_encontradas = []

            # Executa o arsenal completo de 5 estratégias
            res1 = analisar_favoritos_em_niveis(jogo);       
            if res1: oportunidades_encontradas.append(res1)
            res2 = analisar_duelo_tatico(jogo);             
            if res2: oportunidades_encontradas.append(res2)
            res3 = analisar_mercado_otimista(jogo);         
            if res3: oportunidades_encontradas.append(res3)
            res4 = analisar_consenso_de_gols(jogo);
            if res4: oportunidades_encontradas.append(res4)
            res5 = analisar_consenso_de_defesa(jogo);
            if res5: oportunidades_encontradas.append(res5)

            # Envio dos Alertas
            if oportunidades_encontradas:
                alerta_de_aposta_enviado_geral = True
                data_hora_local = datetime.fromisoformat(jogo['commence_time'].replace('Z', '+00:00')).astimezone(fuso_brasilia).strftime('%d/%m/%Y às %H:%M')
                for op in oportunidades_encontradas:
                    print(f"    -> ✅ OPORTUNIDADE ENCONTRADA! Estratégia: {op['nome_estrategia']}")
                    alerta = (f"*{op['emoji']} INSTRUÇÃO DE ENTRADA ({op['nome_estrategia']}) {op['emoji']}*\n\n"
                              f"*⚽ JOGO:* {time_casa_nome} vs {time_fora_nome}\n"
                              f"*🏆 LIGA:* {jogo.get('sport_title', 'Não informada')}\n"
                              f"*🗓️ DATA:* {data_hora_local}\n\n"
                              f"*📈 MERCADO:* {op['mercado']} Gols\n"
                              f"*📊 ODD ENCONTRADA:* *{op['odd']}*")
                    enviar_alerta_telegram(alerta)
                    nova_aposta = {"id_api": jogo['id'], "nome_jogo": f"{time_casa_nome} vs {time_fora_nome}", "mercado": op['mercado']}
                    try:
                        with open(ARQUIVO_PENDENTES, 'r', encoding='utf-8') as f: apostas_salvas = json.load(f)
                    except (FileNotFoundError, json.JSONDecodeError): apostas_salvas = []
                    apostas_salvas.append(nova_aposta)
                    with open(ARQUIVO_PENDENTES, 'w', encoding='utf-8') as f: json.dump(apostas_salvas, f, indent=4)
    
    print("\n--- Análise deste ciclo finalizada. ---")
    if not alerta_de_aposta_enviado_geral:
        fuso_brasilia = timezone(timedelta(hours=-3)); data_hoje_str = datetime.now(fuso_brasilia).strftime('%d/%m/%Y às %H:%M')
        mensagem_status = (f"🤖 *Relatório de Análise Automática*\n\n"
                           f"✅ Análise concluída em: {data_hoje_str}.\n\n"
                           f"🔍 *Resumo:*\n"
                           f"- Verifiquei {num_pendentes} apostas pendentes.\n"
                           f"- Analisei {jogos_analisados} jogos hoje.\n\n"
                           f"🚫 *Resultado:*\n"
                           f"Nenhuma oportunidade encontrada que cumpra todos os critérios neste ciclo.")
        print("Nenhuma oportunidade encontrada. Enviando relatório de status...")
        enviar_alerta_telegram(mensagem_status)

# --- 5. PONTO DE ENTRADA ---
if __name__ == "__main__":
    print("--- Iniciando execução única do bot (v5.2 Estrategista de Odds) ---")
    if not all([API_KEY_ODDS, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
        print("❌ ERRO FATAL: Chaves de API/Telegram não configuradas.")
    else:
        rodar_analise_completa()
    print("--- Execução finalizada com sucesso. ---")
