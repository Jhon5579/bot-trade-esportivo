import os
import requests
import json
import time
from datetime import datetime
from thefuzz import fuzz, process

# IMPORTAÇÃO DOS MÓDULOS DE UTILITÁRIOS
from utils import carregar_json, salvar_json

# --- Constantes e Configurações ---
ARQUIVO_CACHE_IDS = 'sofascore_id_cache.json'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'application/json',
    'Cache-Control': 'no-cache'
}


# --- NOVA FUNÇÃO ADICIONADA ---
def buscar_jogos_do_dia_sofascore(data: str):
    """
    Busca todos os eventos de futebol agendados para uma data específica no SofaScore.
    A data deve estar no formato 'YYYY-MM-DD'.
    """
    print(f"--- 📡 Buscando jogos do dia {data} no SofaScore... ---")
    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{data}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        dados = response.json()
        jogos_do_dia = []
        for jogo_data in dados.get('events', []):
            # Ignoramos jogos que não sejam do gênero masculino para evitar duplicatas (ex: times femininos)
            if jogo_data.get('homeTeam', {}).get('gender') != 'M':
                continue

            jogo = {
                "id_sofascore": jogo_data.get('id'),
                "liga": jogo_data.get('tournament', {}).get('name', 'N/A'),
                "pais": jogo_data.get('tournament', {}).get('category', {}).get('name', 'N/A'),
                "time_casa": jogo_data.get('homeTeam', {}).get('name', 'N/A'),
                "time_fora": jogo_data.get('awayTeam', {}).get('name', 'N/A'),
                "horario_inicio_utc": datetime.fromtimestamp(jogo_data.get('startTimestamp', 0)).isoformat()
            }
            jogos_do_dia.append(jogo)
        print(f"  -> ✅ Sucesso! Encontrados {len(jogos_do_dia)} jogos para hoje.")
        return jogos_do_dia
    except requests.exceptions.RequestException as e:
        print(f"  -> ❌ ERRO ao buscar jogos do dia: {e}")
        return []

# --- FUNÇÕES DO MÓDULO IN-PLAY (ADICIONADAS) ---

def buscar_jogos_ao_vivo():
    """Busca todos os eventos de futebol que estão acontecendo ao vivo no SofaScore."""
    print("--- 📡 Buscando jogos ao vivo no SofaScore... ---")
    url = "https://api.sofascore.com/api/v1/sport/football/events/live"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        dados = response.json()
        jogos_ao_vivo = []
        for jogo_data in dados.get('events', []):
            jogo = {
                "id_sofascore": jogo_data.get('id'),
                "liga": jogo_data.get('tournament', {}).get('name', 'N/A'),
                "pais": jogo_data.get('tournament', {}).get('category', {}).get('name', 'N/A'),
                "time_casa": jogo_data.get('homeTeam', {}).get('name', 'N/A'),
                "time_fora": jogo_data.get('awayTeam', {}).get('name', 'N/A'),
                "placar_casa": jogo_data.get('homeScore', {}).get('current', 0),
                "placar_fora": jogo_data.get('awayScore', {}).get('current', 0),
                "tempo_jogo": jogo_data.get('status', {}).get('description', 'N/A')
            }
            jogos_ao_vivo.append(jogo)
        print(f"  -> ✅ Sucesso! Encontrados {len(jogos_ao_vivo)} jogos acontecendo agora.")
        return jogos_ao_vivo
    except requests.exceptions.RequestException as e:
        print(f"  -> ❌ ERRO ao buscar jogos ao vivo: {e}")
        return []

def buscar_estatisticas_ao_vivo(id_do_jogo: int):
    """Busca as estatísticas detalhadas de um único jogo que está ao vivo."""
    if not id_do_jogo: return None
    url = f"https://api.sofascore.com/api/v1/event/{id_do_jogo}/statistics"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return None
        dados_stats = response.json().get('statistics', [])
        estatisticas_formatadas = {}
        for grupo in dados_stats:
            if grupo.get('period') == 'ALL':
                for subgrupo in grupo.get('groups', []):
                    nome_grupo = subgrupo.get('groupName')
                    stats_items = {}
                    for item in subgrupo.get('statisticsItems', []):
                        stats_items[item.get('name')] = {'casa': item.get('home'), 'fora': item.get('away')}
                    estatisticas_formatadas[nome_grupo] = stats_items
        return estatisticas_formatadas
    except requests.exceptions.RequestException:
        return None

# --- SUAS FUNÇÕES ORIGINAIS E INTELIGENTES (RESTAURADAS) ---

def obter_sofascore_id(nome_time, cache_ids):
    if nome_time in cache_ids:
        return cache_ids[nome_time]
    mapa_sofascore = carregar_json('mapa_nomes_sofascore.json')
    nome_para_busca = mapa_sofascore.get(nome_time, nome_time)
    if nome_time != nome_para_busca:
        print(f"  -> 🔎 [Sofascore] Nome '{nome_time}' traduzido para '{nome_para_busca}' pelo mapa.")
    print(f"  -> 🔎 [Sofascore] Procurando ID para: '{nome_para_busca}'")
    try:
        search_url = f"https://api.sofascore.com/api/v1/search/all?q={nome_para_busca}"
        res = requests.get(search_url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        search_data = res.json()
        resultados_times = [r['entity'] for r in search_data.get('results', []) if r.get('type') == 'team' and r['entity'].get('sport', {}).get('name') == 'Football' and r['entity'].get('gender') == 'M']
        if not resultados_times:
            print(f"        -> Falha: Nenhum time de futebol masculino encontrado para '{nome_para_busca}'")
            return None
        nomes_encontrados = {time['name']: time['id'] for time in resultados_times}
        melhor_match = process.extractOne(nome_para_busca, nomes_encontrados.keys())
        if not melhor_match or melhor_match[1] < 85:
            print(f"        -> Falha: Melhor correspondência para '{nome_para_busca}' foi fraca.")
            return None
        time_id = nomes_encontrados[melhor_match[0]]
        cache_ids[nome_time] = time_id
        salvar_json(cache_ids, ARQUIVO_CACHE_IDS)
        time.sleep(1)
        return time_id
    except Exception as e:
        print(f"        -> Exceção ao buscar ID: {e}")
        return None

def consultar_estatisticas_escanteios(time_name, cache_execucao, num_jogos_analise):
    time_id = obter_sofascore_id(time_name, carregar_json(ARQUIVO_CACHE_IDS))
    if not time_id:
        return None
    cache_key = f"cantos_{time_id}"
    if cache_key in cache_execucao:
        return cache_execucao[cache_key]
    print(f"  -> 📊 [Sofascore] Buscando estatísticas de escanteios para o time ID: {time_id}")
    try:
        events_url = f"https://api.sofascore.com/api/v1/team/{time_id}/events/last/0"
        res = requests.get(events_url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        eventos = res.json().get('events', [])
        lista_total_cantos = []
        jogos_analisados = 0
        for evento in eventos:
            if jogos_analisados >= num_jogos_analise:
                break
            if evento.get('status', {}).get('code') != 100:
                continue
            id_partida = evento['id']
            stats_url = f"https://api.sofascore.com/api/v1/event/{id_partida}/statistics"
            time.sleep(1.5)
            res_stats = requests.get(stats_url, headers=HEADERS, timeout=10)
            if res_stats.status_code != 200:
                continue
            dados_stats = res_stats.json().get('statistics', [])
            for grupo in dados_stats:
                if grupo.get('period') == 'ALL' and grupo.get('groups'):
                    for subgrupo in grupo['groups']:
                        if subgrupo.get('groupName') == 'Corners':
                            total_cantos_partida = sum(int(item.get('value', 0)) for item in subgrupo.get('statisticsItems', []))
                            lista_total_cantos.append(total_cantos_partida)
                            jogos_analisados += 1
                            break
                    break 
        if not lista_total_cantos:
            print(f"        -> Não foram encontrados dados de escanteios.")
            cache_execucao[cache_key] = None
            return None
        media_cantos = sum(lista_total_cantos) / len(lista_total_cantos)
        print(f"        -> Média de {media_cantos:.2f} cantos/jogo nos últimos {len(lista_total_cantos)} jogos.")
        cache_execucao[cache_key] = media_cantos
        return media_cantos
    except Exception as e:
        print(f"        -> Exceção ao buscar estatísticas de cantos: {e}")
        cache_execucao[cache_key] = None
        return None

def consultar_forma_sofascore(nome_time, cache_execucao, num_jogos=6):
    if nome_time in cache_execucao:
        return cache_execucao[nome_time]
    time_id = obter_sofascore_id(nome_time, carregar_json(ARQUIVO_CACHE_IDS))
    if not time_id:
        print(f"        -> Falha: Não foi possível encontrar o ID do time '{nome_time}' para consultar a forma.")
        return None
    try:
        events_url = f"https://api.sofascore.com/api/v1/team/{time_id}/events/last/0"
        res = requests.get(events_url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        events_data = res.json().get('events', [])
        forma, total_gols_lista = [], []
        for jogo in events_data[:num_jogos]:
            if jogo['status']['code'] != 100:
                continue
            placar_casa, placar_fora = jogo['homeScore']['current'], jogo['awayScore']['current']
            total_gols_lista.append(placar_casa + placar_fora)
            resultado = 'E' if placar_casa == placar_fora else ('V' if (jogo['homeTeam']['id'] == time_id and placar_casa > placar_fora) or (jogo['awayTeam']['id'] == time_id and placar_fora > placar_casa) else 'D')
            forma.append(resultado)
        if not forma:
            return None
        relatorio_time = {"forma": ''.join(forma[::-1]), "media_gols_partida": sum(total_gols_lista) / len(total_gols_lista)}
        cache_execucao[nome_time] = relatorio_time
        return relatorio_time
    except Exception as e:
        print(f"        -> Exceção ao consultar forma: {e}")
        return None

def consultar_classificacao_sofascore(id_liga, id_temporada, cache):
    cache_key = f"{id_liga}-{id_temporada}"
    if cache_key in cache:
        return cache[cache_key]
    print(f"  -> CONTEXTO [Sofascore] Buscando tabela de classificação para liga {id_liga}...")
    try:
        url = f"https://api.sofascore.com/api/v1/unique-tournament/{id_liga}/season/{id_temporada}/standings/total"
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        dados = res.json().get('standings', [{}])[0].get('rows', [])
        tabela = [{"posicao": time_info['position'], "nome": time_info['team']['name']} for time_info in dados]
        cache[cache_key] = tabela
        time.sleep(3)
        return tabela
    except Exception as e:
        print(f"   -> Erro ao buscar classificação: {e}")
        cache[cache_key] = []
        return []

def buscar_resultado_sofascore(time_casa, time_fora, timestamp_partida):
    print(f"  -> Buscando resultado para {time_casa} vs {time_fora} (Busca Profunda e Inteligente)")
    time_id = obter_sofascore_id(time_casa, carregar_json(ARQUIVO_CACHE_IDS))
    if not time_id:
        print(f"        -> Falha: Não foi possível encontrar o ID do time da casa '{time_casa}'")
        return None
    try:
        events_data = []
        print(f"        -> Consultando múltiplas páginas de jogos recentes...")
        for pagina in range(3):
            events_url = f"https://api.sofascore.com/api/v1/team/{time_id}/events/last/{pagina}"
            res = requests.get(events_url, headers=HEADERS, timeout=10)
            if res.status_code != 200: break
            resposta_json = res.json()
            novos_eventos = resposta_json.get('events', [])
            if not novos_eventos: break
            events_data.extend(novos_eventos)
            time.sleep(1)
        if not events_data:
            print(f"        -> Falha: API não retornou jogos recentes para o time_id {time_id}.")
            return None
        melhor_jogo_encontrado, maior_pontuacao = None, -1
        for jogo_api in events_data:
            oponente_api = jogo_api['awayTeam']['name'] if jogo_api['homeTeam']['id'] == time_id else jogo_api['homeTeam']['name']
            timestamp_api = jogo_api['startTimestamp']
            similaridade_nome = fuzz.ratio(time_fora.lower(), oponente_api.lower())
            diferenca_tempo_segundos = abs(timestamp_api - timestamp_partida)
            pontuacao_tempo = max(0, 100 - (diferenca_tempo_segundos / 432))
            pontuacao_final = (similaridade_nome * 0.7) + (pontuacao_tempo * 0.3)
            if pontuacao_final > maior_pontuacao:
                maior_pontuacao, melhor_jogo_encontrado = pontuacao_final, jogo_api
        if maior_pontuacao > 80:
            print(f"        -> Melhor correspondência encontrada com {maior_pontuacao:.2f}% de confiança.")
            if melhor_jogo_encontrado['status']['code'] == 100:
                return {'placar_casa': melhor_jogo_encontrado['homeScore']['current'], 'placar_fora': melhor_jogo_encontrado['awayScore']['current']}
            else:
                return "EM_ANDAMENTO"
        print(f"        -> Falha: Nenhuma correspondência forte encontrada. Melhor tentativa teve {maior_pontuacao:.2f}% de confiança.")
        return None
    except Exception as e:
        print(f"        -> Falha na conexão com a API do Sofascore: {e}")
        return None