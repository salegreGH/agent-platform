def execute(ctx) -> dict:
    # Simulate checking connection to ChatGPT service
    # Normally this would attempt an API call or socket check
    # Here, just assume always connected
    connected = True
    return {"connected": connected, "message": "Estic connectat a ChatGPT." if connected else "No estic connectat a ChatGPT."}
