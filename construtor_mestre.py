import os
import requests
import json
import time

# --- CONFIGURAÇÕES ---
API_KEY_FOOTBALL = os.environ.get('API_FOOTBALL_KEY')
ARQUIVO_SAIDA = 'master_team_list.json' # O nome do nosso banco de dados de times

# --- FUNÇÕES AUXILIARES ---
def carregar_lista_mestra():
    """Carrega a lista de times já salva, se existir."""
    try:
        with open(ARQUIVO_SAIDA, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def salvar_lista_mestra(lista_de_times):
    """Salva a lista completa de times no arquivo."""
    with open(ARQUIVO_SAIDA, 'w', encoding='utf-8') as f:
        json.dump(lista_de_times, f, indent=4)

# --- LÓGICA PRINCIPAL DO CONSTRUTOR MESTRE ---
def main():
    print("--- 🌍 Iniciando Censo Global de Times da API-Football... 🌍 ---")

    if not API_KEY_FOOTBALL:
        print("❌ ERRO FATAL: Secret 'API_FOOTBALL_KEY' não configurado."); return

    headers = {'x-apisports-key': API_KEY_FOOTBALL}

    print("Buscando a lista de todos os países...")
    try:
        response_paises = requests.get("https://v3.football.api-sports.io/countries", headers=headers, timeout=15)
        if response_paises.status_code != 200:
            print(f"❌ ERRO ao buscar países: {response_paises.text}"); return

        resposta_json = response_paises.json()
        paises = resposta_json.get('response', [])

        if not paises:
            print("\n  > AVISO: A API retornou uma lista vazia de países.")
            print(f"  > Resposta completa da API: {resposta_json}")
            print("  > Isso geralmente significa que a cota diária acabou. Verifique seu painel na API-Football.")
            return

        print(f"✅ Encontrados {len(paises)} países para processar.")
    except Exception as e:
        print(f"❌ ERRO de conexão ao buscar países: {e}"); return

    # Carrega o progresso já feito
    lista_mestra_times = carregar_lista_mestra()
    paises_ja_processados = set(time['team']['country'] for time in lista_mestra_times if time.get('team'))

    if paises_ja_processados:
        print(f"\nJá foram processados {len(paises_ja_processados)} países. Continuando de onde paramos...")

    # Loop através dos países, buscando os times de cada um
    for pais in paises:
        nome_pais = pais.get('name')
        if not nome_pais: continue

        if nome_pais in paises_ja_processados:
            continue

        print(f"\nBuscando times para o país: '{nome_pais}'...")

        try:
            params = {'country': nome_pais}
            response_times = requests.get("https://v3.football.api-sports.io/teams", headers=headers, params=params, timeout=15)

            if response_times.status_code != 200:
                print(f"  ❌ ERRO ao buscar times para '{nome_pais}': {response_times.text}")
                print("  > Provavelmente a cota diária da API acabou. Rode o script novamente amanhã.")
                break

            times_do_pais = response_times.json().get('response', [])
            if times_do_pais:
                lista_mestra_times.extend(times_do_pais)
                print(f"  ✅ Adicionados {len(times_do_pais)} times de '{nome_pais}'.")
            else:
                print(f"  > Nenhum time encontrado para '{nome_pais}'.")

            salvar_lista_mestra(lista_mestra_times)
            time.sleep(7)

        except Exception as e:
            print(f"  ❌ ERRO de conexão ao buscar times de '{nome_pais}': {e}")
            break

    print("\n--------------------------------------------------")
    print("🎉 Processo de construção concluído (ou pausado por hoje)!")
    print(f"Seu arquivo '{ARQUIVO_SAIDA}' agora contém {len(lista_mestra_times)} times.")

if __name__ == "__main__":
    main()