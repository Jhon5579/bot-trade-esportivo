# main.py (Versão 2.6 Completa - Usando Master Team List)

import requests
import pandas as pd
from thefuzz import fuzz
import json
from datetime import datetime, timezone, timedelta, date
import os
import csv

from estrategias import *
from api_externa import (
    buscar_jogos_api_football, buscar_odds_the_odds_api, 
    verificar_resultado_api_football, buscar_estatisticas_time, 
    buscar_resultados_por_ids
)

# --- ARQUIVOS E CONSTANTES ---
ARQUIVO_HISTORICO_CORRIGIDO = 'dados_historicos_corrigido.csv'
ARQUIVO_MASTER_LIST = 'master_team_list.json'
ARQUIVO_PENDENTES = 'apostas_pendentes.json'
ARQUIVO_HISTORICO = 'historico_de_apostas.json'
ARQUIVO_JOGOS_DIA = 'jogos_a_acompanhar.json'
ARQUIVO_ENTRADAS_ENVIADAS = 'entradas_enviadas.json'
ODD_MINIMA = 1.40
ODD_MAXIMA = 2.00

# --- FUNÇÕES DE SUPORTE E GERENCIAMENTO ---

def enviar_alerta_telegram(mensagem, telegram_token, telegram_chat_id):
    if not telegram_token or not telegram_chat_id:
        print("  -> AVISO: Tokens do Telegram não configurados nos Secrets.")
        return
    caracteres_especiais = ['_', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in caracteres_especiais:
        mensagem = mensagem.replace(char, f'\\{char}')
    
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {'chat_id': telegram_chat_id, 'text': mensagem, 'parse_mode': 'MarkdownV2'}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("  > Mensagem enviada com sucesso para o Telegram!")
        else:
            print(f"  > ERRO ao enviar para o Telegram: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"  > ERRO de conexão com o Telegram: {e}")

def carregar_json(nome_arquivo, valor_padrao):
    try:
        with open(nome_arquivo, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return valor_padrao

def salvar_json(dados, nome_arquivo):
    with open(nome_arquivo, 'w', encoding='utf-8') as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)

def determinar_resultado(aposta, placar_casa, placar_fora):
    mercado = aposta['mercado']
    if placar_casa is None or placar_fora is None or placar_casa < 0 or placar_fora < 0:
        return 'INDEFINIDO'
    if mercado == 'Casa para Vencer': return 'GREEN' if placar_casa > placar_fora else 'RED'
    if mercado == 'Visitante para Vencer': return 'GREEN' if placar_fora > placar_casa else 'RED'
    if mercado == 'Empate': return 'GREEN' if placar_casa == placar_fora else 'RED'
    return 'INDEFINIDO'

def atualizar_historico_local(api_keys):
    print("\n--- 💾 Verificando se há histórico para atualizar... ---")
    jogos_para_atualizar = carregar_json(ARQUIVO_JOGOS_DIA, {"data": "", "jogos": []})
    data_hoje_str = str(date.today())
    if not jogos_para_atualizar.get('jogos') or jogos_para_atualizar.get('data') == data_hoje_str:
        print("  -> Nenhuma atualização de histórico necessária.")
        return
    print(f"  -> Encontrados {len(jogos_para_atualizar['jogos'])} jogos do dia {jogos_para_atualizar['data']} para atualizar.")
    ids_para_buscar = [jogo['id_partida'] for jogo in jogos_para_atualizar['jogos']]
    resultados = buscar_resultados_por_ids(api_keys['football'], ids_para_buscar)
    if not resultados:
        print("  -> Não foi possível obter os resultados."); return
    novas_linhas_csv = []
    for jogo in resultados:
        if jogo.get('fixture', {}).get('status', {}).get('short', '') == 'FT':
            gols_casa = jogo.get('goals', {}).get('home')
            gols_fora = jogo.get('goals', {}).get('away')
            if gols_casa is None or gols_fora is None: continue
            data_jogo = datetime.fromtimestamp(jogo['fixture']['timestamp']).strftime('%d/%m/%Y')
            resultado_final = 'D'
            if gols_casa > gols_fora: resultado_final = 'H'
            elif gols_fora > gols_casa: resultado_final = 'A'
            novas_linhas_csv.append({'Date': data_jogo, 'HomeTeam': jogo['teams']['home']['name'], 'AwayTeam': jogo['teams']['away']['name'], 'FTHG': gols_casa, 'FTAG': gols_fora, 'FTR': resultado_final})
    if novas_linhas_csv:
        try:
            fieldnames = ['Date', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'FTR']
            with open(ARQUIVO_HISTORICO_CORRIGIDO, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if f.tell() == 0: writer.writeheader()
                for linha in novas_linhas_csv:
                    writer.writerow({key: linha.get(key, '') for key in fieldnames})
            print(f"  -> ✅ Histórico atualizado com {len(novas_linhas_csv)} novos resultados!")
        except Exception as e: print(f"  -> ❌ ERRO ao escrever no arquivo CSV: {e}")
    salvar_json({"data": data_hoje_str, "jogos": []}, ARQUIVO_JOGOS_DIA)

def verificar_apostas_pendentes(api_key_football, telegram_config):
    print("\n--- 🔄 Verificando apostas pendentes... ---")
    apostas_pendentes = carregar_json(ARQUIVO_PENDENTES, []); historico = carregar_json(ARQUIVO_HISTORICO, [])
    if not apostas_pendentes: print("  -> Nenhuma aposta pendente para verificar."); return
    apostas_ainda_pendentes = []
    for aposta in apostas_pendentes:
        status, placar_casa, placar_fora = verificar_resultado_api_football(api_key_football, aposta['id_partida'])
        if status == "encerrado":
            resultado = determinar_resultado(aposta, placar_casa, placar_fora)
            if resultado != 'INDEFINIDO':
                aposta.update({'resultado': resultado, 'placar_final': f"{placar_casa} x {placar_fora}"})
                print(f"  -> Jogo finalizado: {aposta['times']}. Resultado: {resultado}")
                emoji = '✅' if resultado == 'GREEN' else '❌'
                mensagem = f"*{emoji} RESULTADO DA ENTRADA {emoji}*\n\n*⚽ JOGO:* {aposta['times']}\n*📈 MERCADO:* {aposta['mercado']}\n*📊 PLACAR FINAL:* {aposta['placar_final']}\n\n*🎯 RESULTADO:* *{resultado}*"
                enviar_alerta_telegram(mensagem, telegram_config['token'], telegram_config['chat_id'])
                historico.append(aposta)
            else: apostas_ainda_pendentes.append(aposta)
        else: apostas_ainda_pendentes.append(aposta)
    salvar_json(apostas_ainda_pendentes, ARQUIVO_PENDENTES); salvar_json(historico, ARQUIVO_HISTORICO)

def calcular_estatisticas_historicas(df):
    if df.empty: return {}, {}, {}
    cols_stats = ['FTHG', 'FTAG', 'HC', 'AC', 'HS', 'AS', 'HST', 'AST', 'HY', 'AY', 'HR', 'AR']
    for col in cols_stats:
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        else: df[col] = 0
    df.dropna(subset=['HomeTeam', 'AwayTeam', 'Date'], inplace=True)
    try:
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
        df.dropna(subset=['Date'], inplace=True)
        df.sort_values(by='Date', inplace=True)
    except Exception:
        print(" -> ERRO: Falha ao converter a coluna de datas."); return {}, {}, {}
    df['ResultadoCasa'] = df.apply(lambda r: 'V' if r['FTHG'] > r['FTAG'] else ('E' if r['FTHG'] == r['FTAG'] else 'D'), axis=1)
    df['ResultadoFora'] = df.apply(lambda r: 'V' if r['FTAG'] > r['FTHG'] else ('E' if r['FTAG'] == r['FTHG'] else 'D'), axis=1)
    print("  -> 📊 Pré-calculando estatísticas gerais e de forma recente...")
    forma_recente = {}
    for index, row in df.iterrows():
        time_casa, time_fora = row['HomeTeam'], row['AwayTeam']
        if time_casa not in forma_recente: forma_recente[time_casa] = []
        if time_fora not in forma_recente: forma_recente[time_fora] = []
        forma_recente[time_casa].insert(0, row['ResultadoCasa'])
        forma_recente[time_fora].insert(0, row['ResultadoFora'])
        if len(forma_recente[time_casa]) > 5: forma_recente[time_casa].pop()
        if len(forma_recente[time_fora]) > 5: forma_recente[time_fora].pop()
    stats_casa = df.groupby('HomeTeam').agg(avg_gols_marcados_casa=('FTHG', 'mean'), avg_gols_sofridos_casa=('FTAG', 'mean'), total_jogos_casa=('HomeTeam', 'count'))
    stats_fora = df.groupby('AwayTeam').agg(avg_gols_marcados_fora=('FTAG', 'mean'), avg_gols_sofridos_fora=('FTHG', 'mean'), total_jogos_fora=('AwayTeam', 'count'))
    vitorias_casa = df[df['ResultadoCasa'] == 'V'].groupby('HomeTeam').size().rename('vitorias_casa')
    empates_casa = df[df['ResultadoCasa'] == 'E'].groupby('HomeTeam').size().rename('empates_casa')
    derrotas_casa = df[df['ResultadoCasa'] == 'D'].groupby('HomeTeam').size().rename('derrotas_casa')
    vitorias_fora = df[df['ResultadoFora'] == 'V'].groupby('AwayTeam').size().rename('vitorias_fora')
    empates_fora = df[df['ResultadoFora'] == 'E'].groupby('AwayTeam').size().rename('empates_fora')
    derrotas_fora = df[df['ResultadoFora'] == 'D'].groupby('AwayTeam').size().rename('derrotas_fora')
    stats_individuais = pd.concat([stats_casa, stats_fora, vitorias_casa, empates_casa, derrotas_casa, vitorias_fora, empates_fora, derrotas_fora], axis=1).fillna(0)
    stats_individuais['perc_vitorias_casa'] = (stats_individuais['vitorias_casa'] / stats_individuais['total_jogos_casa']) * 100
    stats_individuais['perc_derrotas_casa'] = (stats_individuais['derrotas_casa'] / stats_individuais['total_jogos_casa']) * 100
    stats_individuais['perc_empates_casa'] = (stats_individuais['empates_casa'] / stats_individuais['total_jogos_casa']) * 100
    stats_individuais['perc_vitorias_fora'] = (stats_individuais['vitorias_fora'] / stats_individuais['total_jogos_fora']) * 100
    stats_individuais['perc_derrotas_fora'] = (stats_individuais['derrotas_fora'] / stats_individuais['total_jogos_fora']) * 100
    stats_individuais['perc_empates_fora'] = (stats_individuais['empates_fora'] / stats_individuais['total_jogos_fora']) * 100
    stats_individuais = stats_individuais.to_dict('index')
    df['TotalGols'] = df['FTHG'] + df['FTAG']
    df['H2H_Key'] = df.apply(lambda row: '|'.join(sorted([str(row['HomeTeam']), str(row['AwayTeam'])])), axis=1)
    stats_h2h = df.groupby('H2H_Key').agg(avg_gols_h2h=('TotalGols', 'mean'), total_jogos_h2h=('H2H_Key', 'count')).to_dict('index')
    print(f"  -> Estatísticas para {len(stats_individuais)} times e {len(stats_h2h)} confrontos calculadas.")
    return stats_individuais, stats_h2h, forma_recente

def rodar_analise_completa(api_keys, telegram_config):
    atualizar_historico_local(api_keys)
    verificar_apostas_pendentes(api_keys['football'], telegram_config)
    print(f"\n--- 🦅 Iniciando ciclo de análise de novas oportunidades... ---")
    
    data_hoje_str = str(date.today())
    diario_de_envio = carregar_json(ARQUIVO_ENTRADAS_ENVIADAS, {"data": data_hoje_str, "enviadas_ids": []})
    if diario_de_envio.get("data") != data_hoje_str:
        diario_de_envio = {"data": data_hoje_str, "enviadas_ids": []}
    ids_ja_enviados = set(diario_de_envio["enviadas_ids"])
    novas_oportunidades_encontradas = False
    
    apostas_pendentes = carregar_json(ARQUIVO_PENDENTES, [])
    ids_pendentes = {aposta['id_partida'] for aposta in apostas_pendentes}
    
    jogos_principais = buscar_jogos_api_football(api_keys['football'])
    if not jogos_principais: print("Nenhum jogo novo encontrado."); return
        
    dados_dia = carregar_json(ARQUIVO_JOGOS_DIA, {"data": "", "jogos": []})
    if dados_dia.get("data") != data_hoje_str or not dados_dia.get("jogos"):
        salvar_json({"data": str(date.today()), "jogos": jogos_principais}, ARQUIVO_JOGOS_DIA)
        
    jogos_com_odds = buscar_odds_the_odds_api(api_keys['odds'])
    contexto = {}
    try:
        df_historico = pd.read_csv(ARQUIVO_HISTORICO_CORRIGIDO, low_memory=False)
        stats_i, stats_h, forma_r = calcular_estatisticas_historicas(df_historico.copy())
        contexto.update({"stats_individuais": stats_i, "stats_h2h": stats_h, "forma_recente": forma_r})

        print("  -> 🗺️  Carregando mapa de nomes (Master Team List)...")
        mapa_de_nomes = carregar_json(ARQUIVO_MASTER_LIST, {})
        if mapa_de_nomes:
            contexto['mapa_de_nomes'] = mapa_de_nomes
            print(f"  -> Mapa com {len(mapa_de_nomes)} times carregado com sucesso.")
        else:
            print("  -> ⚠️ AVISO: Arquivo master_team_list.json não encontrado ou vazio.")

    except FileNotFoundError:
        print(f"  -> ⚠️ AVISO: Arquivo histórico '{ARQUIVO_HISTORICO_CORRIGIDO}' não encontrado."); return
        
    print(f"\n--- 🔬 Analisando {len(jogos_principais)} jogos encontrados... ---")
    lista_de_funcoes = [
        analisar_favorito_forte_fora, analisar_valor_mandante_azarao, analisar_valor_visitante_azarao,
        analisar_empate_valorizado, analisar_forma_recente_casa, analisar_forma_recente_fora
    ]
    
    for jogo in jogos_principais:
        id_partida, time_casa, time_fora = jogo.get('id_partida'), jogo['home_team'], jogo['away_team']
        if id_partida in ids_pendentes: continue
        print(f"\n--------------------------------------------------\nAnalisando NOVO Jogo: {time_casa} vs {time_fora}")
        
        jogo['bookmakers'] = []
        if jogos_com_odds:
            melhor_match_odds, maior_pontuacao = None, 75
            for jogo_odd in jogos_com_odds:
                pontuacao = fuzz.token_set_ratio(f"{time_casa} {time_fora}", f"{jogo_odd['home_team']} {jogo_odd['away_team']}")
                if pontuacao > maior_pontuacao: maior_pontuacao, melhor_match_odds = pontuacao, jogo_odd
            if melhor_match_odds:
                print(f"  -> Odds encontradas com {maior_pontuacao}% de confiança.")
                jogo['bookmakers'] = melhor_match_odds.get('bookmakers', [])
        
        for func_estrategia in lista_de_funcoes:
            resultado_offline = func_estrategia(jogo, contexto, debug=True)
            
            if isinstance(resultado_offline, str):
                print(f"    - Estratégia '{func_estrategia.__name__}': {resultado_offline}")
            
            elif isinstance(resultado_offline, dict) and resultado_offline.get('type') == 'pre_aprovado':
                print(f"  -> 🔬 Pré-Aprovado pela estratégia '{resultado_offline['nome_estrategia']}' (análise offline).")
                
                stats_casa = buscar_estatisticas_time(api_keys['football'], jogo['home_team_id'], jogo['league_id'])
                stats_fora = buscar_estatisticas_time(api_keys['football'], jogo['away_team_id'], jogo['league_id'])

                validado_online = False
                motivo_online = "Critérios de validação online não atendidos."
                
                if stats_casa and stats_fora:
                    forma_casa, forma_fora = stats_casa.get('forma', ''), stats_fora.get('forma', '')
                    if resultado_offline['nome_estrategia'] == 'Empate Valorizado' and forma_casa.count('L') <= 1 and forma_fora.count('L') <= 1:
                        validado_online = True
                        motivo_online = f"Confirmado com forma recente estável (Casa: {forma_casa}, Fora: {forma_fora})."
                
                if not validado_online:
                    print(f"  -> ❌ Reprovado na validação online.")
                    continue

                print(f"  -> ✅ APROVADO na validação online!")
                
                id_unico_aposta = f"{id_partida}-{func_estrategia.__name__}"
                if id_unico_aposta in ids_ja_enviados:
                    print(f"  -> Oportunidade repetida. Ignorando.")
                    continue
                
                oportunidade = resultado_offline
                odd = _encontrar_odd_especifica(jogo, oportunidade['mercado'])
                motivo_final = motivo_online
                
                oportunidade_encontrada = False
                mensagem = ""
                fuso_horario_br = timezone(timedelta(hours=-3))
                dt_objeto = datetime.fromtimestamp(jogo.get('timestamp', 0), tz=fuso_horario_br)
                data_hora_formatada = dt_objeto.strftime('%d/%m/%Y às %H:%M')

                if odd and ODD_MINIMA <= odd <= ODD_MAXIMA:
                    oportunidade_encontrada = True
                    mensagem = f"*{oportunidade.get('emoji', '⚠️')} ENTRADA VALIDADA {oportunidade.get('emoji', '⚠️')}*\n\n*🗓️ DATA:* {data_hora_formatada}\n*⚽ JOGO:* {time_casa} vs {time_fora}\n*📈 MERCADO:* {oportunidade['mercado']}\n*📊 ODD ENCONTRADA:* *{odd:.2f}*\n\n*🔍 Análise:* _{motivo_final}_"
                elif not odd:
                    oportunidade_encontrada = True
                    mensagem = f"*{oportunidade.get('emoji', '⚠️')} ENTRADA VALIDADA (SEM ODD) {oportunidade.get('emoji', '⚠️')}*\n\n*🗓️ DATA:* {data_hora_formatada}\n*⚽ JOGO:* {time_casa} vs {time_fora}\n*📈 MERCADO SUGERIDO:* {oportunidade['mercado']}\n\n*🔍 Análise:* _{motivo_final}_\n\n_NOTA: Verifique a odd na sua casa de apostas e decida se a entrada tem valor._"
                
                if oportunidade_encontrada:
                    novas_oportunidades_encontradas = True
                    enviar_alerta_telegram(mensagem, telegram_config['token'], telegram_config['chat_id'])
                    ids_ja_enviados.add(id_unico_aposta)
                    diario_de_envio["enviadas_ids"] = list(ids_ja_enviados)
                    salvar_json(diario_de_envio, ARQUIVO_ENTRADAS_ENVIADAS)
                    nova_aposta = {'id_partida': id_partida, 'times': f"{time_casa} vs {time_fora}", 'mercado': oportunidade['mercado'], 'odd_entrada': odd, 'data_aposta': str(date.today())}
                    apostas_pendentes.append(nova_aposta)
                    salvar_json(apostas_pendentes, ARQUIVO_PENDENTES)
                    print(f"  -> Oportunidade salva em '{ARQUIVO_PENDENTES}'.")
                    break
    
    if not novas_oportunidades_encontradas:
        num_pendentes = len(carregar_json(ARQUIVO_PENDENTES, []))
        mensagem_telegram = f"Nenhuma oportunidade *nova* encontrada nesta análise. {num_pendentes} apostas pendentes continuam em monitoramento."
        print(f"\n{mensagem_telegram}")
        enviar_alerta_telegram(mensagem_telegram, telegram_config['token'], telegram_config['chat_id'])
    
    print("\n--- Ciclo de análise finalizado. ---")

if __name__ == "__main__":
    print("--- Carregando chaves da API a partir dos Secrets... ---")
    API_KEY_FOOTBALL = os.getenv('API_KEY')
    API_KEY_ODDS = os.getenv('API_KEY_ODDS')
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
    if not API_KEY_FOOTBALL or not API_KEY_ODDS:
        print("="*60)
        print("❌ ERRO CRÍTICO: Uma ou mais chaves de API não foram encontradas")
        print("   nos Secrets do Replit. Verifique se os nomes estão corretos:")
        print("   - API_KEY (para API-Football)")
        print("   - API_KEY_ODDS (para The Odds API, com dois 'D')")
        print("="*60)
    else:
        print("✅ Chaves da API carregadas com sucesso.")
        api_keys = {'football': API_KEY_FOOTBALL, 'odds': API_KEY_ODDS}
        telegram_config = {'token': TELEGRAM_TOKEN, 'chat_id': TELEGRAM_CHAT_ID}
        try:
            rodar_analise_completa(api_keys, telegram_config)
        except Exception as e:
            print(f"Ocorreu um erro inesperado na execução: {e}")
