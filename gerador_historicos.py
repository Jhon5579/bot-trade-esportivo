import os
import requests
import json
import time
import pandas as pd

# --- 1. CONFIGURAÇÕES ---
API_KEY_FOOTBALL = os.environ.get('API_FOOTBALL_KEY')
ARQUIVO_SAIDA_CSV = 'dados_historicos.csv'
ARQUIVO_ESTADO = 'gerador_historicos_estado.json' # Arquivo para salvar o progresso

# --- SUA LISTA DE DESEJOS ---
# Edite esta lista com os IDs das ligas e as temporadas que você quer baixar.
# Para encontrar o ID de uma liga, você pode usar o `construtor_mestre.py` ou o site da API-Football.
LIGAS_PARA_BUSCAR = [
    # --- Ligas Principais da Europa ---
    {"id_liga": 39, "nome_liga": "Premier League", "temporadas": [2024, 2023, 2022]},
    {"id_liga": 140, "nome_liga": "La Liga", "temporadas": [2024, 2023, 2022]},
    {"id_liga": 135, "nome_liga": "Serie A", "temporadas": [2024, 2023, 2022]},
    {"id_liga": 78, "nome_liga": "Bundesliga", "temporadas": [2024, 2023, 2022]},
    {"id_liga": 61, "nome_liga": "Ligue 1", "temporadas": [2024, 2023, 2022]},

    # --- Liga Principal do Brasil ---
    {"id_liga": 71, "nome_liga": "Brasileirao Serie A", "temporadas": [2024, 2023, 2022]},

    # --- Outras Ligas Populares ---
    {"id_liga": 2, "nome_liga": "Champions League", "temporadas": [2024, 2023, 2022]},
    {"id_liga": 3, "nome_liga": "Europa League", "temporadas": [2024, 2023, 2022]},
    {"id_liga": 11, "nome_liga": "Copa Libertadores", "temporadas": [2024, 2023, 2022]},
]

# --- 2. FUNÇÕES AUXILIARES ---
def carregar_estado():
    try:
        with open(ARQUIVO_ESTADO, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"processados": []}

def salvar_estado(estado):
    with open(ARQUIVO_ESTADO, 'w') as f:
        json.dump(estado, f, indent=4)

def formatar_dados(fixtures_json):
    """Transforma a resposta da API em linhas para o nosso CSV."""
    linhas_de_dados = []
    for fixture in fixtures_json:
        # Pula jogos que não foram finalizados
        if fixture['fixture']['status']['short'] != 'FT':
            continue

        linha = {
            'League': fixture['league']['name'],
            'Date': datetime.fromtimestamp(fixture['fixture']['timestamp']).strftime('%Y-%m-%d'),
            'HomeTeam': fixture['teams']['home']['name'],
            'AwayTeam': fixture['teams']['away']['name'],
            'FTHG': fixture['goals']['home'],
            'FTAG': fixture['goals']['away'],
        }
        linhas_de_dados.append(linha)
    return linhas_de_dados

# --- 3. LÓGICA PRINCIPAL ---
def main():
    print("--- 🏭 Iniciando Gerador de Banco de Dados Históricos... 🏭 ---")
    if not API_KEY_FOOTBALL:
        print("❌ ERRO FATAL: Secret 'API_FOOTBALL_KEY' não configurado."); return

    headers = {'x-apisports-key': API_KEY_FOOTBALL}
    estado = carregar_estado()

    # Carrega o DataFrame existente ou cria um novo
    if os.path.exists(ARQUIVO_SAIDA_CSV):
        df_principal = pd.read_csv(ARQUIVO_SAIDA_CSV)
    else:
        df_principal = pd.DataFrame()

    for liga_info in LIGAS_PARA_BUSCAR:
        for temporada in liga_info['temporadas']:
            id_unico = f"{liga_info['id_liga']}-{temporada}"

            # Lógica "resumível"
            if id_unico in estado['processados']:
                print(f"- Pulando {liga_info['nome_liga']} {temporada} (já processado).")
                continue

            print(f"\nBuscando dados para: {liga_info['nome_liga']} - Temporada {temporada}")

            pagina_atual = 1
            dados_completos_liga = []

            while True: # Loop para lidar com a paginação da API
                params = {'league': liga_info['id_liga'], 'season': temporada, 'page': pagina_atual}
                try:
                    response = requests.get("https://v3.football.api-sports.io/fixtures", headers=headers, params=params)
                    if response.status_code != 200:
                        print(f"  ❌ ERRO ao buscar dados: {response.text}")
                        print("  > Provavelmente a cota diária acabou. O progresso foi salvo. Tente novamente amanhã.")
                        return # Encerra a execução do dia

                    resposta_json = response.json()
                    dados_pagina = formatar_dados(resposta_json.get('response', []))
                    dados_completos_liga.extend(dados_pagina)

                    # Verifica se há mais páginas a serem buscadas
                    total_paginas = resposta_json['paging']['total']
                    print(f"  > Página {pagina_atual}/{total_paginas} processada. {len(dados_pagina)} jogos encontrados.")

                    if pagina_atual >= total_paginas:
                        break # Sai do loop de paginação

                    pagina_atual += 1
                    time.sleep(7) # Pausa entre as páginas para não sobrecarregar a API

                except Exception as e:
                    print(f"  ❌ ERRO de conexão: {e}"); return

            # Adiciona os dados coletados ao DataFrame principal
            if dados_completos_liga:
                df_liga = pd.DataFrame(dados_completos_liga)
                df_principal = pd.concat([df_principal, df_liga], ignore_index=True)
                # Remove duplicatas caso a gente rode de novo por acidente
                df_principal.drop_duplicates(inplace=True)

            # Salva o progresso
            estado['processados'].append(id_unico)
            salvar_estado(estado)
            df_principal.to_csv(ARQUIVO_SAIDA_CSV, index=False)
            print(f"✅ Dados de {liga_info['nome_liga']} {temporada} salvos. Banco de dados agora com {len(df_principal)} jogos.")

    print("\n--------------------------------------------------")
    print("🎉 Processo de construção concluído (ou pausado por hoje)!")
    print(f"Seu arquivo '{ARQUIVO_SAIDA_CSV}' foi criado/atualizado.")


if __name__ == "__main__":
    main()