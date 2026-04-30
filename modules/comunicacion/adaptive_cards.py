# modules/comunicacion/adaptive_cards.py
"""
Builder para Adaptive Cards de Microsoft Teams
"""

from typing import List, Dict, Any, Optional
from datetime import datetime


class CardBuilder:
    """Constructor fluido para Adaptive Cards."""
    
    def __init__(self):
        self.body: List[Dict[str, Any]] = []
        self.actions: List[Dict[str, Any]] = []
    
    def add_header(self, title: str, subtitle: Optional[str] = None, icon: Optional[str] = None) -> 'CardBuilder':
        header_text = f"{icon} {title}" if icon else title
        
        self.body.append({
            "type": "TextBlock",
            "text": header_text,
            "weight": "Bolder",
            "size": "Large",
            "wrap": True
        })
        
        if subtitle:
            self.body.append({
                "type": "TextBlock",
                "text": subtitle,
                "isSubtle": True,
                "size": "Small",
                "spacing": "None"
            })
        
        return self
    
    def add_text(self, text: str, size: str = "Default", weight: str = "Default", color: Optional[str] = None, wrap: bool = True) -> 'CardBuilder':
        block = {
            "type": "TextBlock",
            "text": text,
            "wrap": wrap,
            "size": size,
            "weight": weight
        }
        if color:
            block["color"] = color
        self.body.append(block)
        return self
    
    def add_facts(self, facts: List[tuple], title: Optional[str] = None) -> 'CardBuilder':
        if title:
            self.body.append({
                "type": "TextBlock",
                "text": title,
                "weight": "Bolder",
                "spacing": "Medium"
            })
        
        self.body.append({
            "type": "FactSet",
            "facts": [{"title": k, "value": str(v)} for k, v in facts]
        })
        return self
    
    def add_divider(self) -> 'CardBuilder':
        self.body.append({
            "type": "TextBlock",
            "text": "─" * 40,
            "size": "Small",
            "isSubtle": True,
            "horizontalAlignment": "Center"
        })
        return self
    
    def add_timestamp(self) -> 'CardBuilder':
        self.body.append({
            "type": "TextBlock",
            "text": datetime.now().strftime("🕐 %d/%m/%Y %H:%M:%S"),
            "isSubtle": True,
            "size": "Small",
            "spacing": "Medium"
        })
        return self
    
    def build(self) -> Dict[str, Any]:
        card = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": self.body
        }
        if self.actions:
            card["actions"] = self.actions
        
        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": card
                }
            ]
        }