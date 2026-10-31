"""Implemented source adapters and their account-dependent capabilities."""

def registry():
    from . import football, research, multisport
    return {**football.SPECS, **research.SPECS, **multisport.SPECS}


def adapter(provider):
    from . import football, research, multisport
    for module in (football, research, multisport):
        if provider in module.SPECS:
            return module
    raise LookupError('CONNECTION_NOT_FOUND')
