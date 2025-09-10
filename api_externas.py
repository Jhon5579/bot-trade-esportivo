# api_externas.py

import requests
from datetime import date

def buscar_jogos_api_football(api_key):
    """
    Busca na API-Football os jogos do dia para um conjunto de ligas pré-definidas
    que correspondem ao arquivo de dados históricos.
    VERSÃO CORRIGIDA: Remove o parâmetro 'season' para maior compatibilidade.
    """
    # --- LISTA COMPLETA DE LIGAS PARA ANALISAR ---
    # Esta lista foi criada com base nas ligas encontradas no seu arquivo CSV.
    LIGAS_ALVO = {
        # --- Ligas Principais (América do Sul e do Norte) ---
        '71': 'Brasileirão Série A',
        '128': 'Argentina - Liga Profesional',
        '253': 'USA - MLS',
        '262': 'Mexico - Liga MX',

        # --- Ligas Principais (Europa - Códigos Famosos) ---
        '39': 'England - Premier League (E0)',
        '40': 'England - Championship (E1)',
        '41': 'England - League One (E2)',
        '42': 'England - League Two (E3)',
        '61': 'France - Ligue 1 (F1)',
        '62': 'France - Ligue 2 (F2)',
        '78': 'Germany - Bundesliga (G1)',
        '135': 'Italy - Serie A (I1)',
        '136': 'Italy - Serie B (I2)',
        '140': 'Spain - La Liga (SP1)',
        '141': 'Spain - Segunda Division (SP2)',
        '144': 'Belgium - Jupiler Pro League (B1)',
        '88': 'Netherlands - Eredivisie (N1)',
        '94': 'Portugal - Primeira Liga (P1)',
        '179': 'Scotland - Premiership (SC0)',
        '180': 'Scotland - Championship (SC1)',
        '203': 'Turkey - Super Lig (T1)',

        # --- Outras Ligas Internacionais ---
        '119': 'Sweden - Allsvenskan',
        '116': 'Denmark - Superliga',
        '197': 'Greece - Super League',
        '206': 'Switzerland - Challenge League',
        '98': 'Japan - J1 League (D1)',
        '99': 'Japan - J2 League (D2)'
    }
    
    DATA_HOJE = date.today().strftime('%Y-%m-%d')
    
    headers = {'x-rapidapi-host': "v3.football.api-sports.io", 'x-rapidapi-key': api_key}
    todos_os_jogos = []

    print(f"--- ⚽ Buscando jogos do dia {DATA_HOJE} na API-Football para as ligas selecionadas... ---")

    for league_id, league_name in LIGAS_ALVO.items():
        print(f"  -> Buscando na liga: {league_name} (ID: {league_id})")
        
        url = f"https://v3.football.api-sports.io/fixtures?league={league_id}&date={DATA_HOJE}"
        
        try:
            response = requests.get(url, headers=headers, timeout=20)
            if response.status_code == 200:
                data = response.json().get('response', [])
                if data:
                    print(f"    -> {len(data)} jogo(s) encontrado(s).")
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
                    print("    -> Nenhum jogo agendado para hoje nesta liga.")
            else:
                print(f"    -> ERRO ao buscar na API-Football: Status {response.status_code} - {response.text}")
        except requests.exceptions.RequestException as e:
            print(f"    -> ERRO de conexão com a API-Football: {e}")

    if todos_os_jogos:
        print(f"\n--- ✅ Sucesso! Encontrados {len(todos_os_jogos)} jogos no total para as ligas selecionadas. ---")
    else:
        print("\n--- ⚠️ Nenhum jogo encontrado para hoje nas ligas selecionadas. ---")
        
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
    
    url = f"https://api.the-odds-api.com/v4/sports/soccer_brazil_campeonato/odds/"
    
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
            print("  -> Verifique se sua API Key está correta e se você não excedeu a cota mensal.")

    except requests.exceptions.RequestException as e:
        print(f"  -> ERRO de conexão com a The Odds API: {e}")
        
    return jogos_com_odds
