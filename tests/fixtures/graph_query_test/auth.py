def login(username, password):
    return authenticate(username, password)

def authenticate(username, password):
    return validate_credentials(username, password)

def validate_credentials(username, password):
    return username == "admin"