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
            # Tenta ler com utf-8 primeiro, depois com latin1
            try:
                df_temp = pd.read_csv(arquivo)
            except UnicodeDecodeError:
                df_temp = pd.read_csv(arquivo, encoding='latin1')
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
    # Esta função permanece igual, pois sua fonte é a The Odds API
    print("\n--- 🏗️ FASE 1: EXECUTANDO CONSTRUTOR DE CATÁLOGO... 🏗️ ---")
    catalogo = carregar_json(ARQUIVO_CATALOGO)
    lista_mestra = carregar_json(ARQUIVO_LISTA_MESTRA)
    if not lista_mestra:
        print(f"❌ ERRO: Arquivo '{ARQUIVO_LISTA_MESTRA}' essencial não encontrado."); return -1
    url_jogos_dia = f"https://api.the-odds-api.com/v4/sports/soccer/odds?apiKey={API_KEY_ODDS}&regions=eu,us,uk,au&markets=h2h"
    try:
        response_jogos = requests.get(url_jogos_dia, timeout=20)
        jogos_do_dia = response_jogos.json() if response_jogos.status_code == 200 else []
    except Exception as e:
        print(f"  > ERRO de conexão ao buscar jogos: {e}"); return -1
    nomes_da_api = set(jogo['home_team'] for jogo in jogos_do_dia) | set(jogo['away_team'] for jogo in jogos_do_dia)
    times_novos = sorted([nome for nome in nomes_da_api if nome not in catalogo])
    if not times_novos:
        print("✅ Todos os times de hoje já estão no catálogo."); return 0
    print(f"Encontrados {len(times_novos)} novos times para mapear...")
    times_mapeados_nesta_execucao = 0
    for nome_api in times_novos:
        melhor_partida, maior_pontuacao = max(
            ((time_info['team'], fuzz.ratio(nome_api.lower(), time_info['team'].get('name', '').lower())) 
             for time_info in lista_mestra if time_info.get('team')),
            key=lambda item: item[1], default=(None, 0)
        )
        if maior_pontuacao >= LIMITE_AUTOMATICO_CONSTRUTOR:
            print(f"- Processando '{nome_api}': correspondência encontrada '{melhor_partida.get('name')}' ({maior_pontuacao}%).")
            catalogo.setdefault(nome_api, [])
            novo_time_obj = { "id": melhor_partida['id'], "country": melhor_partida['country'], "name_api_football": melhor_partida['name'] }
            if novo_time_obj not in catalogo[nome_api]:
                catalogo[nome_api].append(novo_time_obj)
                times_mapeados_nesta_execucao += 1
    if times_mapeados_nesta_execucao > 0:
        print(f"✅ {times_mapeados_nesta_execucao} novos times adicionados ao catálogo.")
        salvar_json(catalogo, ARQUIVO_CATALOGO)
    else:
        print("Nenhuma nova correspondência forte encontrada para o catálogo.")
    return times_mapeados_nesta_execucao

def rodar_mapeador():
    """Fase 2: Atualiza o mapa de nomes usando a base de dados combinada."""
    print("\n--- 🗺️ FASE 2: EXECUTANDO MAPEADOR DE NOMES... 🗺️ ---")
    mapa_de_nomes, catalogo = carregar_json(ARQUIVO_MAPA_SAIDA), carregar_json(ARQUIVO_CATALOGO)
    if not catalogo:
        print("❌ ERRO: Catálogo de times está vazio."); return -1

    # MODIFICAÇÃO: Usa a nova função para carregar os dados combinados
    df, arquivos_lidos = carregar_e_combinar_historicos()
    if df.empty:
        print("❌ ERRO: Nenhum arquivo de histórico encontrado para mapear."); return -1

    nomes_csv_unicos = set(map(str, df[COLUNA_TIME_CASA].unique())) | set(map(str, df[COLUNA_TIME_FORA].unique()))
    nomes_csv_a_mapear = [nome for nome in nomes_csv_unicos if nome not in mapa_de_nomes]

    if not nomes_csv_a_mapear:
        print("✅ Todos os times do CSV já foram mapeados."); return 0
    print(f"Analisando {len(nomes_csv_a_mapear)} nomes do CSV que ainda não estão no mapa...")
    mudancas_feitas = 0
    for nome_csv in sorted(nomes_csv_a_mapear):
        melhor_partida_api, maior_pontuacao = max(
            ((nome_api, fuzz.ratio(nome_csv.lower(), nome_api.lower())) for nome_api in set(catalogo.keys())),
            key=lambda item: item[1], default=(None, 0)
        )
        if maior_pontuacao >= LIMITE_AUTOMATICO_MAPEADOR:
            mapa_de_nomes[nome_csv] = melhor_partida_api
            mudancas_feitas += 1
            print(f"- Mapeamento automático: '{nome_csv}' -> '{melhor_partida_api}' ({maior_pontuacao}%)")
    if mudancas_feitas > 0:
        print(f"✅ {mudancas_feitas} novas regras de mapeamento adicionadas.")
        salvar_json(mapa_de_nomes, ARQUIVO_MAPA_SAIDA)
    else:
        print("Nenhuma nova regra de mapeamento encontrada nesta execução.")
    return mudancas_feitas

def rodar_corretor():
    """Fase 3: Aplica o mapa para corrigir a base de dados combinada."""
    print("\n--- ⚙️ FASE 3: EXECUTANDO CORRETOR DE CSV... ⚙️ ---")
    mapa_de_nomes = carregar_json(ARQUIVO_MAPA_SAIDA)
    if not mapa_de_nomes:
        print("❌ ERRO: O arquivo de mapa está vazio."); return False

    # MODIFICAÇÃO: Usa a nova função para carregar os dados combinados
    df, arquivos_lidos = carregar_e_combinar_historicos()
    if df.empty:
        print("❌ ERRO: Nenhum arquivo de histórico encontrado para corrigir."); return False

    print("Aplicando regras de correção ao banco de dados unificado...")
    df[COLUNA_TIME_CASA] = df[COLUNA_TIME_CASA].replace(mapa_de_nomes)
    df[COLUNA_TIME_FORA] = df[COLUNA_TIME_FORA].replace(mapa_de_nomes)
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

    fuso_horario = timezone(timedelta(hours=-3))
    data_hora_atual = datetime.now(fuso_horario).strftime('%d/%m/%Y às %H:%M')

    status_geral = "✅ Sucesso"
    if times_adicionados == -1 or mapas_adicionados == -1 or not sucesso_corretor:
        status_geral = "❌ Falha"

    relatorio = (
        f"🛠️ *Relatório de Manutenção Automática* 🛠️\n\n"
        f"*Status Geral:* {status_geral}\n"
        f"*Data:* {data_hora_atual}\n"
        f"-----------------------------------\n\n"
    )

    if times_adicionados != -1:
        relatorio += f"🏗️ *Construtor de Catálogo:*\n- Adicionou *{times_adicionados}* novos times.\n\n"
    else:
        relatorio += f"🏗️ *Construtor de Catálogo:*\n- ❌ Ocorreu um erro nesta fase.\n\n"

    if mapas_adicionados != -1:
        relatorio += f"🗺️ *Mapeador de Nomes:*\n- Criou *{mapas_adicionados}* novos mapeamentos.\n\n"
    else:
        relatorio += f"🗺️ *Mapeador de Nomes:*\n- ❌ Ocorreu um erro nesta fase.\n\n"

    if sucesso_corretor:
        relatorio += f"⚙️ *Corretor de CSV:*\n- ✅ Arquivo de dados unificado e salvo com sucesso."
    else:
        if times_adicionados != -1 and mapas_adicionados != -1:
             relatorio += f"⚙️ *Corretor de CSV:*\n- ❌ Ocorreu um erro nesta fase."

    enviar_alerta_telegram(relatorio)