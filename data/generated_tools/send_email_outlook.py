def execute(ctx) -> dict:
    # ctx esperat: {"to": str, "subject": str, "body": str}
    # Aquí aniria la lògica per autenticar amb Outlook i enviar el correu
    to_address = ctx.get("to")
    subject = ctx.get("subject")
    body = ctx.get("body")
    # Implementar l'enviament d'email amb l'API Microsoft Graph i les credencials (tenant_id, client_id)
    # Per ara simularem l'enviament
    if not to_address or not subject or not body:
        return {"success": False, "message": "Falten camps obligatoris (to, subject, body)."}
    return {"success": True, "message": f"Email enviat a {to_address} amb èxit."}
