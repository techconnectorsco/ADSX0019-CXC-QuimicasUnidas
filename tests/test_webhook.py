# test_webhook.py
import requests

""" webhook_url = "https://soportexpertocr.webhook.office.com/webhookb2/39c1d4da-ecc1-4057-a80e-47298ee0cb10@2512a2ab-a318-486e-90de-1e4033de0c04/IncomingWebhook/5ebeddb0d8464a8f98447fbc0da04e68/41af7307-6360-4c2e-8f9d-b66d4d30dd6c/V2P0qM3ynsach-jPI4DB1J0XsYVnjJfQcCyZo8Z6MzHtg1" """

webhook_url = "https://soportexpertocr.webhook.office.com/webhookb2/39c1d4da-ecc1-4057-a80e-47298ee0cb10@2512a2ab-a318-486e-90de-1e4033de0c04/IncomingWebhook/12634bf35b984a89852ad3f86759dce6/41af7307-6360-4c2e-8f9d-b66d4d30dd6c/V2u4agiExBD8ysgJLNJMdQmMdAIrq8fbeRCmzN1IGicQ01"

mensaje = {
    "text": "Hola, esto es tercera prueba"
}

response = requests.post(webhook_url, json=mensaje)

if response.status_code == 200:
    print("✅ Mensaje enviado")
else:
    print(f"❌ Error: {response.status_code}")
