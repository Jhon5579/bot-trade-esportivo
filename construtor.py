import os
import requests
import json
import time
import csv

print("--- Módulo construtor.py carregado ---")

# --- 1. CONFIGURAÇÕES ---
NOME_ARQUIVO_CSV = 'dados_historicos.csv'
COLUNA_TIME_CASA = 'HomeTeam'
COLUNA_TIME_FORA = 'AwayTeam'

NOME_ARQUIVO_CATALOGO = 'catalogo_times.json'
API_KEY_FOOTBALL = os.environ.get('API_FOOTBALL_KEY')

# --- 2. FUNÇÕES AUXILIARES ---

def carregar_catalogo_existente():
    try:
        with open(NOME_ARQUIVO_CATALOGO, 'r', encoding='utf-8') as f:
            print(f"Arquivo '{NOME_ARQUIVO_CATALOGO}' encontrado. Carregando catálogo existente.")
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Arquivo '{NOME_ARQUIVO_CATALOGO}' não encontrado. Começando um novo.")
        return {}

def salvar_catalogo(catalogo):
    with open(NOME_ARQUIVO_CATALOGO, 'w', encoding='utf-8') as f:
        json.dump(catalogo, f, indent=4, ensure_ascii=False)

def extrair_times_do_csv():
    nomes_unicos = set()
    try:
        with open(NOME_ARQUIVO_CSV, 'r', encoding='utf-8') as f:
            leitor_csv = csv.DictReader(f)
            for linha in leitor_csv:
                if linha.get(COLUNA_TIME_CASA): nomes_unicos.add(linha[COLUNA_TIME_CASA])
                if linha.get(COLUNA_TIME_FORA): nomes_unicos.add(linha[COLUNA_TIME_FORA])
        print(f"✅ Encontrados {len(nomes_unicos)} times únicos no arquivo '{NOME_ARQUIVO_CSV}'.")
        return sorted(list(nomes_unicos))
    except FileNotFoundError:
        print(f"❌ ERRO: O arquivo '{NOME_ARQUIVO_CSV}' não foi encontrado.")
        return None
    except Exception as e:
        print(f"❌ ERRO ao ler o arquivo CSV: {e}")
        return None

# --- 3. LÓGICA PRINCIPAL ---

def main():
    print("--- Função main() iniciada ---")
    if not API_KEY_FOOTBALL:
        print("❌ ERRO FATAL: Secret 'API_FOOTBALL_KEY' não configurado.")
        return

    times_do_csv = extrair_times_do_csv()
    if not times_do_csv: return

    catalogo = carregar_catalogo_existente()

    print(f"\nIniciando processamento de {len(times_do_csv)} times do CSV...")

    headers_football = {'x-apisports-key': API_KEY_FOOTBALL}
    url_football_teams = "https://v3.football.api-sports.io/teams"

    for nome_time_csv in times_do_csv:
        if nome_time_csv in catalogo:
            continue

        print(f"\n--------------------------------------------------")
        print(f"Processando novo time do CSV: '{nome_time_csv}'")

        params = {'search': nome_time_csv}
        try:
            response = requests.get(url_football_teams, headers=headers_football, params=params, timeout=15)
            if response.status_code != 200:
                print(f" >> ERRO na API-FOOTBALL. Status: {response.status_code}.")
                continue
            resultados = response.json().get('response', [])
        except Exception as e:
            print(f"Erro de conexão com API-FOOTBALL: {e}")
            continue

        if not resultados:
            print(" >> Nenhum resultado encontrado na API-FOOTBALL.")
            continue

        print(" >> Resultados encontrados:")
        for i, item in enumerate(resultados):
            time_info = item.get('team', {})
            print(f"  [{i+1}] Nome: {time_info.get('name')}, País: {time_info.get('country')}, ID: {time_info.get('id')}")

        while True:
            escolha_str = input(" >> Digite os números (ex: 1,2), 't' (todos), 'p' (pular) ou 's' (sair): ").lower()
            if escolha_str == 's':
                print("Saindo do script...")
                return
            if escolha_str == 'p':
                print(f"Pulando o time '{nome_time_csv}'.")
                break

            indices_escolhidos = []
            try:
                if escolha_str == 't':
                    indices_escolhidos = list(range(len(resultados)))
                    print("  Adicionando todos os resultados da lista...")
                else:
                    indices_escolhidos = [int(num.strip()) - 1 for num in escolha_str.split(',')]

                catalogo.setdefault(nome_time_csv, [])
                adicionado_novo = False
                for indice in indices_escolhidos:
                    if 0 <= indice < len(resultados):
                        time_escolhido = resultados[indice]['team']
                        novo_time_obj = { "id": time_escolhido['id'], "country": time_escolhido['country'], "name_api_football": time_escolhido['name'] }
                        if novo_time_obj not in catalogo[nome_time_csv]:
                            catalogo[nome_time_csv].append(novo_time_obj)
                            print(f"  ✅ Adicionado: '{time_escolhido['name']}' (ID: {time_escolhido['id']})")
                            adicionado_novo = True
                        else:
                            print(f"  ℹ️  Informação: '{time_escolhido['name']}' (ID: {time_escolhido['id']}) já estava na lista.")
                    else:
                        print(f"  ⚠️ Número '{indice + 1}' é inválido e foi ignorado.")

                if adicionado_novo:
                    salvar_catalogo(catalogo)
                break 
            except ValueError:
                print("Entrada inválida. Por favor, use números ou uma das letras de opção.")

        time.sleep(7)

    print("\n--------------------------------------------------")
    print("🎉 Processo concluído! Seu 'catalogo_times.json' foi criado/atualizado.")

# --- PONTO DE ENTRADA DO SCRIPT ---
if __name__ == "__main__":
    print("--- Script sendo executado diretamente ---")
    main()