# api_externas.py

import requests
from datetime import date
from decouple import config

def buscar_jogos_api_football(api_key):
    """
    Busca na API-Football TODOS os jogos do dia com uma única chamada.
    NOTA: O plano gratuito retornará apenas jogos das ligas disponíveis na sua assinatura.
    """
    DATA_HOJE = date.today().strftime('%Y-%m-%d')
    headers = {'x-rapidapi-host': "v3.football.api-sports.io", 'x-rapidapi-key': api_key}
    todos_os_jogos = []

    print(f"--- ⚽ Buscando TODOS os jogos do dia {DATA_HOJE} na API-Football (1 chamada)... ---")

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
                print("--- ⚠️ Nenhum jogo encontrado para hoje na API-Football. ---")
        else:
            print(f"--- ❌ Erro ao buscar os jogos: {response.status_code} - {response.text} ---")

    except requests.exceptions.RequestException as e:
        print(f"--- ❌ Erro de conexão com a API-Football: {e} ---")
        
    return todos_os_jogos


def buscar_odds_the_odds_api(api_key):
    """
    Busca odds na The Odds API, procurando em múltiplas casas de apostas.
    """
    print("\n--- 👍 Buscando odds disponíveis na The Odds API... ---")
    
    CASAS_DE_APOSTAS = 'pinnacle,betfair,bet365,marathonbet'
    params = {
        'api_key': api_key, 'regions': 'br,eu',
        'markets': 'h2h', 'bookmakers': CASAS_DE_APOSTAS,
        'oddsFormat': 'decimal'
    }
    url = "https://api.the-odds-api.com/v4/sports/soccer/odds"
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


def verificar_resultado_api_football(api_key, id_partida):
    """
    Verifica o status e o resultado final de uma partida específica na API-Football.
    Esta função consome 1 chamada da sua cota para cada aposta verificada.
    """
    headers = {'x-rapidapi-host': "v3.football.api-sports.io", 'x-rapidapi-key': api_key}
    url = f"https://v3.football.api-sports.io/fixtures?id={id_partida}"
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json().get('response', [])
            if data:
                fixture_data = data[0]
                status = fixture_data.get('fixture', {}).get('status', {}).get('short', 'NS')
                
                # 'FT' é o código para 'Full Time' (Partida Encerrada)
                if status == 'FT':
                    placar_casa = fixture_data.get('goals', {}).get('home', -1)
                    placar_fora = fixture_data.get('goals', {}).get('away', -1)
                    return "encerrado", placar_casa, placar_fora
                else:
                    return "em_andamento", None, None
    except requests.exceptions.RequestException as e:
        print(f"  -> ERRO de conexão ao verificar resultado: {e}")
        return "erro", None, None
        
    return "erro", None, None