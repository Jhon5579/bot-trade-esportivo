# api_externas.py

import requests
import json
from datetime import datetime, timedelta

# --- LÓGICA DE CACHE PARA A SOFASCORE ---
ARQUIVO_CACHE_SOFASCORE = 'cache_sofascore.json'
CACHE_TTL_HORAS = 2 # Cache configurado para 2 horas, como você pediu.

def carregar_cache():
    """Tenta carregar os dados do arquivo de cache."""
    try:
        with open(ARQUIVO_CACHE_SOFASCORE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def salvar_cache(dados):
    """Salva os novos dados e o timestamp atual no arquivo de cache."""
    cache_data = {
        'timestamp': datetime.now().isoformat(),
        'dados': dados
    }
    with open(ARQUIVO_CACHE_SOFASCORE, 'w') as f:
        json.dump(cache_data, f, indent=4)
# -----------------------------------------

def buscar_jogos_sofascore():
    """
    Busca os jogos do dia, utilizando um sistema de cache para evitar
    chamadas excessivas à API da SofaScore.
    """
    print(f"--- ⚽ Buscando jogos do dia {datetime.now().strftime('%Y-%m-%d')}... ---")

    cache = carregar_cache()

    if cache:
        timestamp_cache = datetime.fromisoformat(cache['timestamp'])
        if datetime.now() < timestamp_cache + timedelta(hours=CACHE_TTL_HORAS):
            print(f"--- ✅ Usando dados do cache (válido por {CACHE_TTL_HORAS}h). Nenhuma chamada à API foi feita. ---")
            return cache['dados']

    print("--- 🌐 Cache expirado ou inexistente. Fazendo nova chamada à API da SofaScore... ---")

    data_hoje = datetime.now().strftime('%Y-%m-%d')
    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{data_hoje}"
    headers = {'User-Agent': 'Mozilla/5.0'}

    todos_os_jogos = []
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            eventos = data.get('events', [])
            if eventos:
                print(f"--- ✅ Sucesso! Encontrados {len(eventos)} jogos. Salvando no cache... ---")
                for evento in eventos:
                    jogo = {
                        'home_team': evento.get('homeTeam', {}).get('name', 'N/A'),
                        'away_team': evento.get('awayTeam', {}).get('name', 'N/A'),
                        'league': evento.get('tournament', {}).get('name', 'N/A'),
                        'id_partida': evento.get('id', 0),
                        'timestamp': evento.get('startTimestamp', 0)
                    }
                    todos_os_jogos.append(jogo)
                salvar_cache(todos_os_jogos)
            else:
                print("--- ⚠️ Nenhum jogo encontrado para hoje na SofaScore. ---")
        else:
            print(f"--- ❌ FALHA! A API da SofaScore retornou um erro: Status {response.status_code} ---")
    except requests.exceptions.RequestException as e:
        print(f"--- ❌ ERRO DE CONEXÃO com a SofaScore: {e} ---")

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


def verificar_resultado_sofascore(id_partida):
    """
    Verifica o status e o resultado final de uma partida específica pelo seu ID.
    Esta função é a base para o sistema de apostas pendentes e histórico.
    """
    url = f"https://api.sofascore.com/api/v1/event/{id_partida}"
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json().get('event', {})
            status = data.get('status', {}).get('code', 0)

            # Código 100 = 'Partida Encerrada' na SofaScore
            if status == 100:
                placar_casa = data.get('homeScore', {}).get('current', -1)
                placar_fora = data.get('awayScore', {}).get('current', -1)
                return "encerrado", placar_casa, placar_fora
            else:
                return "em_andamento", None, None # Jogo ainda não acabou ou status desconhecido
    except requests.exceptions.RequestException:
        return "erro", None, None

    return "erro", None, None
