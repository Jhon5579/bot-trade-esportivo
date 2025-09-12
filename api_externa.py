# api_externa.py (Versão Final 2.4)

import requests
from datetime import date, datetime
from gerenciador_cache import ler_cache, salvar_cache
import math

# --- CONSTANTES DE CACHE ---
CACHE_JOGOS_API_FOOTBALL = 'cache/jogos_api_football.json'
CACHE_ODDS_API = 'cache/odds_api.json'
VALIDADE_CACHE_HORAS = 2

def buscar_jogos_api_football(api_key):
    print(f"\n--- ⚽ Buscando jogos do dia na API-Football... ---")
    dados_cache = ler_cache(CACHE_JOGOS_API_FOOTBALL, VALIDADE_CACHE_HORAS)
    if dados_cache is not None:
        print(f"--- ✅ Sucesso! {len(dados_cache)} jogos encontrados no cache. ---")
        return dados_cache

    print("  -> Cache vazio ou expirado. Fazendo chamada real à API...")
    DATA_HOJE = date.today().strftime('%Y-%m-%d')
    headers = {'x-rapidapi-host': "v3.football.api-sports.io", 'x-rapidapi-key': api_key}
    url = f"https://v3.football.api-sports.io/fixtures?date={DATA_HOJE}"
    todos_os_jogos = []
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json().get('response', [])
            if data:
                for fixture in data:
                    todos_os_jogos.append({
                        'id_partida': fixture['fixture']['id'],
                        'home_team': fixture['teams']['home']['name'],
                        'away_team': fixture['teams']['away']['name'],
                        'home_team_id': fixture['teams']['home']['id'],
                        'away_team_id': fixture['teams']['away']['id'],
                        'league_id': fixture['league']['id'],
                        'league': fixture['league']['name'],
                        'timestamp': fixture['fixture']['timestamp'],
                        'status': fixture.get('fixture', {}).get('status', {}).get('short', 'NS'),
                        'placar_casa': fixture.get('goals', {}).get('home'),
                        'placar_fora': fixture.get('goals', {}).get('away')
                    })
                print(f"--- ✅ Sucesso! {len(todos_os_jogos)} jogos encontrados na API. ---")
                salvar_cache(CACHE_JOGOS_API_FOOTBALL, todos_os_jogos)
            else:
                print("--- ⚠️ Nenhum jogo encontrado para hoje na API-Football. ---")
        else:
            print(f"--- ❌ Erro ao buscar os jogos: {response.status_code} - {response.text} ---")
    except requests.exceptions.RequestException as e:
        print(f"--- ❌ Erro de conexão com a API-Football: {e}")
        
    return todos_os_jogos

def buscar_estatisticas_time(api_key, time_id, league_id):
    season = datetime.now().year
    cache_file = f"cache/stats_time_{time_id}_{season}_{league_id}.json"
    dados_cache = ler_cache(cache_file, VALIDADE_CACHE_HORAS)
    if dados_cache is not None:
        return dados_cache

    print(f"  -> 📞 Validação Online: Buscando stats para o time ID {time_id}...")
    headers = {'x-rapidapi-host': "v3.football.api-sports.io", 'x-rapidapi-key': api_key}
    params = {'team': time_id, 'league': league_id, 'season': season}
    url = "https://v3.football.api-sports.io/teams/statistics"
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json().get('response')
            if data and data.get('form'):
                stats = {
                    'forma': data.get('form', ''),
                    'gols_pro_media': data.get('goals', {}).get('for', {}).get('average', {}).get('total', '0'),
                    'gols_contra_media': data.get('goals', {}).get('against', {}).get('average', {}).get('total', '0')
                }
                salvar_cache(cache_file, stats)
                return stats
            else:
                print(f"  -> AVISO: Stats online não disponíveis para o time {time_id} na liga {league_id}.")
    except requests.exceptions.RequestException as e:
        print(f"  -> ERRO de conexão ao buscar stats para o time ID {time_id}: {e}")
    
    return None

def buscar_odds_the_odds_api(api_key):
    print("\n--- 👍 Buscando odds disponíveis na The Odds API... ---")
    dados_cache = ler_cache(CACHE_ODDS_API, VALIDADE_CACHE_HORAS)
    if dados_cache is not None:
        print(f"  -> ✅ Sucesso! Odds para {len(dados_cache)} jogos encontradas no cache.")
        return dados_cache
    
    print("  -> Cache de odds vazio ou expirado. Fazendo chamada real à API...")
    CASAS_DE_APOSTAS = 'pinnacle,betfair,bet365,marathonbet'
    params = {'api_key': api_key, 'regions': 'br,eu', 'markets': 'h2h', 'bookmakers': CASAS_DE_APOSTAS, 'oddsFormat': 'decimal'}
    url = "https://api.the-odds-api.com/v4/sports/soccer/odds"
    jogos_com_odds = []
    try:
        response = requests.get(url, params=params, timeout=20)
        if response.status_code == 200:
            data = response.json()
            if data:
                for jogo in data:
                    jogos_com_odds.append({
                        'id': jogo.get('id'),
                        'home_team': jogo.get('home_team'),
                        'away_team': jogo.get('away_team'),
                        'bookmakers': jogo.get('bookmakers', [])
                    })
                print(f"  -> ✅ Sucesso! Odds para {len(jogos_com_odds)} jogos encontradas na API.")
                salvar_cache(CACHE_ODDS_API, jogos_com_odds)
            else:
                print("  -> Nenhuma odd encontrada na The Odds API.")
        else:
            print(f"  -> 🚨 ERRO AO CHAMAR A THE ODDS API: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"  -> ERRO de conexão com a The Odds API: {e}")
    return jogos_com_odds
    
def buscar_resultados_por_ids(api_key, lista_de_ids):
    if not lista_de_ids:
        return []

    print(f"  -> 📞 Buscando resultados para {len(lista_de_ids)} jogos...")
    headers = {'x-rapidapi-host': "v3.football.api-sports.io", 'x-rapidapi-key': api_key}
    url = "https://v3.football.api-sports.io/fixtures"
    todos_os_resultados = []
    
    ids_por_chamada = 20
    num_chamadas = math.ceil(len(lista_de_ids) / ids_por_chamada)

    for i in range(num_chamadas):
        inicio = i * ids_por_chamada
        fim = inicio + ids_por_chamada
        chunk_ids = lista_de_ids[inicio:fim]
        ids_string = '-'.join(map(str, chunk_ids))
        
        print(f"    -> Fazendo chamada {i+1}/{num_chamadas} para {len(chunk_ids)} IDs...")
        
        try:
            response = requests.get(url, headers=headers, params={'ids': ids_string}, timeout=30)
            if response.status_code == 200:
                data = response.json().get('response', [])
                todos_os_resultados.extend(data)
            else:
                print(f"    -> ERRO na chamada em lote: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"    -> ERRO de conexão na chamada em lote: {e}")
            
    return todos_os_resultados

def verificar_resultado_api_football(api_key, id_partida):
    headers = {'x-rapidapi-host': "v3.football.api-sports.io", 'x-rapidapi-key': api_key}
    url = f"https://v3.football.api-sports.io/fixtures?id={id_partida}"
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json().get('response', [])
            if data:
                fixture_data = data[0]
                status = fixture_data.get('fixture', {}).get('status', {}).get('short', 'NS')
                if status == 'FT':
                    placar_casa = fixture_data.get('goals', {}).get('home', -1)
                    placar_fora = fixture_data.get('goals', {}).get('away', -1)
                    return "encerrado", placar_casa, placar_fora
                else:
                    return "em_andamento", None, None
    except requests.exceptions.RequestException as e:
        print(f"  -> ERRO de conexão ao verificar resultado para ID {id_partida}: {e}")
    return "erro", None, None
