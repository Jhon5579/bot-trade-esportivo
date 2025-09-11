# estrategias.py
from thefuzz import process

# --- FUNÇÕES AUXILIARES ---

def _get_nome_corrigido(nome_time_api, contexto):
    """
    Busca o nome de time mais parecido no banco de dados.
    Usa um cache para não repetir a busca para o mesmo time na mesma execução.
    """
    if 'cache_nomes' not in contexto:
        contexto['cache_nomes'] = {}
        contexto['lista_nomes_historico'] = list(contexto.get('stats_individuais', {}).keys())

    if nome_time_api in contexto['cache_nomes']:
        return contexto['cache_nomes'][nome_time_api]

    if not contexto['lista_nomes_historico']:
        return None

    melhor_match = process.extractOne(nome_time_api, contexto['lista_nomes_historico'], score_cutoff=85)

    nome_correspondente = melhor_match[0] if melhor_match else None
    contexto['cache_nomes'][nome_time_api] = nome_correspondente
    return nome_correspondente

def _encontrar_odd_especifica(jogo, mercado):
    """Encontra a odd de um mercado específico (Home, Away, Draw)."""
    bookmakers = jogo.get('bookmakers', [])
    if not bookmakers: return None

    for market in bookmakers[0].get('markets', []):
        if market.get('key') == 'h2h':
            for outcome in market.get('outcomes', []):
                if outcome.get('name') == mercado:
                    return outcome.get('price')
    return None

# --- ESTRATÉGIAS VALIDADAS (INTEGRADAS DO SEU CÓDIGO ANTIGO) ---

def analisar_favorito_forte_fora(jogo, contexto, debug=False):
    """Visitante com alto favoritismo estatístico."""
    time_casa_api, time_fora_api = jogo['home_team'], jogo['away_team']
    nome_casa = _get_nome_corrigido(time_casa_api, contexto)
    nome_fora = _get_nome_corrigido(time_fora_api, contexto)

    if not nome_casa or not nome_fora:
        if debug: return "Time sem correspondência no histórico."
        return None

    stats_casa = contexto['stats_individuais'][nome_casa]
    stats_fora = contexto['stats_individuais'][nome_fora]

    if (stats_fora.get('perc_vitorias_fora', 0) > 70 and
        stats_casa.get('perc_derrotas_casa', 0) > 70 and
        stats_fora.get('avg_gols_marcados_fora', 0) > 1.8 and
        stats_casa.get('avg_gols_sofridos_casa', 0) > 1.5):

        motivo = "Visitante com >70% de vitórias fora vs. Mandante com >70% de derrotas em casa."
        odd = _encontrar_odd_especifica(jogo, 'Away')
        return {'type': 'aposta', 'nome_estrategia': 'Favorito Forte Fora', 'mercado': 'Visitante para Vencer', 'motivo': motivo, 'odd': odd, 'emoji': '🚀'}
    else:
        if debug: return "Critérios de favoritismo extremo do visitante não atendidos."
        return None

def analisar_valor_mandante_azarao(jogo, contexto, debug=False):
    """Mandante com status de azarão nas odds, mas com bom histórico em casa."""
    time_casa_api = jogo['home_team']
    nome_casa = _get_nome_corrigido(time_casa_api, contexto)

    if not nome_casa:
        if debug: return "Time da casa sem correspondência no histórico."
        return None

    stats_casa = contexto['stats_individuais'][nome_casa]
    odd_casa = _encontrar_odd_especifica(jogo, 'Home')

    if not odd_casa:
        if debug: return "Odd do mandante não encontrada para análise de valor."
        return None

    if (odd_casa > 2.0 and
        stats_casa.get('perc_vitorias_casa', 0) > 45 and
        stats_casa.get('avg_gols_marcados_casa', 0) > 1.5):

        motivo = f"Mandante com odd de {odd_casa} mas com {stats_casa.get('perc_vitorias_casa', 0):.1f}% de vitórias em casa."
        return {'type': 'aposta', 'nome_estrategia': 'Valor no Mandante Azarão', 'mercado': 'Casa para Vencer', 'motivo': motivo, 'odd': odd_casa, 'emoji': '💎'}
    else:
        if debug: return "Critérios de valor para o mandante azarão não atendidos."
        return None

def analisar_valor_visitante_azarao(jogo, contexto, debug=False):
    """Visitante com status de azarão nas odds, mas com bom histórico fora."""
    time_fora_api = jogo['away_team']
    nome_fora = _get_nome_corrigido(time_fora_api, contexto)

    if not nome_fora:
        if debug: return "Time visitante sem correspondência no histórico."
        return None

    stats_fora = contexto['stats_individuais'][nome_fora]
    odd_visitante = _encontrar_odd_especifica(jogo, 'Away')

    if not odd_visitante:
        if debug: return "Odd do visitante não encontrada para análise de valor."
        return None

    if (odd_visitante > 2.2 and
        stats_fora.get('perc_vitorias_fora', 0) > 40 and
        stats_fora.get('avg_gols_marcados_fora', 0) > 1.4):

        motivo = f"Visitante com odd de {odd_visitante} mas com {stats_fora.get('perc_vitorias_fora', 0):.1f}% de vitórias fora."
        return {'type': 'aposta', 'nome_estrategia': 'Valor no Visitante Azarão', 'mercado': 'Visitante para Vencer', 'motivo': motivo, 'odd': odd_visitante, 'emoji': '💎'}
    else:
        if debug: return "Critérios de valor para o visitante azarão não atendidos."
        return None

def analisar_empate_valorizado(jogo, contexto, debug=False):
    """Busca jogos com alta probabilidade de empate com base no histórico."""
    time_casa_api, time_fora_api = jogo['home_team'], jogo['away_team']
    nome_casa = _get_nome_corrigido(time_casa_api, contexto)
    nome_fora = _get_nome_corrigido(time_fora_api, contexto)

    if not nome_casa or not nome_fora:
        if debug: return "Time sem correspondência no histórico."
        return None

    stats_casa = contexto['stats_individuais'][nome_casa]
    stats_fora = contexto['stats_individuais'][nome_fora]

    if (stats_casa.get('perc_empates_casa', 0) > 30 and
        stats_fora.get('perc_empates_fora', 0) > 30 and
        abs(stats_casa.get('avg_gols_marcados_casa', 0) - stats_fora.get('avg_gols_marcados_fora', 0)) < 0.5):

        motivo = "Ambos os times com mais de 30% de empates (casa/fora) e médias de gols similares."
        odd = _encontrar_odd_especifica(jogo, 'Draw')
        return {'type': 'aposta', 'nome_estrategia': 'Empate Valorizado', 'mercado': 'Empate', 'motivo': motivo, 'odd': odd, 'emoji': '🤝'}
    else:
        if debug: return "Critérios para tendência de empate não atendidos."
        return None

# --- ESTRATÉGIAS DE FORMA RECENTE ---

def analisar_forma_recente_casa(jogo, contexto, debug=False):
    """Casa em boa forma recente contra visitante em má forma."""
    time_casa_api, time_fora_api = jogo['home_team'], jogo['away_team']
    nome_casa = _get_nome_corrigido(time_casa_api, contexto)
    nome_fora = _get_nome_corrigido(time_fora_api, contexto)

    if not nome_casa or not nome_fora:
        if debug: return "Time sem correspondência no histórico."
        return None

    forma = contexto.get('forma_recente', {})
    forma_casa = forma.get(nome_casa, [])
    forma_fora = forma.get(nome_fora, [])

    if len(forma_casa) < 5 or len(forma_fora) < 5:
        if debug: return "Times com menos de 5 jogos recentes."
        return None

    if forma_casa.count('V') >= 3 and forma_fora.count('D') >= 3:
        motivo = f"Forma Recente: Casa com {forma_casa.count('V')}V/5j vs Visitante com {forma_fora.count('D')}D/5j."
        odd = _encontrar_odd_especifica(jogo, 'Home')
        return {'type': 'aposta', 'nome_estrategia': 'Forma Recente (Casa Forte)', 'mercado': 'Casa para Vencer', 'motivo': motivo, 'odd': odd, 'emoji': '🔥'}
    else:
        if debug: return f"Reprovado. Vitórias Recentes Casa: {forma_casa.count('V')}, Derrotas Recentes Fora: {forma_fora.count('D')}"
        return None

def analisar_forma_recente_fora(jogo, contexto, debug=False):
    """VERSÃO SIMÉTRICA: Visitante em boa forma recente contra mandante em má forma."""
    time_casa_api, time_fora_api = jogo['home_team'], jogo['away_team']
    nome_casa = _get_nome_corrigido(time_casa_api, contexto)
    nome_fora = _get_nome_corrigido(time_fora_api, contexto)

    if not nome_casa or not nome_fora:
        if debug: return "Time sem correspondência no histórico."
        return None

    forma = contexto.get('forma_recente', {})
    forma_casa = forma.get(nome_casa, [])
    forma_fora = forma.get(nome_fora, [])

    if len(forma_casa) < 5 or len(forma_fora) < 5:
        if debug: return "Times com menos de 5 jogos recentes."
        return None

    if forma_casa.count('D') >= 3 and forma_fora.count('V') >= 3:
        motivo = f"Forma Recente: Visitante com {forma_fora.count('V')}V/5j vs Mandante com {forma_casa.count('D')}D/5j."
        odd = _encontrar_odd_especifica(jogo, 'Away')
        return {'type': 'aposta', 'nome_estrategia': 'Forma Recente (Visitante Forte)', 'mercado': 'Visitante para Vencer', 'motivo': motivo, 'odd': odd, 'emoji': '🔥'}
    else:
        if debug: return f"Reprovado. Derrotas Recentes Casa: {forma_casa.count('D')}, Vitórias Recentes Fora: {forma_fora.count('V')}"
        return None