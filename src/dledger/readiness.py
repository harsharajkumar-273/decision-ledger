"""Credential-safe readiness checks; optional live calls never fall back."""
import os

from .llm import Tier, chat_json


def run(live=False):
    required = ['NEBIUS_API_KEY', 'DLEDGER_MODEL_NANO', 'DLEDGER_MODEL_SUPER', 'DLEDGER_MODEL_ULTRA']
    missing = [name for name in required if not os.getenv(name)]
    result = {'configured': not missing, 'missing': missing, 'live_verified': False, 'probes': []}
    if live and not missing:
        for tier in Tier:
            try:
                response = chat_json(tier, 'Return a JSON object with ok set to true.', 'Connectivity probe only.')
                result['probes'].append({'tier': tier.value, 'model': os.getenv('DLEDGER_MODEL_' + tier.value.upper()),
                                         'ok': isinstance(response, dict) and response.get('ok') is True})
            except Exception as exc:
                result['probes'].append({'tier': tier.value, 'ok': False, 'error_type': type(exc).__name__})
        result['live_verified'] = all(p['ok'] for p in result['probes'])
    return result
