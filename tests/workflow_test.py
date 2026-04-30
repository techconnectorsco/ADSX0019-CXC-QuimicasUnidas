# test_workflow_styled.py
import requests
from datetime import datetime

webhook_url = "https://default2512a2aba318486e90de1e4033de0c.04.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/c4ad8f2c32754668b5aa2b8fd9ea20a2/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=OpkNDGtD6ZlftMSCONH_f6pE-t0wYJLdhlr1SCEJfGY"

mensaje = {
    "type": "message",
    "attachments": [
        {
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": [
                    {
                        "type": "ColumnSet",
                        "columns": [
                            {
                                "type": "Column",
                                "width": "auto",
                                "items": [
                                    {
                                        "type": "Image",
                                        "url": "https://cdn-icons-png.flaticon.com/512/4712/4712027.png",
                                        "size": "Small",
                                        "style": "Person"
                                    }
                                ]
                            },
                            {
                                "type": "Column",
                                "width": "stretch",
                                "items": [
                                    {
                                        "type": "TextBlock",
                                        "text": "🤖 Asistente Digital CXC",
                                        "weight": "Bolder",
                                        "size": "Medium"
                                    },
                                    {
                                        "type": "TextBlock",
                                        "text": "Químicas Unidas",
                                        "size": "Small",
                                        "isSubtle": True,
                                        "spacing": "None"
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "type": "TextBlock",
                        "text": "─" * 40,
                        "size": "Small",
                        "isSubtle": True
                    },
                    {
                        "type": "TextBlock",
                        "text": "✅ Proceso ejecutado correctamente",
                        "weight": "Bolder",
                        "color": "Good",
                        "size": "Medium"
                    },
                    {
                        "type": "FactSet",
                        "facts": [
                            {"title": "📅 Fecha", "value": datetime.now().strftime("%d/%m/%Y")},
                            {"title": "🕐 Hora", "value": datetime.now().strftime("%H:%M:%S")},
                            {"title": "📧 Clientes notificados", "value": "185"},
                            {"title": "❌ Errores", "value": "3"}
                        ]
                    },
                    {
                        "type": "TextBlock",
                        "text": "─" * 40,
                        "size": "Small",
                        "isSubtle": True
                    },
                    {
                        "type": "TextBlock",
                        "text": "Mensaje automático generado por el Asistente Digital",
                        "size": "Small",
                        "isSubtle": True,
                        "horizontalAlignment": "Center"
                    }
                ]
            }
        }
    ]
}

response = requests.post(webhook_url, json=mensaje)

if response.status_code in [200, 202]:
    print("✅ Mensaje enviado")
else:
    print(f"❌ Error: {response.status_code}")
    print(response.text)
