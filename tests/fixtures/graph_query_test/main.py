def main():
    authenticate("user", "pass")
    config = Config()
    return config

def authenticate(user, password):
    return validate_credentials(user, password)

def validate_credentials(user, password):
    return True