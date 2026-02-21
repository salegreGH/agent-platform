def execute(ctx) -> dict:
    # Exemple bàsic: extreu l'últim email usant la connexió m365_email
    m365 = ctx.get('m365_email')
    if not m365:
        return {"error": "No hi ha connexió m365_email disponible."}
    try:
        inbox = m365.get_mailbox().get_folder('Inbox')
        emails = inbox.get_messages(limit=1)
        if not emails:
            return {"result": "No hi ha emails a la safata d'entrada."}
        ult_email = emails[0]
        return {
            "From": ult_email.author.email,
            "Subject": ult_email.subject,
            "ReceivedDateTime": str(ult_email.received_date_time),
            "BodyPreview": ult_email.body_preview
        }
    except Exception as e:
        return {"error": f"Error accedint a Outlook: {str(e)}"}
