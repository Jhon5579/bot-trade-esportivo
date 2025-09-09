from decouple import config, UndefinedValueError
import os

print("--- Iniciando teste do arquivo .env ---")

# Verifica se o arquivo .env existe no diretório atual
if not os.path.exists('.env'):
    print("❌ ERRO GRAVE: O arquivo '.env' não foi encontrado neste diretório!")
else:
    print("✅ SUCESSO: O arquivo '.env' foi encontrado.")

# Teste para cada variável
try:
    token = config('TELEGRAM_TOKEN')
    if token:
        print("✅ TELEGRAM_TOKEN encontrado.")
    else:
        # Decouple levanta erro em vez de retornar None, mas esta verificação é para segurança
        print("❌ TELEGRAM_TOKEN está vazio.")
except UndefinedValueError:
    print("❌ TELEGRAM_TOKEN não foi definido no arquivo .env")

try:
    chat_id = config('TELEGRAM_CHAT_ID')
    if chat_id:
        print("✅ TELEGRAM_CHAT_ID encontrado.")
    else:
        print("❌ TELEGRAM_CHAT_ID está vazio.")
except UndefinedValueError:
    print("❌ TELEGRAM_CHAT_ID não foi definido no arquivo .env")

try:
    api_key = config('API_KEY_ODDS')
    if api_key:
        print("✅ API_KEY_ODDS encontrado.")
    else:
        print("❌ API_KEY_ODDS está vazio.")
except UndefinedValueError:
    print("❌ API_KEY_ODDS não foi definido no arquivo .env")

print("\n--- Teste concluído ---")