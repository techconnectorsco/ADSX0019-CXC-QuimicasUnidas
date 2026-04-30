# modules/comunicacion/__init__.py
"""
Módulo de Comunicación - Químicas Unidas
Maneja notificaciones y mensajes via Microsoft Teams
"""

from .teams_webhook import TeamsNotifier
from .adaptive_cards import CardBuilder
from .sendemail import enviar_estado_cuenta, enviar_control_interno

__all__ = ['TeamsNotifier', 'CardBuilder', 'enviar_estado_cuenta', 'enviar_control_interno']
