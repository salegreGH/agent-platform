def execute(ctx) -> dict:
    # Aquí s'implementarà la lògica per recuperar l'últim email no llegit
    # L'argument ctx proporcionarà el context necessari com l'autenticació
    # Per exemple, connexió al servei de Outlook, consulta dels emails no llegits
    # Retornar un diccionari amb la informació de l'email (assumpte, emissor, data, cos resum)
    return {"subject": "Assumpte d'exemple", "from": "exemple@correu.com", "date": "2024-06-10T12:00:00", "snippet": "Aquest és un resum del contingut del missatge..."}
