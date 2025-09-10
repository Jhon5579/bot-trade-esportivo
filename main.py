import os
import requests
import json
from datetime import datetime, timezone, timedelta
import time
from thefuzz import fuzz, process
import pandas as pd

# --- IMPORTAÇÃO DOS MÓDULOS DO PROJETO ---
from gestao_banca import carregar_banca, calcular_stake, registrar_resultado
from utils import carregar_json, salvar_json
from config import *
from estrategias import *
from api_externas import buscar_jogos_api_football, buscar_odds_the_odds_api

# --- ARQUIVOS E CONSTANTES ---
ARQUIVO_PENDENTES = 'apostas_pendentes.json'
ARQUIVO_HISTORICO_APOSTAS = 'historico_de_apostas.json'
ARQUIVO_RESULTADOS_DIA = 'resultados_do_dia.json'
ARQUIVO_HISTORICO_CORRIGIDO = 'dados_historicos_corrigido.csv'
CASA_ALVO = 'pinnacle'
ARQUIVO_MAPA_LIGAS = 'mapa_ligas.json'

# --- FUNÇÕES DE SUPORTE ---

def enviar_alerta_telegram(mensagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("  -> AVISO: Tokens do Telegram não encontrados. Mensagem não enviada.")
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
        total_jogos_casa=('HomeTeam', 'count')
    )

    stats_fora = df.groupby('AwayTeam').agg(
        avg_gols_marcados_fora=('FTAG', 'mean'),
        avg_gols_sofridos_fora=('FTHG', 'mean'),
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

    df['TotalGols'] = df['FTHG'] + df['FTAG']
    df['H2H_Key'] = df.apply(lambda row: '|'.join(sorted([str(row['HomeTeam']), str(row['AwayTeam'])])), axis=1)
    stats_h2h = df.groupby('H2H_Key').agg(avg_gols_h2h=('TotalGols', 'mean'), total_jogos_h2h=('H2H_Key', 'count')).to_dict('index')
    
    print(f"  -> Estatísticas para {len(stats_individuais)} times e {len(stats_h2h)} confrontos calculadas.")
    return stats_individuais, stats_h2h

# --- FUNÇÃO PRINCIPAL ---
def rodar_analise_completa():
    print(f"\n--- 🦅 Iniciando ciclo de análise... ---")
    
    jogos_principais = buscar_jogos_api_football(API_KEY_FOOTBALL)
    if not jogos_principais:
        print("Nenhum jogo encontrado na API-Football. Encerrando o ciclo.")
        return

    jogos_com_odds = buscar_odds_the_odds_api(API_KEY_ODDS)
    
    contexto = {
        "mapa_ligas": carregar_json(ARQUIVO_MAPA_LIGAS),
        "stats_individuais": {},
        "stats_h2h": {}
    }
    
    try:
        df_historico = pd.read_csv(ARQUIVO_HISTORICO_CORRIGIDO, low_memory=False)
        contexto["stats_individuais"], contexto["stats_h2h"] = calcular_estatisticas_historicas(df_historico)
    except FileNotFoundError:
        print(f"  -> ⚠️ AVISO: Arquivo histórico '{ARQUIVO_HISTORICO_CORRIGIDO}' não encontrado.")
    
    print(f"\n--- 🔬 Analisando os {len(jogos_principais)} jogos encontrados... ---")

    lista_de_funcoes = [
        analisar_reacao_gigante,
        analisar_classico_de_gols,
        analisar_visitante_fraco
    ]
    
    for jogo in jogos_principais:
        time_casa = jogo['home_team']
        time_fora = jogo['away_team']
        print(f"\n--------------------------------------------------\nAnalisando Jogo: {time_casa} vs {time_fora}")

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

        for func in lista_de_funcoes:
            oportunidade = func(jogo, contexto)
            if not oportunidade:
                continue

            if oportunidade.get('type') == 'aposta':
                if oportunidade.get('odd'):
                    if oportunidade.get('odd', 0) >= ODD_MINIMA_GLOBAL:
                        print(f"  -> ✅ OPORTUNIDADE COM ODD APROVADA! Estratégia: {oportunidade['nome_estrategia']}")
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
                    print(f"  -> ✅ OPORTUNIDADE SEM ODD ENCONTRADA! Estratégia: {oportunidade['nome_estrategia']}")
                    mensagem = f"*{oportunidade.get('emoji', '⚠️')} ENTRADA VALIDADA (SEM ODD) {oportunidade.get('emoji', '⚠️')}*\n\n"
                    mensagem += f"*Estratégia:* {oportunidade.get('nome_estrategia', 'N/A')}\n"
                    mensagem += f"*⚽ JOGO:* {time_casa} vs {time_fora}\n"
                    mensagem += f"*📈 MERCADO SUGERIDO:* {oportunidade.get('mercado', 'N/A')}\n\n"
                    mensagem += f"*🔍 Análise do Falcão:* _{oportunidade.get('motivo', 'N/A')}_\n\n"
                    mensagem += "_NOTA: Verifique a odd na sua casa de apostas e decida se a entrada tem valor._"
                    enviar_alerta_telegram(mensagem)
                
                break
    
    print("\n--- Ciclo de análise finalizado. ---")

# --- PONTO DE ENTRADA ---
if __name__ == "__main__":
    print("--- Iniciando execução única do bot ---")
    rodar_analise_completa()
    print("\n--- Ciclo único de análise concluído com sucesso. ---")
