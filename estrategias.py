# api_externas.py

import requests
from datetime import date

def buscar_jogos_api_football(api_key):
    """
    Busca na API-Football TODOS os jogos do dia com uma única chamada de API.
    Esta é a versão mais eficiente para o plano gratuito.
    """
    DATA_HOJE = date.today().strftime('%Y-%m-%d')
    headers = {'x-rapidapi-host': "v3.football.api-sports.io", 'x-rapidapi-key': api_key}
    todos_os_jogos = []

    print(f"--- ⚽ Buscando TODOS os jogos do dia {DATA_HOJE} na API-Football (1 chamada)... ---")

    # URL que pede os jogos do dia, sem filtro de liga
    url = f"https://v3.football.api-sports.io/fixtures?date={DATA_HOJE}"
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json().get('response', [])
            if data:
                print(f"--- ✅ Sucesso! Encontrados {len(data)} jogos no total. ---")
                for fixture in data:
                    jogo = {
                        'id_partida': fixture['fixture']['id'],
                        'home_team': fixture['teams']['home']['name'],
                        'away_team': fixture['teams']['away']['name'],
                        'league': fixture['league']['name'],
                        'timestamp': fixture['fixture']['timestamp']
                    }
                    todos_os_jogos.append(jogo)
            else:
                print("--- ⚠️ Nenhum jogo foi encontrado para a data de hoje com a sua chave de API. ---")
        else:
            print(f"--- ❌ Erro ao buscar os jogos: {response.status_code} - {response.text} ---")

    except requests.exceptions.RequestException as e:
        print(f"--- ❌ Erro de conexão: {e} ---")
        
    return todos_os_jogos


def buscar_odds_the_odds_api(api_key):
    """
    Busca odds na The Odds API para futebol.
    VERSÃO MELHORADA: Inclui tratamento de erros detalhado.
    """
    print("\n--- 👍 Buscando as poucas odds disponíveis na The Odds API... ---")
    
    params = {
        'api_key': api_key,
        'regions': 'br,eu',
        'markets': 'h2h',
        'bookmakers': 'pinnacle',
        'oddsFormat': 'decimal'
    }
    
    url = "https://api.the-odds-api.com/v4/sports/soccer/odds" # URL genérica para futebol
    
    jogos_com_odds = []
    
    try:
        response = requests.get(url, params=params, timeout=20)
        
        if response.status_code == 200:
            data = response.json()
            if data:
                print(f"  -> ✅ Sucesso! Encontradas odds para {len(data)} jogos.")
                for jogo in data:
                    jogos_com_odds.append({
                        'id': jogo.get('id'),
                        'home_team': jogo.get('home_team'),
                        'away_team': jogo.get('away_team'),
                        'bookmakers': jogo.get('bookmakers', [])
                    })
            else:
                print("  -> Nenhuma odd encontrada na The Odds API para os parâmetros atuais.")
        else:
            print(f"\n--- 🚨 ERRO AO CHAMAR A THE ODDS API 🚨 ---")
            print(f"  -> Status da Resposta: {response.status_code}")
            print(f"  -> Mensagem de Erro: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"  -> ERRO de conexão com a The Odds API: {e}")
        
    return jogos_com_odds
