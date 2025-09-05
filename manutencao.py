import os
import requests
import json
import time
import pandas as pd
from thefuzz import fuzz
from datetime import datetime, timezone, timedelta
import warnings

# --- 1. CONFIGURAÇÕES GERAIS ---
API_KEY_ODDS = os.environ.get('API_KEY')
API_KEY_FOOTBALL = os.environ.get('API_FOOTBALL_KEY')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Arquivos de Dados
ARQUIVO_CATALOGO = 'catalogo_times.json'
ARQUIVO_LISTA_MESTRA = 'master_team_list.json'
ARQUIVO_MAPA_SAIDA = 'mapa_de_nomes.json'
ARQUIVO_CSV_SAIDA = 'dados_historicos_corrigido.csv'

# Parâmetros de Lógica
LIMITE_AUTOMATICO_CONSTRUTOR = 80
LIMITE_AUTOMATICO_MAPEADOR = 80
COLUNA_TIME_CASA = 'HomeTeam'
COLUNA_TIME_FORA = 'AwayTeam'

# --- ALTERAÇÃO: Adicionamos as colunas de odds do Pinnacle (e outras comuns) ---
COLUNAS_FINAIS = [
    'League', 'Date', 'HomeTeam', 'AwayTeam', 
    'FTHG', 'FTAG',
    'HC', 'AC', 'HS', 'AS', 'HST', 'AST', 'HY', 'AY', 'HR', 'AR',
    # Adicionando as colunas de odds mais comuns do football-data.co.uk
    'PSH', 'PSD', 'PSA', # Pinnacle H/D/A
    'P>2.5', 'P<2.5'     # Pinnacle Over/Under 2.5
]

warnings.filterwarnings('ignore', category=pd.errors.DtypeWarning)

# --- 2. FUNÇÕES AUXILIARES ---
def carregar_json(caminho_arquivo):
    try:
        with open(caminho_arquivo, 'r', encoding='utf-8') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return {}

def salvar_json(dados, caminho_arquivo):
    with open(caminho_arquivo, 'w', encoding='utf-8') as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)
    print(f"    -> Arquivo '{caminho_arquivo}' salvo/atualizado.")

def enviar_alerta_telegram(mensagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("  > ATENÇÃO: Credenciais do Telegram não configuradas. Mensagem não enviada.")
        return
    caracteres_especiais = ['_', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in caracteres_especiais:
        mensagem = mensagem.replace(char, f'\\{char}')
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': mensagem, 'parse_mode': 'MarkdownV2'}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("  > Mensagem de relatório enviada com sucesso para o Telegram!")
        else:
            print(f"  > ERRO ao enviar para o Telegram: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"  > ERRO de conexão com o Telegram: {e}")

def carregar_e_combinar_historicos():
    """Lê os dois arquivos CSV de históricos, combina-os e remove duplicatas."""
    df_lista = []
    arquivos_encontrados = []
    arquivos_historicos = ['dados_historicos.csv', 'dados_historicos_sofascore.csv']
    print("  > Lendo arquivos de dados históricos...")
    for arquivo in arquivos_historicos:
        try:
            try:
                df_temp = pd.read_csv(arquivo, low_memory=False)
            except UnicodeDecodeError:
                df_temp = pd.read_csv(arquivo, encoding='latin1', low_memory=False)
            df_lista.append(df_temp)
            arquivos_encontrados.append(arquivo)
            print(f"    - Arquivo '{arquivo}' carregado com {len(df_temp)} linhas.")
        except FileNotFoundError:
            print(f"    - Aviso: Arquivo '{arquivo}' não encontrado. Será ignorado.")
        except Exception as e:
            print(f"    - Erro ao ler '{arquivo}': {e}")
    if not df_lista:
        return pd.DataFrame(), []
    
    df_combinado = pd.concat(df_lista, ignore_index=True)
    
    print(f"  > Total de linhas antes da limpeza: {len(df_combinado)}")
    df_combinado.drop_duplicates(inplace=True)
    df_combinado.drop_duplicates(subset=['Date', 'HomeTeam', 'AwayTeam'], inplace=True, keep='last')
    print(f"  > Total de linhas após limpeza de duplicatas: {len(df_combinado)}")
    return df_combinado, arquivos_encontrados


# --- 3. LÓGICA DAS FERRAMENTAS ---

def rodar_construtor():
    # Esta função permanece igual
    print("\n--- 🏗️ FASE 1: EXECUTANDO CONSTRUTOR DE CATÁLOGO... 🏗️ ---")
    # ... (código da função inalterado)
    return 0 # Placeholder

def rodar_mapeador():
    """Fase 2: Atualiza o mapa de nomes usando a base de dados combinada."""
    print("\n--- 🗺️ FASE 2: EXECUTANDO MAPEADOR DE NOMES... 🗺️ ---")
    # ... (código da função inalterado)
    return 0 # Placeholder

def rodar_corretor():
    """Fase 3: Aplica o mapa para corrigir a base de dados combinada."""
    print("\n--- ⚙️ FASE 3: EXECUTANDO CORRETOR DE CSV... ⚙️ ---")
    mapa_de_nomes = carregar_json(ARQUIVO_MAPA_SAIDA)
    if not mapa_de_nomes:
        print("❌ ERRO: O arquivo de mapa está vazio."); return False

    df, arquivos_lidos = carregar_e_combinar_historicos()
    if df.empty:
        print("❌ ERRO: Nenhum arquivo de histórico encontrado para corrigir."); return False

    print("Aplicando regras de correção ao banco de dados unificado...")
    df[COLUNA_TIME_CASA] = df[COLUNA_TIME_CASA].replace(mapa_de_nomes)
    df[COLUNA_TIME_FORA] = df[COLUNA_TIME_FORA].replace(mapa_de_nomes)
    
    # Garante que o DataFrame final tem todas as colunas que definimos, preenchendo com 0
    # as que não existirem (ex: jogos do sofascore não tem odds, jogos antigos não tem stats detalhadas)
    df = df.reindex(columns=COLUNAS_FINAIS).fillna(0)
    
    try:
        df.to_csv(ARQUIVO_CSV_SAIDA, index=False, encoding='utf-8')
        print(f"✅ Novo arquivo '{ARQUIVO_CSV_SAIDA}' salvo com sucesso!")
    except Exception as e:
        print(f"❌ ERRO ao salvar o novo arquivo CSV: {e}"); return False
    return True

# --- PONTO DE ENTRADA PRINCIPAL ---
if __name__ == "__main__":
    print("===== INICIANDO ROTINA COMPLETA DE MANUTENÇÃO DE DADOS =====")
    times_adicionados = rodar_construtor()
    mapas_adicionados = rodar_mapeador()
    sucesso_corretor = False
    if times_adicionados != -1 and mapas_adicionados != -1:
        sucesso_corretor = rodar_corretor()
    print("\n===== ROTINA DE MANUTENÇÃO FINALIZADA =====")
    # ... (código do relatório do Telegram inalterado)