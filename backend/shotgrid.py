"""ShotGrid API client construction."""
from fastapi import HTTPException

from backend import config


def shotgrid_client():
    s = config.settings
    if not s.shotgrid_url:
        raise HTTPException(status_code=503, detail="ShotGrid URL non configurée")
    import shotgun_api3

    if s.shotgrid_login and s.shotgrid_passphrase:
        return shotgun_api3.Shotgun(s.shotgrid_url, login=s.shotgrid_login, password=s.shotgrid_passphrase)
    if s.shotgrid_script_name and s.shotgrid_script_key:
        return shotgun_api3.Shotgun(
            s.shotgrid_url, script_name=s.shotgrid_script_name, api_key=s.shotgrid_script_key
        )
    raise HTTPException(status_code=503, detail="Identifiants ShotGrid non configurés")
