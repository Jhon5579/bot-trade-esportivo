# main.py

import requests
import pandas as pd
from thefuzz import fuzz
import json
from datetime import date

# --- IMPORTAÇÃO DOS MÓDULOS DO PROJETO ---
from config import *
from estrategias import *
from api_externas import buscar_jogos_sofascore, buscar_odds_the_odds_api, verificar_resultado_sofascore

# --- ARQUIVOS E CONSTANTES ---
ARQUIVO_HISTORICO_CORRIGIDO = 'dados_historicos_corrigido.csv'
ARQUIVO_PENDENTES = 'apostas_pendentes.json'
ARQUIVO_HISTORICO = 'historico_de_apostas.json'

# --- FUNÇÕES DE SUPORTE E GERENCIAMENTO ---

def enviar_alerta_telegram(mensagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("  -> AVISO: Tokens do Telegram não encontrados.")
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
    if mercado == 'Casa para Vencer' and placar_casa > placar_fora:
        return 'GREEN'
    return 'RED'

def verificar_apostas_pendentes():
    print("\n--- 🔄 Verificando apostas pendentes... ---")
    apostas_pendentes = carregar_json(ARQUIVO_PENDENTES, [])
    historico = carregar_json(ARQUIVO_HISTORICO, [])
    if not apostas_pendentes:
        print("  -> Nenhuma aposta pendente para verificar.")
        return
    apostas_ainda_pendentes = []
    for aposta in apostas_pendentes:
        status, placar_casa, placar_fora = verificar_resultado_sofascore(aposta['id_partida'])
        if status == "encerrado":
            resultado = determinar_resultado(aposta, placar_casa, placar_fora)
            if resultado != 'INDEFINIDO':
                aposta['resultado'] = resultado
                aposta['placar_final'] = f"{placar_casa} x {placar_fora}"
                print(f"  -> Jogo finalizado: {aposta['times']}. Resultado: {resultado}")
                emoji = '✅' if resultado == 'GREEN' else '❌'
                mensagem = f"*{emoji} RESULTADO DA ENTRADA {emoji}*\n\n*⚽ JOGO:* {aposta['times']}\n*📈 MERCADO:* {aposta['mercado']}\n*📊 PLACAR FINAL:* {aposta['placar_final']}\n\n*🎯 RESULTADO:* *{resultado}*"
                enviar_alerta_telegram(mensagem)
                historico.append(aposta)
            else:
                apostas_ainda_pendentes.append(aposta)
        else:
            apostas_ainda_pendentes.append(aposta)
    salvar_json(apostas_ainda_pendentes, ARQUIVO_PENDENTES)
    salvar_json(historico, ARQUIVO_HISTORICO)

# --- FUNÇÕES DE ANÁLISE ---

def calcular_estatisticas_historicas(df):
    if df.empty: return {}, {}
    cols_stats = ['FTHG', 'FTAG', 'HC', 'AC', 'HS', 'AS', 'HST', 'AST', 'HY', 'AY', 'HR', 'AR']
    for col in cols_stats:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        else:
            df[col] = 0
    print("  -> 📊 Pré-calculando estatísticas do banco de dados histórico...")
    df.dropna(subset=['HomeTeam', 'AwayTeam', 'Date'], inplace=True)
    try:
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
        df.dropna(subset=['Date'], inplace=True)
    except Exception:
        return {}, {}
    df['Resultado'] = df.apply(lambda r: 'V' if r['FTHG'] > r['FTAG'] else ('E' if r['FTHG'] == r['FTAG'] else 'D'), axis=1)
    stats_casa = df.groupby('HomeTeam').agg(avg_gols_marcados_casa=('FTHG', 'mean'), avg_gols_sofridos_casa=('FTAG', 'mean'), total_jogos_casa=('HomeTeam', 'count'))
    stats_fora = df.groupby('AwayTeam').agg(avg_gols_marcados_fora=('FTAG', 'mean'), avg_gols_sofridos_fora=('FTHG', 'mean'), total_jogos_fora=('AwayTeam', 'count'))
    vitorias_casa = df[df['Resultado'] == 'V'].groupby('HomeTeam').size().rename('vitorias_casa')
    derrotas_casa = df[df['Resultado'] == 'D'].groupby('HomeTeam').size().rename('derrotas_casa')
    vitorias_fora = df[df['Resultado'] == 'D'].groupby('AwayTeam').size().rename('vitorias_fora')
    derrotas_fora = df[df['Resultado'] == 'V'].groupby('AwayTeam').size().rename('derrotas_fora')
    stats_individuais = pd.concat([stats_casa, stats_fora, vitorias_casa, vitorias_fora, derrotas_fora, derrotas_casa], axis=1).fillna(0)
    stats_individuais['perc_vitorias_casa'] = (stats_individuais.get('vitorias_casa', 0) / stats_individuais['total_jogos_casa']) * 100
    stats_individuais['perc_derrotas_fora'] = (stats_individuais.get('derrotas_fora', 0) / stats_individuais['total_jogos_fora']) * 100
    stats_individuais = stats_individuais.to_dict('index')
    df['TotalGols'] = df['FTHG'] + df['FTAG']
    df['H2H_Key'] = df.apply(lambda row: '|'.join(sorted([str(row['HomeTeam']), str(row['AwayTeam'])])), axis=1)
    stats_h2h = df.groupby('H2H_Key').agg(avg_gols_h2h=('TotalGols', 'mean'), total_jogos_h2h=('H2H_Key', 'count')).to_dict('index')
    print(f"  -> Estatísticas para {len(stats_individuais)} times e {len(stats_h2h)} confrontos calculadas.")
    return stats_individuais, stats_h2h

def rodar_analise_completa():
    verificar_apostas_pendentes()
    print(f"\n--- 🦅 Iniciando ciclo de análise de novas oportunidades... ---")
    apostas_pendentes = carregar_json(ARQUIVO_PENDENTES, [])
    ids_pendentes = [aposta['id_partida'] for aposta in apostas_pendentes]
    print(f"  -> IDs de apostas pendentes que serão ignoradas: {ids_pendentes}")
    jogos_principais = buscar_jogos_sofascore()
    if not jogos_principais:
        print("Nenhum jogo novo encontrado. Encerrando o ciclo.")
        return
    jogos_com_odds = buscar_odds_the_odds_api(API_KEY_ODDS)
    contexto = {"stats_individuais": {}, "stats_h2h": {}}
    try:
        df_historico = pd.read_csv(ARQUIVO_HISTORICO_CORRIGIDO, low_memory=False)
        contexto["stats_individuais"], contexto["stats_h2h"] = calcular_estatisticas_historicas(df_historico)
    except FileNotFoundError:
        print(f"  -> ⚠️ AVISO: Arquivo histórico '{ARQUIVO_HISTORICO_CORRIGIDO}' não encontrado.")
        return
    print(f"\n--- 🔬 Analisando {len(jogos_principais)} jogos encontrados... ---")
    lista_de_funcoes = [analisar_reacao_gigante, analisar_classico_de_gols, analisar_visitante_fraco]

    for jogo in jogos_principais:
        id_partida = jogo.get('id_partida')
        time_casa = jogo['home_team']
        time_fora = jogo['away_team']

        if id_partida in ids_pendentes:
            continue

        print(f"\n--------------------------------------------------\nAnalisando NOVO Jogo: {time_casa} vs {time_fora} (ID: {id_partida})")

        # >>> INÍCIO DO BLOCO DE CÓDIGO RESTAURADO <<<
        jogo['bookmakers'] = []
        if jogos_com_odds:
            melhor_match_odds = None
            maior_pontuacao = 75
            for jogo_odd in jogos_com_odds:
                pontuacao = fuzz.token_set_ratio(f"{time_casa} {time_fora}", f"{jogo_odd['home_team']} {jogo_odd['away_team']}")
                if pontuacao > maior_pontuacao:
                    maior_pontuacao = pontuacao
                    melhor_match_odds = jogo_odd
            if melhor_match_odds:
                print(f"  -> Odds encontradas com {maior_pontuacao}% de confiança.")
                jogo['bookmakers'] = melhor_match_odds.get('bookmakers', [])

        oportunidade_encontrada_para_o_jogo = False
        for func_estrategia in lista_de_funcoes:
            resultado = func_estrategia(jogo, contexto, debug=True)
            if isinstance(resultado, dict) and resultado.get('type') == 'aposta':
                oportunidade_encontrada_para_o_jogo = True
                oportunidade = resultado
                if oportunidade.get('odd'):
                    if oportunidade.get('odd', 0) >= ODD_MINIMA_GLOBAL:
                        print(f"  -> ✅ OPORTUNIDADE COM ODD APROVADA! Estratégia: {oportunidade['nome_estrategia']}")
                        mensagem = f"*{oportunidade.get('emoji', '⚠️')} ENTRADA VALIDADA {oportunidade.get('emoji', '⚠️')}*\n\n*Estratégia:* {oportunidade.get('nome_estrategia', 'N/A')}\n*⚽ JOGO:* {time_casa} vs {time_fora}\n*📈 MERCADO:* {oportunidade.get('mercado', 'N/A')}\n*📊 ODD ENCONTRADA:* *{oportunidade.get('odd')}*\n\n*🔍 Análise do Falcão:* _{oportunidade.get('motivo', 'N/A')}_"
                        enviar_alerta_telegram(mensagem)
                    else:
                        print(f"  -> ❌ OPORTUNIDADE REPROVADA PELA ODD MÍNIMA ({oportunidade.get('odd', 0)} < {ODD_MINIMA_GLOBAL})")
                        oportunidade_encontrada_para_o_jogo = False # Reprovado, então não salva
                else:
                    print(f"  -> ✅ OPORTUNIDADE SEM ODD ENCONTRADA! Estratégia: {oportunidade['nome_estrategia']}")
                    mensagem = f"*{oportunidade.get('emoji', '⚠️')} ENTRADA VALIDADA (SEM ODD) {oportunidade.get('emoji', '⚠️')}*\n\n*Estratégia:* {oportunidade.get('nome_estrategia', 'N/A')}\n*⚽ JOGO:* {time_casa} vs {time_fora}\n*📈 MERCADO SUGERIDO:* {oportunidade.get('mercado', 'N/A')}\n\n*🔍 Análise do Falcão:* _{oportunidade.get('motivo', 'N/A')}_\n\n_NOTA: Verifique a odd na sua casa de apostas e decida se a entrada tem valor._"
                    enviar_alerta_telegram(mensagem)

                if oportunidade_encontrada_para_o_jogo:
                    nova_aposta = {
                        'id_partida': id_partida,
                        'times': f"{time_casa} vs {time_fora}",
                        'mercado': oportunidade['mercado'],
                        'odd_entrada': oportunidade.get('odd'),
                        'data_aposta': str(date.today())
                    }
                    apostas_pendentes.append(nova_aposta)
                    salvar_json(apostas_pendentes, ARQUIVO_PENDENTES)
                    print(f"  -> Oportunidade salva em '{ARQUIVO_PENDENTES}'.")
                break

            elif isinstance(resultado, str):
                print(f"    - Estratégia '{func_estrategia.__name__}': {resultado}")

        if not oportunidade_encontrada_para_o_jogo:
            print("  -> Nenhuma estratégia encontrou oportunidade para este jogo.")
        # >>> FIM DO BLOCO DE CÓDIGO RESTAURADO <<<

    print("\n--- Ciclo de análise de novas oportunidades finalizado. ---")

# --- PONTO DE ENTRADA ---
if __name__ == "__main__":
    rodar_analise_completa()
