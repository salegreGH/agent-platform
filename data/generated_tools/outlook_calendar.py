def execute(ctx) -> dict:
    # Aquí es pot escriure la lògica per recuperar els esdeveniments del calendari d'Outlook
    # Utilitzant tenant_id i client_id que es configurarien de forma segura.
    # Retornem una llista fictícia per exemple
    events = [
        {"title": "Reunió de projecte", "time": "2024-06-10T10:00"},
        {"title": "Llamada amb client", "time": "2024-06-11T15:00"}
    ]
    return {"events": events}

