# Arquivo: api_externas.py
# Descrição: Centraliza todas as chamadas a APIs externas.

import requests
from datetime import datetime

def buscar_jogos_api_football(api_key):
    """
    Busca todos os jogos do dia usando a API-Football.
    Isso conta como apenas 1 requisição.
    """
    hoje_str = datetime.now().strftime('%Y-%m-%d')
    print(f"--- 📡 Buscando jogos do dia {hoje_str} na API-Football... ---")
    
    url = "https://v3.football.api-sports.io/fixtures"
    params = {"date": hoje_str}
    headers = {"x-apisports-key": api_key}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
        response.raise_for_status()
        dados = response.json()
        
        jogos_do_dia = []
        for jogo_data in dados.get('response', []):
            fixture = jogo_data.get('fixture', {})
            teams = jogo_data.get('teams', {})
            league = jogo_data.get('league', {})
            
            # Pula jogos que não estão agendados (ex: adiados, cancelados)
            if fixture.get('status', {}).get('short') != 'NS':
                continue

            jogo = {
                "id_api_football": fixture.get('id'),
                "liga": league.get('name', 'N/A'),
                "pais": league.get('country', 'N/A'),
                "time_casa": teams.get('home', {}).get('name', 'N/A'),
                "time_fora": teams.get('away', {}).get('name', 'N/A'),
                "horario_inicio_utc": fixture.get('date')
            }
            jogos_do_dia.append(jogo)
            
        print(f"  -> ✅ Sucesso! Encontrados {len(jogos_do_dia)} jogos agendados.")
        return jogos_do_dia
    except requests.exceptions.RequestException as e:
        print(f"  -> ❌ ERRO ao buscar jogos na API-Football: {e}")
        return []

def buscar_odds_the_odds_api(api_key, casa_alvo='pinnacle'):
    """
    Busca a lista limitada de jogos com odds da The Odds API.
    """
    print("\n--- 💰 Buscando as poucas odds disponíveis na The Odds API... ---")
    url_odds = f"https://api.the-odds-api.com/v4/sports/soccer/odds?apiKey={api_key}&regions=eu,us,uk,au&bookmakers={casa_alvo}&oddsFormat=decimal&markets=h2h"
    try:
        response_odds = requests.get(url_odds, timeout=30)
        response_odds.raise_for_status()
        jogos_com_odds = response_odds.json()
        print(f"  -> Encontradas odds para {len(jogos_com_odds)} jogos.")
        return jogos_com_odds
    except requests.exceptions.RequestException as e:
        print(f"  -> ⚠️ AVISO: Não foi possível buscar odds da The Odds API: {e}")
        return []