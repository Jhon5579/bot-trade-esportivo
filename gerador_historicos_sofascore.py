import os
import requests
import json
import time
import pandas as pd
from datetime import datetime

# --- 1. CONFIGURAÇÕES ---
ARQUIVO_SAIDA_CSV = 'dados_historicos_sofascore.csv'
ARQUIVO_ESTADO = 'gerador_sofascore_estado.json' # Arquivo para salvar o progresso

# --- SUA LISTA DE DESEJOS (VERSÃO SOFASCORE) ---
# Para encontrar o ID da Liga e da Temporada no Sofascore:
# 1. Vá para a página da liga no Sofascore (ex: Premier League).
# 2. Selecione a temporada desejada (ex: 2023/2024).
# 3. O ID da Liga estará na URL (ex: /tournament/football/england/premier-league/17) -> ID da Liga = 17
# 4. O ID da Temporada também (ex: /season/52182) -> ID da Temporada = 52182
LIGAS_PARA_BUSCAR = [
    {"id_liga": 17, "nome_liga": "Premier League", "temporadas": {2024: 52182, 2023: 41886, 2022: 37036}},
    {"id_liga": 8, "nome_liga": "La Liga", "temporadas": {2024: 52376, 2023: 42409, 2022: 37223}},
    {"id_liga": 23, "nome_liga": "Serie A", "temporadas": {2024: 52760, 2023: 42293, 2022: 37375}},
    {"id_liga": 35, "nome_liga": "Bundesliga", "temporadas": {2024: 52608, 2023: 42268, 2022: 37166}},
    {"id_liga": 325, "nome_liga": "Brasileirao Serie A", "temporadas": {2024: 52422, 2023: 42841, 2022: 37330}},
    {"id_liga": 7, "nome_liga": "Champions League", "temporadas": {2024: 52162, 2023: 42136, 2022: 36993}},
]

# --- 2. FUNÇÕES AUXILIARES ---
def carregar_estado():
    try:
        with open(ARQUIVO_ESTADO, 'r') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return {"processados": []}

def salvar_estado(estado):
    with open(ARQUIVO_ESTADO, 'w') as f: json.dump(estado, f, indent=4)

def formatar_dados_sofascore(eventos_json, nome_liga):
    """Transforma a resposta da API do SOFASCORE em linhas para o nosso CSV."""
    linhas_de_dados = []
    for evento in eventos_json:
        # Pula jogos que não foram finalizados ou não têm placar
        if evento['status']['code'] != 100 or 'current' not in evento['homeScore']:
            continue

        linha = {
            'League': nome_liga,
            'Date': datetime.fromtimestamp(evento['startTimestamp']).strftime('%Y-%m-%d'),
            'HomeTeam': evento['homeTeam']['name'],
            'AwayTeam': evento['awayTeam']['name'],
            'FTHG': evento['homeScore']['current'],
            'FTAG': evento['awayScore']['current'],
        }
        linhas_de_dados.append(linha)
    return linhas_de_dados

# --- 3. LÓGICA PRINCIPAL ---
def main():
    print("--- 🏭 Iniciando Gerador de Banco de Dados Históricos (Fonte: Sofascore)... 🏭 ---")

    # Headers para simular um navegador, essencial para a API do Sofascore
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    estado = carregar_estado()

    df_principal = pd.read_csv(ARQUIVO_SAIDA_CSV) if os.path.exists(ARQUIVO_SAIDA_CSV) else pd.DataFrame()

    for liga_info in LIGAS_PARA_BUSCAR:
        for ano, id_temporada in liga_info['temporadas'].items():
            id_unico = f"{liga_info['id_liga']}-{id_temporada}"

            if id_unico in estado['processados']:
                print(f"- Pulando {liga_info['nome_liga']} {ano} (já processado).")
                continue

            print(f"\nBuscando dados para: {liga_info['nome_liga']} - Temporada {ano}")

            pagina_atual = 0
            dados_completos_liga = []

            while True: # Loop para lidar com a paginação do Sofascore
                url = f"https://api.sofascore.com/api/v1/unique-tournament/{liga_info['id_liga']}/season/{id_temporada}/events/last/{pagina_atual}"
                try:
                    response = requests.get(url, headers=headers)
                    if response.status_code != 200:
                        print(f"  ❌ Fim dos dados para esta temporada (ou erro {response.status_code}).")
                        break # Encerra o loop desta temporada

                    resposta_json = response.json()
                    eventos = resposta_json.get('events', [])
                    if not eventos:
                        print("  ✅ Nenhum jogo a mais encontrado. Concluindo temporada.")
                        break # Sai do loop de paginação se não houver mais eventos

                    dados_pagina = formatar_dados_sofascore(eventos, liga_info['nome_liga'])
                    dados_completos_liga.extend(dados_pagina)

                    print(f"  > Página {pagina_atual + 1} processada. {len(dados_pagina)} jogos encontrados.")

                    pagina_atual += 1
                    time.sleep(3) # Pausa de 3 segundos para ser responsável com a API

                except Exception as e:
                    print(f"  ❌ ERRO de conexão: {e}"); return

            if dados_completos_liga:
                df_liga = pd.DataFrame(dados_completos_liga)
                df_principal = pd.concat([df_principal, df_liga], ignore_index=True)
                df_principal.drop_duplicates(subset=['Date', 'HomeTeam', 'AwayTeam'], inplace=True, keep='last')

            estado['processados'].append(id_unico)
            salvar_estado(estado)
            df_principal.to_csv(ARQUIVO_SAIDA_CSV, index=False)
            print(f"💾 Dados de {liga_info['nome_liga']} {ano} salvos. Banco de dados agora com {len(df_principal)} jogos.")

    print("\n--------------------------------------------------")
    print("🎉 Processo de construção concluído!")
    print(f"Seu arquivo '{ARQUIVO_SAIDA_CSV}' foi criado/atualizado.")


if __name__ == "__main__":
    main()